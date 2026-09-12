"""Deterministic Layer 2 Phase 1 matching and eligibility logic."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from app.layer2.impact import ImpactModelError, calculate_candidate_impact


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(0)


def _normalized(value: Any) -> str:
    return str(value or "").strip().upper().replace("-", "_").replace(" ", "_")


def _source_priority(source: dict[str, Any]) -> Decimal:
    contribution = _decimal(source.get("contribution_percentage"))
    if contribution > 0:
        return contribution
    return _decimal(source.get("baseline_emissions_kgco2e"))


def _matches(source: dict[str, Any], intervention: dict[str, Any]) -> tuple[bool, list[str]]:
    source_key = str(source.get("source_key") or "")
    source_category = str(source.get("source_category") or "")
    equipment = source.get("equipment") or {}
    equipment_type = _normalized(equipment.get("equipment_type"))

    reasons: list[str] = []
    if source_key in intervention.get("target_source_keys", []):
        reasons.append(f"source key matches {source_key}")
    if source_category in intervention.get("target_source_categories", []):
        reasons.append(f"source category matches {source_category}")
    target_equipment_types = {_normalized(value) for value in intervention.get("target_equipment_types", [])}
    if equipment_type and equipment_type in target_equipment_types:
        reasons.append(f"equipment type matches {equipment_type}")
    return bool(reasons), reasons


def generate_recommendations(profile: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    """Return candidate interventions without calculating impact or cost."""
    sources = list(profile.get("sources") or [])
    interventions = list(catalog.get("interventions") or [])
    recommendations: list[dict[str, Any]] = []
    excluded_sources: list[dict[str, Any]] = []

    for source in sources:
        source_id = source.get("source_id")
        source_name = source.get("source_name") or source.get("source_key")
        if source.get("status") != "CONFIRMED" or source.get("confirmed_source_identity") is not True:
            excluded_sources.append({
                "source_id": source_id,
                "source_name": source_name,
                "reason": "SOURCE_NOT_CONFIRMED",
            })
            continue
        if not source.get("activity_records"):
            excluded_sources.append({
                "source_id": source_id,
                "source_name": source_name,
                "reason": "ACTIVITY_DATA_MISSING",
            })
            continue
        if _decimal(source.get("baseline_emissions_kgco2e")) <= 0:
            excluded_sources.append({
                "source_id": source_id,
                "source_name": source_name,
                "reason": "BASELINE_EMISSIONS_NOT_POSITIVE",
            })
            continue

        matched = False
        priority = _source_priority(source)
        for intervention in interventions:
            does_match, reasons = _matches(source, intervention)
            if not does_match:
                continue
            matched = True
            recommendations.append({
                "recommendation_id": f"{intervention['intervention_id']}:{source_id}",
                "intervention_id": intervention["intervention_id"],
                "intervention_name": intervention["name"],
                "short_description": intervention["short_description"],
                "intervention_type": intervention["intervention_type"],
                "circularity_dimension": intervention["circularity_dimension"],
                "source_id": source_id,
                "source_key": source.get("source_key"),
                "source_name": source_name,
                "baseline_emissions_kgco2e": source.get("baseline_emissions_kgco2e"),
                "contribution_percentage": source.get("contribution_percentage", "0"),
                "hotspot_priority": str(priority),
                "match_reasons": reasons,
                "required_conditions": intervention.get("required_conditions", []),
                "required_evidence": intervention.get("required_evidence", []),
                "eligibility_status": "ELIGIBLE_FOR_IMPACT_MODELING",
                "impact_status": "PENDING_PHASE_2_IMPACT_MODEL",
                "catalog_version": catalog["catalog_version"],
            })
        if not matched:
            excluded_sources.append({
                "source_id": source_id,
                "source_name": source_name,
                "reason": "NO_CATALOG_MATCH",
            })

    recommendations.sort(
        key=lambda item: (
            -_decimal(item["hotspot_priority"]),
            -int(next(
                intervention.get("priority", 0)
                for intervention in interventions
                if intervention.get("intervention_id") == item["intervention_id"]
            )),
            item["intervention_id"],
            item["source_id"],
        )
    )
    for index, item in enumerate(recommendations, start=1):
        item["rank"] = index

    return {
        "schema_version": "layer2-recommendation-candidates-v1",
        "engine_version": "layer2-rules-v1",
        "catalog_id": catalog["catalog_id"],
        "catalog_version": catalog["catalog_version"],
        "profile_id": profile.get("profile_id"),
        "profile_version": profile.get("profile_version"),
        "assessment_id": profile.get("assessment_id"),
        "status": "CANDIDATES_READY",
        "recommendation_count": len(recommendations),
        "recommendations": recommendations,
        "excluded_sources": excluded_sources,
        "limitations": [
            "Candidate generation is deterministic and rule-based in Phase 1.",
            "No projected emissions, cost, savings, payback or portfolio optimization is calculated yet.",
            "Every candidate must pass impact modeling and evidence review before being presented as a quantified intervention.",
        ],
    }


def generate_impact_recommendations(profile: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    """Generate candidates and attach deterministic impact and feasibility scenarios."""
    result = generate_recommendations(profile, catalog)
    sources = {str(source.get("source_id")): source for source in profile.get("sources") or []}
    interventions = {
        str(intervention.get("intervention_id")): intervention
        for intervention in catalog.get("interventions") or []
    }
    constraints = profile.get("business_constraints") or {}
    evaluated: list[dict[str, Any]] = []

    for candidate in result["recommendations"]:
        source = sources.get(str(candidate["source_id"]))
        intervention = interventions.get(str(candidate["intervention_id"]))
        if source is None or intervention is None:
            candidate["impact_status"] = "IMPACT_MODEL_UNAVAILABLE"
            evaluated.append(candidate)
            continue
        try:
            impact = calculate_candidate_impact(candidate, intervention, source, constraints)
        except ImpactModelError as exc:
            candidate["impact_status"] = "IMPACT_MODEL_ERROR"
            candidate["impact_error"] = str(exc)
        else:
            candidate.update(impact)
            candidate["impact_status"] = "CALCULATED_DETERMINISTICALLY"
        evaluated.append(candidate)

    evaluated.sort(
        key=lambda item: (
            0 if item.get("feasibility_status") == "VIABLE_WITHIN_CAPTURED_CONSTRAINTS" else 1,
            -_decimal(item.get("carbon_reduction_kgco2e")),
            -_decimal(item.get("feasibility_score")),
            item["intervention_id"],
            item["source_id"],
        )
    )
    for index, item in enumerate(evaluated, start=1):
        item["rank"] = index

    result.update(
        {
            "phase": "PHASE_2_IMPACT_AND_FEASIBILITY",
            "engine_version": "layer2-impact-v1",
            "recommendations": evaluated,
            "limitations": [
                "ML ranking and portfolio optimization are not used in Phase 2.",
                "Impact, cost, savings and feasibility values are catalog-based estimates.",
                "Evidence review is required before treating a scenario as an implementation decision.",
            ],
            "impact_assumption_notice": (
                "Impact, cost and feasibility values are deterministic estimates from the versioned "
                "catalog assumptions and require evidence review before deployment decisions."
            ),
        }
    )
    return result
