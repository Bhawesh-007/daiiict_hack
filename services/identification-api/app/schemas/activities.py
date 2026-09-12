from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ActivityCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    period_start: datetime
    period_end: datetime
    quantity: Decimal = Field(ge=0, max_digits=24, decimal_places=8)
    unit_code: str = Field(min_length=1, max_length=50)
    data_source_type: str | None = Field(default=None, max_length=30)
    data_quality: str | None = Field(default=None, max_length=30)
    evidence_reference: str | None = Field(default=None, max_length=500)
    notes: str | None = None

    @model_validator(mode="after")
    def validate_period(self):
        if self.period_end < self.period_start:
            raise ValueError("period_end must be on or after period_start")
        return self


class ActivityResponse(ActivityCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    source_inventory_item_id: UUID
    normalized_quantity: Decimal | None = None
    normalized_unit_code: str | None = None
    normalization_multiplier: Decimal | None = None
    created_at: datetime


class ActivityListResponse(BaseModel):
    source_inventory_item_id: UUID
    activities: list[ActivityResponse]
