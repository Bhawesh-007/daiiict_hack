"""Explainable, context-aware universal source checklist."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable


# These are source-family rules, not industry-specific checklists.  A selected
# template supplies a prior; reported facility facts and activity data override it.
KEYWORDS: dict[str, tuple[str, ...]] = {
    "stationary_fuel_combustion": ("boiler", "furnace", "oven", "generator", "heater", "burner", "kiln", "dryer", "diesel", "natural gas", "lpg", "fuel oil", "coal"),
    "mobile_fuel_combustion": ("vehicle", "truck", "forklift", "fleet", "owned transport", "company car"),
    "purchased_grid_electricity": ("electricity", "electric", "grid power", "kwh"),
    "purchased_heat_steam_cooling": ("purchased steam", "district heat", "district cooling", "purchased cooling"),
    "industrial_process_emissions": ("calcination", "clinker", "cement", "lime", "smelting", "electrolysis", "nitric acid", "ammonia", "coke oven", "chemical reaction"),
    "refrigerant_fugitive_emissions": ("cold storage", "cold room", "refrigeration", "refrigerant", "chiller", "freezer", "hvac", "air conditioning"),
    "other_fugitive_emissions": ("methane leak", "sf6", "sulfur hexafluoride", "gas leak", "pipeline leak"),
    "purchased_materials": ("raw material", "ingredient", "packaging", "material", "chemical", "feedstock", "additive"),
    "fuel_energy_related_activities": ("fuel", "electricity", "steam", "energy"),
    "upstream_transportation": ("inbound", "supplier", "receipt", "unloading", "procurement logistics", "upstream transport"),
    "downstream_transportation": ("dispatch", "delivery", "distribution", "shipment", "outbound", "downstream transport"),
    "waste_generated_in_operations": ("waste", "by-product", "scrap", "landfill", "recycle", "disposal"),
    "onsite_wastewater_treatment": ("wastewater treatment", "effluent treatment", "etp", "sewage treatment"),
    "offsite_wastewater_treatment": ("wastewater", "effluent", "cip", "cleaning", "washing", "sanitation", "wet processing"),
}

# Broad categories are plausible information gaps for almost any operating
# facility. Narrow categories require a template, mapped evidence, or a rule.
GENERIC_PLAUSIBLE = frozenset({
    "stationary_fuel_combustion", "mobile_fuel_combustion",
    "purchased_grid_electricity", "refrigerant_fugitive_emissions",
    "purchased_materials", "upstream_transportation", "downstream_transportation",
    "waste_generated_in_operations", "onsite_wastewater_treatment",
    "offsite_wastewater_treatment", "outsourced_manufacturing",
})


def _value(obj: Any, name: str, default: Any = None) -> Any:
    return obj.get(name, default) if isinstance(obj, dict) else getattr(obj, name, default)


def _text(values: Iterable[Any]) -> str:
    return " ".join(str(value or "") for value in values).lower()


def _matches(source_key: str, text: str) -> list[str]:
    return [word for word in KEYWORDS.get(source_key, ()) if word in text]


def _template_sources(template: dict[str, Any] | None) -> set[str]:
    return {
        source_key
        for process in (template or {}).get("processes", [])
        for source_key in process.get("suggested_source_type_ids", [])
    }


def build_contextual_checklist(
    *,
    assessment: Any,
    taxonomy: dict[str, dict[str, Any]],
    universal_source_keys: Iterable[str],
    template: dict[str, Any] | None = None,
    candidates: Iterable[Any] = (),
    inventory: Iterable[Any] = (),
    activity_source_ids: Iterable[Any] = (),
) -> list[dict[str, Any]]:
    """Return the complete checklist with status derived from assessment evidence.

    The function intentionally returns every master category. Consumers can hide
    NOT_APPLICABLE items, while audits still retain the exclusion reason.
    """
    processes = list(_value(assessment, "process_steps", []) or [])
    equipment = [item for process in processes for item in (_value(process, "equipment", []) or [])]
    flows = [item for process in processes for item in (_value(process, "input_output_flows", []) or [])]
    context_text = _text(
        [_value(assessment, "industry_name"), _value(assessment, "industry_code")]
        + [_value(process, "name") for process in processes]
        + [_value(process, "description") for process in processes]
        + [_value(item, "name") for item in equipment]
        + [_value(item, "equipment_type") for item in equipment]
        + [_value(item, "fuel_type") for item in equipment]
        + [_value(item, "energy_type") for item in equipment]
        + [_value(flow, "item_name") for flow in flows]
        + [_value(flow, "category") for flow in flows]
        + [_value(flow, "notes") for flow in flows]
    )
    template_source_keys = _template_sources(template)
    candidate_by_key: dict[str, list[Any]] = defaultdict(list)
    for candidate in candidates:
        if key := _value(candidate, "source_key"):
            candidate_by_key[str(key)].append(candidate)
    inventory_by_key: dict[str, list[Any]] = defaultdict(list)
    for item in inventory:
        if key := _value(item, "source_key"):
            inventory_by_key[str(key)].append(item)
    activity_ids = {str(value) for value in activity_source_ids}
    outsourced_processes = [str(_value(process, "id")) for process in processes if str(_value(process, "is_outsourced", "NO")).upper() == "YES"]
    context_is_mapped = bool(processes and (equipment or flows))

    items: list[dict[str, Any]] = []
    for source_key in universal_source_keys:
        source = taxonomy.get(source_key, {})
        source_inventory = inventory_by_key.get(source_key, [])
        source_candidates = candidate_by_key.get(source_key, [])
        inventory_statuses = {str(_value(item, "status", "")).upper() for item in source_inventory}
        has_activity = any(str(_value(item, "id")) in activity_ids for item in source_inventory)
        matches = _matches(source_key, context_text)
        has_rule_evidence = any(str(_value(candidate, "origin", "")).upper() == "RULE" for candidate in source_candidates)
        has_non_ml_candidate = any(str(_value(candidate, "origin", "")).upper() in {"RULE", "TEMPLATE", "USER"} for candidate in source_candidates)
        template_prior = source_key in template_source_keys
        is_relevant = bool(template_prior or matches or has_rule_evidence or source_inventory or has_non_ml_candidate or source_key in GENERIC_PLAUSIBLE)
        evidence_sources: list[str] = []
        if template_prior:
            evidence_sources.append("industry template")
        if matches:
            evidence_sources.append("process/equipment/flow map")
        if has_rule_evidence:
            evidence_sources.append("rule engine")
        if source_candidates:
            evidence_sources.append("source review")
        if source_inventory:
            evidence_sources.append("reviewed inventory")
        if has_activity:
            evidence_sources.append("activity data")

        if source_key == "outsourced_manufacturing" and outsourced_processes:
            status = "OUTSOURCED"
            reason = "One or more process steps are marked as outsourced; retain this as a value-chain source."
        elif has_activity:
            status = "CONFIRMED"
            reason = "Activity data was recorded for this source."
        elif "CONFIRMED" in inventory_statuses:
            status = "CONFIRMED"
            reason = "This source was confirmed in the reviewed inventory."
        elif "OUTSOURCED" in inventory_statuses:
            status = "OUTSOURCED"
            reason = "This source was marked as outsourced in the reviewed inventory."
        elif "NOT_APPLICABLE" in inventory_statuses:
            status = "NOT_APPLICABLE"
            reason = next((str(_value(item, "confirmation_note")) for item in source_inventory if _value(item, "confirmation_note")), "This source was excluded during inventory review.")
        elif matches or has_rule_evidence:
            status = "POTENTIAL"
            matched = ", ".join(matches[:3])
            reason = f"Relevant evidence was found in the facility map{f': {matched}' if matched else ' by the rule engine'}; verify activity data."
        # A template is a prior, never proof. Industrial-process emissions are
        # deliberately excluded here: a generic industry template cannot make
        # them relevant without evidence of a direct chemical GHG process.
        elif template_prior and source_key != "industrial_process_emissions":
            status = "POTENTIAL"
            reason = "The selected industry template identifies this as commonly relevant; confirm it for this facility."
        elif source_key == "stationary_fuel_combustion" and context_is_mapped:
            status = "NOT_APPLICABLE"
            reason = "The mapped equipment and inputs show no onsite fuel-burning equipment or fuel use."
        elif source_key == "industrial_process_emissions" and context_is_mapped:
            status = "NOT_APPLICABLE"
            reason = "No direct chemical transformation associated with process greenhouse-gas emissions was found."
        elif source_key == "outsourced_manufacturing" and processes:
            status = "NOT_APPLICABLE"
            reason = "All mapped process steps are recorded as operated onsite."
        elif has_non_ml_candidate:
            status = "POTENTIAL"
            reason = "A source suggestion exists for this assessment; verify it against facility records."
        else:
            status = "MISSING_INFORMATION"
            reason = "The available assessment context is insufficient to confirm or reasonably exclude this source."

        items.append({
            "assessment_id": str(_value(assessment, "id")),
            "source_key": source_key,
            "label": source.get("name", source_key),
            "status": status,
            "required_fields": source.get("minimum_data", ["activity_quantity", "activity_unit", "reporting_period"]),
            "reason": reason,
            "candidate_ids": [str(_value(candidate, "id")) for candidate in source_candidates if _value(candidate, "id")],
            "metadata": {
                "evidence_sources": list(dict.fromkeys(evidence_sources)),
                "matched_terms": matches,
                "template_prior": template_prior,
                "is_relevant": is_relevant,
            },
        })
    return items
