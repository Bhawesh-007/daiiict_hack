"""Deterministic, same-dimension unit conversion for activity data."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_UNITS_PATH = PROJECT_ROOT / "data" / "taxonomy" / "units.json"


class UnitConversionError(ValueError):
    """Raised when a quantity or unit cannot be safely normalized."""


@dataclass(frozen=True)
class UnitDefinition:
    dimension_id: str
    unit_id: str
    base_unit: str
    multiplier: Decimal


@dataclass(frozen=True)
class ConversionResult:
    original_quantity: Decimal
    original_unit: str
    normalized_quantity: Decimal
    normalized_unit: str
    normalization_multiplier: Decimal
    dimension_id: str
    taxonomy_version: str | None


class UnitConverter:
    """Load the versioned unit taxonomy and convert within dimensions."""

    def __init__(self, units_path: Path = DEFAULT_UNITS_PATH) -> None:
        try:
            document = json.loads(units_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise UnitConversionError(
                f"Cannot read unit taxonomy: {units_path}"
            ) from exc
        self.taxonomy_version = document.get("version")
        self._units: dict[str, UnitDefinition] = {}
        self._aliases: dict[str, list[UnitDefinition]] = {}
        for dimension in document.get("dimensions", []):
            dimension_id = str(dimension["dimension_id"])
            base_unit = str(dimension["base_unit"])
            for unit in dimension.get("units", []):
                definition = UnitDefinition(
                    dimension_id=dimension_id,
                    unit_id=str(unit["unit_id"]),
                    base_unit=base_unit,
                    multiplier=Decimal(str(unit["to_base_multiplier"])),
                )
                if definition.unit_id in self._units:
                    raise UnitConversionError(
                        f"Duplicate unit ID: {definition.unit_id}"
                    )
                self._units[definition.unit_id] = definition
                names = [
                    definition.unit_id,
                    unit.get("symbol"),
                    *unit.get("aliases", []),
                ]
                for name in names:
                    if name:
                        self._aliases.setdefault(self._key(name), []).append(definition)

    @staticmethod
    def _key(value: Any) -> str:
        return " ".join(str(value).strip().lower().replace("_", " ").split())

    def resolve(self, unit_code: str) -> UnitDefinition:
        key = self._key(unit_code)
        if not key:
            raise UnitConversionError("Unit code cannot be empty")
        exact = self._units.get(str(unit_code).strip())
        if exact is not None:
            return exact
        matches = self._aliases.get(key, [])
        if not matches:
            raise UnitConversionError(f"Unsupported unit code: {unit_code}")
        return matches[0]

    def convert_to_base(
        self, quantity: Decimal | float | str, unit_code: str
    ) -> ConversionResult:
        try:
            original = (
                quantity if isinstance(quantity, Decimal) else Decimal(str(quantity))
            )
        except (InvalidOperation, ValueError) as exc:
            raise UnitConversionError(f"Invalid quantity: {quantity!r}") from exc
        if not original.is_finite():
            raise UnitConversionError("Quantity must be finite")
        if original < 0:
            raise UnitConversionError("Quantity cannot be negative")
        definition = self.resolve(unit_code)
        return ConversionResult(
            original_quantity=original,
            original_unit=str(unit_code),
            normalized_quantity=original * definition.multiplier,
            normalized_unit=definition.base_unit,
            normalization_multiplier=definition.multiplier,
            dimension_id=definition.dimension_id,
            taxonomy_version=self.taxonomy_version,
        )


_DEFAULT_CONVERTER = UnitConverter()


def convert_to_base(
    quantity: Decimal | float | str, unit_code: str
) -> ConversionResult:
    """Convert a quantity to its taxonomy-defined dimension base unit."""
    return _DEFAULT_CONVERTER.convert_to_base(quantity, unit_code)


__all__ = [
    "ConversionResult",
    "UnitConversionError",
    "UnitConverter",
    "convert_to_base",
]
