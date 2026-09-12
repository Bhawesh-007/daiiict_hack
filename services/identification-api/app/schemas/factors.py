from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class FactorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    factor_code: str
    version: str
    name: str
    source_category: str | None = None
    scope: str | None = None
    factor_value: Decimal
    activity_unit: str
    emission_unit: str
    geography: str | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    source_organization: str | None = None
    source_document: str | None = None
    source_url: str | None = None
    method: str | None = None
    quality_rating: str | None = None
    metadata_json: dict[str, Any] | None = None


class FactorResolutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    source_key: str = Field(min_length=1, max_length=200)
    activity_unit: str = Field(min_length=1, max_length=50)
    activity_date: datetime | None = None
    geography: str | None = Field(default=None, max_length=100)
    factor_code: str | None = Field(default=None, max_length=100)
    factor_version: str | None = Field(default=None, max_length=50)


class FactorResolutionResponse(BaseModel):
    status: str
    reason: str
    factor: FactorResponse


class FactorSeedResponse(BaseModel):
    registry_id: str
    registry_version: str
    inserted: int
    existing: int
