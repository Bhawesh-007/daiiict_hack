"""HTTP orchestration for persisted calculation runs and direct CSV ingestion."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.calculations.engine import CalculationInput, run_calculation_pipeline
from app.calculations.factor_resolver import (
    AmbiguousFactorError,
    NoCompatibleFactorError,
    resolve_factor,
)
from app.calculations.unit_converter import convert_to_base
from app.domain.activities.file_import import parse_csv
from app.persistence.database import get_db
from app.persistence.models import (
    ActivityRecord,
    Assessment,
    CalculationLine,
    CalculationRun,
    EmissionFactor,
    SourceInventoryItem,
)

router = APIRouter(prefix="/api", tags=["calculations"])
ROOT = Path(__file__).resolve().parents[4]
DEMO_ASSESSMENT_ID = UUID("10000000-0000-4000-8000-000000000003")


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _line_dict(line: CalculationLine, source_names: dict[str, str] | None = None) -> dict[str, Any]:
    sid = str(line.source_inventory_item_id) if line.source_inventory_item_id else None
    resolved_name = (source_names or {}).get(sid, sid) if sid else (line.source_category or "Emission Source")
    return {
        "id": str(line.id),
        "source_inventory_item_id": sid,
        "source_name": resolved_name,
        "activity_record_id": str(line.activity_record_id) if line.activity_record_id else None,
        "emission_factor_id": str(line.emission_factor_id) if line.emission_factor_id else None,
        "original_quantity": str(line.original_quantity) if line.original_quantity is not None else None,
        "original_unit": line.original_unit,
        "normalized_quantity": str(line.normalized_quantity) if line.normalized_quantity is not None else None,
        "normalized_unit": line.normalized_unit,
        "conversion_multiplier": str(line.conversion_multiplier) if line.conversion_multiplier is not None else None,
        "factor_value_snapshot": str(line.factor_value_snapshot) if line.factor_value_snapshot is not None else None,
        "factor_unit_snapshot": line.factor_unit_snapshot,
        "scope": line.scope,
        "source_category": line.source_category,
        "emissions_kgco2e": str(line.emissions_kgco2e) if line.emissions_kgco2e is not None else "0",
    }


def _run_response(
    run: CalculationRun,
    lines: list[CalculationLine] | None = None,
    source_names: dict[str, str] | None = None,
) -> dict[str, Any]:
    summary = json.loads(run.notes) if run.notes else {}
    tot = Decimal(str(run.total_emissions_kgco2e or 0))
    tot_t = (tot / Decimal(1000)).quantize(Decimal("0.001"))
    return {
        "calculation_run_id": str(run.id),
        "assessment_id": str(run.assessment_id),
        "status": run.status,
        "methodology_version": run.methodology_version,
        "factor_set_version": run.factor_set_version,
        "total_emissions_kgco2e": str(run.total_emissions_kgco2e or 0),
        "total_emissions_tco2e": str(tot_t),
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "summary": summary,
        "lines": [_line_dict(line, source_names) for line in lines] if lines is not None else None,
    }


def _resolve_factor_smart(
    factors: list[EmissionFactor],
    source_key: str,
    activity_unit: str,
    activity_date: datetime | None,
    geography: str | None,
    activity_notes: str | None = None,
    evidence_reference: str | None = None,
    source_name: str | None = None,
) -> EmissionFactor | None:
    try:
        return resolve_factor(
            factors,
            source_key=source_key,
            activity_unit=activity_unit,
            activity_date=activity_date,
            geography=geography,
        )
    except AmbiguousFactorError:
        note_str = f"{activity_notes or ''} {evidence_reference or ''} {source_name or ''}".lower()
        candidates = [
            f for f in factors
            if source_key in (f.metadata_json or {}).get("compatible_source_type_ids", [])
            and f.activity_unit == activity_unit
        ]
        for cand in candidates:
            cand_name = (cand.name or "").lower()
            cat = (cand.source_category or "").lower().replace("_", " ")
            keywords = [w for w in (cand_name + " " + cat).split() if len(w) > 3]
            if any(kw in note_str for kw in keywords):
                return cand
        return candidates[0] if candidates else None
    except NoCompatibleFactorError:
        return None


async def _ensure_demo_factors(db: AsyncSession) -> list[EmissionFactor]:
    factors = list((await db.execute(select(EmissionFactor))).scalars().all())
    if factors:
        return factors
    factor_path = ROOT / "data/emission-factors/demo-factors.json"
    if not factor_path.exists():
        return []
    doc = json.loads(factor_path.read_text(encoding="utf-8"))
    for item in doc.get("factors", []):
        db.add(
            EmissionFactor(
                factor_code=item["factor_id"],
                version=item["factor_version"],
                name=item["name"],
                source_category=item["activity_category"],
                scope="SCOPE_1" if "SCOPE_1" in item["scope_or_boundary"] else ("SCOPE_2" if "SCOPE_2" in item["scope_or_boundary"] else "SCOPE_3"),
                factor_value=Decimal(str(item["factor_value"])),
                activity_unit=item["input_unit"],
                emission_unit=item["output_unit"],
                geography=item["geography"]["country"],
                source_organization=item.get("source_organization"),
                source_document=item.get("source_reference"),
                method=item.get("calculation_method"),
                quality_rating=item.get("quality_label"),
                metadata_json=item,
            )
        )
    await db.flush()
    return list((await db.execute(select(EmissionFactor))).scalars().all())


@router.post("/assessments/{assessment_id}/calculate")
async def calculate_assessment(
    assessment_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    assessment = (
        await db.execute(
            select(Assessment)
            .where(Assessment.id == assessment_id)
            .options(
                selectinload(Assessment.facility),
                selectinload(Assessment.products),
                selectinload(Assessment.process_steps),
                selectinload(Assessment.source_inventory_items).selectinload(
                    SourceInventoryItem.activity_records
                ),
            )
        )
    ).scalar_one_or_none()
    if assessment is None:
        raise HTTPException(404, "Assessment not found")

    factors = await _ensure_demo_factors(db)
    inputs: list[CalculationInput] = []
    source_name_map: dict[str, str] = {}

    for source in assessment.source_inventory_items:
        source_name_map[str(source.id)] = source.source_name
        process = next((item for item in assessment.process_steps if item.id == source.process_step_id), None)
        for activity in source.activity_records:
            factor = _resolve_factor_smart(
                factors,
                source_key=source.source_key,
                activity_unit=activity.normalized_unit_code or activity.unit_code,
                activity_date=activity.period_start,
                geography=assessment.facility.country if assessment.facility else None,
                activity_notes=activity.notes,
                evidence_reference=activity.evidence_reference,
                source_name=source.source_name,
            )
            inputs.append(
                CalculationInput(
                    source_inventory_item_id=str(source.id),
                    activity_record_id=str(activity.id),
                    emission_factor_id=str(factor.id) if factor else None,
                    source_name=source.source_name,
                    source_category=source.source_category,
                    source_status=source.status,
                    scope=source.scope if source.scope in {"SCOPE_1", "SCOPE_2", "SCOPE_3"} else (factor.scope if factor else None),
                    process_step_id=str(source.process_step_id) if source.process_step_id else None,
                    process_name=process.name if process else None,
                    original_quantity=activity.quantity,
                    original_unit=activity.unit_code,
                    normalized_quantity=activity.normalized_quantity,
                    normalized_unit=activity.normalized_unit_code,
                    conversion_multiplier=activity.normalization_multiplier or Decimal(1),
                    factor_value=factor.factor_value if factor else None,
                    factor_unit=factor.activity_unit if factor else None,
                    factor_version=factor.version if factor else None,
                    factor_category=source.source_category if factor else None,
                    factor_scope=factor.scope if factor else None,
                )
            )

    production_quantity = next(
        (product.quantity for product in assessment.products if product.quantity is not None),
        None,
    )
    result = run_calculation_pipeline(inputs, production_quantity=production_quantity)
    run = CalculationRun(
        assessment_id=assessment_id,
        methodology_version="deterministic-decimal-v1",
        factor_set_version="database-active-factors",
        status="COMPLETED",
        total_emissions_kgco2e=result.total_emissions,
        completed_at=datetime.now(UTC),
        notes=json.dumps(_jsonable(result.to_dict())),
    )
    db.add(run)
    await db.flush()
    persisted_lines = []
    for line in result.line_items:
        line_record = CalculationLine(
            calculation_run_id=run.id,
            source_inventory_item_id=UUID(line.source_inventory_item_id) if line.source_inventory_item_id else None,
            activity_record_id=UUID(line.activity_record_id) if line.activity_record_id else None,
            emission_factor_id=UUID(line.emission_factor_id) if line.emission_factor_id else None,
            original_quantity=line.original_quantity,
            original_unit=line.original_unit,
            normalized_quantity=line.normalized_quantity,
            normalized_unit=line.normalized_unit,
            conversion_multiplier=line.conversion_multiplier,
            factor_value_snapshot=line.factor_value_snapshot,
            factor_unit_snapshot=line.factor_unit_snapshot,
            scope=line.scope,
            source_category=line.source_category,
            emissions_kgco2e=line.emissions_kgco2e,
        )
        db.add(line_record)
        persisted_lines.append(line_record)
    await db.flush()
    return _run_response(run, persisted_lines, source_name_map)


@router.post("/prototype/ingest-csv")
@router.post("/assessments/{assessment_id}/ingest-and-calculate-csv")
async def ingest_and_calculate_csv(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    assessment_id: UUID | None = None,
    filename: str = "activity-data.csv",
) -> dict[str, Any]:
    """Single-step prototype endpoint: ingest raw CSV, auto-confirm sources, calculate, and return complete emissions profile."""
    aid = assessment_id or DEMO_ASSESSMENT_ID
    assessment = await db.get(Assessment, aid)
    if assessment is None:
        assessment = (await db.execute(select(Assessment).limit(1))).scalar_one_or_none()
        if assessment is None:
            raise HTTPException(404, "No assessment found")
        aid = assessment.id

    # 1. Ensure factors are seeded
    await _ensure_demo_factors(db)

    # 2. Get CSV bytes
    body = await request.body()
    if not body or len(body.strip()) == 0:
        demo_csv = ROOT / "data/demo/demo-activity-data.csv"
        if demo_csv.exists():
            body = demo_csv.read_bytes()
        else:
            raise HTTPException(422, "No CSV data provided and demo file not found")

    # 3. Parse CSV rows
    rows = parse_csv(body)

    # 4. Map or auto-confirm source inventory items
    sources = list(
        (await db.execute(select(SourceInventoryItem).where(SourceInventoryItem.assessment_id == aid))).scalars().all()
    )
    source_map: dict[str, SourceInventoryItem] = {
        s.source_key: s for s in sources
    }

    defaults = {
        "purchased_grid_electricity": {"name": "Purchased grid electricity", "category": "purchased_energy", "scope": "SCOPE_2"},
        "stationary_fuel_combustion": {"name": "Stationary fuel combustion", "category": "stationary_combustion", "scope": "SCOPE_1"},
        "mobile_fuel_combustion": {"name": "Mobile fuel combustion", "category": "mobile_combustion", "scope": "SCOPE_1"},
        "refrigerant_fugitive_emissions": {"name": "Refrigerant leakage and release", "category": "fugitive_emissions", "scope": "SCOPE_1"},
        "purchased_materials": {"name": "Purchased raw materials, packaging and chemicals", "category": "purchased_goods_services", "scope": "SCOPE_3"},
        "waste_generated_in_operations": {"name": "Waste generated in operations", "category": "waste", "scope": "SCOPE_3"},
        "downstream_transportation": {"name": "Downstream transportation and distribution", "category": "transportation_distribution", "scope": "SCOPE_3"},
        "upstream_transportation": {"name": "Upstream transportation and distribution", "category": "transportation_distribution", "scope": "SCOPE_3"},
        "industrial_process_emissions": {"name": "Industrial process emissions", "category": "industrial_process", "scope": "SCOPE_1"},
    }

    for row in rows:
        skey = row.source_reference
        if skey not in source_map:
            meta = defaults.get(skey, {
                "name": skey.replace("_", " ").capitalize(),
                "category": "unspecified",
                "scope": "SCOPE_1",
            })
            new_src = SourceInventoryItem(
                assessment_id=aid,
                source_key=skey,
                source_name=meta["name"],
                source_category=meta["category"],
                scope=meta["scope"],
                status="CONFIRMED",
                confirmed_by="CSV Ingestion",
                confirmed_at=datetime.now(UTC),
                confirmation_note="Auto-confirmed during CSV ingestion",
            )
            db.add(new_src)
            await db.flush()
            source_map[skey] = new_src
        else:
            if source_map[skey].status != "CONFIRMED":
                source_map[skey].status = "CONFIRMED"
                source_map[skey].confirmed_by = "CSV Ingestion"
                source_map[skey].confirmed_at = datetime.now(UTC)

    # 5. Clear previous activity records for these sources to replace with fresh CSV rows
    source_ids = [s.id for s in source_map.values()]
    if source_ids:
        await db.execute(delete(ActivityRecord).where(ActivityRecord.source_inventory_item_id.in_(source_ids)))

    # 6. Insert new activity records
    for row in rows:
        src = source_map[row.source_reference]
        conv = convert_to_base(row.quantity, row.unit_code)
        period_start = row.period_start or assessment.reporting_period_start or datetime(2025, 4, 1, tzinfo=UTC)
        period_end = row.period_end or assessment.reporting_period_end or datetime(2026, 3, 31, tzinfo=UTC)
        rec = ActivityRecord(
            source_inventory_item_id=src.id,
            period_start=period_start,
            period_end=period_end,
            quantity=row.quantity,
            unit_code=row.unit_code,
            normalized_quantity=conv.normalized_quantity,
            normalized_unit_code=conv.normalized_unit,
            normalization_multiplier=conv.normalization_multiplier,
            data_source_type="IMPORTED_CSV",
            data_quality="HIGH",
            evidence_reference=row.evidence_reference or filename,
            notes=row.notes or f"Imported from {filename}",
        )
        db.add(rec)

    await db.flush()

    # 7. Run calculation
    res = await calculate_assessment(aid, db)
    res["imported_records"] = len(rows)
    res["filename"] = filename
    return res


@router.get("/prototype/latest-profile")
@router.get("/assessments/{assessment_id}/latest-profile")
async def get_latest_profile(
    db: Annotated[AsyncSession, Depends(get_db)],
    assessment_id: UUID | None = None,
) -> dict[str, Any]:
    """Retrieve the latest completed emissions profile, or auto-run demo if none exists."""
    aid = assessment_id or DEMO_ASSESSMENT_ID
    assessment = await db.get(Assessment, aid)
    if assessment is None:
        assessment = (await db.execute(select(Assessment).limit(1))).scalar_one_or_none()
        if assessment:
            aid = assessment.id

    run = (
        await db.execute(
            select(CalculationRun)
            .where(CalculationRun.assessment_id == aid, CalculationRun.status == "COMPLETED")
            .order_by(CalculationRun.completed_at.desc())
            .options(selectinload(CalculationRun.lines))
            .limit(1)
        )
    ).scalar_one_or_none()

    sources = list(
        (await db.execute(select(SourceInventoryItem).where(SourceInventoryItem.assessment_id == aid))).scalars().all()
    )
    source_name_map = {str(s.id): s.source_name for s in sources}

    if run and run.lines and len(run.lines) >= 5:
        return _run_response(run, list(run.lines), source_name_map)

    # Auto-run demo CSV so there is NEVER an empty state
    dummy_req = Request({"type": "http", "method": "POST", "headers": []})
    async def empty_body() -> bytes:
        return b""
    dummy_req.body = empty_body  # type: ignore[method-assign]
    return await ingest_and_calculate_csv(dummy_req, db, assessment_id=aid, filename="demo-activity-data.csv")


@router.get("/calculations/{calculation_id}")
async def read_calculation(calculation_id: UUID, db: Annotated[AsyncSession, Depends(get_db)]) -> dict[str, Any]:
    result = await db.execute(
        select(CalculationRun)
        .where(CalculationRun.id == calculation_id)
        .options(selectinload(CalculationRun.lines))
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(404, "Calculation run not found")
    sources = list(
        (await db.execute(select(SourceInventoryItem).where(SourceInventoryItem.assessment_id == run.assessment_id))).scalars().all()
    )
    source_name_map = {str(s.id): s.source_name for s in sources}
    return _run_response(run, list(run.lines), source_name_map)


@router.get("/assessments/{assessment_id}/hotspots")
async def read_hotspots(assessment_id: UUID, db: Annotated[AsyncSession, Depends(get_db)]) -> dict[str, Any]:
    run = (
        await db.execute(
            select(CalculationRun)
            .where(CalculationRun.assessment_id == assessment_id)
            .order_by(CalculationRun.completed_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(404, "No calculation run found for assessment")
    output = json.loads(run.notes) if run.notes else {}
    return {
        "assessment_id": str(assessment_id),
        "calculation_run_id": str(run.id),
        "status": run.status,
        "hotspot_ranking": output.get("hotspot_ranking", {}),
        "warnings": output.get("warnings", []),
    }
