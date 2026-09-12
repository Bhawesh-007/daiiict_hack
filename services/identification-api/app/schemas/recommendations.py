"""Layer 2 Phase 1 recommendation contracts."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RecommendationCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommendation_id: str
    intervention_id: str
    intervention_name: str
    short_description: str
    intervention_type: str
    circularity_dimension: str
    source_id: UUID
    source_key: str
    source_name: str
    baseline_emissions_kgco2e: str
    contribution_percentage: str
    hotspot_priority: str
    rank: int = Field(ge=1)
    match_reasons: list[str]
    required_conditions: list[str]
    required_evidence: list[str]
    eligibility_status: str
    impact_status: str
    catalog_version: str
    projected_emissions_kgco2e: str
    avoided_emissions_kgco2e: str
    new_intervention_emissions_kgco2e: str
    carbon_reduction_kgco2e: str
    reduction_percentage: str
    implementation_cost_inr: str
    annual_avoided_cost_inr: str
    annual_operating_cost_inr: str
    annual_savings_inr: str
    simple_payback_years: str | None
    circularity_score: str
    technical_feasibility_score: str
    feasibility_score: str
    feasibility_status: str
    budget_status: str
    operational_status: str
    payback_status: str
    assumption_source: str
    impact_model_version: str
    assumptions: dict[str, Any]


class ExcludedSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: UUID | None = None
    source_name: str | None = None
    reason: str


class RecommendationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    engine_version: str
    catalog_id: str
    catalog_version: str
    profile_id: UUID
    profile_version: int = Field(ge=1)
    assessment_id: UUID
    status: str
    phase: str
    recommendation_count: int = Field(ge=0)
    recommendations: list[RecommendationCandidate]
    excluded_sources: list[ExcludedSource]
    limitations: list[str]
    impact_assumption_notice: str


class InterventionCatalogResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    catalog_id: str
    catalog_version: str
    status: str
    warning: str
    interventions: list[dict[str, Any]]
