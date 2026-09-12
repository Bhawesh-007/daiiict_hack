"""Deterministic emission-factor registry resolution."""

from collections.abc import Iterable
from datetime import datetime
from typing import Any


class FactorResolutionError(ValueError):
    pass


class NoCompatibleFactorError(FactorResolutionError):
    pass


class AmbiguousFactorError(FactorResolutionError):
    pass


def _field(factor: Any, name: str, default=None):
    return (
        factor.get(name, default)
        if isinstance(factor, dict)
        else getattr(factor, name, default)
    )


def resolve_factor(
    factors: Iterable[Any],
    *,
    source_key: str,
    activity_unit: str,
    activity_date: datetime | None = None,
    geography: str | None = None,
    factor_code: str | None = None,
    factor_version: str | None = None,
) -> Any:
    """Resolve one exact compatible factor or block the calculation line."""
    matches = []
    for factor in factors:
        metadata = _field(factor, "metadata_json", {}) or {}
        if not metadata.get("active", True):
            continue
        if source_key not in metadata.get("compatible_source_type_ids", []):
            continue
        if _field(factor, "activity_unit") != activity_unit:
            continue
        if factor_code and _field(factor, "factor_code") != factor_code:
            continue
        if factor_version and _field(factor, "version") != factor_version:
            continue
        valid_from, valid_to = _field(factor, "valid_from"), _field(factor, "valid_to")
        if activity_date and (
            (valid_from and activity_date < valid_from)
            or (valid_to and activity_date > valid_to)
        ):
            continue
        factor_geography = (_field(factor, "geography") or "").upper()
        requested_geography = (geography or "").upper()
        if requested_geography and factor_geography not in {
            requested_geography,
            "GLOBAL",
            "UNSPECIFIED",
        }:
            continue
        matches.append(factor)
    if not matches:
        raise NoCompatibleFactorError(
            f"No active factor matches {source_key!r} with unit {activity_unit!r}"
        )
    if len(matches) > 1:
        raise AmbiguousFactorError(
            "Multiple compatible factors matched; select factor_code or factor_version explicitly"
        )
    return matches[0]
