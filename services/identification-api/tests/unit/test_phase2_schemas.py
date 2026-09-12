"""Validation tests for Phase-2 contracts."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from app.schemas.checklist import ChecklistItemContract
from app.schemas.enums import CandidateOrigin, ChecklistStatus, InventoryStatus
from app.schemas.processes import (
    EquipmentContract,
    InputOutputFlowContract,
    ProcessStepContract,
)
from app.schemas.sources import (
    SourceCandidateRequest,
    SourceCandidateResponse,
    SourceInventoryContract,
)
from pydantic import ValidationError


def test_process_rejects_negative_sequence() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        ProcessStepContract(assessment_id=uuid4(), name="Frying", sequence=-1)


def test_combustion_equipment_requires_fuel() -> None:
    with pytest.raises(ValidationError, match="fuel_type is required"):
        EquipmentContract(
            process_step_id=uuid4(),
            name="Steam boiler",
            equipment_type="boiler",
        )


def test_flow_requires_process_or_equipment_and_known_unit() -> None:
    with pytest.raises(ValidationError, match="process_step_id or equipment_id"):
        InputOutputFlowContract(direction="INPUT", item_name="diesel")

    with pytest.raises(ValidationError, match="unsupported unit"):
        InputOutputFlowContract(
            process_step_id=uuid4(),
            direction="INPUT",
            item_name="diesel",
            unit="bucket",
        )


def test_rule_candidate_requires_versioned_rule_evidence() -> None:
    with pytest.raises(ValidationError, match="rule_id"):
        SourceCandidateRequest(
            assessment_id=uuid4(),
            source_key="stationary_fuel_combustion",
            source_name="Stationary fuel combustion",
            origin=CandidateOrigin.RULE,
            reason="A boiler was reported.",
        )


def test_candidate_response_accepts_reviewed_status() -> None:
    candidate = SourceCandidateResponse(
        assessment_id=uuid4(),
        source_key="stationary_fuel_combustion",
        source_name="Stationary fuel combustion",
        origin=CandidateOrigin.RULE,
        reason="A boiler was reported.",
        status="PROMOTED",
        evidence_json={"rule_id": "SRC-RULE-003", "rule_version": "1.0.0"},
    )
    assert candidate.status.value == "PROMOTED"


def test_confirmed_inventory_requires_reviewer_metadata() -> None:
    with pytest.raises(ValidationError, match="confirmed_by"):
        SourceInventoryContract(
            assessment_id=uuid4(),
            candidate_id=uuid4(),
            source_key="purchased_grid_electricity",
            source_name="Purchased grid electricity",
            status=InventoryStatus.CONFIRMED,
        )


def test_not_applicable_checklist_item_requires_reason() -> None:
    with pytest.raises(ValidationError, match="require a reason"):
        ChecklistItemContract(
            assessment_id=uuid4(),
            source_key="industrial_process_emissions",
            label="Industrial process emissions",
            status=ChecklistStatus.NOT_APPLICABLE,
            required_fields=["process_type"],
        )


def test_confirmed_inventory_accepts_reviewer_metadata() -> None:
    item = SourceInventoryContract(
        assessment_id=uuid4(),
        candidate_id=uuid4(),
        source_key="purchased_grid_electricity",
        source_name="Purchased grid electricity",
        status=InventoryStatus.CONFIRMED,
        confirmed_by="facility-manager@example.com",
        confirmed_at=datetime.now(timezone.utc),
    )
    assert item.status is InventoryStatus.CONFIRMED
