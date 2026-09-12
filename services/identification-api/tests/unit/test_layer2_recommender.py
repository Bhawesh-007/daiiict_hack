from app.layer2.catalog import load_catalog, load_demo_profile
from app.layer2.recommender import (
    generate_impact_recommendations,
    generate_recommendations,
)


def test_layer2_matches_confirmed_hotspots_without_recalculating_them():
    profile = {
        "profile_id": "00000000-0000-0000-0000-000000000001",
        "profile_version": 3,
        "assessment_id": "00000000-0000-0000-0000-000000000002",
        "sources": [
            {
                "source_id": "00000000-0000-0000-0000-000000000010",
                "source_key": "stationary_fuel_combustion",
                "source_name": "Stationary fuel combustion",
                "source_category": "stationary_combustion",
                "status": "CONFIRMED",
                "confirmed_source_identity": True,
                "activity_records": [{"quantity": "12500", "unit": "litre"}],
                "baseline_emissions_kgco2e": "33500",
                "contribution_percentage": "75.00",
                "equipment": {"equipment_type": "BOILER"},
            },
            {
                "source_id": "00000000-0000-0000-0000-000000000011",
                "source_key": "waste_generated_in_operations",
                "source_name": "Operations waste",
                "source_category": "waste",
                "status": "MISSING_INFORMATION",
                "confirmed_source_identity": False,
                "activity_records": [],
                "baseline_emissions_kgco2e": "10000",
                "contribution_percentage": "25.00",
            },
        ],
    }

    result = generate_recommendations(profile, load_catalog())

    assert result["status"] == "CANDIDATES_READY"
    assert result["recommendation_count"] == 1
    assert result["recommendations"][0]["intervention_id"] == "CI-004"
    assert result["recommendations"][0]["impact_status"] == "PENDING_PHASE_2_IMPACT_MODEL"
    assert result["excluded_sources"][0]["reason"] == "SOURCE_NOT_CONFIRMED"


def test_layer2_returns_no_candidate_for_unmatched_confirmed_source():
    profile = {
        "profile_id": "00000000-0000-0000-0000-000000000001",
        "profile_version": 1,
        "assessment_id": "00000000-0000-0000-0000-000000000002",
        "sources": [{
            "source_id": "00000000-0000-0000-0000-000000000010",
            "source_key": "industrial_process_emissions",
            "source_name": "Industrial process emissions",
            "source_category": "industrial_process",
            "status": "CONFIRMED",
            "confirmed_source_identity": True,
            "activity_records": [{"quantity": "1", "unit": "tonne"}],
            "baseline_emissions_kgco2e": "100",
            "contribution_percentage": "100",
        }],
    }

    result = generate_recommendations(profile, load_catalog())

    assert result["recommendation_count"] == 0
    assert result["excluded_sources"][0]["reason"] == "NO_CATALOG_MATCH"


def test_synthetic_layer1_profile_feeds_the_demo_flow():
    result = generate_recommendations(load_demo_profile(), load_catalog())

    assert result["profile_id"] == "90000000-0000-4000-8000-000000000001"
    assert result["profile_version"] == 1
    assert result["recommendation_count"] == 5
    assert result["recommendations"][0]["source_name"] == "Purchased grid electricity"


def test_phase2_calculates_impact_cost_and_feasibility():
    result = generate_impact_recommendations(load_demo_profile(), load_catalog())

    electricity = next(
        item for item in result["recommendations"] if item["intervention_id"] == "CI-005"
    )
    assert result["phase"] == "PHASE_2_IMPACT_AND_FEASIBILITY"
    assert result["engine_version"] == "layer2-impact-v1"
    assert electricity["impact_status"] == "CALCULATED_DETERMINISTICALLY"
    assert electricity["projected_emissions_kgco2e"] == "99900.00"
    assert electricity["carbon_reduction_kgco2e"] == "24975.00"
    assert electricity["reduction_percentage"] == "20.00"
    assert electricity["annual_savings_inr"] == "95000.00"
    assert electricity["simple_payback_years"] == "1.84"
    assert electricity["feasibility_status"] == "VIABLE_WITHIN_CAPTURED_CONSTRAINTS"
