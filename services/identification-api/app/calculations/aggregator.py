"""Decimal-safe emissions aggregation and contribution calculation."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from decimal import Decimal
from typing import Any


def _value(line: Any, field: str, default=None):
    return (
        line.get(field, default)
        if isinstance(line, Mapping)
        else getattr(line, field, default)
    )


def _decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _percentage(value: Decimal, total: Decimal) -> Decimal:
    return Decimal(0) if total == 0 else value * Decimal(100) / total


def _group(
    lines: list[Any], total: Decimal, id_field: str, label_field: str | None = None
) -> list[dict[str, Any]]:
    emissions: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
    labels: dict[str, str | None] = {}
    for line in lines:
        key = str(_value(line, id_field) or "UNSPECIFIED")
        emissions[key] += _decimal(_value(line, "emissions_kgco2e"))
        labels[key] = (
            str(_value(line, label_field))
            if label_field and _value(line, label_field)
            else None
        )
    return [
        {
            "key": key,
            "label": labels[key],
            "emissions_kgco2e": amount,
            "percentage": _percentage(amount, total),
        }
        for key, amount in sorted(
            emissions.items(), key=lambda item: (-item[1], item[0])
        )
    ]


def aggregate_calculation_lines(
    lines: Iterable[Any],
    *,
    unquantified_source_ids: Iterable[Any] = (),
    production_quantity: Decimal | float | str | None = None,
) -> dict[str, Any]:
    """Aggregate valid calculation lines without rounding stored results.

    Lines with ``emissions_kgco2e`` as ``None`` are unresolved and excluded from totals.
    Negative calculated emissions are rejected because they indicate invalid input for this MVP.
    """
    all_lines = list(lines)
    quantified = [
        line for line in all_lines if _value(line, "emissions_kgco2e") is not None
    ]
    if any(_decimal(_value(line, "emissions_kgco2e")) < 0 for line in quantified):
        raise ValueError("calculated emissions cannot be negative")
    unresolved = {str(value) for value in unquantified_source_ids}
    unresolved.update(
        str(_value(line, "source_inventory_item_id"))
        for line in all_lines
        if _value(line, "emissions_kgco2e") is None
        and _value(line, "source_inventory_item_id") is not None
    )
    total = sum(
        (_decimal(_value(line, "emissions_kgco2e")) for line in quantified),
        start=Decimal(0),
    )
    if unresolved:
        total_status = "PARTIAL"
    elif quantified:
        total_status = "COMPLETE"
    else:
        total_status = "EMPTY"
    intensity = None
    if production_quantity is not None:
        production = _decimal(production_quantity)
        if production <= 0:
            raise ValueError("production_quantity must be greater than zero")
        intensity = total / production
    return {
        "quantified_total_emissions_kgco2e": total,
        "total_status": total_status,
        "quantified_line_count": len(quantified),
        "unquantified_source_ids": sorted(unresolved),
        "emissions_intensity_kgco2e_per_production_unit": intensity,
        "by_source": _group(
            quantified, total, "source_inventory_item_id", "source_name"
        ),
        "by_scope": _group(quantified, total, "scope"),
        "by_category": _group(quantified, total, "source_category"),
        "by_process": _group(quantified, total, "process_step_id", "process_name"),
    }
