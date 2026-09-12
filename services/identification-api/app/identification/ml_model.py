"""Local statistical model for emission-source candidate identification."""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

MODEL_ID = "taxonomy-tfidf-cosine"
MODEL_VERSION = "1.0.0"
TOKEN_RE = re.compile(r"[a-z][a-z0-9_]+")
STOPWORDS = {"and", "the", "for", "from", "with", "this", "that", "type", "activity", "reporting", "period"}

# Deterministic vocabulary used for structured entity extraction.  A provider
# or fine-tuned model can replace this implementation without changing the
# adapter contract.
ENTITY_PATTERNS: dict[str, tuple[tuple[str, str], ...]] = {
    "process": (("raw material receipt", "raw_material_receipt"), ("thermal processing", "thermal_processing"), ("wet processing", "wet_processing"), ("wastewater treatment", "wastewater_treatment"), ("waste treatment", "waste_treatment"), ("manufacturing", "manufacturing"), ("production", "production"), ("packaging", "packaging"), ("storage", "storage"), ("dispatch", "dispatch"), ("dyeing", "dyeing"), ("finishing", "finishing")),
    "equipment": (("steam generator", "steam_generator"), ("thermic fluid heater", "thermic_fluid_heater"), ("diesel generator", "diesel_generator"), ("refrigeration system", "refrigeration_system"), ("air conditioner", "air_conditioner"), ("cold room", "cold_room"), ("heat pump", "heat_pump"), ("boiler", "boiler"), ("furnace", "furnace"), ("oven", "oven"), ("fryer", "fryer"), ("dryer", "dryer"), ("stenter", "stenter"), ("kiln", "kiln"), ("generator", "generator"), ("chiller", "chiller"), ("chilling unit", "chilling_unit"), ("compressor", "compressor"), ("pump", "pump")),
    "fuel": (("natural gas", "natural_gas"), ("furnace oil", "furnace_oil"), ("diesel", "diesel"), ("petrol", "petrol"), ("gasoline", "petrol"), ("lpg", "lpg"), ("biomass", "biomass"), ("coal", "coal"), ("fuel oil", "fuel_oil")),
    "energy": (("purchased grid electricity", "purchased_grid_electricity"), ("grid electricity", "purchased_grid_electricity"), ("purchased electricity", "purchased_grid_electricity"), ("electricity", "electricity"), ("purchased heat", "purchased_heat"), ("purchased steam", "purchased_steam"), ("purchased cooling", "purchased_cooling"), ("solar power", "solar_power")),
    "refrigerant": (("r134a", "R134a"), ("r404a", "R404A"), ("r410a", "R410A"), ("r32", "R32"), ("r22", "R22"), ("refrigerant", "refrigerant"), ("hfc", "HFC"), ("pfc", "PFC")),
    "material": (("raw material", "raw_material"), ("packaging material", "packaging_material"), ("packaging", "packaging"), ("chemical", "chemical"), ("chemicals", "chemical"), ("steel", "steel"), ("flour", "flour"), ("milk", "milk"), ("cotton", "cotton"), ("polyester", "polyester")),
    "waste": (("solid waste", "solid_waste"), ("food waste", "food_waste"), ("hazardous waste", "hazardous_waste"), ("waste", "waste"), ("sludge", "sludge")),
    "wastewater": (("wastewater", "wastewater"), ("effluent", "effluent"), ("sewage", "sewage")),
    "transportation": (("third party transport", "third_party_transport"), ("transportation", "transportation"), ("transport", "transport"), ("logistics", "logistics"), ("freight", "freight"), ("truck", "truck"), ("vehicle", "vehicle"), ("shipping", "shipping")),
    "outsourced_activity": (("contract manufacturing", "contract_manufacturing"), ("contract processing", "contract_processing"), ("outsourced manufacturing", "outsourced_manufacturing"), ("outsourced processing", "outsourced_processing"), ("third party", "third_party_activity"), ("outsourced", "outsourced_activity")),
}
SEED_PHRASES = {
    "stationary_fuel_combustion": ["diesel boiler generator furnace oven heater burner"],
    "refrigerant_fugitive_emissions": ["cold room cold storage chiller freezer refrigeration ammonia cooling"],
    "purchased_grid_electricity": ["electricity bill grid power meter purchased electricity"],
}


def _tokens(value: Any) -> list[str]:
    text = str(value or "").lower().replace("_", " ")
    return [token for token in TOKEN_RE.findall(text) if token not in STOPWORDS]


class SourceIdentificationModel:
    """TF-IDF vector-space classifier trained from versioned taxonomy text."""

    def __init__(self, taxonomy_path: Path, threshold: float = 0.12) -> None:
        document = json.loads(taxonomy_path.read_text(encoding="utf-8"))
        self.taxonomy_version = document.get("version")
        families = {item["family_id"]: item for item in document.get("source_families", [])}
        self.sources = {item["source_type_id"]: item for item in document.get("source_types", [])}
        profiles: dict[str, list[str]] = {}
        for key, source in self.sources.items():
            family = families.get(source.get("family_id"), {})
            values = [source.get("name"), source.get("scope_rule"), family.get("name"), family.get("description")]
            values.extend(source.get("aliases", []))
            values.extend(SEED_PHRASES.get(key, []))
            profiles[key] = _tokens(" ".join(str(value or "") for value in values))
        document_frequency = Counter(token for values in profiles.values() for token in set(values))
        size = max(len(profiles), 1)
        self.idf = {token: math.log((1 + size) / (1 + count)) + 1 for token, count in document_frequency.items()}
        self.vectors = {key: self._vector(tokens) for key, tokens in profiles.items()}
        self.threshold = threshold

    def _vector(self, tokens: list[str]) -> dict[str, float]:
        counts = Counter(tokens)
        vector = {token: count * self.idf.get(token, 1.0) for token, count in counts.items()}
        norm = math.sqrt(sum(value * value for value in vector.values())) or 1.0
        return {token: value / norm for token, value in vector.items()}

    def predict(self, text: str, *, top_k: int = 1) -> list[dict[str, Any]]:
        query = self._vector(_tokens(text))
        scores = []
        for key, vector in self.vectors.items():
            score = sum(value * vector.get(token, 0.0) for token, value in query.items())
            if score >= self.threshold:
                scores.append((score, key))
        return [
            {"source_key": key, "confidence": round(min(0.99, 0.5 + score / 2), 4), "matched_score": round(score, 4)}
            for score, key in sorted(scores, reverse=True)[:top_k]
        ]

    def extract_entities(self, text: str) -> list[dict[str, Any]]:
        """Extract normalized process, equipment and activity entities."""
        text_value = str(text or "")
        lowered = text_value.lower()
        matches: list[tuple[int, str, str, str]] = []
        for entity_type, patterns in ENTITY_PATTERNS.items():
            for phrase, normalized_value in patterns:
                start = lowered.find(phrase)
                if start >= 0:
                    matches.append((start, entity_type, phrase, normalized_value))
        entities: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for start, entity_type, phrase, normalized_value in sorted(matches):
            identity = (entity_type, normalized_value)
            if identity in seen:
                continue
            seen.add(identity)
            entities.append({
                "entity_type": entity_type,
                "value": phrase,
                "normalized_value": normalized_value,
                "confidence": 0.95,
                "evidence_text": text_value[max(0, start - 40): start + len(phrase) + 40].strip(),
                "model_id": MODEL_ID,
                "model_version": MODEL_VERSION,
            })
        return entities
