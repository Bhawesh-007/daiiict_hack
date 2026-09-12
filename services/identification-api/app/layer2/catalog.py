"""Versioned circular-intervention catalog loading."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
CATALOG_PATH = ROOT / "data" / "interventions" / "circular-interventions-v1.json"
DEMO_PROFILE_PATH = ROOT / "data" / "demo" / "layer1-final-profile.json"


def load_catalog() -> dict[str, Any]:
    document = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    if not document.get("catalog_id") or not document.get("catalog_version"):
        raise ValueError("intervention catalog requires an id and version")
    if not isinstance(document.get("interventions"), list):
        raise TypeError("intervention catalog requires an interventions list")
    return document


def load_demo_profile() -> dict[str, Any]:
    """Load the synthetic Layer 1 profile used for local Layer 2 UI testing."""
    document = json.loads(DEMO_PROFILE_PATH.read_text(encoding="utf-8"))
    if document.get("profile_status") != "FINALIZED" or document.get("synthetic_demo") is not True:
        raise ValueError("demo profile must be a synthetic finalized profile")
    return document
