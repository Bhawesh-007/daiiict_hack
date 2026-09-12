"""Pydantic schemas for Process Steps, Equipment, and Input/Output Flows."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import FlowDirection, ProcessOutsourcing


class EquipmentCreate(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=255)
    equipment_type: str | None = Field(default=None, max_length=100)
    capacity: str | None = Field(default=None, max_length=100)
    fuel_type: str | None = Field(default=None, max_length=100)
    energy_type: str | None = Field(default=None, max_length=100)
    description: str | None = None

    model_config = ConfigDict(extra="ignore")


class EquipmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    process_step_id: UUID
    name: str
    equipment_type: str | None = None
    capacity: str | None = None
    fuel_type: str | None = None
    energy_type: str | None = None
    description: str | None = None
    created_at: datetime
    updated_at: datetime


class InputOutputFlowCreate(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    equipment_id: UUID | None = None
    direction: FlowDirection = FlowDirection.INPUT
    category: str | None = Field(default=None, max_length=100)
    item_name: str = Field(min_length=1, max_length=255)
    unit: str | None = Field(default=None, max_length=50)
    data_availability: str | None = Field(default=None, max_length=50)
    notes: str | None = None

    model_config = ConfigDict(extra="ignore")


class InputOutputFlowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    process_step_id: UUID | None = None
    equipment_id: UUID | None = None
    direction: FlowDirection
    category: str | None = None
    item_name: str
    unit: str | None = None
    data_availability: str | None = None
    notes: str | None = None
    created_at: datetime


class ProcessStepCreate(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=255)
    sequence: int | None = 10
    description: str | None = None
    is_outsourced: ProcessOutsourcing = ProcessOutsourcing.NO
    equipment: list[EquipmentCreate] = Field(default_factory=list)
    input_output_flows: list[InputOutputFlowCreate] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")


class ProcessStepResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    assessment_id: UUID
    name: str
    sequence: int | None = None
    description: str | None = None
    is_outsourced: ProcessOutsourcing
    created_at: datetime
    updated_at: datetime
    equipment: list[EquipmentResponse] = Field(default_factory=list)
    input_output_flows: list[InputOutputFlowResponse] = Field(default_factory=list)


class BulkProcessStepsRequest(BaseModel):
    processes: list[ProcessStepCreate] = Field(default_factory=list)


EquipmentContract = EquipmentCreate
InputOutputFlowContract = InputOutputFlowCreate
ProcessStepContract = ProcessStepCreate

