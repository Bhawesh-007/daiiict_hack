from decimal import Decimal

import pytest

from app.calculations.aggregator import aggregate_calculation_lines

LINES = [
    {
        "source_inventory_item_id": "electricity",
        "source_name": "Grid electricity",
        "scope": "SCOPE_2",
        "source_category": "electricity",
        "process_step_id": "packaging",
        "process_name": "Packaging",
        "emissions_kgco2e": Decimal(675),
    },
    {
        "source_inventory_item_id": "boiler",
        "source_name": "Boiler diesel",
        "scope": "SCOPE_1",
        "source_category": "stationary_combustion",
        "process_step_id": "heating",
        "process_name": "Heating",
        "emissions_kgco2e": Decimal(325),
    },
]


def test_aggregates_total_and_source_percentages():
    result = aggregate_calculation_lines(LINES)
    assert result["quantified_total_emissions_kgco2e"] == Decimal(1000)
    assert result["total_status"] == "COMPLETE"
    assert result["by_source"][0]["percentage"] == Decimal("67.5")
    assert sum(item["percentage"] for item in result["by_source"]) == Decimal(100)


def test_aggregates_scope_category_and_process():
    result = aggregate_calculation_lines(LINES)
    assert {item["key"] for item in result["by_scope"]} == {"SCOPE_1", "SCOPE_2"}
    assert result["by_process"][0]["label"] == "Packaging"


def test_unresolved_line_is_excluded_and_marks_total_partial():
    result = aggregate_calculation_lines(
        [*LINES, {"source_inventory_item_id": "waste", "emissions_kgco2e": None}]
    )
    assert result["quantified_total_emissions_kgco2e"] == Decimal(1000)
    assert result["total_status"] == "PARTIAL"
    assert result["unquantified_source_ids"] == ["waste"]


def test_calculates_emissions_intensity_without_rounding():
    result = aggregate_calculation_lines(LINES, production_quantity="250")
    assert result["emissions_intensity_kgco2e_per_production_unit"] == Decimal(4)


def test_zero_total_has_zero_percentages():
    result = aggregate_calculation_lines([{**LINES[0], "emissions_kgco2e": 0}])
    assert result["by_source"][0]["percentage"] == 0


def test_rejects_negative_emissions_and_nonpositive_production():
    with pytest.raises(ValueError):
        aggregate_calculation_lines([{**LINES[0], "emissions_kgco2e": -1}])
    with pytest.raises(ValueError):
        aggregate_calculation_lines(LINES, production_quantity=0)
