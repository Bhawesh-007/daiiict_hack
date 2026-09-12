"""Build the immutable Layer 1 profile consumed by downstream layers."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID


def _id(value: Any) -> str | None:
    return str(value) if value is not None else None


def _decimal(value: Any) -> str | None:
    return str(value) if value is not None else None


def _sum_decimal(values: Iterable[Any]) -> Decimal:
    return sum((Decimal(str(value or 0)) for value in values), start=Decimal(0))


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def profile_checksum(snapshot: dict[str, Any]) -> str:
    """Return a stable digest for the exact profile snapshot."""
    encoded = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _process_snapshot(process: Any) -> dict[str, Any]:
    equipment = []
    for item in sorted(process.equipment or [], key=lambda value: str(value.id)):
        equipment.append(
            {
                "equipment_id": _id(item.id),
                "name": item.name,
                "equipment_type": item.equipment_type,
                "capacity": item.capacity,
                "fuel_type": item.fuel_type,
                "energy_type": item.energy_type,
                "description": item.description,
                "flows": [
                    {
                        "flow_id": _id(flow.id),
                        "direction": flow.direction,
                        "category": flow.category,
                        "item_name": flow.item_name,
                        "unit": flow.unit,
                        "data_availability": flow.data_availability,
                        "notes": flow.notes,
                    }
                    for flow in sorted(item.input_output_flows or [], key=lambda value: str(value.id))
                ],
            }
        )

    return {
        "process_id": _id(process.id),
        "name": process.name,
        "sequence": process.sequence,
        "description": process.description,
        "is_outsourced": process.is_outsourced,
        "equipment": equipment,
        "flows": [
            {
                "flow_id": _id(flow.id),
                "direction": flow.direction,
                "category": flow.category,
                "item_name": flow.item_name,
                "unit": flow.unit,
                "data_availability": flow.data_availability,
                "notes": flow.notes,
            }
            for flow in sorted(process.input_output_flows or [], key=lambda value: str(value.id))
        ],
    }


def build_profile_snapshot(
    assessment: Any,
    calculation_run: Any,
    source_items: list[Any],
    process_steps: list[Any],
    *,
    profile_id: UUID,
    version: int,
    finalized_at: datetime,
    finalized_by: str | None,
) -> dict[str, Any]:
    """Create the complete, self-contained Layer 1 handoff document."""
    summary = json.loads(calculation_run.notes or "{}")
    lines = list(calculation_run.lines or [])
    lines_by_source: dict[str, list[Any]] = defaultdict(list)
    for line in lines:
        if line.source_inventory_item_id is not None:
            lines_by_source[str(line.source_inventory_item_id)].append(line)

    source_percentages = summary.get("source_percentages", {})
    processes = sorted(process_steps, key=lambda value: (value.sequence or 0, str(value.id)))
    process_by_id = {str(process.id): process for process in processes}
    products = [
        {
            "product_id": _id(product.id),
            "product_name": product.product_name,
            "quantity": _decimal(product.quantity),
            "unit": product.unit,
            "description": product.description,
        }
        for product in assessment.products or []
    ]

    sources: list[dict[str, Any]] = []
    for source in sorted(source_items, key=lambda value: str(value.id)):
        source_id = str(source.id)
        source_lines = lines_by_source.get(source_id, [])
        process = process_by_id.get(str(source.process_step_id)) if source.process_step_id else None
        equipment = None
        if source.equipment_id and process:
            equipment = next(
                (item for item in process.equipment if str(item.id) == str(source.equipment_id)),
                None,
            )
        baseline = _sum_decimal(line.emissions_kgco2e for line in source_lines)
        activity_records = [
            {
                "activity_record_id": _id(activity.id),
                "quantity": _decimal(activity.quantity),
                "unit": activity.unit_code,
                "normalized_quantity": _decimal(activity.normalized_quantity),
                "normalized_unit": activity.normalized_unit_code,
                "period_start": activity.period_start,
                "period_end": activity.period_end,
                "data_source_type": activity.data_source_type,
                "data_quality": activity.data_quality,
                "evidence_reference": activity.evidence_reference,
                "notes": activity.notes,
            }
            for activity in sorted(source.activity_records or [], key=lambda value: str(value.id))
        ]

        sources.append(
            {
                "source_id": source_id,
                "source_key": source.source_key,
                "source_name": source.source_name,
                "source_category": source.source_category,
                "scope": source.scope,
                "status": source.status,
                "confirmed_source_identity": source.status == "CONFIRMED",
                "confirmation_note": source.confirmation_note,
                "confirmed_by": source.confirmed_by,
                "confirmed_at": source.confirmed_at,
                "process": {
                    "process_id": _id(process.id),
                    "name": process.name,
                }
                if process
                else None,
                "equipment": {
                    "equipment_id": _id(equipment.id),
                    "name": equipment.name,
                    "equipment_type": equipment.equipment_type,
                    "fuel_type": equipment.fuel_type,
                    "energy_type": equipment.energy_type,
                }
                if equipment
                else None,
                "current_technology_or_route": {
                    "process_name": process.name if process else None,
                    "equipment_name": equipment.name if equipment else None,
                    "equipment_type": equipment.equipment_type if equipment else None,
                    "fuel_type": equipment.fuel_type if equipment else None,
                    "energy_type": equipment.energy_type if equipment else None,
                },
                "activity_records": activity_records,
                "baseline_emissions_kgco2e": _decimal(baseline),
                "contribution_percentage": _decimal(source_percentages.get(source_id, 0)),
                "calculated_line_count": len(source_lines),
                "recommendation_eligible": source.status == "CONFIRMED" and bool(source_lines),
            }
        )

    quantified_source_count = sum(1 for source in sources if source["calculated_line_count"] > 0)
    completeness = (
        Decimal(quantified_source_count * 100) / Decimal(len(sources))
        if sources
        else Decimal(0)
    ).quantize(Decimal("0.01"))

    return _jsonable(
        {
            "schema_version": "layer1-final-profile-v1",
            "profile_id": profile_id,
            "profile_version": version,
            "assessment_id": assessment.id,
            "profile_status": "FINALIZED",
            "company": {
                "company_id": assessment.facility.company.id,
                "name": assessment.facility.company.name,
                "msme_category": assessment.facility.company.msme_category,
                "registration_number": assessment.facility.company.registration_number,
                "address": assessment.facility.company.address,
            },
            "industry": {
                "name": assessment.industry_name,
                "code": assessment.industry_code,
                "template_key": assessment.industry_template_key,
                "template_version": assessment.industry_template_version,
            },
            "facility": {
                "facility_id": assessment.facility.id,
                "name": assessment.facility.name,
                "location": assessment.facility.location,
                "city": assessment.facility.city,
                "state": assessment.facility.state,
                "country": assessment.facility.country,
                "grid_region": assessment.facility.grid_region,
                "ownership_type": assessment.facility.ownership_type,
            },
            "products": products,
            "reporting_period": {
                "start": assessment.reporting_period_start,
                "end": assessment.reporting_period_end,
            },
            "boundaries": {
                "organizational": assessment.organizational_boundary,
                "operational": assessment.operational_boundary,
            },
            "processes": [_process_snapshot(process) for process in processes],
            "sources": sources,
            "baseline_emissions_kgco2e": _decimal(calculation_run.total_emissions_kgco2e),
            "scope_totals_kgco2e": summary.get("scope_totals", {}),
            "category_totals_kgco2e": summary.get("category_totals", {}),
            "source_ranking": summary.get("hotspot_ranking", {}),
            "unquantified_sources": summary.get("unquantified_sources", []),
            "warnings": summary.get("warnings", []),
            "completeness_percentage": _decimal(completeness),
            "methodology": {
                "layer1_methodology_version": calculation_run.methodology_version,
                "factor_set_version": calculation_run.factor_set_version,
                "calculation_run_id": calculation_run.id,
            },
            "business_constraints": (
                {
                    "status": "CAPTURED_IN_LAYER_1",
                    **assessment.business_constraints,
                }
                if getattr(assessment, "business_constraints", None)
                else {
                    "status": "NOT_CAPTURED_IN_LAYER_1",
                    "budget": None,
                    "operational_constraints": [],
                }
            ),
            "finalization": {
                "finalized_at": finalized_at,
                "finalized_by": finalized_by,
            },
        }
    )
