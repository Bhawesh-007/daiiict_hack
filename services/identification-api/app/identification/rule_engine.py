"""Deterministic, explanation-first source identification rule engine.

The engine intentionally has no database or ML dependency. It consumes
normalized process, equipment and flow facts and returns candidate payloads
that can later be persisted as ``SourceCandidate`` rows. A returned candidate
is always a POTENTIAL source; only the review workflow may confirm it.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.identification.candidate_merger import candidate_key

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_RULES_PATH = (
    PROJECT_ROOT / "data" / "rules" / "source-identification-rules.json"
)
DEFAULT_SOURCE_TYPES_PATH = PROJECT_ROOT / "data" / "taxonomy" / "source-types.json"

_PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z0-9_.-]+)\s*\}\}")


class RuleEngineConfigurationError(ValueError):
    """Raised when the rules or source taxonomy cannot be used safely."""


@dataclass(frozen=True)
class _Fact:
    fact_type: str
    values: Mapping[str, Any]
    process_step_id: Any = None
    equipment_id: Any = None


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuleEngineConfigurationError(
            f"Cannot read knowledge file: {path}"
        ) from exc


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "yes", "y", "1"}


def _is_present(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def _contains_any(actual: Any, expected: list[Any]) -> bool:
    actual_values = actual if isinstance(actual, (list, tuple, set)) else [actual]
    actual_text = {str(value).strip().lower() for value in actual_values}
    return any(str(value).strip().lower() in actual_text for value in expected)


def _condition_matches(condition: Mapping[str, Any], values: Mapping[str, Any]) -> bool:
    field = condition.get("field")
    operator = condition.get("operator")
    actual = values.get(field)
    expected = condition.get("value")

    if operator == "PRESENT":
        return _is_present(actual)
    if operator == "TRUE":
        return _as_bool(actual)
    if operator == "EQUALS":
        return actual == expected
    if operator == "IN":
        return actual in (expected or [])
    if operator == "CONTAINS_ANY":
        return _contains_any(actual, expected or [])
    raise RuleEngineConfigurationError(f"Unsupported rule operator: {operator}")


def _display_value(value: Any) -> str:
    if isinstance(value, (list, tuple, set)):
        return ", ".join(str(item) for item in value)
    if value is None:
        return "unknown"
    return str(value)


def _render(template: str, values: Mapping[str, Any]) -> str:
    return _PLACEHOLDER.sub(
        lambda match: _display_value(values.get(match.group(1))),
        template,
    )


def _context_value(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _fact_type_for_flow(flow: Mapping[str, Any]) -> str:
    explicit = flow.get("fact_type")
    if explicit:
        return str(explicit)
    category = str(flow.get("category") or "").strip().lower()
    item_name = str(flow.get("item_name") or "").strip().lower()
    if category in {"energy", "electricity", "fuel", "heat", "steam", "cooling"}:
        return "energy_input"
    if category in {"material", "materials", "chemical", "packaging", "raw_material"}:
        return "material_input"
    if category in {"transport", "transportation", "distribution"}:
        return "transport_activity"
    if category in {"wastewater", "effluent"} or "wastewater" in item_name:
        return "wastewater_stream"
    if category in {"waste", "solid_waste", "sludge"}:
        return "waste_stream"
    return "flow"


def normalize_facts(
    data: Iterable[Mapping[str, Any]] | Mapping[str, Any],
) -> list[_Fact]:
    """Normalize either a fact list or an assessment mapping into rule facts.

    A mapping may contain ``processes``, ``equipment`` and ``flows`` arrays.
    A fact list must provide ``fact_type`` and may nest attributes under
    ``values`` or ``attributes``. IDs are retained as context for candidates.
    """
    if isinstance(data, Mapping):
        raw_facts: list[tuple[str, Mapping[str, Any]]] = []
        raw_facts.extend(("process", item) for item in data.get("processes", []))
        raw_facts.extend(("equipment", item) for item in data.get("equipment", []))
        raw_facts.extend(("flow", item) for item in data.get("flows", []))
    else:
        raw_facts = [
            (str(item.get("fact_type") or item.get("type") or ""), item)
            for item in data
        ]

    facts: list[_Fact] = []
    for source_type, raw in raw_facts:
        if not source_type:
            raise ValueError("Every normalized fact requires fact_type")
        values = dict(raw.get("values") or raw.get("attributes") or {})
        values.update(
            {
                key: value
                for key, value in raw.items()
                if key not in {"values", "attributes"}
            }
        )
        fact_type = source_type
        if fact_type == "flow":
            fact_type = _fact_type_for_flow(values)
            if fact_type == "energy_input":
                values.setdefault("energy_type", values.get("item_name"))
            elif fact_type == "material_input":
                values.setdefault("material_type", values.get("item_name"))
            if values.get("direction") == "INPUT" and fact_type == "energy_input":
                values.setdefault("consumed_by_facility", True)
            if values.get("purchased") is None and values.get("direction") == "INPUT":
                values.setdefault("purchased", True)
        facts.append(
            _Fact(
                fact_type=fact_type,
                values=values,
                process_step_id=raw.get("process_step_id") or raw.get("process_id"),
                equipment_id=raw.get("equipment_id"),
            )
        )
    return facts


class RuleEngine:
    """Evaluate the versioned JSON rules deterministically."""

    engine_type = "RULE"

    def __init__(
        self,
        rules_path: Path = DEFAULT_RULES_PATH,
        source_types_path: Path = DEFAULT_SOURCE_TYPES_PATH,
    ) -> None:
        self.rules_document = _read_json(rules_path)
        self.source_types_document = _read_json(source_types_path)
        self.ruleset_version = self.rules_document.get("ruleset_version", "unknown")
        self.rules = [
            rule
            for rule in self.rules_document.get("rules", [])
            if rule.get("active", True)
        ]
        self.source_types = {
            item.get("source_type_id", item.get("source_key")): item
            for item in self.source_types_document.get("source_types", [])
        }
        self._validate_configuration()

    def _validate_configuration(self) -> None:
        if not self.rules:
            raise RuleEngineConfigurationError("The active ruleset is empty")
        for rule in self.rules:
            suggestion = rule.get("suggestion") or {}
            source_key = suggestion.get("source_type_id")
            if not source_key or source_key not in self.source_types:
                raise RuleEngineConfigurationError(
                    f"Rule {rule.get('rule_id')} references unknown source type {source_key!r}"
                )
            if rule.get("match") not in {"ALL", "ANY"}:
                raise RuleEngineConfigurationError(
                    f"Rule {rule.get('rule_id')} must use match ALL or ANY"
                )
            for condition in rule.get("conditions", []):
                if condition.get("operator") not in {
                    "EQUALS",
                    "IN",
                    "PRESENT",
                    "TRUE",
                    "CONTAINS_ANY",
                }:
                    raise RuleEngineConfigurationError(
                        f"Rule {rule.get('rule_id')} has an unsupported operator"
                    )

    def identify(
        self,
        data: Iterable[Mapping[str, Any]] | Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        """Return only explained POTENTIAL candidates for matching facts."""
        facts = normalize_facts(data)
        candidates: list[dict[str, Any]] = []

        for fact in facts:
            for rule in sorted(
                self.rules, key=lambda item: (-item.get("priority", 0), item["rule_id"])
            ):
                if rule.get("fact_type") != fact.fact_type:
                    continue
                conditions = rule.get("conditions", [])
                matches = [
                    _condition_matches(condition, fact.values)
                    for condition in conditions
                ]
                rule_matches = (
                    all(matches) if rule.get("match") == "ALL" else any(matches)
                )
                if not rule_matches:
                    continue

                suggestion = rule["suggestion"]
                source_key = suggestion["source_type_id"]
                source = self.source_types[source_key]
                rendered_reason = _render(
                    suggestion.get("reason", "Rule matched."), fact.values
                )
                follow_up_questions = [
                    _render(question, fact.values)
                    for question in rule.get("follow_up_questions", [])
                ]
                process_id = _context_value(fact.process_step_id)
                equipment_id = _context_value(fact.equipment_id)
                generated_candidate = {
                    "source_key": source_key,
                    "process_step_id": process_id,
                    "equipment_id": equipment_id,
                    "value_chain_position": fact.values.get("value_chain_position"),
                }
                candidates.append(
                    {
                        "candidate_key": candidate_key(generated_candidate),
                        "source_key": source_key,
                        "source_name": source.get("name", source_key),
                        "source_category": source.get("family_id"),
                        "suggested_scope": suggestion.get("provisional_scope"),
                        "origin": "RULE",
                        "status": "POTENTIAL",
                        "persistence_status": "PROPOSED",
                        "reason": rendered_reason,
                        "confidence": rule.get("confidence"),
                        "process_step_id": process_id,
                        "equipment_id": equipment_id,
                        "rule_id": rule["rule_id"],
                        "rule_version": rule.get("version", self.ruleset_version),
                        "follow_up_questions": follow_up_questions,
                        "evidence_json": {
                            "rule_id": rule["rule_id"],
                            "rule_version": rule.get("version", self.ruleset_version),
                            "ruleset_version": self.ruleset_version,
                            "fact_type": fact.fact_type,
                            "matched_conditions": [
                                {
                                    "field": condition["field"],
                                    "operator": condition["operator"],
                                    "value": fact.values.get(condition["field"]),
                                }
                                for condition, matched in zip(
                                    conditions, matches, strict=True
                                )
                                if matched
                            ],
                            "follow_up_questions": follow_up_questions,
                        },
                    }
                )
        return candidates

    evaluate = identify
