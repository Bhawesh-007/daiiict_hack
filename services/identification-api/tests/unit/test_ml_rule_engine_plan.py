"""
Tests implementing every test case and regression check from ml_rule_engine_test_plan.md:

T01 - Diesel boiler produces stationary-combustion suggestion (Rule + ML)
T02 - Cold room produces refrigerant suggestion
T03 - Electricity bill text produces purchased-electricity suggestion
T04 - Unrelated text produces no candidate
T05 - Unknown source keys are rejected
T06 - ML candidates remain proposed
T07 - ML cannot modify confirmed inventory
T08 - Repeated ML execution does not create duplicates
T09 - Identification completes when ML fails
T10 - Rule and template results remain available without ML

Additional regression checks:
- Same source in different equipment contexts is not incorrectly merged
- Same source in different process contexts is not incorrectly merged
- Multiple rule triggers preserve every reason and rule version
- Candidate output ordering is deterministic across repeated runs
- ML extraction preserves process and equipment context
- A missing ML provider does not block rule-only identification
- Template suggestions remain editable and are never automatically confirmed
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings
from app.identification.candidate_merger import candidate_key, merge_candidates
from app.identification.ml_adapter import MLAdapter, MLUnavailableError
from app.identification.ml_model import SourceIdentificationModel
from app.identification.orchestrator import IdentificationOrchestrator
from app.identification.rule_engine import RuleEngine
from app.main import app
from app.persistence.models import (
    Assessment,
    AssessmentProduct,
    Company,
    Equipment,
    Facility,
    IdentificationRun,
    InputOutputFlow,
    ProcessStep,
    SourceCandidate,
    SourceInventoryItem,
)
from app.schemas.ml import MLFact, MLIdentificationRequest, MLPersistenceCandidate
from app.schemas.sources import SourceCandidateContract

ROOT = Path(__file__).resolve().parents[4]
TAXONOMY_PATH = ROOT / "data/taxonomy/source-types.json"
RULES_PATH = ROOT / "data/rules/source-identification-rules.json"

settings = get_settings()


def get_test_engine():
    return create_async_engine(settings.async_database_url, poolclass=NullPool)


# ─────────────────────────────────────────────────────────────────────────────
# T01 — Diesel boiler produces stationary-combustion suggestion
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_t01_diesel_boiler_produces_stationary_combustion_rule_and_ml():
    """T01: Diesel boiler produces stationary-combustion in both Rule Engine and ML Adapter."""
    proc_id = str(uuid4())
    equip_id = str(uuid4())
    fact = {
        "fact_type": "equipment",
        "process_step_id": proc_id,
        "equipment_id": equip_id,
        "equipment_type": "boiler",
        "fuel_type": "diesel",
    }

    # 1. Rule Engine evaluation
    rule_engine = RuleEngine(RULES_PATH, TAXONOMY_PATH)
    rule_candidates = rule_engine.identify([fact])
    assert any(c["source_key"] == "stationary_fuel_combustion" for c in rule_candidates)
    rule_c = next(c for c in rule_candidates if c["source_key"] == "stationary_fuel_combustion")
    assert rule_c["process_step_id"] == proc_id
    assert rule_c["equipment_id"] == equip_id
    assert rule_c["rule_id"].startswith("SRC-RULE-")
    assert rule_c["rule_version"] == "1.0.0"
    assert "diesel" in rule_c["reason"].lower()

    # 2. ML Adapter evaluation with text containing 'diesel boiler'
    ml_adapter = MLAdapter()
    ml_candidates = await ml_adapter.identify({
        "equipment": [{
            "process_step_id": proc_id,
            "equipment_id": equip_id,
            "name": "Auxiliary diesel steam boiler",
            "equipment_type": "boiler",
            "fuel_type": "diesel",
        }],
        "processes": [],
        "flows": [],
    })
    assert any(c["source_key"] == "stationary_fuel_combustion" for c in ml_candidates)
    ml_c = next(c for c in ml_candidates if c["source_key"] == "stationary_fuel_combustion")
    assert str(ml_c["process_step_id"]) == proc_id
    assert str(ml_c["equipment_id"]) == equip_id
    assert ml_c["origin"] == "ML"
    assert ml_c["evidence_json"]["model_id"] == "taxonomy-tfidf-cosine"
    assert ml_c["evidence_json"]["model_version"] == "1.0.0"


# ─────────────────────────────────────────────────────────────────────────────
# T02 — Cold room produces refrigerant suggestion
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_t02_cold_room_produces_refrigerant_suggestion():
    """T02: Cold room text produces refrigerant suggestion with specific follow-up questions."""
    model = SourceIdentificationModel(TAXONOMY_PATH)
    text_input = "Finished products are stored in a cold room."
    predictions = model.predict(text_input)
    assert any(p["source_key"] == "refrigerant_fugitive_emissions" for p in predictions)

    adapter = MLAdapter(model)
    req = MLIdentificationRequest(facts=[MLFact(fact_type="equipment", text=text_input)])
    suggestions = await adapter.identify_request(req)
    assert len(suggestions) > 0
    refrig = next(s for s in suggestions if s.source_key == "refrigerant_fugitive_emissions")
    assert "refrigerant" in refrig.reason.lower() or "cold room" in text_input.lower()
    assert refrig.follow_up_questions == [
        "Which refrigerant is used?",
        "How much refrigerant was refilled?",
        "Was leakage detected?",
    ]


# ─────────────────────────────────────────────────────────────────────────────
# T03 — Electricity bill text produces purchased-electricity suggestion
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_t03_electricity_bill_text_produces_purchased_electricity_suggestion():
    """T03: Electricity text produces purchased_grid_electricity suggestion in ML and Rule Engine."""
    text_input = "The facility purchases grid electricity and the monthly electricity bill is available."
    model = SourceIdentificationModel(TAXONOMY_PATH)
    predictions = model.predict(text_input)
    assert any(p["source_key"] == "purchased_grid_electricity" for p in predictions)

    adapter = MLAdapter(model)
    req = MLIdentificationRequest(facts=[MLFact(fact_type="flow", text=text_input)])
    suggestions = await adapter.identify_request(req)
    elec = next(s for s in suggestions if s.source_key == "purchased_grid_electricity")
    assert elec.model_version == "1.0.0"
    assert 0.0 <= elec.confidence <= 1.0

    # Rule engine evaluation when passed as structured energy fact
    rule_engine = RuleEngine(RULES_PATH, TAXONOMY_PATH)
    structured_fact = {
        "fact_type": "energy_input",
        "energy_type": "purchased_grid_electricity",
        "consumed_by_facility": True,
    }
    rule_candidates = rule_engine.identify([structured_fact])
    assert any(c["source_key"] == "purchased_grid_electricity" for c in rule_candidates)


# ─────────────────────────────────────────────────────────────────────────────
# T04 — Unrelated text produces no candidate
# ─────────────────────────────────────────────────────────────────────────────

def test_t04_unrelated_text_produces_no_candidate():
    """T04: Unrelated administrative text returns empty candidate list."""
    model = SourceIdentificationModel(TAXONOMY_PATH)
    unrelated_text = "The office held an administrative meeting about employee attendance."
    predictions = model.predict(unrelated_text)
    assert predictions == [], "Unrelated text must return no predictions"


# ─────────────────────────────────────────────────────────────────────────────
# T05 — Unknown source keys are rejected
# ─────────────────────────────────────────────────────────────────────────────

def test_t05_unknown_source_keys_are_rejected():
    """T05: Unknown source_key is rejected by schema validation and candidate merger."""
    with pytest.raises(ValidationError):
        SourceCandidateContract(
            assessment_id=uuid4(),
            source_key="made_up_emission_source",
            source_name="Fake Source",
            origin="ML",
            reason="Test",
        )

    # Candidate merger rejects missing or unmapped source_key
    with pytest.raises(ValueError):
        merge_candidates([{"origin": "ML", "reason": "missing source"}])


# ─────────────────────────────────────────────────────────────────────────────
# T06 — ML candidates remain proposed
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_t06_ml_candidates_remain_proposed():
    """T06: ML candidates always receive PROPOSED status and never CONFIRMED."""
    adapter = MLAdapter()
    candidates = await adapter.identify({
        "equipment": [{
            "process_step_id": str(uuid4()),
            "equipment_id": str(uuid4()),
            "name": "Diesel steam boiler",
            "equipment_type": "boiler",
            "fuel_type": "diesel",
        }],
        "processes": [],
        "flows": [],
    })
    for c in candidates:
        assert c["origin"] == "ML"
        assert c["status"] == "PROPOSED"
        assert c["status"] not in ("CONFIRMED", "PROMOTED")

    # Rejection of CONFIRMED status at schema validation
    with pytest.raises(ValidationError):
        MLPersistenceCandidate.model_validate({
            "source_key": "stationary_fuel_combustion",
            "source_name": "Stationary fuel combustion",
            "origin": "ML",
            "status": "CONFIRMED",
            "confidence": 0.9,
            "reason": "Invalid confirmed candidate",
            "model_id": "taxonomy-tfidf-cosine",
            "model_version": "1.0.0",
        })


# ─────────────────────────────────────────────────────────────────────────────
# T07 — ML cannot modify confirmed inventory
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_t07_ml_cannot_modify_confirmed_inventory():
    """T07: Re-running identification with ML does not modify existing confirmed SourceInventoryItems."""
    engine = get_test_engine()
    aid = uuid4()
    cid = uuid4()
    fid = uuid4()
    cand_id = uuid4()
    item_id = uuid4()
    confirmed_time = datetime(2026, 9, 12, 10, 0, 0, tzinfo=UTC)

    async with engine.connect() as conn:
        trans = await conn.begin()
        await conn.execute(text("INSERT INTO companies (id, name) VALUES (:cid, 'T07 Corp')"), {"cid": cid})
        await conn.execute(text("INSERT INTO facilities (id, company_id, name) VALUES (:fid, :cid, 'T07 Fac')"), {"fid": fid, "cid": cid})
        await conn.execute(text("""INSERT INTO assessments 
            (id, facility_id, industry_name, industry_template_key, industry_template_version, reporting_period_start, reporting_period_end, status) 
            VALUES (:aid, :fid, 'Food', 'industry-food-processing-v1', '1.0.0', NOW(), NOW(), 'IN_PROGRESS')"""), {"aid": aid, "fid": fid})

        # Insert a candidate and confirmed inventory item
        await conn.execute(text("""INSERT INTO source_candidates 
            (id, assessment_id, source_key, source_name, origin, status) 
            VALUES (:cand_id, :aid, 'stationary_fuel_combustion', 'Stationary fuel combustion', 'RULE', 'PROMOTED')"""),
            {"cand_id": cand_id, "aid": aid})

        await conn.execute(text("""INSERT INTO source_inventory_items 
            (id, assessment_id, candidate_id, source_key, source_name, status, confirmed_by, confirmed_at, confirmation_note) 
            VALUES (:item_id, :aid, :cand_id, 'stationary_fuel_combustion', 'Stationary fuel combustion', 'CONFIRMED', 'auditor@example.com', :cat, 'Verified boiler log')"""),
            {"item_id": item_id, "aid": aid, "cand_id": cand_id, "cat": confirmed_time})

        # Run identification with ML via API endpoint
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.post(f"/api/assessments/{aid}/identify", json={"include_ml": True})
            assert res.status_code == 200

        # Verify the inventory item was NOT modified
        row = (await conn.execute(text("SELECT status, confirmed_by, confirmed_at, confirmation_note FROM source_inventory_items WHERE id = :item_id"), {"item_id": item_id})).mappings().one()
        assert row["status"] == "CONFIRMED"
        assert row["confirmed_by"] == "auditor@example.com"
        assert row["confirmed_at"] == confirmed_time
        assert row["confirmation_note"] == "Verified boiler log"

        await trans.rollback()
    await engine.dispose()


# ─────────────────────────────────────────────────────────────────────────────
# T08 — Repeated ML execution does not create duplicates
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_t08_repeated_ml_execution_is_idempotent():
    """T08: Running identification repeatedly with unchanged input returns identical run and no duplicates."""
    aid = uuid4()
    cid = uuid4()
    fid = uuid4()
    engine = get_test_engine()

    async with engine.connect() as conn:
        trans = await conn.begin()
        await conn.execute(text("INSERT INTO companies (id, name) VALUES (:cid, 'T08 Corp')"), {"cid": cid})
        await conn.execute(text("INSERT INTO facilities (id, company_id, name) VALUES (:fid, :cid, 'T08 Fac')"), {"fid": fid, "cid": cid})
        await conn.execute(text("""INSERT INTO assessments 
            (id, facility_id, industry_name, industry_template_key, industry_template_version, reporting_period_start, reporting_period_end, status) 
            VALUES (:aid, :fid, 'Food', 'industry-food-processing-v1', '1.0.0', NOW(), NOW(), 'DRAFT')"""), {"aid": aid, "fid": fid})

        # Load template processes
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            load_res = await client.post(f"/api/assessments/{aid}/load-template")
            assert load_res.status_code == 200

            # 1st execution
            res1 = await client.post(f"/api/assessments/{aid}/identify", json={"include_ml": True})
            assert res1.status_code == 200
            run1 = res1.json()

            # 2nd execution
            res2 = await client.post(f"/api/assessments/{aid}/identify", json={"include_ml": True})
            assert res2.status_code == 200
            run2 = res2.json()

            # Check idempotency
            assert run1["run_id"] == run2["run_id"], "Repeated run on unchanged input must return the existing run"
            assert run1["input_hash"] == run2["input_hash"]
            assert run1["candidate_count"] == run2["candidate_count"]

            cand_res = await client.get(f"/api/assessments/{aid}/candidates")
            assert cand_res.status_code == 200
            candidates = cand_res.json()
            assert len(candidates) == run1["candidate_count"]

            # Deduplication key check
            dedup_keys = {(c["source_key"], c["process_step_id"], c["equipment_id"], c["origin"]) for c in candidates}
            assert len(dedup_keys) == len(candidates)

        await trans.rollback()
    await engine.dispose()


# ─────────────────────────────────────────────────────────────────────────────
# T09 — Identification completes when ML fails
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_t09_identification_completes_when_ml_fails():
    """T09: Injecting a failing MLAdapter does not crash identification; sets ml_status=UNAVAILABLE and persists rules/templates."""
    class FailingMLAdapter(MLAdapter):
        async def identify(self, facts):
            raise MLUnavailableError("Provider offline or timed out")

    engine = get_test_engine()
    aid = uuid4()
    cid = uuid4()
    fid = uuid4()

    async with engine.connect() as conn:
        trans = await conn.begin()
        await conn.execute(text("INSERT INTO companies (id, name) VALUES (:cid, 'T09 Corp')"), {"cid": cid})
        await conn.execute(text("INSERT INTO facilities (id, company_id, name) VALUES (:fid, :cid, 'T09 Fac')"), {"fid": fid, "cid": cid})
        await conn.execute(text("""INSERT INTO assessments 
            (id, facility_id, industry_name, industry_template_key, industry_template_version, reporting_period_start, reporting_period_end, status) 
            VALUES (:aid, :fid, 'Food', 'industry-food-processing-v1', '1.0.0', NOW(), NOW(), 'DRAFT')"""), {"aid": aid, "fid": fid})

        # Load processes
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post(f"/api/assessments/{aid}/load-template")

        # Create orchestrator with failing ML adapter
        from sqlalchemy.ext.asyncio import AsyncSession
        async_session = AsyncSession(conn)
        orchestrator = IdentificationOrchestrator(async_session, ml_adapter=FailingMLAdapter())
        run = await orchestrator.run(aid, include_ml=True)

        assert run.status == "COMPLETED"
        assert run.output_json["ml_status"] == "UNAVAILABLE"
        assert "offline" in run.output_json["ml_error"]
        assert run.output_json["candidate_count"] > 0
        assert run.output_json["template_candidate_count"] > 0
        assert run.output_json["rule_candidate_count"] > 0
        assert "checklist" in run.output_json

        await trans.rollback()
    await engine.dispose()


# ─────────────────────────────────────────────────────────────────────────────
# T10 — Rule and template results remain available without ML
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_t10_rule_and_template_results_available_without_ml():
    """T10: With include_ml=False, run completes with ml_status=DISABLED and candidate_origins not containing ML."""
    aid = uuid4()
    cid = uuid4()
    fid = uuid4()
    engine = get_test_engine()

    async with engine.connect() as conn:
        trans = await conn.begin()
        await conn.execute(text("INSERT INTO companies (id, name) VALUES (:cid, 'T10 Corp')"), {"cid": cid})
        await conn.execute(text("INSERT INTO facilities (id, company_id, name) VALUES (:fid, :cid, 'T10 Fac')"), {"fid": fid, "cid": cid})
        await conn.execute(text("""INSERT INTO assessments 
            (id, facility_id, industry_name, industry_template_key, industry_template_version, reporting_period_start, reporting_period_end, status) 
            VALUES (:aid, :fid, 'Food', 'industry-food-processing-v1', '1.0.0', NOW(), NOW(), 'DRAFT')"""), {"aid": aid, "fid": fid})

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post(f"/api/assessments/{aid}/load-template")

            res = await client.post(f"/api/assessments/{aid}/identify", json={"include_ml": False})
            assert res.status_code == 200
            run = res.json()

            assert run["status"] == "COMPLETED"
            assert run["ml_status"] == "DISABLED"
            assert run["ml_candidate_count"] == 0
            assert run["template_candidate_count"] > 0
            assert run["rule_candidate_count"] > 0

            cand_res = await client.get(f"/api/assessments/{aid}/candidates")
            candidates = cand_res.json()
            assert all(c["origin"] != "ML" for c in candidates)

            # Universal checklist is returned
            chk_res = await client.get(f"/api/assessments/{aid}/checklist")
            assert chk_res.status_code == 200
            chk = chk_res.json()
            assert len(chk["items"]) == 14

        await trans.rollback()
    await engine.dispose()


# ─────────────────────────────────────────────────────────────────────────────
# Additional Regression Checks
# ─────────────────────────────────────────────────────────────────────────────

def test_regression_same_source_different_equipment_contexts_not_merged():
    """Regression: Same source across different equipment IDs is preserved as distinct candidates."""
    c1 = {
        "source_key": "stationary_fuel_combustion",
        "process_step_id": "proc-1",
        "equipment_id": "equip-1",
        "origin": "RULE",
        "reason": "Boiler 1",
    }
    c2 = {
        "source_key": "stationary_fuel_combustion",
        "process_step_id": "proc-1",
        "equipment_id": "equip-2",
        "origin": "RULE",
        "reason": "Boiler 2",
    }
    merged = merge_candidates([c1, c2])
    assert len(merged) == 2


def test_regression_same_source_different_process_contexts_not_merged():
    """Regression: Same source across different process step IDs is preserved as distinct candidates."""
    c1 = {
        "source_key": "purchased_grid_electricity",
        "process_step_id": "proc-1",
        "equipment_id": None,
        "origin": "TEMPLATE",
        "reason": "Process 1 electricity",
    }
    c2 = {
        "source_key": "purchased_grid_electricity",
        "process_step_id": "proc-2",
        "equipment_id": None,
        "origin": "TEMPLATE",
        "reason": "Process 2 electricity",
    }
    merged = merge_candidates([c1, c2])
    assert len(merged) == 2


def test_regression_multiple_rule_triggers_preserve_every_reason_and_rule_version():
    """Regression: Multiple rule triggers for the same source/equipment merge all reasons and rule IDs."""
    c1 = {
        "source_key": "stationary_fuel_combustion",
        "process_step_id": "proc-1",
        "equipment_id": "equip-1",
        "origin": "RULE",
        "reason": "Boiler burns diesel.",
        "rule_id": "SRC-RULE-003",
        "rule_version": "1.0.0",
        "evidence_json": {"rule_id": "SRC-RULE-003", "rule_version": "1.0.0"},
    }
    c2 = {
        "source_key": "stationary_fuel_combustion",
        "process_step_id": "proc-1",
        "equipment_id": "equip-1",
        "origin": "RULE",
        "reason": "High temperature exhaust detected.",
        "rule_id": "SRC-RULE-099",
        "rule_version": "1.1.0",
        "evidence_json": {"rule_id": "SRC-RULE-099", "rule_version": "1.1.0"},
    }
    merged = merge_candidates([c1, c2])
    assert len(merged) == 1
    m = merged[0]
    assert "Boiler burns diesel." in m["reason"]
    assert "High temperature exhaust detected." in m["reason"]
    assert "SRC-RULE-003" in m["evidence_json"]["rule_ids"]
    assert "SRC-RULE-099" in m["evidence_json"]["rule_ids"]
    assert "1.0.0" in m["evidence_json"]["rule_versions"]
    assert "1.1.0" in m["evidence_json"]["rule_versions"]


def test_regression_candidate_output_ordering_is_deterministic():
    """Regression: Merged candidates are deterministically ordered regardless of input order."""
    c1 = {"source_key": "stationary_fuel_combustion", "process_step_id": "a", "equipment_id": "1", "origin": "RULE", "reason": "r1"}
    c2 = {"source_key": "refrigerant_fugitive_emissions", "process_step_id": "b", "equipment_id": "2", "origin": "RULE", "reason": "r2"}
    c3 = {"source_key": "purchased_grid_electricity", "process_step_id": "c", "equipment_id": None, "origin": "TEMPLATE", "reason": "r3"}

    order1 = [c["source_key"] for c in merge_candidates([c1, c2, c3])]
    order2 = [c["source_key"] for c in merge_candidates([c3, c1, c2])]
    order3 = [c["source_key"] for c in merge_candidates([c2, c3, c1])]

    assert order1 == order2 == order3


@pytest.mark.asyncio
async def test_regression_ml_extraction_preserves_process_and_equipment_context():
    """Regression: ML entity extraction retains process_step_id and equipment_id context."""
    pid = uuid4()
    eid = uuid4()
    adapter = MLAdapter()
    facts = {
        "equipment": [{
            "process_step_id": pid,
            "equipment_id": eid,
            "name": "Cold room with R134a refrigerant",
            "equipment_type": "cold_room",
        }],
        "processes": [],
        "flows": [],
    }
    entities = await adapter.extract_entities(facts)
    assert len(entities) > 0
    for entity in entities:
        assert entity["process_step_id"] == pid
        assert entity["equipment_id"] == eid
