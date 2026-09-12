"""Phase-2 universal checklist contracts."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.enums import ChecklistStatus
from app.schemas.knowledge import is_known_source_type, universal_source_type_ids


class ChecklistItemContract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: UUID = Field(default_factory=uuid4)
    assessment_id: UUID
    source_key: str = Field(min_length=1, max_length=200)
    label: str = Field(min_length=1, max_length=255)
    status: ChecklistStatus
    required_fields: list[str] = Field(min_length=1)
    reason: str | None = None
    candidate_ids: list[UUID] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None

    @field_validator("source_key")
    @classmethod
    def validate_source_key(cls, value: str) -> str:
        if not is_known_source_type(value):
            raise ValueError(f"unknown source_key: {value}")
        return value

    @model_validator(mode="after")
    def validate_status_reason(self) -> ChecklistItemContract:
        if self.status is ChecklistStatus.NOT_APPLICABLE and not self.reason:
            raise ValueError("NOT_APPLICABLE checklist items require a reason")
        if self.status is ChecklistStatus.MISSING_INFORMATION and not self.reason:
            raise ValueError("MISSING_INFORMATION checklist items require a reason")
        return self


class ChecklistResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assessment_id: UUID
    items: list[ChecklistItemContract] = Field(min_length=1)

    @model_validator(mode="after")
    def require_complete_universal_coverage(self) -> ChecklistResponse:
        item_keys = [item.source_key for item in self.items]
        if len(item_keys) != len(set(item_keys)):
            raise ValueError("checklist must contain only one item per source_key")
        expected = universal_source_type_ids()
        missing = sorted(expected - set(item_keys))
        if missing:
            raise ValueError(
                "checklist is missing universal source types: " + ", ".join(missing)
            )
        if any(item.assessment_id != self.assessment_id for item in self.items):
            raise ValueError(
                "all checklist items must belong to the response assessment"
            )
        return self
