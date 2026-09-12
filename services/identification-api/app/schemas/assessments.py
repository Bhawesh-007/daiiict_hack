"""Request and response contracts for the Phase-1 assessment flow."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

AssessmentStatus = Literal[
    "DRAFT",
    "IN_PROGRESS",
    "IDENTIFIED",
    "QUANTIFIED",
    "FINALIZED",
    "ARCHIVED",
]


class StrictModel(BaseModel):
    """Reject unknown input fields so seed mistakes are visible."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CompanySeed(StrictModel):
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=255)
    msme_category: str | None = Field(default=None, max_length=50)
    registration_number: str | None = Field(default=None, max_length=100)
    contact_email: str | None = Field(default=None, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=50)
    address: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class FacilitySeed(StrictModel):
    id: UUID = Field(default_factory=uuid4)
    company_id: UUID
    name: str = Field(min_length=1, max_length=255)
    location: str | None = Field(default=None, max_length=500)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    country: str | None = Field(default="India", max_length=100)
    grid_region: str | None = Field(default=None, max_length=100)
    ownership_type: str | None = Field(default=None, max_length=50)
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None



class AssessmentSeed(StrictModel):
    id: UUID = Field(default_factory=uuid4)
    facility_id: UUID
    industry_name: str = Field(min_length=1, max_length=200)
    industry_code: str | None = Field(default=None, max_length=50)
    industry_template_key: str | None = Field(default=None, max_length=200)
    industry_template_version: str | None = Field(default=None, max_length=50)
    reporting_period_start: datetime
    reporting_period_end: datetime
    organizational_boundary: str | None = Field(default=None, max_length=100)
    operational_boundary: str | None = Field(default=None, max_length=100)
    status: AssessmentStatus = "DRAFT"

    @model_validator(mode="after")
    def validate_reporting_period(self) -> AssessmentSeed:
        if (
            self.reporting_period_start.tzinfo is None
            or self.reporting_period_end.tzinfo is None
        ):
            raise ValueError("reporting period timestamps must include a timezone")
        if self.reporting_period_end < self.reporting_period_start:
            raise ValueError(
                "reporting_period_end must be on or after reporting_period_start"
            )
        return self


class ProductSeed(StrictModel):
    id: UUID = Field(default_factory=uuid4)
    product_name: str = Field(min_length=1, max_length=255)
    quantity: Decimal | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, max_length=50)
    description: str | None = None


class AssessmentCreateRequest(StrictModel):
    seed_version: str = Field(default="1.0.0", max_length=20)
    company: CompanySeed
    facility: FacilitySeed
    assessment: AssessmentSeed
    products: list[ProductSeed] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_references(self) -> AssessmentCreateRequest:
        if self.facility.company_id != self.company.id:
            raise ValueError("facility.company_id must match company.id")
        if self.assessment.facility_id != self.facility.id:
            raise ValueError("assessment.facility_id must match facility.id")
        return self


class SingleAssessmentCreate(StrictModel):
    id: UUID = Field(default_factory=uuid4)
    facility_id: UUID
    industry_name: str = Field(min_length=1, max_length=200)
    industry_code: str | None = Field(default=None, max_length=50)
    industry_template_key: str | None = Field(default=None, max_length=200)
    industry_template_version: str | None = Field(default=None, max_length=50)
    reporting_period_start: datetime
    reporting_period_end: datetime
    organizational_boundary: str | None = Field(default=None, max_length=100)
    operational_boundary: str | None = Field(default=None, max_length=100)
    status: AssessmentStatus = "DRAFT"

    @model_validator(mode="after")
    def validate_reporting_period(self) -> SingleAssessmentCreate:
        if (
            self.reporting_period_start.tzinfo is None
            or self.reporting_period_end.tzinfo is None
        ):
            raise ValueError("reporting period timestamps must include a timezone")
        if self.reporting_period_end < self.reporting_period_start:
            raise ValueError(
                "reporting_period_end must be on or after reporting_period_start"
            )
        return self


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_name: str
    quantity: Decimal | None
    unit: str | None
    description: str | None


class CompanyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    msme_category: str | None


class FacilityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    name: str
    location: str | None
    city: str | None
    state: str | None
    country: str | None
    grid_region: str | None
    ownership_type: str | None


class AssessmentResponse(BaseModel):
    id: UUID
    facility_id: UUID
    industry_name: str
    industry_code: str | None
    industry_template_key: str | None
    industry_template_version: str | None
    reporting_period_start: datetime
    reporting_period_end: datetime
    organizational_boundary: str | None
    operational_boundary: str | None
    status: AssessmentStatus
    created_at: datetime
    updated_at: datetime
    company: CompanyResponse
    facility: FacilityResponse
    products: list[ProductResponse]
