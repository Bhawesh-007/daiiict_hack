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
