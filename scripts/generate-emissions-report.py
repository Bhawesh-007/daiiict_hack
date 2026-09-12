#!/usr/bin/env python3
"""Generate a complete emissions report from a raw activity CSV file.

Usage:
    python scripts/generate-emissions-report.py [path/to/activity.csv]
"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

# Add services/identification-api to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
API_DIR = PROJECT_ROOT / "services" / "identification-api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from app.calculations.engine import CalculationInput, run_calculation_pipeline
from app.calculations.factor_resolver import AmbiguousFactorError, resolve_factor
from app.calculations.unit_converter import convert_to_base
from app.domain.activities.file_import import parse_csv

DEFAULT_CSV = PROJECT_ROOT / "data" / "demo" / "demo-activity-data.csv"
FACTORS_PATH = PROJECT_ROOT / "data" / "emission-factors" / "demo-factors.json"


class MockFactor:
    def __init__(self, data: dict):
        self.factor_code = data["factor_id"]
        self.version = data["factor_version"]
        self.name = data["name"]
        self.source_category = data["activity_category"]
        self.scope = (
            "SCOPE_1"
            if "SCOPE_1" in data["scope_or_boundary"]
            else ("SCOPE_2" if "SCOPE_2" in data["scope_or_boundary"] else "SCOPE_3")
        )
        self.factor_value = Decimal(str(data["factor_value"]))
        self.activity_unit = data["input_unit"]
        self.emission_unit = data["output_unit"]
        self.geography = data["geography"]["country"]
        self.valid_from = None
        self.valid_to = None
        self.metadata_json = data


def load_factors() -> list[MockFactor]:
    doc = json.loads(FACTORS_PATH.read_text(encoding="utf-8"))
    return [MockFactor(f) for f in doc.get("factors", [])]


def resolve_factor_smart(
    factors: list[MockFactor],
    source_key: str,
    unit: str,
    notes: str | None = None,
) -> MockFactor | None:
    try:
        return resolve_factor(
            factors,
            source_key=source_key,
            activity_unit=unit,
            geography="India",
        )
    except AmbiguousFactorError:
        note_str = (notes or "").lower()
        candidates = [
            f for f in factors
            if source_key in f.metadata_json.get("compatible_source_type_ids", [])
            and f.activity_unit == unit
        ]
        for cand in candidates:
            cand_name = cand.name.lower()
            cat = cand.source_category.lower().replace("_", " ")
            keywords = [w for w in (cand_name + " " + cat).split() if len(w) > 3]
            if any(kw in note_str for kw in keywords):
                return cand
        return candidates[0] if candidates else None
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate final emissions report from raw CSV")
    parser.add_argument("csv_path", nargs="?", default=str(DEFAULT_CSV), help="Path to raw CSV file")
    parser.add_argument("--output", "-o", default="final_emissions_report.md", help="Output markdown report path")
    args = parser.parse_args()

    csv_file = Path(args.csv_path)
    if not csv_file.exists():
        print(f"Error: File not found: {csv_file}", file=sys.stderr)
        return 1

    payload = csv_file.read_bytes()
    rows = parse_csv(payload)
    factors = load_factors()

    inputs: list[CalculationInput] = []
    source_defaults = {
        "purchased_grid_electricity": ("Purchased grid electricity", "purchased_energy", "SCOPE_2"),
        "stationary_fuel_combustion": ("Stationary fuel combustion", "stationary_combustion", "SCOPE_1"),
        "mobile_fuel_combustion": ("Mobile fuel combustion", "mobile_combustion", "SCOPE_1"),
        "refrigerant_fugitive_emissions": ("Refrigerant leakage and release", "fugitive_emissions", "SCOPE_1"),
        "purchased_materials": ("Purchased packaging and raw materials", "purchased_goods_services", "SCOPE_3"),
        "waste_generated_in_operations": ("Waste generated in operations", "waste", "SCOPE_3"),
        "downstream_transportation": ("Downstream transportation and distribution", "transportation_distribution", "SCOPE_3"),
    }

    for i, r in enumerate(rows, start=1):
        conv = convert_to_base(r.quantity, r.unit_code)
        factor = resolve_factor_smart(factors, r.source_reference, conv.normalized_unit, r.notes)
        sname, scat, sscope = source_defaults.get(
            r.source_reference,
            (r.source_reference.replace("_", " ").capitalize(), "unspecified", "SCOPE_1"),
        )
        if factor and factor.scope:
            sscope = factor.scope

        inputs.append(
            CalculationInput(
                source_inventory_item_id=f"src-{r.source_reference}",
                activity_record_id=f"act-{i:03d}",
                emission_factor_id=factor.factor_code if factor else None,
                source_name=sname,
                source_category=scat,
                source_status="CONFIRMED",
                scope=sscope,
                original_quantity=r.quantity,
                original_unit=r.unit_code,
                normalized_quantity=conv.normalized_quantity,
                normalized_unit=conv.normalized_unit,
                conversion_multiplier=conv.normalization_multiplier,
                factor_value=factor.factor_value if factor else None,
                factor_unit=factor.activity_unit if factor else None,
                factor_version=factor.version if factor else None,
                factor_category=scat if factor else None,
                factor_scope=factor.scope if factor else None,
            )
        )

    # Run pure calculation engine pipeline
    result = run_calculation_pipeline(inputs, production_quantity=Decimal("50000"))

    total_kg = result.total_emissions
    total_t = (total_kg / Decimal(1000)).quantize(Decimal("0.001"))

    # Print Report to Console
    print("=" * 80)
    print("           EMISSIONLENS — FINAL EMISSIONS REPORT")
    print("=" * 80)
    print(f"Source File: {csv_file.name} ({len(rows)} activity rows)")
    print(f"Total Quantified GHG Emissions: {total_kg:,.2f} kgCO2e  ({total_t} tCO2e)")
    print(f"Completeness Status: {result.status}")
    print("-" * 80)

    print("\n[1] GHG SCOPE BREAKDOWN")
    print("-" * 80)
    for scope in ["SCOPE_1", "SCOPE_2", "SCOPE_3"]:
        amt = result.scope_totals.get(scope, Decimal(0))
        pct = (amt * Decimal(100) / total_kg).quantize(Decimal("0.1")) if total_kg > 0 else Decimal(0)
        t_val = (amt / Decimal(1000)).quantize(Decimal("0.001"))
        print(f"  {scope:<10}: {amt:>14,.2f} kgCO2e ({t_val:>9} tCO2e) | {pct:>5.1f}%")

    print("\n[2] TOP QUANTIFIED EMISSION SOURCES (HOTSPOTS)")
    print("-" * 80)
    for s in result.hotspot_ranking.get("top_sources", []):
        pct = Decimal(str(s.get("percentage", 0))).quantize(Decimal("0.1"))
        amt = Decimal(str(s.get("emissions_kgco2e", 0)))
        print(f"  #{s['rank']} {s['label']:<40} : {amt:>12,.2f} kgCO2e ({pct:>5.1f}%)")

    print("\n[3] DETAILED LINE-ITEM LEDGER")
    print("-" * 80)
    print(f"{'Source':<32} {'Scope':<9} {'Activity':<18} {'Factor':<16} {'Emissions (kgCO2e)':>18}")
    print("-" * 80)
    for line in result.line_items:
        act_str = f"{line.normalized_quantity:,.1f} {line.normalized_unit}"
        fac_str = f"{line.factor_value_snapshot} kg/{line.factor_unit_snapshot}"
        print(f"{line.source_name[:30]:<32} {line.scope:<9} {act_str:<18} {fac_str:<16} {line.emissions_kgco2e:>18,.2f}")
    print("-" * 80)

    # Generate Markdown Report File
    lines_md = []
    for line in result.line_items:
        lines_md.append(
            f"| {line.source_name} | `{line.scope}` | {line.original_quantity} {line.original_unit} | {line.normalized_quantity:,.1f} {line.normalized_unit} | {line.factor_value_snapshot} ({line.factor_version}) | **{line.emissions_kgco2e:,.2f}** |"
        )

    hotspots_md = []
    for s in result.hotspot_ranking.get("top_sources", []):
        pct = Decimal(str(s.get("percentage", 0))).quantize(Decimal("0.1"))
        amt = Decimal(str(s.get("emissions_kgco2e", 0)))
        hotspots_md.append(f"- **Rank {s['rank']}**: {s['label']} — **{amt:,.2f} kgCO₂e** ({pct}% of total)")

    scope_md = []
    for scope in ["SCOPE_1", "SCOPE_2", "SCOPE_3"]:
        amt = result.scope_totals.get(scope, Decimal(0))
        pct = (amt * Decimal(100) / total_kg).quantize(Decimal("0.1")) if total_kg > 0 else Decimal(0)
        scope_md.append(f"| **{scope}** | {amt:,.2f} kgCO₂e | {(amt/1000):,.3f} tCO₂e | **{pct}%** |")

    md_content = f"""# Final Emissions Report

**Source Activity File:** `{csv_file.name}`  
**Generated At:** {sys.version.split()[0]} Environment  
**Completeness Status:** `{result.status}`  

---

## Executive Summary

- **Total Quantified Emissions:** **{total_kg:,.2f} kgCO₂e** (**{total_t:,.3f} tCO₂e**)
- **Quantified Line Items:** {len(result.line_items)} of {len(rows)}
- **Unquantified Gaps:** {len(result.unquantified_sources)}

### Emissions by Scope

| Scope | Emissions (kgCO₂e) | Emissions (tCO₂e) | % Contribution |
| :--- | :---: | :---: | :---: |
{chr(10).join(scope_md)}

---

## Top Quantified Emission Sources (Hotspots)

{chr(10).join(hotspots_md)}

---

## Line-Item Calculation Ledger

| Source | Scope | Original Activity | Normalized Activity | Emission Factor | Emissions (kgCO₂e) |
| :--- | :---: | :---: | :---: | :---: | :---: |
{chr(10).join(lines_md)}

---

*Report generated deterministically using pure Decimal arithmetic.*
"""

    out_file = PROJECT_ROOT / args.output
    out_file.write_text(md_content, encoding="utf-8")
    print(f"\nSaved Markdown Report to: {out_file.resolve()}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
