"""Finalize and read immutable Layer 1 profiles for downstream consumers."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.final_profile import build_profile_snapshot, profile_checksum
from app.persistence.database import get_db
from app.persistence.models import (
    Assessment,
    AuditEvent,
    CalculationRun,
    Equipment,
    Facility,
    FinalProfile,
    ProcessStep,
    SourceInventoryItem,
)
from app.schemas.final_profile import FinalProfileListResponse, FinalProfileResponse

router = APIRouter(prefix="/api", tags=["final-profiles"])


async def _load_calculation_run(assessment_id: UUID, db: AsyncSession) -> CalculationRun:
    result = await db.execute(
        select(CalculationRun)
        .where(
            CalculationRun.assessment_id == assessment_id,
            CalculationRun.status == "COMPLETED",
        )
        .order_by(CalculationRun.completed_at.desc())
        .options(selectinload(CalculationRun.lines))
        .limit(1)
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Run the Layer 1 calculation before finalizing the profile",
        )
    return run


async def _load_assessment(assessment_id: UUID, db: AsyncSession) -> Assessment:
    result = await db.execute(
        select(Assessment)
        .where(Assessment.id == assessment_id)
        .options(
            selectinload(Assessment.facility).selectinload(Facility.company),
            selectinload(Assessment.products),
            selectinload(Assessment.process_steps)
            .selectinload(ProcessStep.equipment)
            .selectinload(Equipment.input_output_flows),
            selectinload(Assessment.process_steps).selectinload(ProcessStep.input_output_flows),
            selectinload(Assessment.source_inventory_items).selectinload(
                SourceInventoryItem.activity_records
            ),
        )
    )
    assessment = result.scalar_one_or_none()
    if assessment is None:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return assessment


def _profile_payload(profile: FinalProfile) -> dict[str, Any]:
    snapshot = dict(profile.profile_snapshot_json or {})
    snapshot.setdefault("profile_id", str(profile.id))
    snapshot.setdefault("profile_version", profile.version)
    snapshot["checksum"] = profile.checksum
    snapshot["finalized_at"] = profile.finalized_at
    return snapshot


@router.post(
    "/assessments/{assessment_id}/finalize",
    response_model=FinalProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
async def finalize_profile(
    assessment_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Freeze the latest calculated Layer 1 state into a versioned snapshot."""
    assessment = await _load_assessment(assessment_id, db)
    run = await _load_calculation_run(assessment_id, db)
    summary = json.loads(run.notes or "{}")
    if summary.get("status") == "EMPTY":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="At least one calculated Layer 1 source is required before finalization",
        )

    next_version = (
        await db.execute(
            select(func.coalesce(func.max(FinalProfile.version), 0) + 1).where(
                FinalProfile.assessment_id == assessment_id
            )
        )
    ).scalar_one()
    finalized_at = datetime.now(UTC)
    profile_id = uuid4()
    snapshot = build_profile_snapshot(
        assessment,
        run,
        list(assessment.source_inventory_items),
        list(assessment.process_steps),
        profile_id=profile_id,
        version=int(next_version),
        finalized_at=finalized_at,
        finalized_by="system",
    )
    checksum = profile_checksum(snapshot)
    quantified_sources = sum(
        1 for source in snapshot["sources"] if source["calculated_line_count"] > 0
    )
    completeness = snapshot["completeness_percentage"]

    profile = FinalProfile(
        id=profile_id,
        assessment_id=assessment_id,
        calculation_run_id=run.id,
        version=int(next_version),
        total_emissions_kgco2e=run.total_emissions_kgco2e,
        completeness_percentage=completeness,
        scope_totals_json=snapshot["scope_totals_kgco2e"],
        category_totals_json=snapshot["category_totals_kgco2e"],
        source_ranking_json=snapshot["source_ranking"],
        unquantified_sources_json=snapshot["unquantified_sources"],
        profile_snapshot_json=snapshot,
        checksum=checksum,
        finalized_by="system",
        finalized_at=finalized_at,
    )
    db.add(profile)
    assessment.status = "FINALIZED"
    db.add(
        AuditEvent(
            actor="system",
            action="FINALIZE_PROFILE",
            entity_type="FinalProfile",
            entity_id=profile_id,
            after_value={
                "assessment_id": str(assessment_id),
                "profile_version": int(next_version),
                "calculation_run_id": str(run.id),
                "quantified_source_count": quantified_sources,
            },
            metadata_json={"checksum": checksum},
        )
    )
    await db.flush()
    return _profile_payload(profile)


@router.get(
    "/assessments/{assessment_id}/latest-final-profile",
    response_model=FinalProfileResponse,
)
async def read_latest_final_profile(
    assessment_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    result = await db.execute(
        select(FinalProfile)
        .where(FinalProfile.assessment_id == assessment_id)
        .order_by(FinalProfile.version.desc())
        .limit(1)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="No finalized Layer 1 profile found")
    return _profile_payload(profile)


@router.get(
    "/final-profiles/{profile_id}",
    response_model=FinalProfileResponse,
)
async def read_final_profile(
    profile_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    profile = await db.get(FinalProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Finalized Layer 1 profile not found")
    return _profile_payload(profile)


@router.get(
    "/assessments/{assessment_id}/final-profiles",
    response_model=FinalProfileListResponse,
)
async def list_final_profiles(
    assessment_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    profiles = list(
        (
            await db.execute(
                select(FinalProfile)
                .where(FinalProfile.assessment_id == assessment_id)
                .order_by(FinalProfile.version.desc())
            )
        )
        .scalars()
        .all()
    )
    return {"profiles": [_profile_payload(profile) for profile in profiles]}
