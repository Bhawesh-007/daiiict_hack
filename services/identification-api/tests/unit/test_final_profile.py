import json
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.domain.final_profile import build_profile_snapshot, profile_checksum


def test_final_profile_contains_the_complete_layer1_handoff():
    company = SimpleNamespace(
        id=uuid4(), name="Example Foods", msme_category="SMALL",
        registration_number=None, address="Ahmedabad",
    )
    facility = SimpleNamespace(
        id=uuid4(), name="Main Facility", location="Ahmedabad",
        city="Ahmedabad", state="Gujarat", country="India",
        grid_region="WESTERN_REGION", ownership_type="OWNED", company=company,
    )
    process_id = uuid4()
    equipment_id = uuid4()
    flow_id = uuid4()
    process = SimpleNamespace(
        id=process_id, name="Boiler house", sequence=1, description=None,
        is_outsourced="NO",
        equipment=[SimpleNamespace(
            id=equipment_id, name="Diesel boiler", equipment_type="BOILER",
            capacity="2 tonne/hour", fuel_type="DIESEL", energy_type=None,
            description=None,
            input_output_flows=[SimpleNamespace(
                id=flow_id, direction="INPUT", category="FUEL",
                item_name="Diesel", unit="litre", data_availability="AVAILABLE", notes=None,
            )],
        )],
        input_output_flows=[],
    )
    source_id = uuid4()
    activity = SimpleNamespace(
        id=uuid4(), quantity=Decimal(12500), unit_code="litre",
        normalized_quantity=Decimal(12500), normalized_unit_code="litre",
        period_start=datetime(2025, 4, 1, tzinfo=UTC),
        period_end=datetime(2026, 3, 31, tzinfo=UTC),
        data_source_type="IMPORTED_CSV", data_quality="HIGH",
        evidence_reference="diesel-logbook.csv", notes=None,
    )
    source = SimpleNamespace(
        id=source_id, source_key="stationary_fuel_combustion",
        source_name="Stationary fuel combustion", source_category="stationary_combustion",
        scope="SCOPE_1", status="CONFIRMED", confirmation_note="Reviewed",
        confirmed_by="reviewer", confirmed_at=activity.period_start,
        process_step_id=process_id, equipment_id=equipment_id,
        activity_records=[activity],
    )
    line = SimpleNamespace(
        source_inventory_item_id=source_id, emissions_kgco2e=Decimal(33500),
    )
    run = SimpleNamespace(
        id=uuid4(), total_emissions_kgco2e=Decimal(33500),
        methodology_version="deterministic-decimal-v1", factor_set_version="demo-v1",
        lines=[line], notes=json.dumps({
            "status": "COMPLETE",
            "scope_totals": {"SCOPE_1": "33500"},
            "category_totals": {"stationary_combustion": "33500"},
            "source_percentages": {str(source_id): "100.00"},
            "hotspot_ranking": {"top_sources": []},
            "unquantified_sources": [],
            "warnings": [],
        }),
    )
    assessment = SimpleNamespace(
        id=uuid4(), facility=facility, products=[SimpleNamespace(
            id=uuid4(), product_name="Milk", quantity=Decimal(3000),
            unit="tonne", description="Annual production",
        )], industry_name="Food processing", industry_code="food_processing",
        industry_template_key="industry-food-processing-v1", industry_template_version="1.0.0",
        reporting_period_start=activity.period_start, reporting_period_end=activity.period_end,
        organizational_boundary="OPERATIONAL_CONTROL", operational_boundary="SCOPE_1_SCOPE_2",
    )

    snapshot = build_profile_snapshot(
        assessment, run, [source], [process], profile_id=uuid4(), version=1,
        finalized_at=datetime(2026, 9, 13, tzinfo=UTC), finalized_by="system",
    )

    assert snapshot["schema_version"] == "layer1-final-profile-v1"
    assert snapshot["sources"][0]["confirmed_source_identity"] is True
    assert snapshot["sources"][0]["recommendation_eligible"] is True
    assert snapshot["sources"][0]["baseline_emissions_kgco2e"] == "33500"
    assert snapshot["sources"][0]["contribution_percentage"] == "100.00"
    assert snapshot["sources"][0]["activity_records"][0]["unit"] == "litre"
    assert snapshot["sources"][0]["current_technology_or_route"]["equipment_name"] == "Diesel boiler"
    assert snapshot["processes"][0]["equipment"][0]["flows"][0]["item_name"] == "Diesel"
    assert profile_checksum(snapshot)
