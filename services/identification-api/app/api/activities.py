import json
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.calculations.unit_converter import UnitConversionError, convert_to_base
from app.domain.activities.file_import import ActivityImportError, parse_activity_file
from app.persistence.database import get_db
from app.persistence.models import ActivityRecord, Assessment, SourceInventoryItem
from app.schemas.activities import ActivityCreate, ActivityListResponse
from app.schemas.sources import SourceInventoryContract

router = APIRouter(prefix="/api", tags=["activities"])
ROOT = Path(__file__).resolve().parents[4]
MAX_IMPORT_BYTES = 5 * 1024 * 1024


def _units() -> set[str]:
    document = json.loads(
        (ROOT / "data/taxonomy/units.json").read_text(encoding="utf-8")
    )
    return {
        unit["unit_id"]
        for dimension in document.get("dimensions", [])
        for unit in dimension.get("units", [])
    }


def _source_key(value: str) -> str:
    return " ".join(value.strip().lower().replace("_", " ").split())


def _match_source(reference: str, sources: list[SourceInventoryItem]) -> SourceInventoryItem | None:
    target = _source_key(reference)
    exact = [
        source
        for source in sources
        if target in {_source_key(source.source_key), _source_key(source.source_name)}
    ]
    if len(exact) == 1:
        return exact[0]
    partial = [
        source
        for source in sources
        if target in _source_key(source.source_key)
        or target in _source_key(source.source_name)
        or _source_key(source.source_key) in target
        or _source_key(source.source_name) in target
    ]
    return partial[0] if len(partial) == 1 else None


@router.get(
    "/assessments/{assessment_id}/inventory",
    response_model=list[SourceInventoryContract],
)
async def read_inventory(
    assessment_id: UUID, db: Annotated[AsyncSession, Depends(get_db)]
):
    statement = (
        select(SourceInventoryItem)
        .where(SourceInventoryItem.assessment_id == assessment_id)
        .order_by(SourceInventoryItem.created_at)
    )
    return list((await db.execute(statement)).scalars().all())


@router.get("/units")
async def read_units() -> dict:
    return json.loads((ROOT / "data/taxonomy/units.json").read_text(encoding="utf-8"))


@router.post("/assessments/{assessment_id}/import-activity-file")
async def import_activity_file(
    assessment_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    filename: str,
) -> dict:
    """Import CSV/PDF activity rows into matching confirmed inventory sources."""
    payload = await request.body()
    if not payload:
        raise HTTPException(422, "The uploaded file is empty")
    if len(payload) > MAX_IMPORT_BYTES:
        raise HTTPException(413, "Upload must be smaller than 5 MB")
    assessment = await db.get(Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(404, "Assessment not found")
    sources = list(
        (
            await db.execute(
                select(SourceInventoryItem).where(
                    SourceInventoryItem.assessment_id == assessment_id,
                    SourceInventoryItem.status == "CONFIRMED",
                )
            )
        )
        .scalars()
        .all()
    )
    if not sources:
        raise HTTPException(409, "Confirm at least one source before importing activity data")
    try:
        rows = parse_activity_file(filename, payload)
    except ActivityImportError as exc:
        raise HTTPException(422, str(exc)) from exc

    existing = list(
        (
            await db.execute(
                select(ActivityRecord).where(
                    ActivityRecord.source_inventory_item_id.in_([source.id for source in sources])
                )
            )
        )
        .scalars()
        .all()
    )
    inserted = skipped = 0
    issues: list[str] = []
    for row in rows:
        source = _match_source(row.source_reference, sources)
        if source is None:
            skipped += 1
            issues.append(f"No confirmed source matched '{row.source_reference}'")
            continue
        try:
            conversion = convert_to_base(row.quantity, row.unit_code)
        except UnitConversionError as exc:
            skipped += 1
            issues.append(f"{row.source_reference}: {exc}")
            continue
        period_start = row.period_start or assessment.reporting_period_start
        period_end = row.period_end or assessment.reporting_period_end
        duplicate = any(
            record.source_inventory_item_id == source.id
            and record.quantity == row.quantity
            and record.unit_code == row.unit_code
            and record.period_start == period_start
            and record.period_end == period_end
            for record in existing
        )
        if duplicate:
            skipped += 1
            continue
        record = ActivityRecord(
            source_inventory_item_id=source.id,
            period_start=period_start,
            period_end=period_end,
            quantity=row.quantity,
            unit_code=row.unit_code,
            normalized_quantity=conversion.normalized_quantity,
            normalized_unit_code=conversion.normalized_unit,
            normalization_multiplier=conversion.normalization_multiplier,
            data_source_type="IMPORTED_FILE",
            data_quality="MEDIUM",
            evidence_reference=row.evidence_reference or filename,
            notes=row.notes or f"Imported from {filename}",
        )
        db.add(record)
        existing.append(record)
        inserted += 1
    await db.flush()
    return {
        "filename": filename,
        "detected_rows": len(rows),
        "imported_records": inserted,
        "skipped_records": skipped,
        "issues": issues,
    }


@router.get("/sources/{source_id}/activities", response_model=ActivityListResponse)
async def read_activities(
    source_id: UUID, db: Annotated[AsyncSession, Depends(get_db)]
):
    source = await db.get(SourceInventoryItem, source_id)
    if source is None:
        raise HTTPException(404, "Source inventory item not found")
    records = (
        (
            await db.execute(
                select(ActivityRecord)
                .where(ActivityRecord.source_inventory_item_id == source_id)
                .order_by(ActivityRecord.period_start)
            )
        )
        .scalars()
        .all()
    )
    return {"source_inventory_item_id": source_id, "activities": list(records)}


@router.put("/sources/{source_id}/activities", response_model=ActivityListResponse)
async def replace_activities(
    source_id: UUID,
    payload: list[ActivityCreate],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    source = await db.get(SourceInventoryItem, source_id)
    if source is None:
        raise HTTPException(404, "Source inventory item not found")
    if source.status != "CONFIRMED":
        raise HTTPException(
            409, "Activity data can only be recorded for a CONFIRMED source"
        )
    await db.execute(
        delete(ActivityRecord).where(
            ActivityRecord.source_inventory_item_id == source_id
        )
    )
    records = []
    for item in payload:
        try:
            conversion = convert_to_base(item.quantity, item.unit_code)
        except UnitConversionError as exc:
            raise HTTPException(422, str(exc)) from exc
        records.append(
            ActivityRecord(
                source_inventory_item_id=source_id,
                **item.model_dump(),
                normalized_quantity=conversion.normalized_quantity,
                normalized_unit_code=conversion.normalized_unit,
                normalization_multiplier=conversion.normalization_multiplier,
            )
        )
    db.add_all(records)
    await db.flush()
    return {"source_inventory_item_id": source_id, "activities": records}
