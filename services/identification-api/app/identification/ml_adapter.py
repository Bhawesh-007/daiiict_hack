"""Validated adapter around the local identification model."""

from pathlib import Path
from typing import Any

from app.identification.ml_model import (
    MODEL_ID,
    MODEL_VERSION,
    SourceIdentificationModel,
)
from app.schemas.ml import (
    MLFact,
    MLIdentificationRequest,
    MLPersistenceCandidate,
    MLSuggestion,
)

ROOT = Path(__file__).resolve().parents[4]


class MLUnavailableError(RuntimeError):
    """Raised when the optional identification model cannot run."""


class MLAdapter:
    def __init__(self, model: SourceIdentificationModel | None = None) -> None:
        try:
            self.model = model or SourceIdentificationModel(
                ROOT / "data/taxonomy/source-types.json"
            )
        except (OSError, ValueError) as exc:
            raise MLUnavailableError(
                "Identification model could not be loaded"
            ) from exc

    @staticmethod
    def _contract(facts: dict[str, list[dict[str, Any]]]) -> list[MLFact]:
        fact_types = {"processes": "process", "equipment": "equipment", "flows": "flow"}
        records: list[MLFact] = []
        for bucket, values in facts.items():
            fact_type = fact_types.get(bucket)
            if fact_type is None:
                continue
            for value in values:
                text = " ".join(
                    str(value.get(key) or "")
                    for key in (
                        "name",
                        "description",
                        "equipment_type",
                        "fuel_type",
                        "energy_type",
                        "category",
                        "item_name",
                        "direction",
                    )
                ).strip()
                if text:
                    records.append(
                        MLFact(
                            fact_type=fact_type,
                            text=text,
                            process_step_id=value.get("process_step_id"),
                            equipment_id=value.get("equipment_id"),
                        )
                    )
        return records

    @staticmethod
    def _questions(source_key: str) -> list[str]:
        return {
            "refrigerant_fugitive_emissions": [
                "Which refrigerant is used?",
                "How much refrigerant was refilled?",
                "Was leakage detected?",
            ],
            "stationary_fuel_combustion": [
                "Which fuel is consumed?",
                "How much fuel was consumed during the reporting period?",
            ],
            "purchased_grid_electricity": [
                "How much electricity was purchased?",
                "Are electricity bills or meter records available?",
            ],
        }.get(
            source_key,
            ["What activity quantity and unit are available for this source?"],
        )

    async def identify_request(
        self, request: MLIdentificationRequest
    ) -> list[MLSuggestion]:
        suggestions: list[MLSuggestion] = []
        for fact in request.facts:
            for prediction in self.model.predict(fact.text):
                source = self.model.sources[prediction["source_key"]]
                suggestions.append(
                    MLSuggestion(
                        source_key=prediction["source_key"],
                        confidence=prediction["confidence"],
                        reason=f"The local identification model matched reported {fact.fact_type} text to {source['name']}.",
                        follow_up_questions=self._questions(prediction["source_key"]),
                        model_id=MODEL_ID,
                        model_version=MODEL_VERSION,
                        process_step_id=fact.process_step_id,
                        equipment_id=fact.equipment_id,
                    )
                )
        return suggestions

    async def extract_entities(
        self, facts: dict[str, list[dict[str, Any]]]
    ) -> list[dict[str, Any]]:
        """Extract structured entities while retaining source context."""
        entities: list[dict[str, Any]] = []
        for fact in self._contract(facts):
            for entity in self.model.extract_entities(fact.text):
                entities.append(
                    {
                        **entity,
                        "fact_type": fact.fact_type,
                        "process_step_id": fact.process_step_id,
                        "equipment_id": fact.equipment_id,
                    }
                )
        return entities

    async def identify(
        self, facts: dict[str, list[dict[str, Any]]]
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        records = self._contract(facts)
        if not records:
            return []
        entities_by_context: dict[tuple[Any, Any], list[dict[str, Any]]] = {}
        for entity in await self.extract_entities(facts):
            context = (entity.get("process_step_id"), entity.get("equipment_id"))
            entities_by_context.setdefault(context, []).append(entity)
        for suggestion in await self.identify_request(
            MLIdentificationRequest(facts=records)
        ):
            source = self.model.sources[suggestion.source_key]
            evidence = {
                "model_id": suggestion.model_id,
                "model_version": suggestion.model_version,
                "taxonomy_version": self.model.taxonomy_version,
                "follow_up_questions": suggestion.follow_up_questions,
                "entities": entities_by_context.get(
                    (suggestion.process_step_id, suggestion.equipment_id), []
                ),
            }
            candidate = MLPersistenceCandidate(
                source_key=suggestion.source_key,
                source_name=source["name"],
                source_category=source.get("family_id"),
                suggested_scope=source.get("default_scope"),
                process_step_id=suggestion.process_step_id,
                equipment_id=suggestion.equipment_id,
                origin="ML",
                status="PROPOSED",
                confidence=suggestion.confidence,
                reason=suggestion.reason,
                model_id=suggestion.model_id,
                model_version=suggestion.model_version,
                evidence_json=evidence,
            )
            candidates.append(candidate.model_dump())
        return candidates
