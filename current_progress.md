# EmissionLens current project progress

Status reviewed on 15 September 2026 from the current working tree. This report describes what is implemented now; it is not a future plan.

## Overall status

The repository contains a working Layer 1 prototype and an initial Layer 2 recommendation prototype.

```text
Layer 1 identification ........ implemented
Layer 1 activity/calculation .. implemented
Layer 1 finalized profile ..... implemented
Layer 2 rule matching ......... implemented
Layer 2 impact/feasibility .... implemented in memory
Layer 2 ML ranking ............ adapter implemented; model not trained
Layer 2 persistence ........... not implemented
Layer 2 portfolio optimization not implemented
```

## Layer 1: assessment and identification

Implemented backend capabilities:

- Company and facility creation/read APIs.
- Assessment creation/read with industry, product, reporting period and boundaries.
- Industry-template and source-type knowledge APIs.
- Template loading into editable process suggestions.
- Process-step persistence and retrieval.
- Equipment persistence per process.
- Input/output flow persistence per process.
- Rule-based candidate generation from normalized process, equipment and flow facts.
- Local deterministic ML suggestion adapter.
- Structured extraction for process, equipment, fuel, energy, refrigerant, material, waste, wastewater, transport and outsourced activity entities.
- Follow-up questions for contextual suggestions.
- Candidate deterministic merge/deduplication across origins.
- Idempotent identification runs for the same input snapshot.
- Universal checklist materialization.
- Candidate review statuses: confirmed, missing information, not applicable, outsourced and potential.
- Promotion of reviewed candidates into source inventory.
- ML failure fallback to rule/checklist processing.

Important behavior: template and ML entries remain suggestions until a user reviews them. Only confirmed inventory items are eligible for calculation.

## Layer 1: activity, factors and calculations

Implemented backend capabilities:

- Activity-record create/read/update APIs.
- CSV and text-based PDF activity-file parsing.
- Automatic source matching for imported activity rows.
- Unit validation and conversion to base units.
- Demo emission-factor seeding.
- Versioned factor metadata and compatibility resolution.
- Pure Decimal calculation functions independent of the database.
- Line-item calculation with controlled gaps for missing/incompatible values.
- Aggregation by total, scope, source, process and category.
- Source percentages, production intensity and hotspot ranking.
- Immutable calculation-run creation on recalculation.
- Prototype one-step CSV ingestion and calculation endpoint.

Calculation rules preserve original/normalized quantities, factor snapshots, factor versions, warnings and unresolved lines. Demonstration factors are synthetic and must not be used for regulatory reporting.

## Layer 1: finalized profile handoff

Implemented files and APIs:

- `services/identification-api/app/domain/final_profile.py`
- `services/identification-api/app/schemas/final_profile.py`
- `services/identification-api/app/api/profiles.py`
- `final_profiles` and `audit_events` database tables through migration `0006`.
- Layer 1 profile checksum generation.
- Versioned immutable profile snapshots.
- Finalization audit event.

Available endpoints:

```text
POST /api/assessments/{assessment_id}/finalize
GET  /api/assessments/{assessment_id}/latest-final-profile
GET  /api/final-profiles/{profile_id}
GET  /api/assessments/{assessment_id}/final-profiles
```

The profile contains company, industry, facility, products, boundaries, processes, sources, activity records, baseline emissions, scope/category totals, source ranking, warnings, completeness, methodology versions, constraints and finalization metadata.

Shared JSON contracts are now populated in `packages/contracts/`:

- `assessment.schema.json`
- `source.schema.json`
- `calculation.schema.json`
- `final-profile.schema.json`
- `recommendation.schema.json`

## Layer 1 frontend

Implemented routes:

- `/` — assessment landing page using the seeded assessment read API.
- `/template` — load and view the industry starter map.
- `/processes` — read and display saved process steps.
- `/equipment/{processId}` — edit and save equipment.
- `/workflow` — guided identification workflow with visible API results, source review and KPI cards.
- `/calculations` — calculation summary, charts, percentages and hotspots.

The frontend includes responsive styling, visible loading/error states and labelled navigation buttons instead of requiring users to open raw APIs.

## Layer 2 currently implemented

### Intervention catalog

File: `data/interventions/circular-interventions-v1.json`

Catalog version: `1.0.0`. It currently contains six curated interventions covering:

- Organic by-product recovery/anaerobic digestion.
- Packaging reduction, reuse and recycled content.
- Refrigerant leak prevention and low-GWP replacement.
- Boiler heat recovery and circular fuel substitution.
- Purchased-electricity efficiency and renewable supply.
- Transport load consolidation and return logistics.

Loader: `services/identification-api/app/layer2/catalog.py`.

### Rule-based Layer 2 candidate retrieval

File: `services/identification-api/app/layer2/recommender.py`.

The engine reads only a finalized Layer 1 snapshot and:

- excludes unconfirmed sources;
- excludes sources without activity records;
- excludes non-positive baselines;
- matches source keys/categories/equipment to catalog records;
- records match reasons and required conditions/evidence;
- orders candidates by hotspot priority and catalog priority.

### Deterministic impact and feasibility

File: `services/identification-api/app/layer2/impact.py`.

Implemented outputs include projected emissions, avoided emissions, new intervention emissions, carbon reduction, reduction percentage, implementation cost, annual savings, simple payback, circularity score, technical score, feasibility score, budget status, operational status and payback status.

This currently uses catalog-based deterministic assumptions. It does not yet expose explicit LOW/CENTRAL/HIGH scenario objects.

### ML ranking adapter

File: `services/identification-api/app/layer2/ml_ranker.py`.

The LightGBM LambdaMART inference adapter is present with:

- `objective = lambdarank`;
- NDCG metadata;
- model artifact loading from `LAYER2_LIGHTGBM_MODEL_PATH`;
- six normalized ranking features;
- explicit weighted-prior fallback;
- model status, rank score, feature snapshot and ranking explanation.

No trained model artifact or training-data pipeline is currently present. Fresh environments should show `LIGHTGBM_UNTRAINED` or `LIGHTGBM_DEPENDENCY_MISSING` and use the labelled demo fallback.

### Layer 2 APIs

```text
GET /api/layer2/interventions
GET /api/layer2/model-status
GET /api/layer2/demo/profile
GET /api/layer2/demo/candidates
GET /api/layer2/demo/recommendations
GET/POST /api/final-profiles/{profile_id}/recommendations
GET /api/final-profiles/{profile_id}/intervention-candidates
GET /api/assessments/{assessment_id}/recommendations
GET /api/assessments/{assessment_id}/intervention-candidates
```

### Layer 2 frontend

- `/recommendations` shows deterministic rule matches, excluded sources, reasons and required evidence.
- `/recommendations/ranked` shows impact/feasibility outputs and ML or fallback ranking metadata.

## Tests and verification

The targeted profile/contract/Layer 2 test set currently passes:

```text
12 passed
```

The full unit suite currently stops at one existing ML test failure:

```text
test_t02_cold_room_produces_refrigerant_suggestion
```

The failing input is `Finished products are stored in a cold room.`; the local ML predictor currently does not score it above its threshold for `refrigerant_fugitive_emissions`. This is an ML matching gap, not a Layer 2 API or profile-persistence failure.

## Not implemented yet

- Layer 2 database models and migrations for interventions, evidence, compatibility evaluations, recommendation runs/items, scenarios, portfolios and feedback.
- Persistence-backed recommendation-run creation and retrieval.
- Dedicated profile-adapter validation module.
- Separate compatibility engine with explicit `ELIGIBLE`, `CONDITIONAL`, `NOT_RECOMMENDED` and `NOT_EVALUATED` statuses.
- Explicit LOW/CENTRAL/HIGH impact scenario records.
- SHAP/TreeSHAP explanations for trained LightGBM inference.
- LightGBM training-data generation and evaluation pipeline.
- OR-Tools portfolio optimization.
- Recommendation feedback API.
- Portfolio API.
- Full evidence registry separate from the intervention catalog.
- Production-grade authentication, authorization and multi-company assessment selection.

## Current conclusion

Layer 1 is sufficiently complete to provide a versioned profile handoff. Layer 2 currently has a functioning in-memory prototype through rule matching, deterministic impact modeling and an ML ranking adapter, plus demo and profile-based read APIs and frontend pages. It is not yet a complete production Layer 2 because recommendation runs, evidence, scenarios, feedback and portfolio selections are not persisted, and the LambdaMART model is not trained.
