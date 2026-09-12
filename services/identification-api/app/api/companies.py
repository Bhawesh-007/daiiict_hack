"""API endpoints for Companies and Facilities."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.database import get_db
from app.persistence.models import Company, Facility
from app.schemas.companies import CompanyCreate, CompanyResponse, FacilityCreate, FacilityResponse

router = APIRouter(prefix="/api/companies", tags=["companies"])


@router.post("", response_model=CompanyResponse, status_code=status.HTTP_201_CREATED)
async def create_company(
    payload: CompanyCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CompanyResponse:
    """Create a new Company."""
    existing = await db.get(Company, payload.id)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Company with id {payload.id} already exists",
        )

    company = Company(**payload.model_dump())
    db.add(company)
    await db.flush()
    return CompanyResponse.model_validate(company)


@router.get("/{company_id}", response_model=CompanyResponse)
async def read_company(
    company_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CompanyResponse:
    """Read a Company by ID."""
    company = await db.get(Company, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company {company_id} not found",
        )
    return CompanyResponse.model_validate(company)


@router.post("/{company_id}/facilities", response_model=FacilityResponse, status_code=status.HTTP_201_CREATED)
async def create_facility(
    company_id: UUID,
    payload: FacilityCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FacilityResponse:
    """Create a Facility linked to a company."""
    company = await db.get(Company, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company {company_id} not found",
        )

    existing_facility = await db.get(Facility, payload.id)
    if existing_facility is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Facility with id {payload.id} already exists",
        )

    data = payload.model_dump()
    data["company_id"] = company_id
    facility = Facility(**data)
    db.add(facility)
    await db.flush()
    return FacilityResponse.model_validate(facility)
