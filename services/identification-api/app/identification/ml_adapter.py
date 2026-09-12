"""Validated adapter around the local identification model."""

from pathlib import Path
from typing import Any

from app.identification.ml_model import (
    MODEL_ID,
    MODEL_VERSION,
    SourceIdentificationModel,
)

ROOT = Path(__file__).resolve().parents[4]


class MLUnavailableError(RuntimeError):
    """Raised when the optional identification model cannot run."""


class MLAdapter:
    def __init__(self, model: SourceIdentificationModel | None = None) -> None:
        try:
            self.model = model or SourceIdentificationModel(ROOT / "data/taxonomy/source-types.json")
        except (OSError, ValueError) as exc:
            raise MLUnavailableError("Identification model could not be loaded") from exc

    async def identify(self, facts: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for fact_type, records in facts.items():
            for record in records:
                text = " ".join(str(record.get(key) or "") for key in ("name", "description", "equipment_type", "fuel_type", "energy_type", "category", "item_name", "direction"))
                for prediction in self.model.predict(text):
                    source = self.model.sources[prediction["source_key"]]
                    candidates.append({
                        "source_key": prediction["source_key"],
                        "source_name": source["name"],
                        "source_category": source.get("family_id"),
                        "suggested_scope": source.get("default_scope"),
                        "process_step_id": record.get("process_step_id"),
                        "equipment_id": record.get("equipment_id"),
                        "origin": "ML",
                        "status": "POTENTIAL",
                        "confidence": prediction["confidence"],
                        "reason": f"The local identification model matched reported {fact_type.rstrip('s')} text to {source['name']}.",
                        "evidence_json": {"model_id": MODEL_ID, "model_version": MODEL_VERSION, "taxonomy_version": self.model.taxonomy_version, "fact_type": fact_type.rstrip("s"), "similarity_score": prediction["matched_score"], "input_text": text},
                    })
        return candidates
