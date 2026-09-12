from decimal import Decimal

import pytest

from app.calculations.unit_converter import UnitConversionError, UnitConverter


@pytest.fixture
def converter() -> UnitConverter:
    return UnitConverter()


@pytest.mark.parametrize(
    ("quantity", "unit", "normalized", "base"),
    [
        ("2", "MWh", Decimal(2000), "kWh"),
        ("3", "tonne", Decimal(3000), "kg"),
        ("4", "mile", Decimal("6.437376"), "km"),
        ("5", "kg_km", Decimal("0.005"), "tonne_km"),
    ],
)
def test_converts_to_dimension_base_unit(converter, quantity, unit, normalized, base):
    result = converter.convert_to_base(quantity, unit)
    assert result.normalized_quantity == normalized
    assert result.normalized_unit == base
    assert result.original_quantity == Decimal(quantity)
    assert result.original_unit == unit


def test_alias_and_multiplier_are_preserved(converter):
    result = converter.convert_to_base("2", "kilowatt hours")
    assert result.normalized_quantity == Decimal(2)
    assert result.normalization_multiplier == Decimal(1)
    assert result.taxonomy_version == "2026.1-demo"


def test_rejects_negative_and_unknown_quantities(converter):
    with pytest.raises(UnitConversionError, match="negative"):
        converter.convert_to_base("-1", "kg")
    with pytest.raises(UnitConversionError, match="Unsupported unit"):
        converter.convert_to_base("1", "bucket")


def test_converts_only_to_the_unit_dimension_base(converter):
    result = converter.convert_to_base("1", "MWh")
    assert result.dimension_id == "electricity"
    assert result.normalized_unit == "kWh"
