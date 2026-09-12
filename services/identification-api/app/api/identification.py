from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.identification.orchestrator import IdentificationOrchestrator
from app.persistence.database import get_db
from app.persistence.models import (
    IdentificationRun,
    SourceCandidate,
    SourceInventoryItem,
)
from app.schemas.checklist import ChecklistItemContract, ChecklistResponse
from app.schemas.identification import (
    CandidateResponse,
    IdentificationRequest,
    IdentificationRunDetail,
    IdentificationRunResponse,
)
from app.schemas.sources import SourceInventoryContract, SourceStatusUpdate

router = APIRouter(prefix="/api", tags=["identification"])

def _response(run: IdentificationRun) -> IdentificationRunResponse:
    d = run.output_json or {}; return IdentificationRunResponse(run_id=run.id, assessment_id=run.assessment_id, status=run.status, engine_type=run.engine_type, engine_version=run.engine_version, input_hash=run.input_hash, **{k: d.get(k, 0) for k in ("candidate_count", "template_candidate_count", "rule_candidate_count", "ml_candidate_count")}, ml_status=d.get("ml_status", "DISABLED"))

@router.post("/assessments/{assessment_id}/identify", response_model=IdentificationRunResponse)
async def identify(assessment_id: UUID, payload: IdentificationRequest, db: Annotated[AsyncSession, Depends(get_db)]):
    return _response(await IdentificationOrchestrator(db).run(assessment_id, payload.include_ml))

@router.get("/assessments/{assessment_id}/candidates", response_model=list[CandidateResponse])
async def candidates(assessment_id: UUID, db: Annotated[AsyncSession, Depends(get_db)]):
    return list((await db.execute(select(SourceCandidate).where(SourceCandidate.assessment_id == assessment_id).order_by(SourceCandidate.created_at))).scalars().all())

@router.get("/assessments/{assessment_id}/identification-runs/{run_id}", response_model=IdentificationRunDetail)
async def run_detail(assessment_id: UUID, run_id: UUID, db: Annotated[AsyncSession, Depends(get_db)]):
    run = (await db.execute(select(IdentificationRun).where(IdentificationRun.id == run_id, IdentificationRun.assessment_id == assessment_id))).scalar_one_or_none()
    if run is None: raise HTTPException(404, "Identification run not found")
    return IdentificationRunDetail(**_response(run).model_dump(), output_json=run.output_json)

@router.get("/assessments/{assessment_id}/checklist", response_model=ChecklistResponse)
async def checklist(assessment_id: UUID, db: Annotated[AsyncSession, Depends(get_db)]):
    run = (await db.execute(select(IdentificationRun).where(IdentificationRun.assessment_id == assessment_id, IdentificationRun.status == "COMPLETED").order_by(IdentificationRun.completed_at.desc()))).scalars().first()
    if run is None or not run.output_json or "checklist" not in run.output_json:
        raise HTTPException(404, "No materialized checklist exists for this assessment")
    return ChecklistResponse(assessment_id=assessment_id, items=[ChecklistItemContract(**item) for item in run.output_json["checklist"]])

@router.post("/assessments/{assessment_id}/candidates/{candidate_id}/review", response_model=SourceInventoryContract, status_code=201)
async def review_candidate(assessment_id: UUID, candidate_id: UUID, payload: SourceStatusUpdate, db: Annotated[AsyncSession, Depends(get_db)]):
    candidate = (await db.execute(select(SourceCandidate).where(SourceCandidate.id == candidate_id, SourceCandidate.assessment_id == assessment_id))).scalar_one_or_none()
    if candidate is None:
        raise HTTPException(404, "Source candidate not found")
    item = (await db.execute(select(SourceInventoryItem).where(SourceInventoryItem.assessment_id == assessment_id, SourceInventoryItem.candidate_id == candidate.id))).scalar_one_or_none()
    if item is None:
        item = SourceInventoryItem(
        assessment_id=assessment_id,
        candidate_id=candidate.id,
        process_step_id=candidate.process_step_id,
        equipment_id=candidate.equipment_id,
        source_key=candidate.source_key,
        source_name=candidate.source_name,
        source_category=candidate.source_category,
        scope=candidate.suggested_scope,
        status=payload.status.value,
        confirmation_note=payload.confirmation_note,
        confirmed_by=payload.confirmed_by,
        confirmed_at=payload.confirmed_at,
        )
        db.add(item)
    else:
        item.status = payload.status.value
        item.confirmation_note = payload.confirmation_note
        item.confirmed_by = payload.confirmed_by
        item.confirmed_at = payload.confirmed_at
    candidate.status = "PROMOTED"
    await db.flush()
    return item
