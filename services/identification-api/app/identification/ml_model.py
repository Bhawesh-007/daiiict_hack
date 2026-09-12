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

