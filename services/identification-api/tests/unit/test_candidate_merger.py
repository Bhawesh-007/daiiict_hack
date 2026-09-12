from random import Random

import pytest

from app.identification.candidate_merger import candidate_key, merge_candidates


def _candidate(origin: str, reason: str, rule_id: str | None = None) -> dict:
    evidence = {"rule_id": rule_id, "rule_version": "1.0.0"} if rule_id else {}
    return {
        "source_key": "stationary_fuel_combustion",
        "source_name": "Stationary fuel combustion",
        "source_category": "stationary_combustion",
        "suggested_scope": "SCOPE_1",
        "process_step_id": "process-1",
        "equipment_id": "equipment-1",
        "origin": origin,
        "reason": reason,
        "rule_id": rule_id,
        "rule_version": "1.0.0" if rule_id else None,
        "evidence_json": evidence,
    }


def test_candidate_key_uses_source_process_and_equipment_context() -> None:
    first = _candidate("TEMPLATE", "The template suggests a boiler.")
    second = {**first, "equipment_id": "equipment-2"}

    assert candidate_key(first) == (
        "stationary_fuel_combustion|process-1|equipment-1|-"
    )
    assert candidate_key(first) != candidate_key(second)


def test_merge_preserves_all_origins_reasons_and_rule_versions() -> None:
    candidates = [
        _candidate("TEMPLATE", "The template suggests a boiler."),
        _candidate("RULE", "A boiler uses diesel.", "SRC-RULE-003"),
        _candidate("CHECKLIST", "Stationary combustion was reviewed."),
        _candidate("USER", "The facility confirmed the boiler."),
    ]

    merged = merge_candidates(candidates)

    assert len(merged) == 1
    result = merged[0]
    assert result["status"] == "MERGED"
    assert result["origin"] == "USER"
    assert result["evidence_json"]["origins"] == [
        "TEMPLATE",
        "RULE",
        "CHECKLIST",
        "USER",
    ]
    assert len(result["evidence_json"]["provenance"]) == 4
    assert result["evidence_json"]["rule_ids"] == ["SRC-RULE-003"]
    assert result["evidence_json"]["rule_versions"] == ["1.0.0"]
    assert all(reason in result["reason"] for reason in (
        "The template suggests a boiler.",
        "A boiler uses diesel.",
        "Stationary combustion was reviewed.",
        "The facility confirmed the boiler.",
    ))


def test_merge_is_deterministic_and_does_not_merge_different_contexts() -> None:
    candidates = [
        _candidate("RULE", "Rule reason one.", "RULE-1"),
        _candidate("RULE", "Rule reason two.", "RULE-2"),
        {**_candidate("TEMPLATE", "Other equipment."), "equipment_id": "equipment-2"},
    ]
    shuffled = list(candidates)
    Random(42).shuffle(shuffled)

    assert merge_candidates(candidates) == merge_candidates(shuffled)
    assert len(merge_candidates(candidates)) == 2
    assert merge_candidates(candidates)[0]["evidence_json"]["rule_ids"] == [
        "RULE-1",
        "RULE-2",
    ]


def test_merge_rejects_missing_source_type() -> None:
    with pytest.raises(ValueError, match="source_key"):
        merge_candidates([{"origin": "RULE", "reason": "missing source"}])
