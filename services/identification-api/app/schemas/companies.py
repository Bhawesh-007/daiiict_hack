"""Pydantic schemas for Company and Facility entities."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class CompanyCreate(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=255)
    msme_category: str | None = Field(default=None, max_length=50)
    registration_number: str | None = Field(default=None, max_length=100)
    contact_email: str | None = Field(default=None, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=50)
    address: str | None = None

    model_config = ConfigDict(extra="ignore")


class CompanyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    msme_category: str | None = None
    registration_number: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    address: str | None = None
    created_at: datetime
    updated_at: datetime


class FacilityCreate(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    company_id: UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    location: str | None = Field(default=None, max_length=500)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    country: str | None = Field(default="India", max_length=100)
    grid_region: str | None = Field(default=None, max_length=100)
    ownership_type: str | None = Field(default=None, max_length=50)
    latitude: Decimal | None = None
    longitude: Decimal | None = None

    model_config = ConfigDict(extra="ignore")


class FacilityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    name: str
    location: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = "India"
    grid_region: str | None = None
    ownership_type: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    created_at: datetime
    updated_at: datetime
