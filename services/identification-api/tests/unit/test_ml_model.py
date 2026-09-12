from pathlib import Path
from uuid import uuid4

import pytest

from app.identification.ml_adapter import MLAdapter
from app.identification.ml_model import SourceIdentificationModel
from app.schemas.ml import MLFact, MLIdentificationRequest, MLPersistenceCandidate

ROOT = Path(__file__).resolve().parents[4]


def test_diesel_boiler_predicts_stationary_combustion():
    model = SourceIdentificationModel(ROOT / "data/taxonomy/source-types.json")
    result = model.predict("diesel steam boiler")
    assert result and result[0]["source_key"] == "stationary_fuel_combustion"


def test_unknown_text_does_not_create_candidate():
    model = SourceIdentificationModel(ROOT / "data/taxonomy/source-types.json")
    assert model.predict("administrative meeting schedule") == []


def test_model_extracts_structured_entities():
    model = SourceIdentificationModel(ROOT / "data/taxonomy/source-types.json")
    entities = model.extract_entities(
        "Dyeing uses a diesel steam boiler and grid electricity. "
        "The cold room contains R134a. Cotton and chemicals create wastewater; "
        "a third party truck handles outsourced transport."
    )
    values = {(item["entity_type"], item["normalized_value"]) for item in entities}
    assert {"process", "equipment", "fuel", "energy", "refrigerant", "material", "wastewater", "transportation", "outsourced_activity"} <= {item["entity_type"] for item in entities}
    assert ("fuel", "diesel") in values
    assert ("refrigerant", "R134a") in values


@pytest.mark.asyncio
async def test_adapter_returns_proposed_ml_candidate():
    candidates = await MLAdapter().identify({"processes": [], "equipment": [{"process_step_id": None, "equipment_id": None, "name": "diesel boiler", "equipment_type": "boiler", "fuel_type": "diesel"}], "flows": []})
    assert candidates
    assert candidates[0]["origin"] == "ML"
    assert candidates[0]["status"] == "PROPOSED"
    assert candidates[0]["evidence_json"]["model_version"] == "1.0.0"


@pytest.mark.asyncio
async def test_refrigeration_suggestion_includes_follow_up_questions():
    facts = {
        "processes": [],
        "equipment": [{
            "process_step_id": uuid4(),
            "equipment_id": uuid4(),
            "name": "cold room",
            "equipment_type": "cold_room",
        }],
        "flows": [],
    }
    candidates = await MLAdapter().identify(facts)
    refrigerant = next(
        candidate for candidate in candidates
        if candidate["source_key"] == "refrigerant_fugitive_emissions"
    )
    questions = refrigerant["evidence_json"]["follow_up_questions"]
    assert questions == [
        "Which refrigerant is used?",
        "How much refrigerant was refilled?",
        "Was leakage detected?",
    ]


@pytest.mark.asyncio
async def test_adapter_exposes_contextual_entities():
    process_id = uuid4()
    equipment_id = uuid4()
    facts = {
        "processes": [],
        "equipment": [{
            "process_step_id": process_id,
            "equipment_id": equipment_id,
            "name": "diesel boiler",
            "equipment_type": "boiler",
            "fuel_type": "diesel",
        }],
        "flows": [],
    }
    adapter = MLAdapter()
    entities = await adapter.extract_entities(facts)
    assert {item["normalized_value"] for item in entities} >= {"boiler", "diesel"}
    candidates = await adapter.identify(facts)
    assert candidates[0]["evidence_json"]["entities"]


@pytest.mark.asyncio
async def test_strict_request_returns_expected_cold_room_suggestion():
    request = MLIdentificationRequest(
        facts=[MLFact(fact_type="equipment", text="ammonia cold room")]
    )
    suggestions = await MLAdapter().identify_request(request)
    assert suggestions[0].source_key == "refrigerant_fugitive_emissions"
    assert suggestions[0].model_id == "taxonomy-tfidf-cosine"
    assert suggestions[0].follow_up_questions == [
        "Which refrigerant is used?",
        "How much refrigerant was refilled?",
        "Was leakage detected?",
    ]


def test_strict_request_rejects_unknown_fields():
    with pytest.raises(ValueError):
        MLIdentificationRequest.model_validate(
            {"facts": [{"fact_type": "equipment", "text": "boiler", "unknown": 1}]}
        )


def test_ml_persistence_rejects_confirmed_status():
    with pytest.raises(ValueError):
        MLPersistenceCandidate.model_validate(
            {
                "source_key": "stationary_fuel_combustion",
                "source_name": "Stationary fuel combustion",
                "origin": "ML",
                "status": "CONFIRMED",
                "confidence": 0.9,
                "reason": "A diesel boiler was reported.",
                "model_id": "taxonomy-tfidf-cosine",
                "model_version": "1.0.0",
                "evidence_json": {
                    "model_id": "taxonomy-tfidf-cosine",
                    "model_version": "1.0.0",
                },
            }
        )
