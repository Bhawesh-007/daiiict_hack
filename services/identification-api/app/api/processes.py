"""API endpoints for Process Mapping, Equipment, and Input/Output Flows."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.persistence.database import get_db
from app.persistence.models import Assessment, Equipment, InputOutputFlow, ProcessStep
from app.schemas.processes import (
    BulkProcessStepsRequest,
    EquipmentCreate,
    EquipmentResponse,
    InputOutputFlowCreate,
    InputOutputFlowResponse,
    ProcessStepCreate,
    ProcessStepResponse,
)

router = APIRouter(prefix="/api", tags=["processes"])

PROJECT_ROOT = Path(__file__).resolve().parents[4]
TEMPLATE_DIRECTORY = PROJECT_ROOT / "data" / "industry-templates"


def _read_template(template_key: str) -> dict:
    for path in TEMPLATE_DIRECTORY.glob("*.json"):
        try:
            tmpl = json.loads(path.read_text(encoding="utf-8"))
            if tmpl.get("template_id") == template_key:
                return tmpl
        except Exception:
            continue
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Template {template_key!r} not found",
    )


@router.get("/assessments/{assessment_id}/processes", response_model=list[ProcessStepResponse])
async def get_assessment_processes(
    assessment_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ProcessStepResponse]:
    """Retrieve all processes for an assessment, ordered by sequence."""
    assessment = await db.get(Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment {assessment_id} not found",
        )

    stmt = (
        select(ProcessStep)
        .where(ProcessStep.assessment_id == assessment_id)
        .options(
            selectinload(ProcessStep.equipment),
            selectinload(ProcessStep.input_output_flows),
        )
        .order_by(ProcessStep.sequence.asc().nulls_last(), ProcessStep.created_at.asc())
    )
    result = await db.execute(stmt)
    steps = result.scalars().all()
    return [ProcessStepResponse.model_validate(step) for step in steps]


@router.post("/assessments/{assessment_id}/load-template", response_model=list[ProcessStepResponse])
async def load_industry_template(
    assessment_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    payload: dict | None = None,
) -> list[ProcessStepResponse]:
    """Load default processes from an industry template into the assessment."""
    assessment = await db.get(Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment {assessment_id} not found",
        )

    template_key = None
    if payload and "template_key" in payload:
        template_key = payload["template_key"]
    elif assessment.industry_template_key:
        template_key = assessment.industry_template_key
    else:
        template_key = "industry-food-processing-v1"

    tmpl = _read_template(template_key)
    processes_data = tmpl.get("processes", [])

    # Delete existing processes for this assessment
    await db.execute(delete(InputOutputFlow).where(InputOutputFlow.process_step_id.in_(
        select(ProcessStep.id).where(ProcessStep.assessment_id == assessment_id)
    )))
    await db.execute(delete(Equipment).where(Equipment.process_step_id.in_(
        select(ProcessStep.id).where(ProcessStep.assessment_id == assessment_id)
    )))
    await db.execute(delete(ProcessStep).where(ProcessStep.assessment_id == assessment_id))

    for proc in processes_data:
        step_id = uuid4()
        step = ProcessStep(
            id=step_id,
            assessment_id=assessment_id,
            name=proc.get("name", "Unnamed process"),
            sequence=proc.get("sequence", 10),
            description=f"Template process: {proc.get('process_id', '')}",
            is_outsourced="NO",
        )
        db.add(step)

        # Add suggested equipment defaults if available
        equipment_types = proc.get("typical_equipment_types", [])
        for eq_type in equipment_types:
            eq_name = eq_type.replace("_", " ").title()
            is_combustion = any(c in eq_type for c in ["boiler", "generator", "heater", "oven", "furnace", "dryer", "fryer"])
            fuel = "diesel" if is_combustion else None
            eq = Equipment(
                id=uuid4(),
                process_step_id=step_id,
                name=eq_name,
                equipment_type=eq_type,
                fuel_type=fuel,
                energy_type="fuel" if fuel else ("electricity" if "electric" in eq_type or "pump" in eq_type else "other"),
            )
            db.add(eq)

        # Add suggested inputs & outputs defaults
        inputs = proc.get("typical_input_types", [])
        for inp in inputs:
            is_electricity = "electricity" in inp
            category = "electricity" if is_electricity else ("fuel" if any(f in inp for f in ["diesel", "gas", "fuel", "biomass", "coal"]) else "material")
            item_name = "purchased_grid_electricity" if is_electricity else inp
            flow = InputOutputFlow(
                id=uuid4(),
                process_step_id=step_id,
                direction="INPUT",
                category=category,
                item_name=item_name,
                unit="kWh" if is_electricity else "kg",
            )
            db.add(flow)

        outputs = proc.get("typical_output_types", [])
        for outp in outputs:
            flow = InputOutputFlow(
                id=uuid4(),
                process_step_id=step_id,
                direction="OUTPUT",
                category="waste" if "waste" in outp or "release" in outp else "product",
                item_name=outp,
                unit="kg",
            )
            db.add(flow)

    await db.flush()
    return await get_assessment_processes(assessment_id, db)



@router.put("/assessments/{assessment_id}/processes", response_model=list[ProcessStepResponse])
async def update_assessment_processes(
    assessment_id: UUID,
    payload: BulkProcessStepsRequest | list[ProcessStepCreate],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ProcessStepResponse]:
    """Bulk update or replace process steps for an assessment, and update status to IN_PROGRESS."""
    assessment = await db.get(Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment {assessment_id} not found",
        )

    processes_input = payload.processes if isinstance(payload, BulkProcessStepsRequest) else payload

    # Clear existing steps and children
    await db.execute(delete(InputOutputFlow).where(InputOutputFlow.process_step_id.in_(
        select(ProcessStep.id).where(ProcessStep.assessment_id == assessment_id)
    )))
    await db.execute(delete(Equipment).where(Equipment.process_step_id.in_(
        select(ProcessStep.id).where(ProcessStep.assessment_id == assessment_id)
    )))
    await db.execute(delete(ProcessStep).where(ProcessStep.assessment_id == assessment_id))

    for item in processes_input:
        step = ProcessStep(
            id=item.id,
            assessment_id=assessment_id,
            name=item.name,
            sequence=item.sequence,
            description=item.description,
            is_outsourced=item.is_outsourced.value if hasattr(item.is_outsourced, "value") else str(item.is_outsourced),
        )
        db.add(step)

        for eq in item.equipment:
            equipment_obj = Equipment(
                id=eq.id,
                process_step_id=step.id,
                name=eq.name,
                equipment_type=eq.equipment_type,
                capacity=eq.capacity,
                fuel_type=eq.fuel_type,
                energy_type=eq.energy_type,
                description=eq.description,
            )
            db.add(equipment_obj)

        for flow in item.input_output_flows:
            flow_obj = InputOutputFlow(
                id=flow.id,
                process_step_id=step.id,
                equipment_id=flow.equipment_id,
                direction=flow.direction.value if hasattr(flow.direction, "value") else str(flow.direction),
                category=flow.category,
                item_name=flow.item_name,
                unit=flow.unit,
                data_availability=flow.data_availability,
                notes=flow.notes,
            )
            db.add(flow_obj)

    # Update assessment status to IN_PROGRESS if currently DRAFT
    if assessment.status == "DRAFT":
        assessment.status = "IN_PROGRESS"
        db.add(assessment)

    await db.flush()
    return await get_assessment_processes(assessment_id, db)


@router.put("/processes/{process_id}/equipment", response_model=list[EquipmentResponse])
async def update_process_equipment(
    process_id: UUID,
    payload: list[EquipmentCreate],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[EquipmentResponse]:
    """Replace equipment items for a process step."""
    step = await db.get(ProcessStep, process_id)
    if step is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Process step {process_id} not found",
        )

    await db.execute(delete(Equipment).where(Equipment.process_step_id == process_id))

    result_equipment = []
    for item in payload:
        eq = Equipment(
            id=item.id,
            process_step_id=process_id,
            name=item.name,
            equipment_type=item.equipment_type,
            capacity=item.capacity,
            fuel_type=item.fuel_type,
            energy_type=item.energy_type,
            description=item.description,
        )
        db.add(eq)
        result_equipment.append(eq)

    await db.flush()
    return [EquipmentResponse.model_validate(eq) for eq in result_equipment]


@router.put("/processes/{process_id}/flows", response_model=list[InputOutputFlowResponse])
async def update_process_flows(
    process_id: UUID,
    payload: list[InputOutputFlowCreate],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[InputOutputFlowResponse]:
    """Replace input/output flows for a process step."""
    step = await db.get(ProcessStep, process_id)
    if step is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Process step {process_id} not found",
        )

    await db.execute(delete(InputOutputFlow).where(InputOutputFlow.process_step_id == process_id))

    result_flows = []
    for item in payload:
        flow = InputOutputFlow(
            id=item.id,
            process_step_id=process_id,
            equipment_id=item.equipment_id,
            direction=item.direction.value if hasattr(item.direction, "value") else str(item.direction),
            category=item.category,
            item_name=item.item_name,
            unit=item.unit,
            data_availability=item.data_availability,
            notes=item.notes,
        )
        db.add(flow)
        result_flows.append(flow)

    await db.flush()
    return [InputOutputFlowResponse.model_validate(flow) for flow in result_flows]
