"""Read-only endpoints for versioned JSON knowledge assets."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/api", tags=["knowledge"])
PROJECT_ROOT = Path(__file__).resolve().parents[4]
TEMPLATE_DIRECTORY = PROJECT_ROOT / "data" / "industry-templates"
SOURCE_TYPES_FILE = PROJECT_ROOT / "data" / "taxonomy" / "source-types.json"


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Knowledge file cannot be read: {path.name}",
        ) from exc


@router.get("/industry-templates")
async def list_industry_templates() -> list[dict]:
    templates = [_read_json(path) for path in sorted(TEMPLATE_DIRECTORY.glob("*.json"))]
    return [
        {
            "template_id": item["template_id"],
            "template_version": item["template_version"],
            "industry_code": item["industry_code"],
            "name": item["name"],
            "status": item["status"],
        }
        for item in templates
    ]


@router.get("/industry-templates/{template_id}")
async def read_industry_template(template_id: str) -> dict:
    for path in sorted(TEMPLATE_DIRECTORY.glob("*.json")):
        template = _read_json(path)
        if template.get("template_id") == template_id:
            return template
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Industry template {template_id!r} was not found",
    )


@router.get("/source-types")
async def list_source_types() -> list[dict]:
    return _read_json(SOURCE_TYPES_FILE)["source_types"]


@router.get("/source-types/{source_type_id}")
async def read_source_type(source_type_id: str) -> dict:
    source_types = _read_json(SOURCE_TYPES_FILE)["source_types"]
    for source_type in source_types:
        if source_type.get("source_type_id") == source_type_id:
            return source_type
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Source type {source_type_id!r} was not found",
    )
