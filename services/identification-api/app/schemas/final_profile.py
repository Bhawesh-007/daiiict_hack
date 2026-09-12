"""Response contract for the immutable Layer 1 profile handoff."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class FinalProfileResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: str
    profile_id: UUID
    profile_version: int = Field(ge=1)
    assessment_id: UUID
    profile_status: str
    company: dict[str, Any]
    industry: dict[str, Any]
    facility: dict[str, Any]
    products: list[dict[str, Any]]
    reporting_period: dict[str, Any]
    boundaries: dict[str, Any]
    processes: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    baseline_emissions_kgco2e: str
    scope_totals_kgco2e: dict[str, Any]
    category_totals_kgco2e: dict[str, Any]
    source_ranking: dict[str, Any]
    unquantified_sources: list[Any]
    warnings: list[str]
    completeness_percentage: str
    methodology: dict[str, Any]
    business_constraints: dict[str, Any]
    finalization: dict[str, Any]


class FinalProfileListResponse(BaseModel):
    profiles: list[FinalProfileResponse]

