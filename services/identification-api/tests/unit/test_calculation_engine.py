"""Unit tests for pure, database-independent emissions calculation engine."""

from decimal import Decimal
import pytest

from app.calculations.engine import (
    CalculationError,
    CalculationGap,
    CalculationInput,
    CalculationLineList,
    CalculationLineResult,
    CalculationResult,
    CalculationRunResult,
    IncompatibleFactorError,
    InvalidQuantityError,
    MissingCalculationInputError,
    aggregate_by_category,
    aggregate_by_process,
    aggregate_by_scope,
    aggregate_by_source,
    aggregate_total,
    calculate_intensity,
    calculate_line_item,
    calculate_lines,
    calculate_lines_with_gaps,
    calculate_source_percentages,
    check_compatibility_or_raise,
    rank_hotspots,
    run_calculation_pipeline,
    verify_compatibility,
)


# ═════════════════════════════════════════════════════════════════════════════
# 1. LINE-ITEM CALCULATION TESTS
# ═════════════════════════════════════════════════════════════════════════════

def test_calculate_line_item_success():
    result = calculate_line_item(
        normalized_quantity=Decimal("150.5"),
        emission_factor=Decimal("2.68"),
        conversion_multiplier=Decimal("1.0"),
        factor_unit="kg CO2e / L",
    )
    assert isinstance(result, CalculationResult)
    assert result.normalized_quantity == Decimal("150.5")
    assert result.factor_value == Decimal("2.68")
    assert result.factor_unit == "kg CO2e / L"
    assert result.conversion_multiplier == Decimal("1.0")
    # 150.5 * 2.68 = 403.34
    assert result.emissions_kgco2e == Decimal("403.34")


def test_calculate_line_item_rejects_negative_quantity():
    with pytest.raises(InvalidQuantityError, match="Quantity cannot be negative"):
        calculate_line_item(
            normalized_quantity=Decimal("-10"),
            emission_factor=Decimal("2.5"),
        )


def test_calculate_line_item_rejects_negative_factor():
    with pytest.raises(InvalidQuantityError, match="factor cannot be negative"):
        calculate_line_item(
            normalized_quantity=Decimal("100"),
            emission_factor=Decimal("-0.5"),
        )


def test_calculate_line_item_missing_inputs_raise_controlled_error():
    with pytest.raises(MissingCalculationInputError):
        calculate_line_item(normalized_quantity=None, emission_factor=Decimal("1.5"))
    with pytest.raises(MissingCalculationInputError):
        calculate_line_item(normalized_quantity=Decimal("100"), emission_factor=None)


def test_calculate_line_item_no_internal_rounding():
    # Verify decimal arithmetic maintains exact precision without rounding
    qty = Decimal("1.123456789")
    factor = Decimal("2.987654321")
    result = calculate_line_item(normalized_quantity=qty, emission_factor=factor)
    assert result.emissions_kgco2e == qty * factor


# ═════════════════════════════════════════════════════════════════════════════
# 2. ACTIVITY AND FACTOR COMPATIBILITY TESTS
# ═════════════════════════════════════════════════════════════════════════════

def test_verify_compatibility_success():
    ok, reason = verify_compatibility(
        activity_unit="kWh",
        factor_unit="kWh",
        activity_category="purchased_electricity",
        factor_category="purchased_electricity",
        activity_scope="SCOPE_2",
        factor_scope="SCOPE_2",
        factor_version="1.0.0",
    )
    assert ok is True
    assert reason is None


def test_verify_compatibility_rejects_missing_factor_version():
    ok, reason = verify_compatibility(
        activity_unit="kWh",
        factor_unit="kWh",
        factor_version=None,
    )
    assert ok is False
    assert "version is missing" in reason.lower()


def test_verify_compatibility_rejects_unit_mismatch():
    ok, reason = verify_compatibility(
        activity_unit="L",
        factor_unit="kWh",
        factor_version="1.0.0",
    )
    assert ok is False
    assert "unit mismatch" in reason.lower()


def test_verify_compatibility_rejects_category_mismatch():
    ok, reason = verify_compatibility(
        activity_unit="L",
        factor_unit="L",
        activity_category="stationary_combustion",
        factor_category="mobile_combustion",
        factor_version="1.0.0",
    )
    assert ok is False
    assert "category mismatch" in reason.lower()


def test_check_compatibility_or_raise_raises_incompatible_error():
    with pytest.raises(IncompatibleFactorError, match="Unit mismatch"):
        check_compatibility_or_raise(
            activity_unit="kg",
            factor_unit="L",
            factor_version="1.0.0",
        )


# ═════════════════════════════════════════════════════════════════════════════
# 3. BATCH CALCULATION TESTS
# ═════════════════════════════════════════════════════════════════════════════

def test_calculate_lines_batch_success_and_retains_fields():
    inputs = [
        CalculationInput(
            source_inventory_item_id="src-001",
            activity_record_id="act-001",
            emission_factor_id="fac-001",
            source_name="Boiler Diesel",
            source_category="stationary_combustion",
            source_status="CONFIRMED",
            scope="SCOPE_1",
            process_step_id="proc-steam",
            process_name="Steam Generation",
            original_quantity=Decimal("1000"),
            original_unit="L",
            normalized_quantity=Decimal("1000"),
            normalized_unit="L",
            conversion_multiplier=Decimal("1.0"),
            factor_value=Decimal("2.68"),
            factor_unit="L",
            factor_version="1.0.0",
            factor_category="stationary_combustion",
            factor_scope="SCOPE_1",
        ),
        CalculationInput(
            source_inventory_item_id="src-002",
            activity_record_id="act-002",
            emission_factor_id="fac-002",
            source_name="Grid Electricity",
            source_category="purchased_energy",
            source_status="CONFIRMED",
            scope="SCOPE_2",
            process_step_id="proc-packaging",
            process_name="Packaging",
            original_quantity=Decimal("500"),
            original_unit="kWh",
            normalized_quantity=Decimal("500"),
            normalized_unit="kWh",
            conversion_multiplier=Decimal("1.0"),
            factor_value=Decimal("0.82"),
            factor_unit="kWh",
            factor_version="1.0.0",
            factor_category="purchased_energy",
            factor_scope="SCOPE_2",
        ),
    ]

    results = calculate_lines(inputs)
    assert isinstance(results, CalculationLineList)
    assert len(results) == 2
    assert len(results.gaps) == 0

    first = results[0]
    assert first.source_inventory_item_id == "src-001"
    assert first.activity_record_id == "act-001"
    assert first.emission_factor_id == "fac-001"
    assert first.original_quantity == Decimal("1000")
    assert first.original_unit == "L"
    assert first.normalized_quantity == Decimal("1000")
    assert first.normalized_unit == "L"
    assert first.conversion_multiplier == Decimal("1.0")
    assert first.factor_value_snapshot == Decimal("2.68")
    assert first.emissions_kgco2e == Decimal("2680.00")
    assert first.scope == "SCOPE_1"
    assert first.source_category == "stationary_combustion"


def test_calculate_lines_separates_unresolved_lines_as_gaps():
    inputs = [
        # 1. Valid line
        CalculationInput(
            source_inventory_item_id="src-001",
            activity_record_id="act-001",
            emission_factor_id="fac-001",
            source_status="CONFIRMED",
            normalized_quantity=Decimal("100"),
            normalized_unit="L",
            factor_value=Decimal("2.5"),
            factor_unit="L",
            factor_version="1.0.0",
        ),
        # 2. Unconfirmed source
        CalculationInput(
            source_inventory_item_id="src-002",
            source_status="PROPOSED",
            normalized_quantity=Decimal("100"),
            normalized_unit="L",
            factor_value=Decimal("2.5"),
            factor_unit="L",
            factor_version="1.0.0",
        ),
        # 3. Missing factor
        CalculationInput(
            source_inventory_item_id="src-003",
            source_status="CONFIRMED",
            normalized_quantity=Decimal("100"),
            normalized_unit="L",
            factor_value=None,
        ),
        # 4. Incompatible units
        CalculationInput(
            source_inventory_item_id="src-004",
            source_status="CONFIRMED",
            normalized_quantity=Decimal("100"),
            normalized_unit="kg",
            factor_value=Decimal("2.5"),
            factor_unit="kWh",
            factor_version="1.0.0",
        ),
    ]

    lines, gaps = calculate_lines_with_gaps(inputs)
    assert len(lines) == 1
    assert lines[0].source_inventory_item_id == "src-001"

    assert len(gaps) == 3
    gap_sources = {g.source_inventory_item_id for g in gaps}
    assert gap_sources == {"src-002", "src-003", "src-004"}


# ═════════════════════════════════════════════════════════════════════════════
# 4. TOTAL AGGREGATION TESTS
# ═════════════════════════════════════════════════════════════════════════════

def test_aggregations():
    lines = [
        CalculationLineResult(
            source_inventory_item_id="src-boiler",
            activity_record_id="act-1",
            emission_factor_id="fac-1",
            source_name="Boiler",
            source_category="stationary_combustion",
            scope="SCOPE_1",
            process_step_id="proc-1",
            process_name="Process 1",
            original_quantity=Decimal("100"),
            original_unit="L",
            normalized_quantity=Decimal("100"),
            normalized_unit="L",
            conversion_multiplier=Decimal("1.0"),
            factor_value_snapshot=Decimal("3.0"),
            factor_unit_snapshot="L",
            factor_version="1.0.0",
            emissions_kgco2e=Decimal("300"),
        ),
        CalculationLineResult(
            source_inventory_item_id="src-electricity",
            activity_record_id="act-2",
            emission_factor_id="fac-2",
            source_name="Electricity",
            source_category="purchased_energy",
            scope="SCOPE_2",
            process_step_id="proc-2",
            process_name="Process 2",
            original_quantity=Decimal("700"),
            original_unit="kWh",
            normalized_quantity=Decimal("700"),
            normalized_unit="kWh",
            conversion_multiplier=Decimal("1.0"),
            factor_value_snapshot=Decimal("1.0"),
            factor_unit_snapshot="kWh",
            factor_version="1.0.0",
            emissions_kgco2e=Decimal("700"),
        ),
    ]

    assert aggregate_total(lines) == Decimal("1000")
    assert aggregate_by_scope(lines) == {"SCOPE_2": Decimal("700"), "SCOPE_1": Decimal("300")}
    assert aggregate_by_source(lines) == {"src-electricity": Decimal("700"), "src-boiler": Decimal("300")}
    assert aggregate_by_process(lines) == {"proc-2": Decimal("700"), "proc-1": Decimal("300")}
    assert aggregate_by_category(lines) == {"purchased_energy": Decimal("700"), "stationary_combustion": Decimal("300")}


# ═════════════════════════════════════════════════════════════════════════════
# 5. SOURCE PERCENTAGES TESTS
# ═════════════════════════════════════════════════════════════════════════════

def test_calculate_source_percentages():
    source_totals = {
        "source-a": Decimal("600"),
        "source-b": Decimal("400"),
    }
    percentages = calculate_source_percentages(source_totals)
    assert percentages["source-a"] == Decimal("60")
    assert percentages["source-b"] == Decimal("40")


def test_calculate_source_percentages_zero_total():
    source_totals = {
        "source-a": Decimal("0"),
        "source-b": Decimal("0"),
    }
    percentages = calculate_source_percentages(source_totals)
    assert percentages["source-a"] == Decimal("0")
    assert percentages["source-b"] == Decimal("0")


# ═════════════════════════════════════════════════════════════════════════════
# 6. PRODUCTION INTENSITY TESTS
# ═════════════════════════════════════════════════════════════════════════════

def test_calculate_intensity_success():
    res = calculate_intensity(total_emissions=Decimal("1000"), production_quantity=Decimal("250"))
    assert res.status == "AVAILABLE"
    assert res.emissions_intensity == Decimal("4")
    assert res.warning is None


def test_calculate_intensity_missing_or_zero_production():
    res_zero = calculate_intensity(total_emissions=Decimal("1000"), production_quantity=Decimal("0"))
    assert res_zero.status == "UNAVAILABLE"
    assert res_zero.emissions_intensity is None
    assert "greater than zero" in res_zero.warning.lower()

    res_missing = calculate_intensity(total_emissions=Decimal("1000"), production_quantity=None)
    assert res_missing.status == "UNAVAILABLE"
    assert res_missing.emissions_intensity is None
    assert "missing" in res_missing.warning.lower()


# ═════════════════════════════════════════════════════════════════════════════
# 7. HOTSPOT RANKING TESTS
# ═════════════════════════════════════════════════════════════════════════════

def test_rank_hotspots():
    sources = {
        "src-1": Decimal("500"),
        "src-2": Decimal("300"),
        "src-3": Decimal("150"),
        "src-4": Decimal("50"),
    }
    ranking = rank_hotspots(sources, top_n=3, unquantified_sources=["src-missing"])

    assert ranking["ranking_label"] == "Top quantified emission sources"
    assert len(ranking["top_sources"]) == 3
    assert [s["key"] for s in ranking["top_sources"]] == ["src-1", "src-2", "src-3"]
    assert ranking["ranking_status"] == "PROVISIONAL"
    assert ranking["warning"] == "Unquantified sources may change this ranking."
    assert ranking["unquantified_sources"] == ["src-missing"]


def test_rank_hotspots_complete():
    sources = {"src-1": Decimal("100")}
    ranking = rank_hotspots(sources, unquantified_sources=[])
    assert ranking["ranking_status"] == "COMPLETE"
    assert ranking["warning"] is None


# ═════════════════════════════════════════════════════════════════════════════
# 8. FULL PIPELINE RUN OUTPUT TESTS
# ═════════════════════════════════════════════════════════════════════════════

def test_run_calculation_pipeline():
    inputs = [
        CalculationInput(
            source_inventory_item_id="src-1",
            activity_record_id="act-1",
            emission_factor_id="fac-1",
            source_name="Diesel generator",
            source_category="stationary_combustion",
            source_status="CONFIRMED",
            scope="SCOPE_1",
            process_step_id="proc-1",
            process_name="Power",
            normalized_quantity=Decimal("100"),
            normalized_unit="L",
            factor_value=Decimal("2.68"),
            factor_unit="L",
            factor_version="1.0.0",
        ),
        CalculationInput(
            source_inventory_item_id="src-2",
            source_name="Wastewater",
            source_status="CONFIRMED",
            normalized_quantity=Decimal("50"),
            normalized_unit="m3",
            factor_value=None,  # Missing factor -> creates a gap
        ),
    ]

    run_res = run_calculation_pipeline(
        inputs,
        production_quantity=Decimal("50"),
    )

    assert isinstance(run_res, CalculationRunResult)
    assert len(run_res.line_items) == 1
    assert run_res.total_emissions == Decimal("268.00")
    assert run_res.scope_totals == {"SCOPE_1": Decimal("268.00")}
    assert run_res.source_totals == {"src-1": Decimal("268.00")}
    assert run_res.source_percentages == {"src-1": Decimal("100")}
    assert run_res.is_partial is True
    assert run_res.status == "PARTIAL"
    assert "src-2" in run_res.unquantified_sources
    assert len(run_res.warnings) >= 1
    assert run_res.production_intensity.status == "AVAILABLE"
    assert run_res.production_intensity.emissions_intensity == Decimal("268.00") / Decimal("50")
