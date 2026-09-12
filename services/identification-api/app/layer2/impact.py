"""Deterministic impact and feasibility calculations for Layer 2 Phase 2."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

ZERO = Decimal(0)
HUNDRED = Decimal(100)
TWO_PLACES = Decimal("0.01")


class ImpactModelError(ValueError):
    """Raised when a catalog impact assumption is invalid."""


def _decimal(value: Any, name: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ImpactModelError(f"{name} must be a decimal value") from exc
    if not parsed.is_finite() or parsed < ZERO:
        raise ImpactModelError(f"{name} must be finite and non-negative")
    return parsed


def _money(value: Decimal) -> str:
    return format(value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP), "f")


def _percentage(value: Decimal) -> str:
    return _money(value)


def _constraint_number(constraints: dict[str, Any], key: str) -> Decimal | None:
    value = constraints.get(key)
    if value is None:
        return None
    return _decimal(value, f"business_constraints.{key}")


def calculate_candidate_impact(
    candidate: dict[str, Any],
    intervention: dict[str, Any],
    source: dict[str, Any],
    constraints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Calculate one intervention scenario using only versioned catalog assumptions."""
    constraints = constraints or {}
    model = intervention.get("impact_model") or {}
    if not model:
        raise ImpactModelError("intervention has no impact_model")

    baseline = _decimal(source.get("baseline_emissions_kgco2e"), "baseline_emissions_kgco2e")
    if baseline <= ZERO:
        raise ImpactModelError("baseline_emissions_kgco2e must be positive")

    avoided_fraction = _decimal(model.get("avoided_emissions_fraction"), "avoided_emissions_fraction")
    new_fraction = _decimal(
        model.get("new_intervention_emissions_fraction"),
        "new_intervention_emissions_fraction",
    )
    if avoided_fraction > Decimal(1) or new_fraction > Decimal(1):
        raise ImpactModelError("emissions fractions must be between 0 and 1")

    avoided_emissions = baseline * avoided_fraction
    new_intervention_emissions = baseline * new_fraction
    projected_emissions = baseline - avoided_emissions + new_intervention_emissions
    carbon_reduction = baseline - projected_emissions
    reduction_percentage = (carbon_reduction / baseline) * HUNDRED

    implementation_cost = _decimal(model.get("implementation_cost_inr"), "implementation_cost_inr")
    annual_operating_cost = _decimal(
        model.get("annual_operating_cost_inr"), "annual_operating_cost_inr"
    )
    annual_avoided_cost = _decimal(model.get("annual_avoided_cost_inr"), "annual_avoided_cost_inr")
    annual_savings = annual_avoided_cost - annual_operating_cost
    simple_payback_years = (
        implementation_cost / annual_savings if annual_savings > ZERO else None
    )

    budget = constraints.get("budget") or {}
    budget_limit = _constraint_number(budget, "amount") if isinstance(budget, dict) else None
    if budget_limit is None:
        budget_status = "NOT_PROVIDED"
        budget_score = Decimal(80)
    elif implementation_cost <= budget_limit:
        budget_status = "WITHIN_BUDGET"
        budget_score = HUNDRED
    else:
        budget_status = "EXCEEDS_BUDGET"
        budget_score = ZERO

    shutdown_required = _decimal(model.get("shutdown_hours_required"), "shutdown_hours_required")
    max_shutdown = _constraint_number(constraints, "max_shutdown_hours")
    if max_shutdown is None:
        operational_status = "NOT_PROVIDED"
        operational_score = Decimal(80)
    elif shutdown_required <= max_shutdown:
        operational_status = "WITHIN_CONSTRAINT"
        operational_score = HUNDRED
    else:
        operational_status = "SHUTDOWN_EXCEEDS_LIMIT"
        operational_score = ZERO

    technical_score = _decimal(model.get("technical_feasibility_score"), "technical_feasibility_score")
    circularity_score = _decimal(model.get("circularity_score"), "circularity_score")
    if technical_score > HUNDRED or circularity_score > HUNDRED:
        raise ImpactModelError("scores must be between 0 and 100")
    feasibility_score = (technical_score * Decimal("0.60")) + (budget_score * Decimal("0.25")) + (
        operational_score * Decimal("0.15")
    )

    conflicts = []
    if budget_status == "EXCEEDS_BUDGET":
        conflicts.append("implementation cost exceeds the captured budget")
    if operational_status == "SHUTDOWN_EXCEEDS_LIMIT":
        conflicts.append("required shutdown exceeds the captured operational limit")
    if conflicts:
        feasibility_status = "CONSTRAINT_CONFLICT"
    elif budget_status == "NOT_PROVIDED" or operational_status == "NOT_PROVIDED":
        feasibility_status = "REQUIRES_CONSTRAINT_REVIEW"
    else:
        feasibility_status = "VIABLE_WITHIN_CAPTURED_CONSTRAINTS"

    payback_target = _constraint_number(constraints, "target_payback_months")
    if simple_payback_years is None:
        payback_status = "NO_POSITIVE_ANNUAL_SAVINGS"
    elif payback_target is None:
        payback_status = "TARGET_NOT_PROVIDED"
    elif simple_payback_years * Decimal(12) <= payback_target:
        payback_status = "WITHIN_TARGET"
    else:
        payback_status = "EXCEEDS_TARGET"

    return {
        "projected_emissions_kgco2e": _money(projected_emissions),
        "avoided_emissions_kgco2e": _money(avoided_emissions),
        "new_intervention_emissions_kgco2e": _money(new_intervention_emissions),
        "carbon_reduction_kgco2e": _money(carbon_reduction),
        "reduction_percentage": _percentage(reduction_percentage),
        "implementation_cost_inr": _money(implementation_cost),
        "annual_avoided_cost_inr": _money(annual_avoided_cost),
        "annual_operating_cost_inr": _money(annual_operating_cost),
        "annual_savings_inr": _money(annual_savings),
        "simple_payback_years": _money(simple_payback_years) if simple_payback_years is not None else None,
        "circularity_score": _percentage(circularity_score),
        "technical_feasibility_score": _percentage(technical_score),
        "feasibility_score": _percentage(feasibility_score),
        "feasibility_status": feasibility_status,
        "budget_status": budget_status,
        "operational_status": operational_status,
        "payback_status": payback_status,
        "assumption_source": "circular-interventions-v1 impact_model",
        "impact_model_version": "layer2-impact-v1",
        "assumptions": {
            "avoided_emissions_fraction": _percentage(avoided_fraction * HUNDRED),
            "new_intervention_emissions_fraction": _percentage(new_fraction * HUNDRED),
            "shutdown_hours_required": _money(shutdown_required),
        },
    }
