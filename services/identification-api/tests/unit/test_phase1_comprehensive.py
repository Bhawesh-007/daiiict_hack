"""
Phase 1 Comprehensive Test Suite.

Covers all 8 sections of Phase 1 requirements:
1. Knowledge-base file tests
2. Database migration tests
3. Seed-data tests
4. Template read tests
5. Source-type read tests
6. Relationship tests
7. API contract tests
8. Phase 1 acceptance test
"""

import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.main import app

PROJECT_ROOT = Path(__file__).resolve().parents[4]
KNOWLEDGE_DIR = PROJECT_ROOT / "data"
TEMPLATES_DIR = KNOWLEDGE_DIR / "industry-templates"
SOURCE_TYPES_FILE = KNOWLEDGE_DIR / "taxonomy" / "source-types.json"
SEED_COMPANY_FILE = KNOWLEDGE_DIR / "seed" / "sample-company.json"
SEED_ASSESSMENT_FILE = KNOWLEDGE_DIR / "seed" / "sample-assessment.json"

settings = get_settings()


def get_test_engine():
    """Create a fresh async engine with NullPool to avoid event-loop mismatch across async tests."""
    return create_async_engine(settings.async_database_url, poolclass=NullPool)


# ─────────────────────────────────────────────────────────────────────────────
# 1. KNOWLEDGE-BASE FILE TESTS
# ─────────────────────────────────────────────────────────────────────────────

def test_kb_json_files_parse_successfully():
    """Every template JSON and source-type JSON file parses successfully."""
    template_files = list(TEMPLATES_DIR.glob("*.json"))
    assert len(template_files) >= 3, "Expected at least 3 industry template files"
    for tf in template_files:
        data = json.loads(tf.read_text(encoding="utf-8"))
        assert isinstance(data, dict)

    assert SOURCE_TYPES_FILE.exists()
    st_data = json.loads(SOURCE_TYPES_FILE.read_text(encoding="utf-8"))
    assert isinstance(st_data, dict)
    assert "source_types" in st_data


def test_kb_templates_have_required_fields():
    """Each template has template_id, template_version, industry_code, processes, verification_questions."""
    template_files = list(TEMPLATES_DIR.glob("*.json"))
    for tf in template_files:
        t = json.loads(tf.read_text(encoding="utf-8"))
        assert "template_id" in t and isinstance(t["template_id"], str)
        assert "template_version" in t and isinstance(t["template_version"], str)
        assert "industry_code" in t and isinstance(t["industry_code"], str)
        assert "processes" in t and isinstance(t["processes"], list)
        assert "verification_questions" in t and isinstance(t["verification_questions"], list)


def test_kb_source_types_have_required_fields():
    """Each source type has source_type_id, name, family_id, default_scope, supported_activity_types, minimum_data."""
    st_data = json.loads(SOURCE_TYPES_FILE.read_text(encoding="utf-8"))
    source_types = st_data["source_types"]
    assert len(source_types) > 0
    for st in source_types:
        assert "source_type_id" in st and isinstance(st["source_type_id"], str)
        assert "name" in st and isinstance(st["name"], str)
        assert "family_id" in st and isinstance(st["family_id"], str)
        assert "default_scope" in st and isinstance(st["default_scope"], str)
        assert "supported_activity_types" in st and isinstance(st["supported_activity_types"], list)
        assert "minimum_data" in st and isinstance(st["minimum_data"], list)


def test_kb_template_references_point_to_existing_source_types():
    """Every template reference points to an existing source_type_id."""
    st_data = json.loads(SOURCE_TYPES_FILE.read_text(encoding="utf-8"))
    valid_source_ids = {st["source_type_id"] for st in st_data["source_types"]}

    for tf in TEMPLATES_DIR.glob("*.json"):
        t = json.loads(tf.read_text(encoding="utf-8"))
        for proc in t.get("processes", []):
            for st_id in proc.get("suggested_source_type_ids", []):
                assert st_id in valid_source_ids, f"Template {t['template_id']} references unknown source_type_id '{st_id}' in process '{proc.get('process_id')}'"
        for vq in t.get("verification_questions", []):
            for st_id in vq.get("required_for_source_type_ids", []):
                assert st_id in valid_source_ids, f"Template {t['template_id']} references unknown source_type_id '{st_id}' in question '{vq.get('question_id')}'"
        for st_id in t.get("universal_source_type_ids", []):
            assert st_id in valid_source_ids, f"Template {t['template_id']} references unknown universal source_type_id '{st_id}'"


def test_kb_no_duplicate_template_or_source_type_ids():
    """No duplicate template IDs or source-type IDs exist."""
    template_ids = []
    for tf in TEMPLATES_DIR.glob("*.json"):
        t = json.loads(tf.read_text(encoding="utf-8"))
        template_ids.append(t["template_id"])
    assert len(template_ids) == len(set(template_ids)), f"Duplicate template IDs found: {template_ids}"

    st_data = json.loads(SOURCE_TYPES_FILE.read_text(encoding="utf-8"))
    st_ids = [st["source_type_id"] for st in st_data["source_types"]]
    assert len(st_ids) == len(set(st_ids)), f"Duplicate source_type IDs found: {st_ids}"


@pytest.mark.asyncio
async def test_kb_unknown_template_version_rejected():
    """Unknown template versions are rejected clearly with 422."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = json.loads(SEED_ASSESSMENT_FILE.read_text(encoding="utf-8"))
        cid = str(uuid4())
        fid = str(uuid4())
        aid = str(uuid4())
        payload["company"]["id"] = cid
        payload["facility"]["id"] = fid
        payload["facility"]["company_id"] = cid
        payload["assessment"]["id"] = aid
        payload["assessment"]["facility_id"] = fid
        payload["assessment"]["industry_template_version"] = "99.9.9"
        res = await client.post("/api/assessments", json=payload)
        assert res.status_code == 422
        assert "unavailable" in res.json()["detail"] or "version" in res.json()["detail"]


@pytest.mark.asyncio
async def test_kb_unknown_source_type_id_returns_404():
    """Unknown source-type IDs return a controlled 'not found' response (404)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/source-types/nonexistent_source_type_123")
        assert res.status_code == 404
        assert "not found" in res.json()["detail"].lower()


# ─────────────────────────────────────────────────────────────────────────────
# 2. DATABASE MIGRATION & SCHEMA TESTS
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_db_phase1_tables_exist():
    """Alembic migrations create all Phase 1 tables successfully: companies, facilities, assessments, assessment_products, process_steps."""
    engine = get_test_engine()
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
        required_tables = ["companies", "facilities", "assessments", "assessment_products", "process_steps"]
        for rt in required_tables:
            assert rt in tables, f"Table '{rt}' missing from database schema"
    await engine.dispose()


@pytest.mark.asyncio
async def test_db_foreign_keys_enforced():
    """Foreign keys are enforced: assessment cannot reference nonexistent facility; facility cannot reference nonexistent company."""
    engine = get_test_engine()
    async with engine.connect() as conn:
        trans = await conn.begin()
        fake_company_id = uuid4()
        fake_facility_id = uuid4()

        try:
            await conn.execute(
                text("INSERT INTO facilities (id, company_id, name) VALUES (:fid, :cid, 'Test')"),
                {"fid": fake_facility_id, "cid": fake_company_id},
            )
            pytest.fail("Should fail foreign key check for nonexistent company_id")
        except IntegrityError:
            pass
        await trans.rollback()

        trans = await conn.begin()
        try:
            await conn.execute(
                text("""INSERT INTO assessments 
                    (id, facility_id, industry_name, reporting_period_start, reporting_period_end) 
                    VALUES (:aid, :fid, 'Food', NOW(), NOW())"""),
                {"aid": uuid4(), "fid": fake_facility_id},
            )
            pytest.fail("Should fail foreign key check for nonexistent facility_id")
        except IntegrityError:
            pass
        await trans.rollback()

    await engine.dispose()


@pytest.mark.asyncio
async def test_db_check_constraints_work():
    """Reporting-period validation (start <= end) and status check constraints work."""
    engine = get_test_engine()
    async with engine.connect() as conn:
        cid, fid = uuid4(), uuid4()

        # Test invalid status
        trans1 = await conn.begin()
        await conn.execute(text("INSERT INTO companies (id, name) VALUES (:cid, 'C')"), {"cid": cid})
        await conn.execute(text("INSERT INTO facilities (id, company_id, name) VALUES (:fid, :cid, 'F')"), {"fid": fid, "cid": cid})
        try:
            await conn.execute(
                text("""INSERT INTO assessments 
                    (id, facility_id, industry_name, status, reporting_period_start, reporting_period_end) 
                    VALUES (:aid, :fid, 'Food', 'INVALID_STATUS', '2025-01-01', '2025-12-31')"""),
                {"aid": uuid4(), "fid": fid},
            )
            pytest.fail("Should fail check constraint for invalid status")
        except IntegrityError:
            pass
        await trans1.rollback()

        # Test invalid period (end < start)
        trans2 = await conn.begin()
        await conn.execute(text("INSERT INTO companies (id, name) VALUES (:cid, 'C')"), {"cid": cid})
        await conn.execute(text("INSERT INTO facilities (id, company_id, name) VALUES (:fid, :cid, 'F')"), {"fid": fid, "cid": cid})
        try:
            await conn.execute(
                text("""INSERT INTO assessments 
                    (id, facility_id, industry_name, status, reporting_period_start, reporting_period_end) 
                    VALUES (:aid, :fid, 'Food', 'DRAFT', '2025-12-31', '2025-01-01')"""),
                {"aid": uuid4(), "fid": fid},
            )
            pytest.fail("Should fail check constraint for invalid reporting period")
        except IntegrityError:
            pass
        await trans2.rollback()

    await engine.dispose()


# ─────────────────────────────────────────────────────────────────────────────
# 3. SEED-DATA TESTS
# ─────────────────────────────────────────────────────────────────────────────

def test_seed_fixtures_valid_json():
    """The seed fixtures (sample-company.json and sample-assessment.json) are valid JSON and non-empty."""
    assert SEED_COMPANY_FILE.stat().st_size > 0, "sample-company.json must not be empty"
    company_seed = json.loads(SEED_COMPANY_FILE.read_text(encoding="utf-8"))
    assert "company" in company_seed
    assert company_seed["company"]["name"]

    assert SEED_ASSESSMENT_FILE.stat().st_size > 0, "sample-assessment.json must not be empty"
    assessment_seed = json.loads(SEED_ASSESSMENT_FILE.read_text(encoding="utf-8"))
    assert "assessment" in assessment_seed
    assert "facility" in assessment_seed
    assert "company" in assessment_seed
    assert "products" in assessment_seed


@pytest.mark.asyncio
async def test_seed_insertion_and_readback_and_idempotency():
    """Insert synthetic company, facility, assessment, product and read back. Verify idempotency."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = json.loads(SEED_ASSESSMENT_FILE.read_text(encoding="utf-8"))
        cid = str(uuid4())
        fid = str(uuid4())
        aid = str(uuid4())
        pid = str(uuid4())
        payload["company"]["id"] = cid
        payload["facility"]["id"] = fid
        payload["facility"]["company_id"] = cid
        payload["assessment"]["id"] = aid
        payload["assessment"]["facility_id"] = fid
        payload["products"][0]["id"] = pid
        payload["products"][0]["assessment_id"] = aid

        # 1st insertion
        res1 = await client.post("/api/assessments", json=payload)
        assert res1.status_code == 201

        # 2nd insertion (Idempotency test)
        res2 = await client.post("/api/assessments", json=payload)
        assert res2.status_code == 409, "Second seed execution should return 409 Conflict (idempotent, no duplicates created)"

        # Read back
        read_res = await client.get(f"/api/assessments/{aid}")
        assert read_res.status_code == 200
        data = read_res.json()
        assert data["id"] == aid
        assert data["company"]["name"] == payload["company"]["name"]
        assert data["facility"]["name"] == payload["facility"]["name"]
        assert data["industry_name"] == payload["assessment"]["industry_name"]
        assert data["reporting_period_start"]
        assert data["reporting_period_end"]
        assert len(data["products"]) > 0
        assert data["products"][0]["product_name"] == payload["products"][0]["product_name"]
        assert data["status"] == "DRAFT"


# ─────────────────────────────────────────────────────────────────────────────
# 4. TEMPLATE READ TESTS
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_template_read_endpoints():
    """Test template listing, specific loading, industry selection, process ordering, and confirmation status."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # GET /api/industry-templates
        list_res = await client.get("/api/industry-templates")
        assert list_res.status_code == 200
        templates = list_res.json()
        assert len(templates) >= 3
        keys = {t["template_id"] for t in templates}
        assert "industry-food-processing-v1" in keys
        assert "industry-textile-v1" in keys
        assert "industry-universal-v1" in keys

        # Food processing template
        food_res = await client.get("/api/industry-templates/industry-food-processing-v1")
        assert food_res.status_code == 200
        food_t = food_res.json()
        assert food_t["industry_code"] == "food_processing"
        
        # Check process order and IDs
        sequences = [p["sequence"] for p in food_t["processes"]]
        assert sequences == sorted(sequences), "Process sequence order must be preserved"
        process_ids = [p["process_id"] for p in food_t["processes"]]
        assert "food_raw_material_receipt" in process_ids
        assert "food_thermal_processing" in process_ids

        # Textile template
        textile_res = await client.get("/api/industry-templates/industry-textile-v1")
        assert textile_res.status_code == 200
        textile_t = textile_res.json()
        assert textile_t["industry_code"] == "textile"

        # Universal fallback template
        univ_res = await client.get("/api/industry-templates/industry-universal-v1")
        assert univ_res.status_code == 200
        univ_t = univ_res.json()
        assert univ_t["industry_code"] == "other"

        # Loading a template does not mark any process, equipment, or source as confirmed
        assert food_t["candidate_default_status"] == "POTENTIAL"


# ─────────────────────────────────────────────────────────────────────────────
# 5. SOURCE-TYPE READ TESTS
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_source_type_read_endpoints():
    """Test source-type retrieval, metadata, scope preservation, and universal checklist resolution."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Load by ID
        st_res = await client.get("/api/source-types/purchased_grid_electricity")
        assert st_res.status_code == 200
        st = st_res.json()
        assert st["source_type_id"] == "purchased_grid_electricity"
        assert st["name"] == "Purchased grid electricity"
        assert st["default_scope"] == "SCOPE_2"
        assert "electricity" in st["supported_activity_types"]

        # Universal checklist resolution
        univ_res = await client.get("/api/industry-templates/industry-universal-v1")
        univ_source_ids = univ_res.json()["universal_source_type_ids"]
        assert len(univ_source_ids) == 14
        for st_id in univ_source_ids:
            item_res = await client.get(f"/api/source-types/{st_id}")
            assert item_res.status_code == 200, f"Failed to resolve universal source type '{st_id}'"

        # Invalid ID returns 404
        err_res = await client.get("/api/source-types/invalid_source_type_xyz")
        assert err_res.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# 6. RELATIONSHIP TESTS
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_relationships_and_cascade_deletion():
    """Test 1:N relationships and cascade deletes: company->facilities->assessments->products/process_steps."""
    engine = get_test_engine()
    async with engine.connect() as conn:
        trans = await conn.begin()

        cid = uuid4()
        fid1, fid2 = uuid4(), uuid4()
        aid1, aid2 = uuid4(), uuid4()
        pid1, pid2 = uuid4(), uuid4()
        psid1, psid2 = uuid4(), uuid4()

        # 1 Company -> 2 Facilities
        await conn.execute(text("INSERT INTO companies (id, name) VALUES (:cid, 'Test Corp')"), {"cid": cid})
        await conn.execute(text("INSERT INTO facilities (id, company_id, name) VALUES (:f1, :cid, 'Fac 1'), (:f2, :cid, 'Fac 2')"), {"f1": fid1, "f2": fid2, "cid": cid})

        # 1 Facility -> 2 Assessments
        await conn.execute(text("""INSERT INTO assessments 
            (id, facility_id, industry_name, reporting_period_start, reporting_period_end) 
            VALUES (:a1, :f1, 'Food', NOW(), NOW()), (:a2, :f1, 'Textile', NOW(), NOW())"""), 
            {"a1": aid1, "a2": aid2, "f1": fid1})

        # 1 Assessment -> 2 Products
        await conn.execute(text("""INSERT INTO assessment_products (id, assessment_id, product_name)
            VALUES (:p1, :a1, 'Prod 1'), (:p2, :a1, 'Prod 2')"""), {"p1": pid1, "p2": pid2, "a1": aid1})

        # 1 Assessment -> 2 Process Steps
        await conn.execute(text("""INSERT INTO process_steps (id, assessment_id, name)
            VALUES (:ps1, :a1, 'Step 1'), (:ps2, :a1, 'Step 2')"""), {"ps1": psid1, "ps2": psid2, "a1": aid1})

        # Verify insertion
        res_prod = await conn.execute(text("SELECT COUNT(*) FROM assessment_products WHERE assessment_id = :a1"), {"a1": aid1})
        assert res_prod.scalar() == 2

        res_ps = await conn.execute(text("SELECT COUNT(*) FROM process_steps WHERE assessment_id = :a1"), {"a1": aid1})
        assert res_ps.scalar() == 2

        # Cascade delete assessment -> products & process_steps deleted
        await conn.execute(text("DELETE FROM assessments WHERE id = :a1"), {"a1": aid1})
        res_prod_after = await conn.execute(text("SELECT COUNT(*) FROM assessment_products WHERE id IN (:p1, :p2)"), {"p1": pid1, "p2": pid2})
        assert res_prod_after.scalar() == 0
        res_ps_after = await conn.execute(text("SELECT COUNT(*) FROM process_steps WHERE id IN (:ps1, :ps2)"), {"ps1": psid1, "ps2": psid2})
        assert res_ps_after.scalar() == 0

        # Cascade delete company -> facilities & remaining assessment deleted
        await conn.execute(text("DELETE FROM companies WHERE id = :cid"), {"cid": cid})
        res_fac_after = await conn.execute(text("SELECT COUNT(*) FROM facilities WHERE company_id = :cid"), {"cid": cid})
        assert res_fac_after.scalar() == 0
        res_ass_after = await conn.execute(text("SELECT COUNT(*) FROM assessments WHERE id = :a2"), {"a2": aid2})
        assert res_ass_after.scalar() == 0

        await trans.rollback()

    await engine.dispose()


# ─────────────────────────────────────────────────────────────────────────────
# 7. API CONTRACT TESTS
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_api_contracts_validation_and_security():
    """Test HTTP status codes, validation error formats (422), UUID validity, timestamp serialization, and sensitive data exclusion."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Invalid payload (missing required fields)
        invalid_res = await client.post("/api/assessments", json={"invalid": "payload"})
        assert invalid_res.status_code in (400, 422)

        # Valid payload returns HTTP 201
        payload = json.loads(SEED_ASSESSMENT_FILE.read_text(encoding="utf-8"))
        cid = str(uuid4())
        fid = str(uuid4())
        new_aid = str(uuid4())
        payload["company"]["id"] = cid
        payload["facility"]["id"] = fid
        payload["facility"]["company_id"] = cid
        payload["assessment"]["id"] = new_aid
        payload["assessment"]["facility_id"] = fid

        create_res = await client.post("/api/assessments", json=payload)
        assert create_res.status_code == 201

        body = create_res.json()
        assert UUID(body["id"]) == UUID(new_aid)
        assert "T" in body["created_at"]  # ISO 8601 timestamp

        # Verify no database passwords or internal stack traces are exposed in 404/422 responses
        err_res = await client.get(f"/api/assessments/{uuid4()}")
        assert err_res.status_code == 404
        err_body = json.dumps(err_res.json())
        assert "password" not in err_body.lower()
        assert "traceback" not in err_body.lower()


# ─────────────────────────────────────────────────────────────────────────────
# 8. PHASE 1 ACCEPTANCE TEST
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_phase1_end_to_end_acceptance():
    """
    End-to-End Acceptance Test:
    Insert synthetic company -> insert facility -> create assessment -> attach product
    -> read assessment -> load food-processing template -> read template processes
    -> read at least one referenced source type -> verify all records and metadata.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        cid = str(uuid4())
        fid = str(uuid4())
        aid = str(uuid4())
        pid = str(uuid4())

        # 1. Insert synthetic company
        c_res = await client.post("/api/companies", json={
            "id": cid,
            "name": "Phase 1 Acceptance Agro Ltd.",
            "msme_category": "MEDIUM",
            "address": "Vadodara, Gujarat",
        })
        assert c_res.status_code == 201
        company_data = c_res.json()

        # 2. Insert facility
        f_res = await client.post(f"/api/companies/{cid}/facilities", json={
            "id": fid,
            "company_id": cid,
            "name": "Vadodara Dairy Processing Plant",
            "city": "Vadodara",
            "state": "Gujarat",
            "country": "India",
        })
        assert f_res.status_code == 201
        facility_data = f_res.json()

        # 3. Create assessment with attached product
        a_payload = {
            "assessment": {
                "id": aid,
                "facility_id": fid,
                "industry_name": "Food processing",
                "industry_code": "food_processing",
                "industry_template_key": "industry-food-processing-v1",
                "industry_template_version": "1.0.0",
                "reporting_period_start": "2025-04-01T00:00:00+05:30",
                "reporting_period_end": "2026-03-31T23:59:59+05:30",
                "status": "DRAFT",
            },
            "facility": facility_data,
            "company": company_data,
            "products": [
                {
                    "id": pid,
                    "assessment_id": aid,
                    "product_name": "Processed Milk & Cheese",
                    "quantity": "1500.0",
                    "unit": "tonne",
                    "description": "Synthetic annual output for acceptance test",
                }
            ],
        }
        create_ass_res = await client.post("/api/assessments", json=a_payload)
        assert create_ass_res.status_code == 201

        # 4. Read assessment
        read_ass_res = await client.get(f"/api/assessments/{aid}")
        assert read_ass_res.status_code == 200
        ass_data = read_ass_res.json()

        # 5. Load food-processing template
        t_key = ass_data["industry_template_key"]
        t_res = await client.get(f"/api/industry-templates/{t_key}")
        assert t_res.status_code == 200
        template_data = t_res.json()

        # 6. Read template processes
        processes = template_data["processes"]
        assert len(processes) > 0
        ref_source_type_id = processes[0]["suggested_source_type_ids"][0]

        # 7. Read referenced source type
        st_res = await client.get(f"/api/source-types/{ref_source_type_id}")
        assert st_res.status_code == 200
        source_type_data = st_res.json()

        # Final assertions:
        # seeded assessment = readable
        # selected template = readable
        # referenced source type = readable
        # all relationships = intact
        # nothing = incorrectly confirmed
        assert ass_data["id"] == aid
        assert ass_data["company"]["id"] == cid
        assert ass_data["facility"]["id"] == fid
        assert ass_data["products"][0]["id"] == pid
        assert template_data["template_id"] == "industry-food-processing-v1"
        assert source_type_data["source_type_id"] == ref_source_type_id
        assert ass_data["status"] == "DRAFT"
        assert template_data["candidate_default_status"] == "POTENTIAL"
