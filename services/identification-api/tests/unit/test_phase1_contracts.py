"""Contract checks that do not require a running database."""

import json
from pathlib import Path

import pytest
from app.api.knowledge import read_industry_template, read_source_type
from app.main import app
from app.schemas.assessments import AssessmentCreateRequest
from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[4]
SAMPLE_ASSESSMENT = PROJECT_ROOT / "data" / "seed" / "sample-assessment.json"


def test_sample_assessment_matches_request_contract() -> None:
    payload = json.loads(SAMPLE_ASSESSMENT.read_text(encoding="utf-8"))
    request = AssessmentCreateRequest.model_validate(payload)

    assert request.assessment.industry_template_key == "industry-food-processing-v1"
    assert request.assessment.facility_id == request.facility.id
    assert request.facility.company_id == request.company.id
    assert request.products[0].quantity is not None


def test_request_rejects_mismatched_facility_reference() -> None:
    payload = json.loads(SAMPLE_ASSESSMENT.read_text(encoding="utf-8"))
    payload["assessment"]["facility_id"] = "20000000-0000-4000-8000-000000000002"

    with pytest.raises(ValidationError, match="assessment.facility_id"):
        AssessmentCreateRequest.model_validate(payload)


def test_business_constraints_are_optional_layer1_input() -> None:
    payload = json.loads(SAMPLE_ASSESSMENT.read_text(encoding="utf-8"))
    payload["assessment"]["business_constraints"] = {
        "budget": {"amount": "250000", "currency": "INR"},
        "operational_constraints": ["No production shutdown longer than 8 hours"],
        "target_payback_months": 24,
    }

    request = AssessmentCreateRequest.model_validate(payload)

    assert request.assessment.business_constraints["target_payback_months"] == 24


@pytest.mark.asyncio
async def test_knowledge_endpoints_read_template_and_source_type() -> None:
    template = await read_industry_template("industry-food-processing-v1")
    source_type = await read_source_type("purchased_grid_electricity")

    assert template["template_id"] == "industry-food-processing-v1"
    assert source_type["source_type_id"] == "purchased_grid_electricity"


def test_openapi_exposes_phase_one_routes() -> None:
    paths = app.openapi()["paths"]

    assert "/api/assessments" in paths
    assert "/api/assessments/{assessment_id}" in paths
    assert "/api/industry-templates/{template_id}" in paths
    assert "/api/source-types/{source_type_id}" in paths
    assert "/api/assessments/{assessment_id}/finalize" in paths
    assert "/api/assessments/{assessment_id}/latest-final-profile" in paths
    assert "/api/final-profiles/{profile_id}" in paths


def test_shared_layer_one_contracts_are_present_and_versioned() -> None:
    contracts = PROJECT_ROOT / "packages" / "contracts"
    for filename, required_id in (
        ("assessment.schema.json", "assessment-v1"),
        ("source.schema.json", "source-v1"),
        ("calculation.schema.json", "calculation-v1"),
        ("final-profile.schema.json", "layer1-final-profile-v1"),
    ):
        document = json.loads((contracts / filename).read_text(encoding="utf-8"))
        assert document["$id"].endswith(required_id + ".json")
        assert document["type"] == "object"
        assert document["required"]
