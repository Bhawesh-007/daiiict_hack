# Rule Engine and ML Suggestion Test Plan

## Objective

Verify that the rule-based engine and ML suggestion layer identify expected emission sources, reject invalid suggestions, preserve user-confirmed data, remain idempotent, and continue working when ML is unavailable.

This plan covers source identification only. It does not test activity-data collection, emission-factor resolution, emissions calculation, aggregation, or final profile generation.

## System under test

```text
RuleEngine
SourceIdentificationModel
MLAdapter
IdentificationOrchestrator
Candidate merger
Source review/inventory endpoint
```

Relevant implementation paths:

```text
services/identification-api/app/identification/rule_engine.py
services/identification-api/app/identification/ml_model.py
services/identification-api/app/identification/ml_adapter.py
services/identification-api/app/identification/orchestrator.py
services/identification-api/app/identification/candidate_merger.py
services/identification-api/app/api/identification.py
```

## Test setup

1. Use the project virtual environment.
2. Load the versioned source taxonomy and ruleset.
3. Use a seeded assessment with a valid facility, process, equipment, and flow context.
4. Use UUIDs for process and equipment identifiers.
5. Start with ML enabled for ML tests and inject a failing adapter for failure tests.
6. Clear or isolate candidate and identification-run records for each test unless the test explicitly checks persistence or idempotency.

Suggested command:

```bash
cd services/identification-api
.venv/bin/pytest -q --disable-warnings
```

## Common assertions

Every generated candidate must:

- Reference a known `source_key` from the taxonomy.
- Include process/equipment context when available.
- Have an explanation in `reason`.
- Remain a proposal until user review.
- Preserve origin and evidence metadata.

ML must not write to or change a confirmed `SourceInventoryItem`.

## Test cases

### T01 — Diesel boiler produces stationary-combustion suggestion

**Input**

```json
{
  "fact_type": "equipment",
  "process_step_id": "<process_uuid>",
  "equipment_id": "<equipment_uuid>",
  "equipment_type": "boiler",
  "fuel_type": "diesel"
}
```

**Execute**

- Run the rule engine with the fact.
- Run the ML adapter with text containing `diesel boiler`.

**Expected**

- Rule output contains `stationary_fuel_combustion`.
- ML output contains `stationary_fuel_combustion`.
- Candidate context contains the same process and equipment IDs.
- Rule candidate contains rule ID and rule version.
- ML candidate contains model ID and model version.

### T02 — Cold room produces refrigerant suggestion

**Input**

```text
Finished products are stored in a cold room.
```

**Expected**

- ML output contains `refrigerant_fugitive_emissions`.
- The candidate explanation mentions refrigeration/cooling equipment.
- Follow-up questions include:

```text
Which refrigerant is used?
How much refrigerant was refilled?
Was leakage detected?
```

### T03 — Electricity bill text produces purchased-electricity suggestion

**Input**

```text
The facility purchases grid electricity and the monthly electricity bill is available.
```

**Expected**

- ML output contains `purchased_grid_electricity`.
- The candidate origin is `ML`.
- The candidate has a confidence value between 0 and 1.
- The evidence contains the model version and the input context.

If the text is passed as a structured energy fact, the rule engine should also produce `purchased_grid_electricity` when `consumed_by_facility=true`.

### T04 — Unrelated text produces no candidate

**Input**

```text
The office held an administrative meeting about employee attendance.
```

**Expected**

- ML returns an empty candidate list.
- No source inventory item is created.
- No candidate is persisted for the unrelated text.

### T05 — Unknown source keys are rejected

**Input**

Create an ML suggestion or candidate with:

```json
{
  "source_key": "made_up_emission_source",
  "origin": "ML"
}
```

**Expected**

- Schema validation rejects the payload.
- The API returns a validation error when submitted through the API.
- No candidate is persisted.
- No candidate merger output contains the unknown key.

### T06 — ML candidates remain proposed

**Execute**

- Run ML identification for a diesel boiler or cold room.
- Inspect the returned candidate and persisted `SourceCandidate`.

**Expected**

- Origin is `ML`.
- Status is `PROPOSED` before user review.
- ML cannot return `CONFIRMED`, `PROMOTED`, or a reviewed inventory status.
- The candidate may be merged with other origins, but merging does not confirm it.

### T07 — ML cannot modify confirmed inventory

**Setup**

1. Create an ML candidate.
2. Review it as `CONFIRMED` with reviewer and timestamp metadata.
3. Save the confirmed `SourceInventoryItem`.

**Execute**

- Run ML again with changed or repeated text for the same source.

**Expected**

- The confirmed inventory status remains `CONFIRMED`.
- Reviewer, confirmation timestamp, and confirmation note remain unchanged.
- ML may create a separate proposal or identification run, but cannot overwrite the inventory item.
- No ML response contains a confirmed inventory status.

### T08 — Repeated ML execution does not create duplicates

**Setup**

- Use the same assessment snapshot, process/equipment records, template version, ruleset version, and ML setting.

**Execute**

1. Run identification with ML enabled.
2. Record the run ID, input hash, and candidate IDs/count.
3. Run identification again without changing the input snapshot.

**Expected**

- The second execution returns the existing completed run or an equivalent idempotent result.
- The input hash is identical.
- Candidate count is unchanged.
- No duplicate candidates are created for the same source/process/equipment context.
- Candidate origins, reasons, model version, and evidence remain stable.

### T09 — Identification completes when ML fails

**Setup**

Inject an adapter whose `identify` method raises an exception or `MLUnavailableError`.

**Execute**

- Run identification with ML enabled.

**Expected**

- Identification run completes successfully.
- Run status is `COMPLETED`.
- ML status is `UNAVAILABLE`.
- The response records the ML failure without exposing sensitive input data.
- Rule and template candidates are still persisted.
- Checklist generation still completes.

### T10 — Rule and template results remain available without ML

**Setup**

- Use the seeded food-processing assessment.
- Disable ML or call identification with `include_ml=false`.

**Execute**

- Run identification.
- Read the candidates and identification-run detail.

**Expected**

- Identification run status is `COMPLETED`.
- Template candidates are present where the selected process matches the industry template.
- Rule candidates are present where structured facts match the ruleset.
- ML candidate count is zero.
- ML status is `DISABLED`.
- Candidate origins contain `TEMPLATE` and/or `RULE`, never `ML`.
- The universal checklist is still returned.

## Additional regression checks

Run these checks after the required tests:

- Same source in different equipment contexts is not incorrectly merged.
- Same source in different process contexts is not incorrectly merged.
- Multiple rule triggers preserve every reason and rule version.
- Candidate output ordering is deterministic across repeated runs.
- ML extraction preserves process and equipment context.
- A missing ML provider does not block rule-only identification.
- Template suggestions remain editable and are never automatically confirmed.

## Pass criteria

The pre-calculation identification layer passes when:

1. T01–T10 pass.
2. No test shows ML modifying confirmed inventory.
3. No unknown source key reaches persistence.
4. ML failure still produces a completed rule/template run.
5. Repeated identical runs do not create duplicate persisted results.

Any failure involving confirmation, data mutation, unknown taxonomy keys, or duplicate runs is a blocking failure for the ML integration.
