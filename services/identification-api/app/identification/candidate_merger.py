"""Deterministic candidate-keying and provenance-preserving merging.

Candidate generation is intentionally allowed to produce the same source from
multiple origins.  This module turns those proposals into one stable payload
per source/process/equipment context.  It is pure Python so it can be used by
the orchestrator and tested without a database.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from copy import deepcopy
from typing import Any

_ORIGIN_ORDER = {
    "TEMPLATE": 10,
    "RULE": 20,
    "CHECKLIST": 30,
    "ML": 40,
    "USER": 50,
}
_REQUIRED_ORIGINS = frozenset(_ORIGIN_ORDER)


def _text(value: Any) -> str | None:
    """Return a stable string representation for a key component."""
    if value is None:
        return None
    if hasattr(value, "value"):
        value = value.value
    value = str(value).strip()
    return value or None


def candidate_key(candidate: Mapping[str, Any]) -> str:
    """Build the deterministic identity for a candidate.

    Source type is always required.  Process and equipment IDs are explicit
    context components; ``-`` is used for an absent component.  A value-chain
    position, when supplied, prevents upstream/downstream candidates from
    colliding while retaining the required source/process/equipment basis.
    """
    source_key = _text(candidate.get("source_key") or candidate.get("source_type_id"))
    if source_key is None:
        raise ValueError("candidate requires source_key or source_type_id")
    process_id = _text(candidate.get("process_step_id") or candidate.get("process_id"))
    equipment_id = _text(candidate.get("equipment_id"))
    value_chain_position = _text(candidate.get("value_chain_position"))
    return "|".join(
        (
            source_key,
            process_id or "-",
            equipment_id or "-",
            value_chain_position or "-",
        )
    )


def _jsonable(value: Any) -> Any:
    if hasattr(value, "value"):
        return _jsonable(value.value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return str(value)


def _stable_unique(values: Iterable[Any]) -> list[Any]:
    result: list[Any] = []
    seen: set[str] = set()
    for value in values:
        normalized = _jsonable(value)
        marker = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
        if marker not in seen:
            seen.add(marker)
            result.append(normalized)
    return result


def _origin_sort_key(origin: str) -> tuple[int, str]:
    return (_ORIGIN_ORDER.get(origin, 999), origin)


def _provenance(candidate: Mapping[str, Any], origin: str) -> dict[str, Any]:
    evidence = deepcopy(_jsonable(candidate.get("evidence_json") or {}))
    rule_id = _text(candidate.get("rule_id") or evidence.get("rule_id"))
    rule_version = _text(candidate.get("rule_version") or evidence.get("rule_version"))
    return {
        "origin": origin,
        "reason": _text(candidate.get("reason")),
        "rule_id": rule_id,
        "rule_version": rule_version,
        "evidence": evidence,
    }


def merge_candidates(candidates: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Merge candidates by deterministic context while retaining provenance.

    The returned records are persistence-ready apart from assessment/run IDs.
    ``origin`` is the highest-precedence origin for the merged record, while
    ``evidence_json`` contains all origins, reasons, rule IDs and rule versions.
    A merged record remains ``PROPOSED`` when it has one origin and becomes
    ``MERGED`` when multiple origins agree; neither status confirms a source.
    """
    groups: dict[str, list[tuple[str, Mapping[str, Any]]]] = {}
    for candidate in candidates:
        origin = _text(candidate.get("origin"))
        if origin not in _REQUIRED_ORIGINS:
            raise ValueError(f"unsupported candidate origin: {origin!r}")
        groups.setdefault(candidate_key(candidate), []).append((origin, candidate))

    merged: list[dict[str, Any]] = []
    for key in sorted(groups):
        entries = groups[key]
        entries.sort(
            key=lambda item: (
                _origin_sort_key(item[0]),
                _text(item[1].get("reason")) or "",
                json.dumps(_jsonable(item[1].get("evidence_json") or {}), sort_keys=True),
            )
        )
        origins = sorted({origin for origin, _ in entries}, key=_origin_sort_key)
        # Keep occurrences rather than set-unifying them: two identical-looking
        # triggers can still represent two pieces of evidence in the audit trail.
        provenance = [
            _provenance(candidate, origin) for origin, candidate in entries
        ]
        reasons = [
            _text(candidate.get("reason"))
            for _, candidate in entries
            if _text(candidate.get("reason"))
        ]
        rule_ids = [
            _text(candidate.get("rule_id") or (candidate.get("evidence_json") or {}).get("rule_id"))
            for _, candidate in entries
            if candidate.get("rule_id")
            or (candidate.get("evidence_json") or {}).get("rule_id")
        ]
        rule_versions = [
            _text(candidate.get("rule_version") or (candidate.get("evidence_json") or {}).get("rule_version"))
            for _, candidate in entries
            if candidate.get("rule_version")
            or (candidate.get("evidence_json") or {}).get("rule_version")
        ]
        first = entries[0][1]
        confidence_values = [
            float(candidate["confidence"])
            for _, candidate in entries
            if candidate.get("confidence") is not None
        ]
        result = {
            "source_key": _text(first.get("source_key") or first.get("source_type_id")),
            "source_name": first.get("source_name") or first.get("name") or key.split("|", 1)[0],
            "source_category": first.get("source_category"),
            "suggested_scope": first.get("suggested_scope"),
            "process_step_id": first.get("process_step_id") or first.get("process_id"),
            "equipment_id": first.get("equipment_id"),
            "origin": origins[-1],
            "status": "MERGED" if len(origins) > 1 else "PROPOSED",
            "reason": "; ".join(str(reason) for reason in reasons) or None,
            "confidence": max(confidence_values) if confidence_values else None,
            "evidence_json": {
                "candidate_key": key,
                "origins": origins,
                "reasons": reasons,
                "rule_ids": rule_ids,
                "rule_versions": rule_versions,
                "provenance": provenance,
            },
        }
        merged.append(result)

    return merged


def group_candidates_by_source(candidates: Iterable[Any]) -> list[dict[str, Any]]:
    """Collapse context-level proposals into one record per canonical source type.

    ``merge_candidates`` intentionally preserves process/equipment context for
    auditability. This second pass is the source-inventory boundary: all those
    contexts become evidence on one source record, never duplicate suggestions.
    """
    groups: dict[str, list[Any]] = {}
    for candidate in candidates:
        key = _text(candidate.get("source_key")) if isinstance(candidate, Mapping) else _text(getattr(candidate, "source_key", None))
        if key:
            groups.setdefault(key, []).append(candidate)

    grouped: list[dict[str, Any]] = []
    for source_key in sorted(groups):
        rows = groups[source_key]

        def field(row: Any, name: str, default: Any = None) -> Any:
            return row.get(name, default) if isinstance(row, Mapping) else getattr(row, name, default)

        # Prefer an active proposal as the actionable representative. Historical
        # PROMOTED/DISMISSED rows still remain in evidence but do not become the
        # row the UI asks the reviewer to act on.
        active = [row for row in rows if str(field(row, "status", "")).upper() not in {"PROMOTED", "DISMISSED"}]
        representative = (active or rows)[-1]
        evidence: list[dict[str, Any]] = []
        seen: set[str] = set()
        origins: set[str] = set()
        reasons: list[str] = []
        rule_ids: set[str] = set()
        for row in rows:
            origin = _text(field(row, "origin")) or "UNKNOWN"
            origins.add(origin)
            reason = _text(field(row, "reason"))
            marker = json.dumps({"origin": origin, "reason": reason, "process_step_id": _jsonable(field(row, "process_step_id")), "equipment_id": _jsonable(field(row, "equipment_id"))}, sort_keys=True)
            if marker in seen:
                continue
            seen.add(marker)
            if reason and reason not in reasons:
                reasons.append(reason)
            nested = field(row, "evidence_json") or {}
            for rule_id in nested.get("rule_ids", []) if isinstance(nested, Mapping) else []:
                rule_ids.add(str(rule_id))
            evidence.append({
                "candidate_id": str(field(row, "id")) if field(row, "id") else None,
                "origin": origin,
                "process_step_id": _jsonable(field(row, "process_step_id")),
                "equipment_id": _jsonable(field(row, "equipment_id")),
                "reason": reason,
                "evidence": _jsonable(nested),
            })
        grouped.append({
            "id": field(representative, "id"),
            "assessment_id": field(representative, "assessment_id"),
            "identification_run_id": field(representative, "identification_run_id"),
            "process_step_id": field(representative, "process_step_id"),
            "equipment_id": field(representative, "equipment_id"),
            "source_key": source_key,
            "source_name": field(representative, "source_name") or source_key,
            "source_category": field(representative, "source_category"),
            "suggested_scope": field(representative, "suggested_scope"),
            "origin": sorted(origins, key=lambda origin: _origin_sort_key(origin))[-1],
            "reason": "; ".join(reasons) if reasons else None,
            "confidence": max((float(field(row, "confidence")) for row in rows if field(row, "confidence") is not None), default=None),
            "status": field(representative, "status", "PROPOSED"),
            "evidence_json": {
                "grouped_by": "source_key",
                "candidate_count": len(rows),
                "active_candidate_count": len(active),
                "origins": sorted(origins, key=lambda origin: _origin_sort_key(origin)),
                "rule_ids": sorted(rule_ids),
                "evidence": evidence,
            },
        })
    return grouped


__all__ = ["candidate_key", "group_candidates_by_source", "merge_candidates"]
