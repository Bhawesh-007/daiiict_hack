"""Phase-2 source candidate and reviewed-inventory contracts."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.enums import CandidateOrigin, CandidateStatus, InventoryStatus
from app.schemas.knowledge import is_known_source_type


class SourceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_key: str = Field(min_length=1, max_length=200)
    source_name: str = Field(min_length=1, max_length=255)
    source_category: str | None = Field(default=None, max_length=100)

    @field_validator("source_key")
    @classmethod
    def validate_source_key(cls, value: str) -> str:
        if not is_known_source_type(value):
            raise ValueError(f"unknown source_key: {value}")
        return value


class SourceCandidateContract(SourceModel):
    id: UUID = Field(default_factory=uuid4)
    assessment_id: UUID
    process_step_id: UUID | None = None
    equipment_id: UUID | None = None
    identification_run_id: UUID | None = None
    suggested_scope: str | None = Field(default=None, max_length=50)
    origin: CandidateOrigin
    reason: str | None = None
    confidence: Decimal | None = Field(default=None, ge=0, le=1)
    status: CandidateStatus = CandidateStatus.PROPOSED
    evidence_json: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_rule_evidence(self) -> SourceCandidateContract:
        if self.origin is CandidateOrigin.RULE:
            if not self.reason:
                raise ValueError("rule-generated candidates require a reason")
            if not self.evidence_json or not self.evidence_json.get("rule_id"):
                raise ValueError(
                    "rule-generated candidates require evidence_json.rule_id"
                )
            if not self.evidence_json.get("rule_version"):
                raise ValueError(
                    "rule-generated candidates require evidence_json.rule_version"
                )
        return self


class SourceCandidateRequest(SourceCandidateContract):
    """Input contract for a newly generated candidate."""

    @model_validator(mode="after")
    def require_proposed_status(self) -> SourceCandidateRequest:
        if self.status is not CandidateStatus.PROPOSED:
            raise ValueError(
                "new candidates must start as PROPOSED; promotion or dismissal is a review action"
            )
        return self


class SourceCandidateResponse(SourceCandidateContract):
    """Output contract that can represent every persisted candidate status."""


class SourceCandidatesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: list[SourceCandidateResponse]


class SourceInventoryContract(SourceModel):
    id: UUID = Field(default_factory=uuid4)
    assessment_id: UUID
    candidate_id: UUID
    process_step_id: UUID | None = None
    equipment_id: UUID | None = None
    scope: str | None = Field(default=None, max_length=50)
    status: InventoryStatus = InventoryStatus.POTENTIAL
    confirmation_note: str | None = None
    confirmed_by: str | None = Field(default=None, max_length=255)
    confirmed_at: datetime | None = None

    @model_validator(mode="after")
    def validate_review_metadata(self) -> SourceInventoryContract:
        if self.status is InventoryStatus.CONFIRMED and (
            not self.confirmed_by or self.confirmed_at is None
        ):
            raise ValueError(
                "CONFIRMED inventory items require confirmed_by and confirmed_at"
            )
        if self.status is InventoryStatus.NOT_APPLICABLE and not self.confirmation_note:
            raise ValueError("NOT_APPLICABLE inventory items require confirmation_note")
        return self


class SourceStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    status: InventoryStatus
    confirmation_note: str | None = None
    confirmed_by: str | None = Field(default=None, max_length=255)
    confirmed_at: datetime | None = None

    @model_validator(mode="after")
    def validate_review_metadata(self) -> SourceStatusUpdate:
        if self.status is InventoryStatus.CONFIRMED and (
            not self.confirmed_by or self.confirmed_at is None
        ):
            raise ValueError("CONFIRMED status requires confirmed_by and confirmed_at")
        if self.status is InventoryStatus.NOT_APPLICABLE and not self.confirmation_note:
            raise ValueError("NOT_APPLICABLE status requires confirmation_note")
        return self


SourceInventoryResponse = SourceInventoryContract
