from types import SimpleNamespace
from uuid import uuid4

from app.identification.checklist import build_contextual_checklist


def _taxonomy() -> dict:
    keys = [
        "stationary_fuel_combustion", "mobile_fuel_combustion", "purchased_grid_electricity",
        "purchased_heat_steam_cooling", "industrial_process_emissions",
        "refrigerant_fugitive_emissions", "other_fugitive_emissions", "purchased_materials",
        "fuel_energy_related_activities", "upstream_transportation", "downstream_transportation",
        "waste_generated_in_operations", "onsite_wastewater_treatment",
        "offsite_wastewater_treatment", "outsourced_manufacturing",
    ]
    return {key: {"name": key.replace("_", " ").title(), "minimum_data": ["quantity"]} for key in keys}


def _food_assessment() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(), industry_name="Food processing", industry_code="food_processing",
        process_steps=[
            SimpleNamespace(id=uuid4(), name="Cold storage and dispatch", description=None, is_outsourced="NO", equipment=[
                SimpleNamespace(name="Cold room chiller", equipment_type="refrigeration", fuel_type=None, energy_type="electricity"),
                SimpleNamespace(name="Steam boiler", equipment_type="boiler", fuel_type="natural gas", energy_type=None),
            ], input_output_flows=[
                SimpleNamespace(item_name="raw milk packaging", category="material", notes=None),
                SimpleNamespace(item_name="wastewater from CIP cleaning", category="wastewater", notes=None),
                SimpleNamespace(item_name="organic waste", category="waste", notes=None),
            ]),
        ],
    )


def _by_key(items: list[dict]) -> dict[str, dict]:
    return {item["source_key"]: item for item in items}


def test_food_context_prioritizes_evidence_and_excludes_unrelated_process_emissions() -> None:
    assessment = _food_assessment()
    electricity = SimpleNamespace(id=uuid4(), source_key="purchased_grid_electricity", status="CONFIRMED")
    items = _by_key(build_contextual_checklist(
        assessment=assessment, taxonomy=_taxonomy(), universal_source_keys=_taxonomy().keys(),
        template={"processes": [{"suggested_source_type_ids": ["purchased_materials", "industrial_process_emissions"]}]},
        inventory=[electricity], activity_source_ids=[electricity.id],
    ))
    assert items["purchased_grid_electricity"]["status"] == "CONFIRMED"
    assert items["stationary_fuel_combustion"]["status"] == "POTENTIAL"
    assert items["refrigerant_fugitive_emissions"]["status"] == "POTENTIAL"
    assert items["purchased_materials"]["status"] == "POTENTIAL"
    assert items["offsite_wastewater_treatment"]["status"] == "POTENTIAL"
    assert items["industrial_process_emissions"]["status"] == "NOT_APPLICABLE"


def test_stationary_combustion_is_not_applicable_only_with_a_mapped_negative_context() -> None:
    assessment = _food_assessment()
    assessment.process_steps[0].equipment = [SimpleNamespace(name="Packing table", equipment_type="manual", fuel_type=None, energy_type=None)]
    assessment.process_steps[0].input_output_flows = []
    items = _by_key(build_contextual_checklist(
        assessment=assessment, taxonomy=_taxonomy(), universal_source_keys=_taxonomy().keys(), template={},
    ))
    assert items["stationary_fuel_combustion"]["status"] == "NOT_APPLICABLE"
    assert items["mobile_fuel_combustion"]["status"] == "MISSING_INFORMATION"


def test_outsourced_process_and_candidates_are_merged_into_one_item() -> None:
    assessment = _food_assessment()
    assessment.process_steps[0].is_outsourced = "YES"
    candidate = SimpleNamespace(id=uuid4(), source_key="refrigerant_fugitive_emissions", origin="RULE", status="PROPOSED")
    items = _by_key(build_contextual_checklist(
        assessment=assessment, taxonomy=_taxonomy(), universal_source_keys=_taxonomy().keys(), template={}, candidates=[candidate],
    ))
    assert items["outsourced_manufacturing"]["status"] == "OUTSOURCED"
    assert items["refrigerant_fugitive_emissions"]["candidate_ids"] == [str(candidate.id)]


def test_narrow_unrelated_categories_are_not_relevant_without_evidence() -> None:
    assessment = SimpleNamespace(id=uuid4(), industry_name="Food processing", industry_code="food_processing", process_steps=[])
    items = _by_key(build_contextual_checklist(
        assessment=assessment, taxonomy=_taxonomy(), universal_source_keys=_taxonomy().keys(), template={},
    ))
    assert items["industrial_process_emissions"]["metadata"]["is_relevant"] is False
    assert items["purchased_heat_steam_cooling"]["metadata"]["is_relevant"] is False
    assert items["purchased_grid_electricity"]["metadata"]["is_relevant"] is True
