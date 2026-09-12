"""Database-backed identification orchestration."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.identification.candidate_merger import group_candidates_by_source, merge_candidates
from app.identification.checklist import build_contextual_checklist
from app.identification.ml_adapter import MLAdapter
from app.identification.rule_engine import RuleEngine
from app.persistence.models import (
    Assessment,
    ActivityRecord,
    IdentificationRun,
    ProcessStep,
    SourceCandidate,
    SourceInventoryItem,
)

ROOT = Path(__file__).resolve().parents[4]


def _jsonable(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "value"):
        return _jsonable(value.value)
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


def _uuid_or_none(value: Any) -> UUID | None:
    if value is None or value == "":
        return None
    return value if isinstance(value, UUID) else UUID(str(value))


class IdentificationOrchestrator:
    def __init__(self, db: AsyncSession, ml_adapter: MLAdapter | None = None) -> None:
        self.db = db
        self.ml_adapter = ml_adapter or MLAdapter()

    def _template(self, key: str) -> dict[str, Any]:
        for path in (ROOT / "data" / "industry-templates").glob("*.json"):
            document = json.loads(path.read_text(encoding="utf-8"))
            if document.get("template_id") == key:
                return document
        raise HTTPException(422, f"Unknown industry template: {key}")

    def _taxonomy(self) -> dict[str, dict[str, Any]]:
        document = json.loads(
            (ROOT / "data" / "taxonomy" / "source-types.json").read_text(encoding="utf-8")
        )
        return {item["source_type_id"]: item for item in document.get("source_types", [])}

    def _checklist(
        self,
        assessment: Assessment,
        candidates: list[dict[str, Any]],
        taxonomy: dict[str, dict[str, Any]],
        template: dict[str, Any],
        inventory: list[SourceInventoryItem] | None = None,
        activity_source_ids: set[UUID] | None = None,
    ) -> list[dict[str, Any]]:
        universal = json.loads(
            (ROOT / "data" / "industry-templates" / "universal.json").read_text(
                encoding="utf-8"
            )
        ).get("universal_source_type_ids", [])
        return build_contextual_checklist(
            assessment=assessment,
            taxonomy=taxonomy,
            universal_source_keys=universal,
            template=template,
            candidates=candidates,
            inventory=inventory or [],
            activity_source_ids=activity_source_ids or set(),
        )

    async def build_current_checklist(self, assessment_id: UUID) -> list[dict[str, Any]]:
        """Evaluate master coverage against live assessment, review and activity data."""
        assessment = await self._load_assessment(assessment_id)
        template = self._template(assessment.industry_template_key) if assessment.industry_template_key else None
        candidates = list((await self.db.execute(select(SourceCandidate).where(SourceCandidate.assessment_id == assessment_id))).scalars().all())
        inventory = list((await self.db.execute(select(SourceInventoryItem).where(SourceInventoryItem.assessment_id == assessment_id))).scalars().all())
        activity_source_ids = set(
            (await self.db.execute(
                select(ActivityRecord.source_inventory_item_id)
                .join(SourceInventoryItem)
                .where(SourceInventoryItem.assessment_id == assessment_id)
            )).scalars().all()
        )
        return self._checklist(assessment, candidates, self._taxonomy(), template or {}, inventory, activity_source_ids)

    async def _load_assessment(self, assessment_id: UUID) -> Assessment:
        statement = (
            select(Assessment)
            .where(Assessment.id == assessment_id)
            .options(
                selectinload(Assessment.process_steps).selectinload(ProcessStep.equipment),
                selectinload(Assessment.process_steps).selectinload(ProcessStep.input_output_flows),
            )
        )
        assessment = (await self.db.execute(statement)).scalar_one_or_none()
        if assessment is None:
            raise HTTPException(404, f"Assessment {assessment_id} not found")
        return assessment

    @staticmethod
    def _facts_and_snapshot(
        assessment: Assessment, template: dict[str, Any], rules: dict[str, Any]
    ) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
        facts: dict[str, list[dict[str, Any]]] = {"processes": [], "equipment": [], "flows": []}
        snapshot: dict[str, Any] = {
            "assessment": {},
            "process_steps": [],
            "equipment": [],
            "flows": [],
            "template": {"id": template["template_id"], "version": template.get("template_version")},
            "ruleset": {"id": rules["ruleset_id"], "version": rules["ruleset_version"]},
        }
        fields = (
            "id", "industry_name", "industry_code", "industry_template_key",
            "industry_template_version", "reporting_period_start", "reporting_period_end",
            "organizational_boundary", "operational_boundary",
        )
        snapshot["assessment"] = {
            field: _jsonable(getattr(assessment, field, None)) for field in fields
        }
        for process in sorted(assessment.process_steps, key=lambda item: str(item.id)):
            process_fact = {
                "process_step_id": str(process.id),
                "name": process.name,
                "description": process.description,
                "is_outsourced": process.is_outsourced,
            }
            facts["processes"].append(process_fact)
            snapshot["process_steps"].append(process_fact)
            for equipment in sorted(process.equipment, key=lambda item: str(item.id)):
                equipment_fact = {
                    "process_step_id": str(process.id),
                    "equipment_id": str(equipment.id),
                    "name": equipment.name,
                    "equipment_type": equipment.equipment_type,
                    "fuel_type": equipment.fuel_type,
                    "energy_type": equipment.energy_type,
                }
                facts["equipment"].append(equipment_fact)
                snapshot["equipment"].append(equipment_fact)
            for flow in sorted(process.input_output_flows, key=lambda item: str(item.id)):
                flow_fact = {
                    "process_step_id": str(process.id),
                    "equipment_id": str(flow.equipment_id) if flow.equipment_id else None,
                    "direction": flow.direction,
                    "category": flow.category,
                    "item_name": flow.item_name,
                    "unit": flow.unit,
                }
                facts["flows"].append(flow_fact)
                snapshot["flows"].append(flow_fact)
        return facts, snapshot

    async def run(self, assessment_id: UUID, include_ml: bool = False) -> IdentificationRun:
        assessment = await self._load_assessment(assessment_id)
        if not assessment.industry_template_key:
            raise HTTPException(422, "Assessment has no industry template")
        template = self._template(assessment.industry_template_key)
        template_version = template.get("template_version")
        if assessment.industry_template_version and assessment.industry_template_version != template_version:
            raise HTTPException(422, "Industry template version mismatch")
        rules = json.loads(
            (ROOT / "data" / "rules" / "source-identification-rules.json").read_text(encoding="utf-8")
        )
        facts, snapshot = self._facts_and_snapshot(assessment, template, rules)
        snapshot["include_ml"] = include_ml
        input_hash = hashlib.sha256(
            json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        existing_statement = (
            select(IdentificationRun)
            .where(
                IdentificationRun.assessment_id == assessment_id,
                IdentificationRun.input_hash == input_hash,
                IdentificationRun.status == "COMPLETED",
            )
            .order_by(IdentificationRun.started_at.desc())
            .limit(1)
        )
        existing = (await self.db.execute(existing_statement)).scalar_one_or_none()
        if existing is not None:
            return existing

        run = IdentificationRun(
            assessment_id=assessment_id,
            engine_type="RULE_TEMPLATE_ML" if include_ml else "RULE_AND_TEMPLATE",
            engine_version=rules["ruleset_version"],
            input_hash=input_hash,
            status="RUNNING",
        )
        self.db.add(run)
        await self.db.flush()

        taxonomy = self._taxonomy()
        candidates: list[dict[str, Any]] = []
        template_processes = {p.get("process_id"): p for p in template.get("processes", [])}
        for process in assessment.process_steps:
            process_name = process.name.lower()
            template_process = next(
                (
                    item for item in template_processes.values()
                    if process_name == item.get("name", "").lower()
                    or process_name in item.get("name", "").lower()
                    or item.get("name", "").lower() in process_name
                ),
                None,
            )
            if template_process is None:
                continue
            for source_key in template_process.get("suggested_source_type_ids", []):
                source = taxonomy.get(source_key)
                if source is None:
                    continue
                candidates.append(
                    {
                        "process_step_id": process.id,
                        "source_key": source_key,
                        "source_name": source["name"],
                        "source_category": source.get("family_id"),
                        "suggested_scope": source.get("default_scope"),
                        "origin": "TEMPLATE",
                        "reason": f"Industry template suggests {source['name']} for process '{process.name}'.",
                        "evidence_json": {
                            "template_id": template["template_id"],
                            "template_version": template_version,
                            "process_id": template_process.get("process_id"),
                        },
                    }
                )
        candidates.extend(RuleEngine().identify(facts))
        ml_status = "DISABLED"
        ml_error: str | None = None
        if include_ml:
            try:
                candidates.extend({**candidate, "origin": "ML"} for candidate in await self.ml_adapter.identify(facts))
                ml_status = "COMPLETED"
            except Exception as exc:  # noqa: BLE001 - ML is non-fatal
                ml_status = "UNAVAILABLE"
                ml_error = str(exc)

        merged = group_candidates_by_source(merge_candidates(candidates))
        for candidate in merged:
            suggested_scope = candidate.get("suggested_scope")
            evidence_json = dict(candidate.get("evidence_json") or {})
            if suggested_scope and len(str(suggested_scope)) > 20:
                evidence_json["scope_review_status"] = suggested_scope
                suggested_scope = taxonomy.get(candidate["source_key"], {}).get(
                    "default_scope"
                )
            self.db.add(
                SourceCandidate(
                    assessment_id=assessment_id,
                    identification_run_id=run.id,
                    process_step_id=_uuid_or_none(candidate.get("process_step_id")),
                    equipment_id=_uuid_or_none(candidate.get("equipment_id")),
                    source_key=candidate["source_key"],
                    source_name=candidate["source_name"],
                    source_category=candidate.get("source_category"),
                    suggested_scope=suggested_scope,
                    origin=candidate["origin"],
                    reason=candidate.get("reason"),
                    confidence=candidate.get("confidence"),
                    status=candidate["status"],
                    evidence_json=evidence_json,
                )
            )

        origin_sets = [set(item["evidence_json"].get("origins", [])) for item in merged]
        counts = {
            origin: sum(origin in origins for origins in origin_sets)
            for origin in ("TEMPLATE", "RULE", "ML", "CHECKLIST", "USER")
        }
        run.status = "COMPLETED"
        run.completed_at = datetime.now(UTC)
        run.output_json = {
            "ruleset_id": rules["ruleset_id"],
            "ruleset_version": rules["ruleset_version"],
            "template_id": template["template_id"],
            "template_version": template_version,
            "input_hash": input_hash,
            "candidate_count": len(merged),
            "template_candidate_count": counts["TEMPLATE"],
            "rule_candidate_count": counts["RULE"],
            "ml_candidate_count": counts["ML"],
            "checklist_candidate_count": counts["CHECKLIST"],
            "user_candidate_count": counts["USER"],
            "ml_status": ml_status,
            "checklist": self._checklist(assessment, merged, taxonomy, template),
            **({"ml_error": ml_error} if ml_error else {}),
        }
        await self.db.flush()
        return run
