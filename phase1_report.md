# Phase 1 Exit-Condition Report

Date: 2026-09-12

## Exit condition

> A seeded assessment, industry template, and source type can be stored and read.

## Verdict

**PASSED end-to-end for the current Supabase-backed vertical slice.** Alembic connected to Supabase at revision `0007 (head)`, the seed/read script exited successfully, and response-content assertions passed for the assessment, food-processing template, and `purchased_grid_electricity` source type.

## Checks performed

| Check | Result | Evidence |
|---|---|---|
| Seed JSON files parse | PASS | `data/seed/sample-company.json` and `data/seed/sample-assessment.json` are valid JSON. |
| Seed references are structurally valid | PASS | Company, facility, assessment, and product IDs are internally linked in `sample-assessment.json`. |
| Industry templates are readable | PASS (static) | Three valid templates exist: food processing, textile, and universal. |
| Source taxonomy is readable | PASS (static) | `data/taxonomy/source-types.json` contains 15 source types. |
| Template/source references resolve | PASS | Cross-reference check found 0 errors across templates, rules, and factors. |
| Database migration path exists | PASS (offline) | Alembic generated SQL for 17 tables and 2 reporting views through revision `0007`. |
| Assessment create/read API exists | PASS (code inspection) | `POST /api/assessments` and `GET /api/assessments/{assessment_id}` are defined. |
| Template read API exists | PASS (code inspection) | `GET /api/industry-templates` and `GET /api/industry-templates/{template_id}` are defined. |
| Source-type read API exists | PASS (code inspection) | `GET /api/source-types` and `GET /api/source-types/{source_type_id}` are defined. |
| Seed round trip against Supabase | PASS | `scripts/seed-data.sh` exited 0; the existing seeded assessment, template, and source type were all readable. |
| Returned response-content assertions | PASS | Assessment relationships, template ID/version/processes, and source-type ID/scope were asserted successfully. |
| Automated acceptance test | NOT PASSED | `tests/e2e/assessment-flow.spec.ts` is empty. |

## Runtime path intended by the repository

`scripts/seed-data.sh` is designed to:

1. POST `data/seed/sample-assessment.json` to `/api/assessments`.
2. Read the seeded assessment.
3. Read `industry-food-processing-v1`.
4. Read `purchased_grid_electricity`.

The script currently checks only HTTP success, not response contents or field correctness.

## Important scope caveat

Templates and source types are currently file-backed knowledge assets, not database entities. Therefore, “stored” means versioned files that can be loaded and referenced by an assessment. If the exit condition requires them to be database-persisted, template and source-type tables/import logic are still needed.

Also, the current template-loading implementation creates default equipment and input/output flow rows directly. Those rows do not yet carry explicit template provenance or a proposed/accepted review status, so this should be corrected before treating the process-mapping flow as compliant with the rule that template entries are never confirmed facts.

## Evidence collected for the passing round trip

Executed against the Supabase PostgreSQL instance and a running local API:

```text
1. Apply migrations successfully.
2. Run scripts/seed-data.sh successfully.
3. GET /api/assessments/10000000-0000-4000-8000-000000000003.
4. Assert the response contains the expected company, facility, assessment, and product.
5. GET /api/industry-templates/industry-food-processing-v1.
6. Assert the template ID, version, and process list.
7. GET /api/source-types/purchased_grid_electricity.
8. Assert the source ID, family, scope, and supported activity types.
9. Repeat the seed command and assert no duplicate assessment is created.
```

The Phase 1 storage/read exit condition is accepted for this environment. The separate automated-test and template-provenance gaps remain open for later hardening.
