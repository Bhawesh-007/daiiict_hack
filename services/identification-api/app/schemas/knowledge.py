"""Lookup helpers for validating references to JSON knowledge assets."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
UNITS_FILE = PROJECT_ROOT / "data" / "taxonomy" / "units.json"
SOURCE_TYPES_FILE = PROJECT_ROOT / "data" / "taxonomy" / "source-types.json"
UNIVERSAL_TEMPLATE_FILE = (
    PROJECT_ROOT / "data" / "industry-templates" / "universal.json"
)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def supported_unit_ids() -> frozenset[str]:
    document = _read_json(UNITS_FILE)
    if "dimensions" in document:
        return frozenset(
            unit["unit_id"]
            for dimension in document["dimensions"]
            for unit in dimension.get("units", [])
        )
    return frozenset(unit["unit_id"] for unit in document.get("units", []))


@lru_cache(maxsize=1)
def source_type_ids() -> frozenset[str]:
    document = _read_json(SOURCE_TYPES_FILE)
    return frozenset(
        item.get("source_type_id", item.get("source_key"))
        for item in document.get("source_types", [])
    )


@lru_cache(maxsize=1)
def universal_source_type_ids() -> frozenset[str]:
    document = _read_json(UNIVERSAL_TEMPLATE_FILE)
    configured = document.get("universal_source_type_ids")
    if configured:
        return frozenset(configured)
    return source_type_ids()


def is_supported_unit(unit_id: str) -> bool:
    return unit_id in supported_unit_ids()


def is_known_source_type(source_key: str) -> bool:
    return source_key in source_type_ids()
