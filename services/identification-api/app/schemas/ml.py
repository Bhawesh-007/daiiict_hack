"""Strict contracts for identification-layer ML input and output."""

from typing import Any, Literal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from app.schemas.knowledge import is_known_source_type


class MLFact(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    fact_type: Literal["process", "equipment", "flow"]
    text: str = Field(min_length=1, max_length=4000)
    process_step_id: UUID | None = None
    equipment_id: UUID | None = None


class MLIdentificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    facts: list[MLFact] = Field(min_length=1, max_length=500)


class MLSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    source_key: str = Field(min_length=1, max_length=200)
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=2000)
    follow_up_questions: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices(
            "follow_up_questions", "follow_up_questions_questions"
        ),
    )
    model_id: str = Field(min_length=1, max_length=100)
    model_version: str = Field(min_length=1, max_length=50)
    process_step_id: UUID | None = None
    equipment_id: UUID | None = None

    @field_validator("source_key")
    @classmethod
    def validate_source_key(cls, value: str) -> str:
        if not is_known_source_type(value):
            raise ValueError(f"unknown source_key: {value}")
        return value


class MLPersistenceCandidate(BaseModel):
    """The only ML payload allowed to enter candidate merging/persistence."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    source_key: str = Field(min_length=1, max_length=200)
    source_name: str = Field(min_length=1, max_length=255)
    source_category: str | None = Field(default=None, max_length=100)
    suggested_scope: str | None = Field(default=None, max_length=50)
    process_step_id: UUID | None = None
    equipment_id: UUID | None = None
    origin: Literal["ML"] = "ML"
    status: Literal["PROPOSED"] = "PROPOSED"
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=2000)
    model_id: str = Field(min_length=1, max_length=100)
    model_version: str = Field(min_length=1, max_length=50)
    evidence_json: dict[str, Any]

    @field_validator("source_key")
    @classmethod
    def validate_source_key(cls, value: str) -> str:
        if not is_known_source_type(value):
            raise ValueError(f"unknown source_key: {value}")
        return value

    @field_validator("evidence_json")
    @classmethod
    def validate_model_evidence(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not value.get("model_id") or not value.get("model_version"):
            raise ValueError("ML evidence requires model_id and model_version")
        return value
