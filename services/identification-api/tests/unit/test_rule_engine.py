"""Tests for deterministic rule evaluation."""

from app.identification.rule_engine import RuleEngine


def test_rule_engine_identifies_explained_potential_candidates() -> None:
    engine = RuleEngine()
    candidates = engine.identify(
        {
            "equipment": [
                {
                    "process_step_id": "process-1",
                    "equipment_id": "equipment-1",
                    "equipment_type": "boiler",
                    "fuel_type": "diesel",
                },
                {
                    "process_step_id": "process-2",
                    "equipment_id": "equipment-2",
                    "equipment_type": "cold_room",
                    "contained_gases": ["refrigerant"],
                },
            ],
            "flows": [
                {
                    "process_step_id": "process-2",
                    "category": "energy",
                    "item_name": "purchased_grid_electricity",
                    "direction": "INPUT",
                }
            ],
        }
    )

    source_keys = {candidate["source_key"] for candidate in candidates}
    assert source_keys == {
        "stationary_fuel_combustion",
        "refrigerant_fugitive_emissions",
        "purchased_grid_electricity",
    }
    for candidate in candidates:
        assert candidate["status"] == "POTENTIAL"
        assert candidate["persistence_status"] == "PROPOSED"
        assert candidate["origin"] == "RULE"
        assert candidate["rule_id"].startswith("SRC-RULE-")
        assert candidate["rule_version"] == "1.0.0"
        assert candidate["reason"]
        assert candidate["evidence_json"]["rule_id"] == candidate["rule_id"]
        assert candidate["evidence_json"]["rule_version"] == candidate["rule_version"]


def test_rule_engine_does_not_guess_from_unrelated_facts() -> None:
    engine = RuleEngine()

    candidates = engine.identify(
        [{"fact_type": "equipment", "equipment_type": "manual_table"}]
    )

    assert candidates == []


def test_rule_engine_is_deterministic_and_renders_values() -> None:
    engine = RuleEngine()
    facts = [
        {
            "fact_type": "equipment",
            "equipment_type": "boiler",
            "fuel_type": "diesel",
        }
    ]

    first = engine.identify(facts)
    second = engine.identify(facts)

    assert first == second
    assert first[0]["reason"] == "boiler is reported with diesel as a fuel input."
    assert first[0]["follow_up_questions"]

