"""Pure, database-independent greenhouse gas emissions calculation engine.

This module provides deterministic, Decimal-safe calculation, aggregation,
source percentage computation, production intensity, and hotspot ranking.
It is strictly database-independent and contains no SQLAlchemy or HTTP logic.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Optional


# ═════════════════════════════════════════════════════════════════════════════
# 1. EXCEPTIONS
# ═════════════════════════════════════════════════════════════════════════════

class CalculationError(ValueError):
    """Base exception for calculation errors."""


class MissingCalculationInputError(CalculationError):
    """Raised when a required calculation input (quantity, factor) is missing."""


class InvalidQuantityError(CalculationError):
    """Raised when a quantity or factor value is negative or non-finite."""


class IncompatibleFactorError(CalculationError):
    """Raised when an emission factor is incompatible with the activity or source."""


class UnconfirmedSourceError(CalculationError):
    """Raised when attempting to calculate an unconfirmed inventory source."""


# ═════════════════════════════════════════════════════════════════════════════
# 2. DATA STRUCTURES
# ═════════════════════════════════════════════════════════════════════════════

def _to_decimal(value: Any, name: str = "value") -> Decimal:
    """Convert a value to Decimal without silent precision loss."""
    if value is None:
        raise MissingCalculationInputError(f"{name} is missing or None")
    if isinstance(value, Decimal):
        d = value
    else:
        try:
            d = Decimal(str(value).strip())
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise InvalidQuantityError(f"{name} must be a valid numeric Decimal: {value!r}") from exc
    if not d.is_finite():
        raise InvalidQuantityError(f"{name} must be finite: {value!r}")
    return d


@dataclass(frozen=True)
class CalculationResult:
    """Result of a single line-item emission calculation."""
    normalized_quantity: Decimal
    factor_value: Decimal
    factor_unit: Optional[str]
    conversion_multiplier: Decimal
    emissions_kgco2e: Decimal

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CalculationInput:
    """Input payload representing an activity record and its associated factor."""
    source_inventory_item_id: Optional[str] = None
    activity_record_id: Optional[str] = None
    emission_factor_id: Optional[str] = None
    source_name: Optional[str] = None
    source_category: Optional[str] = None
    source_status: Optional[str] = "CONFIRMED"  # Must be CONFIRMED to calculate
    scope: Optional[str] = None
    process_step_id: Optional[str] = None
    process_name: Optional[str] = None

    # Activity values
    original_quantity: Optional[Decimal] = None
    original_unit: Optional[str] = None
    normalized_quantity: Optional[Decimal] = None
    normalized_unit: Optional[str] = None
    conversion_multiplier: Decimal = Decimal("1.0")

    # Factor values
    factor_value: Optional[Decimal] = None
    factor_unit: Optional[str] = None
    factor_version: Optional[str] = None
    factor_category: Optional[str] = None
    factor_scope: Optional[str] = None

    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CalculationLineResult:
    """Detailed result of a single batch calculation line."""
    source_inventory_item_id: Optional[str]
    activity_record_id: Optional[str]
    emission_factor_id: Optional[str]
    source_name: Optional[str]
    source_category: Optional[str]
    scope: Optional[str]
    process_step_id: Optional[str]
    process_name: Optional[str]
    original_quantity: Optional[Decimal]
    original_unit: Optional[str]
    normalized_quantity: Decimal
    normalized_unit: Optional[str]
    conversion_multiplier: Decimal
    factor_value_snapshot: Decimal
    factor_unit_snapshot: Optional[str]
    factor_version: Optional[str]
    emissions_kgco2e: Decimal

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CalculationGap:
    """Represents an unresolved line that could not be calculated."""
    source_inventory_item_id: Optional[str]
    activity_record_id: Optional[str]
    source_name: Optional[str]
    reason: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CalculationLineList(list):
    """List of CalculationLineResult objects with attached gaps attribute."""
    def __init__(self, items: Iterable[CalculationLineResult] = (), gaps: Iterable[CalculationGap] = ()):
        super().__init__(items)
        self.gaps: list[CalculationGap] = list(gaps)


@dataclass(frozen=True)
class IntensityResult:
    """Emissions intensity per production unit."""
    status: str  # "AVAILABLE" or "UNAVAILABLE"
    emissions_intensity: Optional[Decimal]
    production_quantity: Optional[Decimal]
    warning: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CalculationRunResult:
    """Complete aggregated calculation run output."""
    line_items: list[CalculationLineResult]
    total_emissions: Decimal
    scope_totals: dict[str, Decimal]
    source_totals: dict[str, Decimal]
    process_totals: dict[str, Decimal]
    category_totals: dict[str, Decimal]
    source_percentages: dict[str, Decimal]
    hotspot_ranking: dict[str, Any]
    unquantified_sources: list[str]
    warnings: list[str]
    is_partial: bool
    status: str
    production_intensity: Optional[IntensityResult] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "line_items": [line.to_dict() for line in self.line_items],
            "total_emissions": self.total_emissions,
            "scope_totals": dict(self.scope_totals),
            "source_totals": dict(self.source_totals),
            "process_totals": dict(self.process_totals),
            "category_totals": dict(self.category_totals),
            "source_percentages": dict(self.source_percentages),
            "hotspot_ranking": self.hotspot_ranking,
            "unquantified_sources": list(self.unquantified_sources),
            "warnings": list(self.warnings),
            "is_partial": self.is_partial,
            "status": self.status,
            "production_intensity": self.production_intensity.to_dict() if self.production_intensity else None,
        }


# ═════════════════════════════════════════════════════════════════════════════
# 3. LINE-ITEM CALCULATION
# ═════════════════════════════════════════════════════════════════════════════

def calculate_line_item(
    normalized_quantity: Decimal | float | str | None,
    emission_factor: Decimal | float | str | None,
    conversion_multiplier: Decimal | float | str = Decimal("1.0"),
    factor_unit: Optional[str] = None,
) -> CalculationResult:
    """Calculate emissions for a single activity-factor pair.

    Formula:
        emissions_kgco2e = normalized_quantity * emission_factor

    Validations:
        - normalized_quantity is not negative.
        - emission_factor is not negative.
        - Both values are finite Decimal numbers.
        - Rounding is not performed internally.
    """
    if normalized_quantity is None:
        raise MissingCalculationInputError("normalized_quantity is required")
    if emission_factor is None:
        raise MissingCalculationInputError("emission_factor is required")

    qty = _to_decimal(normalized_quantity, "normalized_quantity")
    factor = _to_decimal(emission_factor, "emission_factor")
    multiplier = _to_decimal(conversion_multiplier, "conversion_multiplier")

    if qty < Decimal(0):
        raise InvalidQuantityError(f"Quantity cannot be negative: {qty}")
    if factor < Decimal(0):
        raise InvalidQuantityError(f"Emission factor cannot be negative: {factor}")
    if multiplier < Decimal(0):
        raise InvalidQuantityError(f"Conversion multiplier cannot be negative: {multiplier}")

    emissions = qty * factor

    return CalculationResult(
        normalized_quantity=qty,
        factor_value=factor,
        factor_unit=factor_unit,
        conversion_multiplier=multiplier,
        emissions_kgco2e=emissions,
    )


# ═════════════════════════════════════════════════════════════════════════════
# 4. ACTIVITY AND FACTOR COMPATIBILITY
# ═════════════════════════════════════════════════════════════════════════════

def _normalize_str(val: Optional[str]) -> str:
    return " ".join(str(val or "").strip().lower().replace("_", " ").split())


def verify_compatibility(
    activity_unit: Optional[str],
    factor_unit: Optional[str],
    *,
    activity_category: Optional[str] = None,
    factor_category: Optional[str] = None,
    activity_scope: Optional[str] = None,
    factor_scope: Optional[str] = None,
    factor_version: Optional[str] = None,
) -> tuple[bool, Optional[str]]:
    """Verify compatibility between activity data and emission factor.

    Checks:
        1. Factor version is present and non-empty.
        2. Activity normalized unit matches factor input unit.
        3. Source category matches factor category (when specified).
        4. Scope is compatible (when specified).

    Returns:
        (is_compatible, reason_if_incompatible)
    """
    if not factor_version or not str(factor_version).strip():
        return False, "Factor version is missing or empty"

    if not activity_unit or not factor_unit:
        return False, f"Missing unit: activity_unit={activity_unit!r}, factor_unit={factor_unit!r}"

    if _normalize_str(activity_unit) != _normalize_str(factor_unit):
        return False, f"Unit mismatch: activity unit {activity_unit!r} != factor unit {factor_unit!r}"

    if activity_category and factor_category:
        if _normalize_str(activity_category) != _normalize_str(factor_category):
            return False, f"Category mismatch: activity category {activity_category!r} != factor category {factor_category!r}"

    if activity_scope and factor_scope:
        norm_act_scope = _normalize_str(activity_scope)
        norm_fac_scope = _normalize_str(factor_scope)
        if norm_act_scope != norm_fac_scope and norm_fac_scope not in {"unspecified", "all"}:
            return False, f"Scope mismatch: activity scope {activity_scope!r} != factor scope {factor_scope!r}"

    return True, None


def check_compatibility_or_raise(
    activity_unit: Optional[str],
    factor_unit: Optional[str],
    *,
    activity_category: Optional[str] = None,
    factor_category: Optional[str] = None,
    activity_scope: Optional[str] = None,
    factor_scope: Optional[str] = None,
    factor_version: Optional[str] = None,
) -> None:
    """Verify compatibility or raise IncompatibleFactorError."""
    ok, reason = verify_compatibility(
        activity_unit,
        factor_unit,
        activity_category=activity_category,
        factor_category=factor_category,
        activity_scope=activity_scope,
        factor_scope=factor_scope,
        factor_version=factor_version,
    )
    if not ok:
        raise IncompatibleFactorError(reason)


# ═════════════════════════════════════════════════════════════════════════════
# 5. BATCH CALCULATION
# ═════════════════════════════════════════════════════════════════════════════

def calculate_lines(
    inputs: Sequence[CalculationInput],
) -> CalculationLineList:
    """Calculate multiple activity/factor pairs in batch.

    Returns a CalculationLineList containing all valid CalculationLineResult objects.
    Unresolved lines are available on the `.gaps` attribute and are excluded from the list.
    """
    lines, gaps = calculate_lines_with_gaps(inputs)
    return CalculationLineList(lines, gaps=gaps)


def calculate_lines_with_gaps(
    inputs: Sequence[CalculationInput],
) -> tuple[list[CalculationLineResult], list[CalculationGap]]:
    """Calculate batch inputs and return separate (valid_lines, gaps)."""
    valid_lines: list[CalculationLineResult] = []
    gaps: list[CalculationGap] = []

    for item in inputs:
        source_id = item.source_inventory_item_id
        activity_id = item.activity_record_id
        source_name = item.source_name

        # 1. Verify confirmed source status
        status = str(item.source_status or "").upper()
        if status and status not in {"CONFIRMED", "ACTIVE", "APPROVED"}:
            gaps.append(
                CalculationGap(
                    source_inventory_item_id=source_id,
                    activity_record_id=activity_id,
                    source_name=source_name,
                    reason=f"Source is unconfirmed (status: {item.source_status})",
                    details={"source_status": item.source_status},
                )
            )
            continue

        # 2. Check for missing factor
        if item.factor_value is None or item.emission_factor_id is None:
            gaps.append(
                CalculationGap(
                    source_inventory_item_id=source_id,
                    activity_record_id=activity_id,
                    source_name=source_name,
                    reason="Emission factor is missing or unresolved",
                    details={"emission_factor_id": item.emission_factor_id},
                )
            )
            continue

        # 3. Check for missing factor version
        if not item.factor_version:
            gaps.append(
                CalculationGap(
                    source_inventory_item_id=source_id,
                    activity_record_id=activity_id,
                    source_name=source_name,
                    reason="Emission factor version is missing",
                    details={"emission_factor_id": item.emission_factor_id},
                )
            )
            continue

        # 4. Resolve normalized quantity and unit
        norm_qty = item.normalized_quantity
        norm_unit = item.normalized_unit or item.original_unit
        multiplier = item.conversion_multiplier or Decimal("1.0")

        if norm_qty is None:
            if item.original_quantity is not None:
                norm_qty = item.original_quantity * multiplier
            else:
                gaps.append(
                    CalculationGap(
                        source_inventory_item_id=source_id,
                        activity_record_id=activity_id,
                        source_name=source_name,
                        reason="Activity quantity is missing",
                    )
                )
                continue

        # 5. Check compatibility
        compatible, reason = verify_compatibility(
            norm_unit,
            item.factor_unit,
            activity_category=item.source_category,
            factor_category=item.factor_category,
            activity_scope=item.scope,
            factor_scope=item.factor_scope,
            factor_version=item.factor_version,
        )
        if not compatible:
            gaps.append(
                CalculationGap(
                    source_inventory_item_id=source_id,
                    activity_record_id=activity_id,
                    source_name=source_name,
                    reason=f"Incompatible factor: {reason}",
                    details={"incompatibility_reason": reason},
                )
            )
            continue

        # 6. Calculate line item
        try:
            line_calc = calculate_line_item(
                normalized_quantity=norm_qty,
                emission_factor=item.factor_value,
                conversion_multiplier=multiplier,
                factor_unit=item.factor_unit,
            )
        except CalculationError as exc:
            gaps.append(
                CalculationGap(
                    source_inventory_item_id=source_id,
                    activity_record_id=activity_id,
                    source_name=source_name,
                    reason=f"Calculation failed: {exc}",
                )
            )
            continue

        valid_lines.append(
            CalculationLineResult(
                source_inventory_item_id=source_id,
                activity_record_id=activity_id,
                emission_factor_id=item.emission_factor_id,
                source_name=source_name,
                source_category=item.source_category,
                scope=item.scope,
                process_step_id=item.process_step_id,
                process_name=item.process_name,
                original_quantity=item.original_quantity,
                original_unit=item.original_unit,
                normalized_quantity=line_calc.normalized_quantity,
                normalized_unit=norm_unit,
                conversion_multiplier=line_calc.conversion_multiplier,
                factor_value_snapshot=line_calc.factor_value,
                factor_unit_snapshot=line_calc.factor_unit,
                factor_version=item.factor_version,
                emissions_kgco2e=line_calc.emissions_kgco2e,
            )
        )

    return valid_lines, gaps


# ═════════════════════════════════════════════════════════════════════════════
# 6. TOTAL AGGREGATIONS
# ═════════════════════════════════════════════════════════════════════════════

def _get_line_field(line: Any, field_name: str, default: Any = None) -> Any:
    if isinstance(line, Mapping):
        return line.get(field_name, default)
    return getattr(line, field_name, default)


def _get_line_emissions(line: Any) -> Optional[Decimal]:
    val = _get_line_field(line, "emissions_kgco2e")
    if val is None:
        return None
    return _to_decimal(val, "emissions_kgco2e")


def aggregate_total(lines: Iterable[Any]) -> Decimal:
    """Aggregate total emissions from valid calculated lines.

    Formula:
        total_emissions = sum(valid line-item emissions)
    """
    total = Decimal(0)
    for line in lines:
        emissions = _get_line_emissions(line)
        if emissions is not None:
            if emissions < Decimal(0):
                raise InvalidQuantityError(f"Calculated emissions cannot be negative: {emissions}")
            total += emissions
    return total


def _aggregate_by_field(
    lines: Iterable[Any],
    field_name: str,
    default_key: str = "UNSPECIFIED",
) -> dict[str, Decimal]:
    groups: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
    for line in lines:
        emissions = _get_line_emissions(line)
        if emissions is not None:
            if emissions < Decimal(0):
                raise InvalidQuantityError(f"Calculated emissions cannot be negative: {emissions}")
            key = str(_get_line_field(line, field_name) or default_key)
            groups[key] += emissions
    return dict(sorted(groups.items(), key=lambda x: (-x[1], x[0])))


def aggregate_by_scope(lines: Iterable[Any]) -> dict[str, Decimal]:
    """Aggregate emissions by GHG scope (e.g. SCOPE_1, SCOPE_2, SCOPE_3)."""
    return _aggregate_by_field(lines, "scope")


def aggregate_by_source(lines: Iterable[Any]) -> dict[str, Decimal]:
    """Aggregate emissions by source identifier."""
    return _aggregate_by_field(lines, "source_inventory_item_id")


def aggregate_by_process(lines: Iterable[Any]) -> dict[str, Decimal]:
    """Aggregate emissions by process step identifier."""
    return _aggregate_by_field(lines, "process_step_id")


def aggregate_by_category(lines: Iterable[Any]) -> dict[str, Decimal]:
    """Aggregate emissions by source category."""
    return _aggregate_by_field(lines, "source_category")


# ═════════════════════════════════════════════════════════════════════════════
# 7. SOURCE PERCENTAGES
# ═════════════════════════════════════════════════════════════════════════════

def calculate_source_percentages(
    source_totals: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    quantified_total: Optional[Decimal | float | str] = None,
) -> dict[str, Decimal]:
    """Calculate percentage contribution of each source to the quantified total.

    Formula:
        source_percentage = source_emissions / quantified_total * 100

    If quantified total is zero, returns 0 for all sources rather than dividing by zero.
    """
    parsed_totals: dict[str, Decimal] = {}

    if isinstance(source_totals, Mapping):
        for k, v in source_totals.items():
            parsed_totals[str(k)] = _to_decimal(v, f"source_total[{k}]")
    elif isinstance(source_totals, Sequence):
        for item in source_totals:
            key = str(item.get("key") or item.get("source_inventory_item_id") or "UNSPECIFIED")
            amt = _to_decimal(item.get("emissions_kgco2e", 0), f"source_total[{key}]")
            parsed_totals[key] = parsed_totals.get(key, Decimal(0)) + amt
    else:
        for k, v in dict(source_totals).items():
            parsed_totals[str(k)] = _to_decimal(v, f"source_total[{k}]")

    if quantified_total is not None:
        total = _to_decimal(quantified_total, "quantified_total")
    else:
        total = sum(parsed_totals.values(), start=Decimal(0))

    if total < Decimal(0):
        raise InvalidQuantityError(f"Quantified total cannot be negative: {total}")

    percentages: dict[str, Decimal] = {}
    for key, amount in parsed_totals.items():
        if amount < Decimal(0):
            raise InvalidQuantityError(f"Source amount cannot be negative: {amount}")
        if total == Decimal(0):
            percentages[key] = Decimal(0)
        else:
            percentages[key] = amount * Decimal(100) / total

    return percentages


# ═════════════════════════════════════════════════════════════════════════════
# 8. PRODUCTION INTENSITY
# ═════════════════════════════════════════════════════════════════════════════

def calculate_intensity(
    total_emissions: Decimal | float | str | None,
    production_quantity: Decimal | float | str | None,
) -> IntensityResult:
    """Calculate emissions intensity per unit of production.

    Formula:
        emissions_intensity = quantified_total_emissions / production_quantity

    If production quantity is missing or zero, returns unavailable with a warning.
    """
    if total_emissions is None:
        return IntensityResult(
            status="UNAVAILABLE",
            emissions_intensity=None,
            production_quantity=None,
            warning="Total emissions value is missing",
        )

    total = _to_decimal(total_emissions, "total_emissions")
    if total < Decimal(0):
        raise InvalidQuantityError(f"Total emissions cannot be negative: {total}")

    if production_quantity is None:
        return IntensityResult(
            status="UNAVAILABLE",
            emissions_intensity=None,
            production_quantity=None,
            warning="Production quantity is missing",
        )

    try:
        qty = _to_decimal(production_quantity, "production_quantity")
    except (InvalidQuantityError, MissingCalculationInputError) as exc:
        return IntensityResult(
            status="UNAVAILABLE",
            emissions_intensity=None,
            production_quantity=None,
            warning=f"Invalid production quantity: {exc}",
        )

    if qty <= Decimal(0):
        return IntensityResult(
            status="UNAVAILABLE",
            emissions_intensity=None,
            production_quantity=qty,
            warning="Production quantity must be greater than zero",
        )

    intensity = total / qty

    return IntensityResult(
        status="AVAILABLE",
        emissions_intensity=intensity,
        production_quantity=qty,
        warning=None,
    )


# ═════════════════════════════════════════════════════════════════════════════
# 9. HOTSPOT RANKING
# ═════════════════════════════════════════════════════════════════════════════

def rank_hotspots(
    source_totals: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    top_n: int = 3,
    *,
    unquantified_sources: Optional[Iterable[Any]] = None,
    threshold_percentage: Decimal | float | str = Decimal("20"),
    source_names: Optional[Mapping[str, str]] = None,
) -> dict[str, Any]:
    """Rank quantified sources from highest to lowest emissions.

    Wording: "Top quantified emission sources" (never "all major sources" if unquantified exist).
    """
    if top_n < 1:
        raise ValueError("top_n must be at least 1")

    threshold = _to_decimal(threshold_percentage, "threshold_percentage")
    if threshold < Decimal(0) or threshold > Decimal(100):
        raise ValueError("threshold_percentage must be between 0 and 100")

    # Normalize source totals input
    entries: list[dict[str, Any]] = []
    names = dict(source_names or {})

    if isinstance(source_totals, Mapping):
        for k, v in source_totals.items():
            key = str(k)
            amt = _to_decimal(v, f"source[{key}]")
            entries.append({"key": key, "label": names.get(key, key), "emissions_kgco2e": amt})
    else:
        for item in source_totals:
            key = str(item.get("key") or item.get("source_inventory_item_id") or "UNSPECIFIED")
            amt = _to_decimal(item.get("emissions_kgco2e", 0), f"source[{key}]")
            label = str(item.get("label") or item.get("source_name") or names.get(key, key))
            entries.append({"key": key, "label": label, "emissions_kgco2e": amt})

    total_emissions = sum((e["emissions_kgco2e"] for e in entries), start=Decimal(0))
    percentages = calculate_source_percentages(
        {e["key"]: e["emissions_kgco2e"] for e in entries},
        quantified_total=total_emissions,
    )

    # Attach percentages and sort descending
    for e in entries:
        e["percentage"] = percentages.get(e["key"], Decimal(0))

    entries.sort(key=lambda x: (-x["emissions_kgco2e"], x["key"]))

    ranked_sources = [
        {
            **item,
            "rank": rank,
            "is_top_source": rank <= top_n,
            "exceeds_threshold": item["percentage"] >= threshold,
        }
        for rank, item in enumerate(entries, start=1)
    ]

    unresolved = sorted({str(s) for s in (unquantified_sources or []) if s is not None})
    has_gaps = len(unresolved) > 0

    return {
        "ranking_label": "Top quantified emission sources",
        "ranked_sources": ranked_sources,
        "top_sources": ranked_sources[:top_n],
        "threshold_percentage": threshold,
        "threshold_source_count": sum(1 for item in ranked_sources if item["exceeds_threshold"]),
        "unquantified_sources": unresolved,
        "ranking_status": "PROVISIONAL" if has_gaps else "COMPLETE",
        "warning": "Unquantified sources may change this ranking." if has_gaps else None,
    }


# ═════════════════════════════════════════════════════════════════════════════
# 10. CALCULATION RUN PIPELINE
# ═════════════════════════════════════════════════════════════════════════════

def run_calculation_pipeline(
    inputs: Sequence[CalculationInput],
    *,
    unquantified_source_ids: Optional[Iterable[Any]] = None,
    production_quantity: Optional[Decimal | float | str] = None,
    top_n_hotspots: int = 3,
) -> CalculationRunResult:
    """Execute the full calculation pipeline in the recommended order:

        Validate activity/factor
            → Calculate line items
            → Aggregate totals
            → Calculate percentages
            → Rank hotspots
            → Generate warnings

    Returns a complete, immutable CalculationRunResult.
    """
    # 1 & 2: Validate and calculate lines
    valid_lines, gaps = calculate_lines_with_gaps(inputs)

    # 3: Aggregate totals
    total_emissions = aggregate_total(valid_lines)
    scope_totals = aggregate_by_scope(valid_lines)
    source_totals = aggregate_by_source(valid_lines)
    process_totals = aggregate_by_process(valid_lines)
    category_totals = aggregate_by_category(valid_lines)

    # 4: Source percentages
    source_percentages = calculate_source_percentages(source_totals, quantified_total=total_emissions)

    # Track all unquantified sources
    unresolved_sources = set(str(s) for s in (unquantified_source_ids or []))
    for gap in gaps:
        if gap.source_inventory_item_id:
            unresolved_sources.add(str(gap.source_inventory_item_id))
    unresolved_list = sorted(unresolved_sources)

    # 5: Hotspot ranking
    source_name_map = {
        line.source_inventory_item_id: line.source_name
        for line in valid_lines
        if line.source_inventory_item_id and line.source_name
    }
    hotspots = rank_hotspots(
        source_totals,
        top_n=top_n_hotspots,
        unquantified_sources=unresolved_list,
        source_names=source_name_map,
    )

    # 6: Production intensity
    intensity = calculate_intensity(total_emissions, production_quantity)

    # 7: Warnings and status determination
    warnings: list[str] = []
    is_partial = len(unresolved_list) > 0

    if is_partial:
        warnings.append(
            f"{len(unresolved_list)} source(s) remain unquantified; totals are marked as PARTIAL."
        )
    if hotspots.get("warning"):
        warnings.append(str(hotspots["warning"]))
    if intensity.warning:
        warnings.append(intensity.warning)
    for gap in gaps:
        warnings.append(f"Gap for source '{gap.source_name or gap.source_inventory_item_id}': {gap.reason}")

    if is_partial:
        status = "PARTIAL"
    elif valid_lines:
        status = "COMPLETE"
    else:
        status = "EMPTY"

    return CalculationRunResult(
        line_items=valid_lines,
        total_emissions=total_emissions,
        scope_totals=scope_totals,
        source_totals=source_totals,
        process_totals=process_totals,
        category_totals=category_totals,
        source_percentages=source_percentages,
        hotspot_ranking=hotspots,
        unquantified_sources=unresolved_list,
        warnings=warnings,
        is_partial=is_partial,
        status=status,
        production_intensity=intensity,
    )


__all__ = [
    "CalculationError",
    "CalculationGap",
    "CalculationInput",
    "CalculationLineList",
    "CalculationLineResult",
    "CalculationResult",
    "CalculationRunResult",
    "IncompatibleFactorError",
    "IntensityResult",
    "InvalidQuantityError",
    "MissingCalculationInputError",
    "UnconfirmedSourceError",
    "aggregate_by_category",
    "aggregate_by_process",
    "aggregate_by_scope",
    "aggregate_by_source",
    "aggregate_total",
    "calculate_intensity",
    "calculate_line_item",
    "calculate_lines",
    "calculate_lines_with_gaps",
    "calculate_source_percentages",
    "check_compatibility_or_raise",
    "rank_hotspots",
    "run_calculation_pipeline",
    "verify_compatibility",
]
