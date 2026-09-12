from pathlib import Path

import pytest

from app.identification.ml_adapter import MLAdapter
from app.identification.ml_model import SourceIdentificationModel

ROOT = Path(__file__).resolve().parents[4]


def test_diesel_boiler_predicts_stationary_combustion():
    model = SourceIdentificationModel(ROOT / "data/taxonomy/source-types.json")
    result = model.predict("diesel steam boiler")
    assert result and result[0]["source_key"] == "stationary_fuel_combustion"


def test_unknown_text_does_not_create_candidate():
    model = SourceIdentificationModel(ROOT / "data/taxonomy/source-types.json")
    assert model.predict("administrative meeting schedule") == []


@pytest.mark.asyncio
async def test_adapter_returns_proposed_ml_candidate():
    candidates = await MLAdapter().identify({"processes": [], "equipment": [{"process_step_id": None, "equipment_id": None, "name": "diesel boiler", "equipment_type": "boiler", "fuel_type": "diesel"}], "flows": []})
    assert candidates
    assert candidates[0]["origin"] == "ML"
    assert candidates[0]["status"] == "POTENTIAL"
    assert candidates[0]["evidence_json"]["model_version"] == "1.0.0"
