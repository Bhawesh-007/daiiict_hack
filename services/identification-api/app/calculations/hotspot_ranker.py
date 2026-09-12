"""Rank quantified emission sources without hiding completeness gaps."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from decimal import Decimal
from typing import Any


def _decimal(value: Any) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def rank_hotspots(
    source_totals: Iterable[Mapping[str, Any]],
    *,
    unquantified_source_ids: Iterable[Any] = (),
    top_n: int = 3,
    threshold_percentage: Decimal | float | str = Decimal(20),
) -> dict[str, Any]:
    """Rank source totals and preserve uncertainty about unquantified sources."""
    if top_n < 1:
        raise ValueError("top_n must be at least 1")
    threshold = _decimal(threshold_percentage)
    if threshold < 0 or threshold > 100:
        raise ValueError("threshold_percentage must be between 0 and 100")
    prepared = []
    for source in source_totals:
        emissions = _decimal(source.get("emissions_kgco2e", 0))
        percentage = _decimal(source.get("percentage", 0))
        if emissions < 0:
            raise ValueError("source emissions cannot be negative")
        if percentage < 0 or percentage > 100:
            raise ValueError("source percentage must be between 0 and 100")
        prepared.append(
            {**source, "emissions_kgco2e": emissions, "percentage": percentage}
        )
    prepared.sort(
        key=lambda source: (-source["emissions_kgco2e"], str(source.get("key", "")))
    )
    ranked = [
        {
            **source,
            "rank": index,
            "is_top_source": index <= top_n,
            "exceeds_threshold": source["percentage"] >= threshold,
        }
        for index, source in enumerate(prepared, start=1)
    ]
    unresolved = sorted({str(source_id) for source_id in unquantified_source_ids})
    return {
        "ranking_label": "top quantified emission sources",
        "ranked_sources": ranked,
        "top_sources": ranked[:top_n],
        "threshold_percentage": threshold,
        "threshold_source_count": sum(item["exceeds_threshold"] for item in ranked),
        "unquantified_source_ids": unresolved,
        "ranking_status": "PROVISIONAL" if unresolved else "COMPLETE",
        "warning": (
            "Unquantified sources may change this ranking." if unresolved else None
        ),
    }


def rank_aggregation(
    aggregation: Mapping[str, Any],
    *,
    top_n: int = 3,
    threshold_percentage: Decimal | float | str = Decimal(20),
) -> dict[str, Any]:
    """Rank the by-source section returned by aggregate_calculation_lines."""
    return rank_hotspots(
        aggregation.get("by_source", []),
        unquantified_source_ids=aggregation.get("unquantified_source_ids", []),
        top_n=top_n,
        threshold_percentage=threshold_percentage,
    )
