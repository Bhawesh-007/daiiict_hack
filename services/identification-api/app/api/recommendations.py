"""Layer 2 Phase 1 APIs driven exclusively by finalized Layer 1 profiles."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.layer2.catalog import load_catalog, load_demo_profile
from app.layer2.recommender import generate_impact_recommendations
from app.persistence.database import get_db
from app.persistence.models import FinalProfile
from app.schemas.recommendations import (
    InterventionCatalogResponse,
    RecommendationResponse,
)

router = APIRouter(prefix="/api", tags=["layer-2-recommendations"])


async def _profile_for_id(profile_id: UUID, db: AsyncSession) -> FinalProfile:
    profile = await db.get(FinalProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Finalized Layer 1 profile not found")
    if not profile.profile_snapshot_json:
        raise HTTPException(status_code=409, detail="Finalized Layer 1 profile has no snapshot")
    return profile


async def _latest_profile_for_assessment(assessment_id: UUID, db: AsyncSession) -> FinalProfile:
    result = await db.execute(
        select(FinalProfile)
        .where(FinalProfile.assessment_id == assessment_id)
        .order_by(FinalProfile.version.desc())
        .limit(1)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="No finalized Layer 1 profile found")
    return profile


def _recommendation_payload(profile: FinalProfile) -> dict[str, Any]:
    snapshot = dict(profile.profile_snapshot_json or {})
    snapshot["profile_id"] = str(profile.id)
    snapshot["profile_version"] = profile.version
    return generate_impact_recommendations(snapshot, load_catalog())


@router.get("/layer2/interventions", response_model=InterventionCatalogResponse)
async def read_intervention_catalog() -> dict[str, Any]:
    """Read the versioned intervention catalog used by candidate generation."""
    return load_catalog()


@router.get("/layer2/demo/profile")
async def read_demo_profile() -> dict[str, Any]:
    """Return the synthetic Layer 1 profile used by the demo recommendation flow."""
    return load_demo_profile()


@router.get("/layer2/demo/recommendations", response_model=RecommendationResponse)
async def recommend_from_demo_profile() -> dict[str, Any]:
    """Feed the synthetic Layer 1 profile directly into the Phase 1 engine."""
    return generate_impact_recommendations(load_demo_profile(), load_catalog())


@router.get(
    "/final-profiles/{profile_id}/recommendations",
    response_model=RecommendationResponse,
)
@router.post(
    "/final-profiles/{profile_id}/recommendations",
    response_model=RecommendationResponse,
)
async def recommend_from_final_profile(
    profile_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Generate candidates from the stored profile; no duplicate profile input is accepted."""
    profile = await _profile_for_id(profile_id, db)
    return _recommendation_payload(profile)


@router.get(
    "/assessments/{assessment_id}/recommendations",
    response_model=RecommendationResponse,
)
async def recommend_from_latest_profile(
    assessment_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Generate candidates from the latest finalized profile for an assessment."""
    profile = await _latest_profile_for_assessment(assessment_id, db)
    return _recommendation_payload(profile)
