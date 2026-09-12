# Rule-Based Source Identification Engine

## Purpose

The rule engine converts structured assessment facts into explained potential emission-source candidates.

It is deterministic: the same facts and the same ruleset produce the same candidates. It does not confirm sources, collect activity data, resolve emission factors, or calculate emissions.

## Input

The engine accepts either a list of normalized facts or an assessment mapping containing:

- `processes`
- `equipment`
- `flows`

Each fact may include:

- `fact_type`
- `process_step_id`
- `equipment_id`
- Fact attributes such as equipment type, fuel type, energy type, ownership, treatment location, or value-chain position

Flow facts are normalized into fact types using their category:

| Flow category | Normalized fact type |
|---|---|
| Energy, electricity, fuel, heat, steam, cooling | `energy_input` |
| Material, chemical, packaging, raw material | `material_input` |
| Transport or distribution | `transport_activity` |
| Wastewater or effluent | `wastewater_stream` |
| Waste, solid waste or sludge | `waste_stream` |
| Other | `flow` |

For energy-input flows, the engine derives `energy_type`, `consumed_by_facility`, and `purchased` where the input direction provides enough information.

## Rule configuration

Rules are stored in:

```text
data/rules/source-identification-rules.json
```

Current ruleset:

```text
Ruleset ID: source-identification-rules
Version: 1.0.0
Status: DEMO_ACTIVE
```

Every rule contains:

- Rule ID
- Rule version
- Active/inactive status
- Priority
- Fact type
- Match mode: `ALL` or `ANY`
- Conditions
- Suggested source type
- Provisional scope
- User-facing reason
- Follow-up questions

Inactive rules are ignored. Active rules are validated when the engine starts.

## Supported condition operators

The engine supports these operators:

| Operator | Meaning |
|---|---|
| `EQUALS` | The field equals the configured value. |
| `IN` | The field value is one of the configured values. |
| `PRESENT` | The field has a non-empty value. |
| `TRUE` | The field represents true, including `true`, `yes`, `y`, or `1`. |
| `CONTAINS_ANY` | A list or scalar field contains at least one configured value. |

Missing or empty values do not match `PRESENT`, and normally cause the rule to return no match.

## Configured rules

### SRC-RULE-001 — Purchased grid electricity

- Fact type: `energy_input`
- Conditions:
  - `energy_type` equals `purchased_grid_electricity`
  - `consumed_by_facility` is true
- Source: `purchased_grid_electricity`
- Provisional scope: `SCOPE_2`
- Follow-up: electricity bills, meter records, onsite generation, exported electricity, and renewable-electricity records

### SRC-RULE-002 — Purchased heat, steam or cooling

- Fact type: `energy_input`
- Conditions:
  - `energy_type` is `purchased_heat`, `purchased_steam`, or `purchased_cooling`
  - `consumed_by_facility` is true
- Source: `purchased_heat_steam_cooling`
- Provisional scope: `SCOPE_2`
- Follow-up: supplier, billed unit, supplier factor, and boundary description

### SRC-RULE-003 — Stationary fuel combustion

- Fact type: `equipment`
- Conditions:
  - Equipment is a boiler, steam generator, furnace, oven, fryer, dryer, stenter, thermic-fluid heater, kiln, diesel generator, or generator
  - `fuel_type` is present
- Source: `stationary_fuel_combustion`
- Provisional scope: `REQUIRES_CONTROL_REVIEW`
- Follow-up: ownership/control, fuel quantity, and equipment-specific records

### SRC-RULE-004 — Mobile fuel combustion

- Fact type: `vehicle`
- Conditions:
  - `ownership_or_control` is `owned` or `operationally_controlled`
  - `fuel_type` is present
- Source: `mobile_fuel_combustion`
- Provisional scope: `SCOPE_1`
- Follow-up: fuel quantity or distance and duplicate-record check

### SRC-RULE-005 — Refrigerant fugitive emissions

- Fact type: `equipment`
- Conditions:
  - Equipment is a refrigeration system, chilling unit, cold room, chiller, air conditioner, or heat pump; or
  - `contained_gases` contains refrigerant, HFC, or PFC
- Source: `refrigerant_fugitive_emissions`
- Provisional scope: `REQUIRES_CONTROL_REVIEW`
- Follow-up: refrigerant type, charge, additions, recovery, disposal, transfer, and maintenance records

### SRC-RULE-006 — Industrial process emissions

- Fact type: `process`
- Conditions:
  - `direct_ghg_release` is true; or
  - `emission_mechanism` is chemical reaction, biological reaction, calcination, fermentation, carbonate use, or process venting
- Source: `industrial_process_emissions`
- Provisional scope: `REQUIRES_CONTROL_REVIEW`
- Follow-up: gas released, mechanism, process activity, and material-balance data

### SRC-RULE-007 — Purchased materials

- Fact type: `material_input`
- Conditions:
  - `purchased` is true
  - `material_type` is present
- Source: `purchased_materials`
- Provisional scope: `SCOPE_3_CATEGORY_1`
- Follow-up: purchased quantity, material specification, recycled content, and supplier data

### SRC-RULE-008 — Upstream transportation

- Fact type: `transport_activity`
- Conditions:
  - `provider_control` equals `third_party`
  - `value_chain_position` equals `upstream`
- Source: `upstream_transportation`
- Provisional scope: `SCOPE_3_CATEGORY_4`
- Follow-up: transport arranger/payer, mass, distance, route, and mode

### SRC-RULE-009 — Downstream transportation

- Fact type: `transport_activity`
- Conditions:
  - `provider_control` equals `third_party`
  - `value_chain_position` equals `downstream`
- Source: `downstream_transportation`
- Provisional scope: `REQUIRES_CATEGORY_REVIEW`
- Follow-up: transport arranger/payer, mass, distance, route, and mode

### SRC-RULE-010 — Waste generated in operations

- Fact type: `waste_stream`
- Conditions:
  - `generated_by_facility` is true
  - `treatment_location` equals `offsite`
- Source: `waste_generated_in_operations`
- Provisional scope: `SCOPE_3_CATEGORY_5`
- Follow-up: quantity by treatment route and contractor evidence

### SRC-RULE-011 — Onsite wastewater treatment

- Fact type: `wastewater_stream`
- Conditions:
  - `generated_by_facility` is true
  - `treatment_location` equals `onsite`
- Source: `onsite_wastewater_treatment`
- Provisional scope: `REQUIRES_CONTROL_REVIEW`
- Follow-up: technology, volume, COD, BOD, methane recovery, and sludge records

### SRC-RULE-012 — Offsite wastewater treatment

- Fact type: `wastewater_stream`
- Conditions:
  - `generated_by_facility` is true
  - `treatment_location` equals `offsite`
- Source: `offsite_wastewater_treatment`
- Provisional scope: `SCOPE_3_CATEGORY_5`
- Follow-up: volume, treatment route, and utility/contractor record

### SRC-RULE-013 — Outsourced manufacturing or processing

- Fact type: `outsourced_activity`
- Conditions:
  - `performed_by_third_party` is true
  - `activity_type` is manufacturing, processing, packaging, washing, maintenance, or treatment
- Source: `outsourced_manufacturing`
- Provisional scope: `REQUIRES_CATEGORY_REVIEW`
- Follow-up: supplier, purchased output/service quantity, and supplier emissions data

### SRC-RULE-014 — Other fugitive emissions

- Fact type: `equipment`
- Conditions:
  - `contained_gases` is present
  - `release_possible` is true
- Source: `other_fugitive_emissions`
- Provisional scope: `REQUIRES_CONTROL_REVIEW`
- Follow-up: gases present, greenhouse-gas classification, inventory, refill, transfer, and incident records

## Evaluation algorithm

For each input fact:

1. Normalize its fact type and attributes.
2. Sort active rules by descending priority and then by rule ID.
3. Ignore rules whose `fact_type` differs from the fact type.
4. Evaluate every condition using its configured operator.
5. For `ALL`, require every condition to match.
6. For `ANY`, require at least one condition to match.
7. If the rule does not match, produce no candidate.
8. If the rule matches, resolve the source type from the taxonomy.
9. Render placeholders in reasons and follow-up questions using fact values.
10. Create one explained `RULE` candidate.

The engine validates that every configured source type exists in the taxonomy and that every operator is supported before evaluation begins.

## Candidate output

Each matching rule produces a candidate with:

- `source_key`
- `source_name`
- `source_category`
- `suggested_scope`
- `process_step_id`
- `equipment_id`
- `origin: RULE`
- `status: POTENTIAL`
- `persistence_status: PROPOSED`
- `reason`
- `confidence`, when configured
- `rule_id`
- `rule_version`
- `follow_up_questions`
- `evidence_json`

The evidence contains the ruleset version, fact type, rule ID, rule version, matched fields, operators, values, and rendered follow-up questions.

## Candidate identity and deduplication

The engine assigns a deterministic candidate key using:

```text
source_type | process_step_id | equipment_id | value_chain_position
```

Missing context is represented by `-`. The key lets the later merger combine repeated rule matches with template, checklist, ML, or user origins without combining different process or equipment contexts.

The rule engine may emit multiple candidates for the same key when multiple rules match. The candidate merger combines them while preserving every reason, rule ID, rule version, and evidence record.

## Safety boundary

Rule output means:

```text
This source should be reviewed.
```

It does not mean:

```text
This source is confirmed.
```

Only the user-review endpoint can create or update a reviewed source-inventory item. Activity collection, factor selection, calculations, aggregation, ranking, and final profile generation occur after review in later pipeline stages.

## Failure behavior

- Missing fields result in no match.
- Unknown source types make the ruleset invalid.
- Unsupported operators make the ruleset invalid.
- Invalid rule configuration raises a configuration error before candidates are generated.
- The rule engine has no database or ML dependency.
- Rule identification can therefore continue when the ML provider is unavailable.

## Current implementation

The implementation is located at:

```text
services/identification-api/app/identification/rule_engine.py
```

The rules are configured in the JSON ruleset rather than hard-coded in Python. This allows industry-specific rules to be added or disabled through versioned configuration while keeping one common evaluation engine.
