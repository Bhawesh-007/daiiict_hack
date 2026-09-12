from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class IdentificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    include_ml: bool = False


class IdentificationRunResponse(BaseModel):
    run_id: UUID
    assessment_id: UUID
    status: str
    engine_type: str
    engine_version: str | None = None
    input_hash: str | None = None
    candidate_count: int = 0
    template_candidate_count: int = 0
    rule_candidate_count: int = 0
    ml_candidate_count: int = 0
    ml_status: str = "DISABLED"


class CandidateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    assessment_id: UUID
    identification_run_id: UUID | None = None
    process_step_id: UUID | None = None
    equipment_id: UUID | None = None
    source_key: str
    source_name: str
    source_category: str | None = None
    suggested_scope: str | None = None
    origin: str
    reason: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    status: str
    evidence_json: dict[str, Any] | None = None


class IdentificationRunDetail(IdentificationRunResponse):
    output_json: dict[str, Any] | None = None
