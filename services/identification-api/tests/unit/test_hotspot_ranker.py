from decimal import Decimal

import pytest

from app.calculations.aggregator import aggregate_calculation_lines
from app.calculations.hotspot_ranker import rank_aggregation, rank_hotspots


def totals():
    return [
        {
            "key": "electricity",
            "label": "Electricity",
            "emissions_kgco2e": Decimal(600),
            "percentage": Decimal(60),
        },
        {
            "key": "diesel",
            "label": "Diesel",
            "emissions_kgco2e": Decimal(250),
            "percentage": Decimal(25),
        },
        {
            "key": "refrigerant",
            "label": "Refrigerant",
            "emissions_kgco2e": Decimal(100),
            "percentage": Decimal(10),
        },
        {
            "key": "waste",
            "label": "Waste",
            "emissions_kgco2e": Decimal(50),
            "percentage": Decimal(5),
        },
    ]


def test_ranks_sources_and_selects_top_three():
    result = rank_hotspots(totals())
    assert [item["key"] for item in result["top_sources"]] == [
        "electricity",
        "diesel",
        "refrigerant",
    ]
    assert [item["rank"] for item in result["ranked_sources"]] == [1, 2, 3, 4]


def test_flags_sources_at_or_above_threshold():
    result = rank_hotspots(totals(), threshold_percentage=25)
    assert [
        item["key"] for item in result["ranked_sources"] if item["exceeds_threshold"]
    ] == ["electricity", "diesel"]


def test_unquantified_sources_make_ranking_provisional():
    result = rank_hotspots(totals(), unquantified_source_ids=["transport"])
    assert result["ranking_status"] == "PROVISIONAL"
    assert result["warning"] == "Unquantified sources may change this ranking."


def test_complete_ranking_has_no_warning():
    result = rank_hotspots(totals())
    assert result["ranking_status"] == "COMPLETE"
    assert result["warning"] is None


def test_ranks_aggregator_output():
    aggregation = aggregate_calculation_lines(
        [
            {
                "source_inventory_item_id": "a",
                "source_name": "A",
                "emissions_kgco2e": 75,
            },
            {
                "source_inventory_item_id": "b",
                "source_name": "B",
                "emissions_kgco2e": 25,
            },
        ]
    )
    assert rank_aggregation(aggregation)["top_sources"][0]["key"] == "a"


def test_rejects_invalid_configuration_and_values():
    with pytest.raises(ValueError):
        rank_hotspots(totals(), top_n=0)
    with pytest.raises(ValueError):
        rank_hotspots(totals(), threshold_percentage=101)
    with pytest.raises(ValueError):
        rank_hotspots([{**totals()[0], "emissions_kgco2e": -1}])
