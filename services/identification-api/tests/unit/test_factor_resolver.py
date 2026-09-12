from datetime import UTC, datetime

import pytest

from app.calculations.factor_resolver import (
    AmbiguousFactorError,
    NoCompatibleFactorError,
    resolve_factor,
)


def factor(code="EF-1", unit="kWh", active=True):
    return {
        "factor_code": code,
        "version": "1.0.0",
        "activity_unit": unit,
        "geography": "India",
        "valid_from": datetime(2025, 4, 1, tzinfo=UTC),
        "valid_to": datetime(2026, 3, 31, tzinfo=UTC),
        "metadata_json": {
            "active": active,
            "compatible_source_type_ids": ["purchased_grid_electricity"],
        },
    }


def test_resolves_exact_source_unit_date_and_geography():
    selected = resolve_factor(
        [factor()],
        source_key="purchased_grid_electricity",
        activity_unit="kWh",
        activity_date=datetime(2025, 9, 1, tzinfo=UTC),
        geography="India",
    )
    assert selected["factor_code"] == "EF-1"


def test_does_not_convert_units_or_invent_factor():
    with pytest.raises(NoCompatibleFactorError):
        resolve_factor(
            [factor()],
            source_key="purchased_grid_electricity",
            activity_unit="MWh",
        )


def test_inactive_factor_is_not_selected():
    with pytest.raises(NoCompatibleFactorError):
        resolve_factor(
            [factor(active=False)],
            source_key="purchased_grid_electricity",
            activity_unit="kWh",
        )


def test_multiple_equal_matches_require_explicit_selection():
    with pytest.raises(AmbiguousFactorError):
        resolve_factor(
            [factor("EF-1"), factor("EF-2")],
            source_key="purchased_grid_electricity",
            activity_unit="kWh",
        )


def test_explicit_factor_code_resolves_ambiguity():
    selected = resolve_factor(
        [factor("EF-1"), factor("EF-2")],
        source_key="purchased_grid_electricity",
        activity_unit="kWh",
        factor_code="EF-2",
    )
    assert selected["factor_code"] == "EF-2"
