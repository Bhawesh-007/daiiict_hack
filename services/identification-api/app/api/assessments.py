"""Create and read assessments for the Phase-1 vertical slice."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.persistence.database import get_db
from app.persistence.models import Assessment, AssessmentProduct, Company, Facility
from app.schemas.assessments import (
    AssessmentCreateRequest,
    AssessmentResponse,
    CompanyResponse,
    FacilityResponse,
    ProductResponse,
)

router = APIRouter(prefix="/api/assessments", tags=["assessments"])
PROJECT_ROOT = Path(__file__).resolve().parents[4]
TEMPLATE_DIRECTORY = PROJECT_ROOT / "data" / "industry-templates"


def _load_template(template_key: str, template_version: str | None) -> dict:
    """Resolve a template by canonical ID and optionally enforce its version."""
    for path in TEMPLATE_DIRECTORY.glob("*.json"):
        try:
            template = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Knowledge template cannot be read: {path.name}",
            ) from exc

        if template.get("template_id") != template_key:
            continue
        if template_version and template.get("template_version") != template_version:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Template {template_key!r} exists but version "
                    f"{template_version!r} is unavailable"
                ),
            )
        return template

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=f"Unknown industry template: {template_key}",
    )


def _to_response(
    assessment: Assessment, company: Company, facility: Facility
) -> AssessmentResponse:
    products_list = []
    if "products" in assessment.__dict__ and assessment.products:
        products_list = [ProductResponse.model_validate(p) for p in assessment.products]

    return AssessmentResponse(
        id=assessment.id,
        facility_id=assessment.facility_id,
        industry_name=assessment.industry_name,
        industry_code=assessment.industry_code,
        industry_template_key=assessment.industry_template_key,
        industry_template_version=assessment.industry_template_version,
        reporting_period_start=assessment.reporting_period_start,
        reporting_period_end=assessment.reporting_period_end,
        organizational_boundary=assessment.organizational_boundary,
        operational_boundary=assessment.operational_boundary,
        status=assessment.status,
        created_at=assessment.created_at,
        updated_at=assessment.updated_at,
        company=CompanyResponse.model_validate(company),
        facility=FacilityResponse.model_validate(facility),
        products=products_list,
    )


from pydantic import ValidationError
from app.schemas.assessments import SingleAssessmentCreate

@router.post("", response_model=AssessmentResponse, status_code=status.HTTP_201_CREATED)
async def create_assessment(
    raw_payload: dict,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AssessmentResponse:
    """Atomically store an assessment (supports full seed structure or single assessment structure)."""
    if "company" in raw_payload and "assessment" in raw_payload:
        try:
            payload = AssessmentCreateRequest.model_validate(raw_payload)
        except ValidationError as e:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.errors())
        
        assessment_input = payload.assessment
        if assessment_input.industry_template_key:
            _load_template(
                assessment_input.industry_template_key,
                assessment_input.industry_template_version,
            )

        if await db.get(Assessment, assessment_input.id) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Assessment {assessment_input.id} already exists",
            )

        company = await db.get(Company, payload.company.id)
        if company is None:
            company = Company(**payload.company.model_dump())
            db.add(company)
        elif company.name != payload.company.name:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The company ID already exists with different data",
            )

        facility = await db.get(Facility, payload.facility.id)
        if facility is None:
            facility = Facility(**payload.facility.model_dump())
            db.add(facility)

        assessment = Assessment(**assessment_input.model_dump())
        assessment.products = [
            AssessmentProduct(**product.model_dump()) for product in payload.products
        ]
        db.add(assessment)

        try:
            await db.flush()
        except IntegrityError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The assessment could not be stored because a referenced or unique record conflicts",
            ) from exc

        return await read_assessment(assessment.id, db)
    else:
        try:
            single = SingleAssessmentCreate.model_validate(raw_payload)
        except ValidationError as e:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.errors())

        if single.industry_template_key:
            _load_template(
                single.industry_template_key,
                single.industry_template_version,
            )

        if await db.get(Assessment, single.id) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Assessment {single.id} already exists",
            )

        facility = await db.get(Facility, single.facility_id)
        if facility is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Facility {single.facility_id} not found",
            )

        assessment = Assessment(**single.model_dump())
        db.add(assessment)

        try:
            await db.flush()
        except IntegrityError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The assessment could not be stored because a referenced or unique record conflicts",
            ) from exc

        return await read_assessment(assessment.id, db)


@router.get("/{assessment_id}", response_model=AssessmentResponse)
async def read_assessment(
    assessment_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AssessmentResponse:
    """Read a stored assessment with its company, facility, and products."""
    result = await db.execute(
        select(Assessment)
        .where(Assessment.id == assessment_id)
        .options(
            selectinload(Assessment.products),
            selectinload(Assessment.facility).selectinload(Facility.company),
        )
    )
    assessment = result.scalar_one_or_none()
    if assessment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment {assessment_id} was not found",
        )

    return _to_response(assessment, assessment.facility.company, assessment.facility)
