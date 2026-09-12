#!/usr/bin/env python3
"""Phase 2 API verification script.

Usage:
  python scripts/test-phase2.py --assessment-id <uuid>

The script never talks directly to PostgreSQL; it verifies the running API and
prints JSON suitable for importing into Gemini as a test report.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from uuid import UUID

DEFAULT_ASSESSMENT = "10000000-0000-4000-8000-000000000003"


def request(base: str, method: str, path: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base.rstrip("/") + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        try: payload = json.loads(exc.read() or b"{}")
        except json.JSONDecodeError: payload = {"detail": str(exc)}
        return exc.code, payload
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return 0, {"error": str(exc)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--assessment-id", default=DEFAULT_ASSESSMENT)
    args = parser.parse_args()
    UUID(args.assessment_id)
    aid = args.assessment_id
    results: list[dict] = []

    def check(name: str, passed: bool, detail: str = ""):
        results.append({"test": name, "passed": bool(passed), "detail": detail})

    code, payload = request(args.base_url, "GET", "/health")
    check("health endpoint", code == 200 and payload.get("status") == "ok", str(payload))

    code, processes = request(args.base_url, "GET", f"/api/assessments/{aid}/processes")
    check("read process/equipment/flow mappings", code == 200 and isinstance(processes, list), str(processes)[:300])
    if code == 200:
        check("process response includes nested mappings", all("equipment" in p and "input_output_flows" in p for p in processes), "")
        if not processes:
            # A clean assessment has no facts to trigger rules. Load its selected
            # template so this smoke test exercises the complete Phase 2 path.
            code, processes = request(args.base_url, "POST", f"/api/assessments/{aid}/load-template", {})
            check("prepare test mappings from selected template", code == 200 and bool(processes), str(processes)[:300])

    code, run = request(args.base_url, "POST", f"/api/assessments/{aid}/identify", {"include_ml": False})
    check("ML-free identification completes", code == 200 and run.get("status") == "COMPLETED" and run.get("ml_status") == "DISABLED", str(run))
    run_id = run.get("run_id")

    code, candidates = request(args.base_url, "GET", f"/api/assessments/{aid}/candidates")
    check("read explained candidates", code == 200 and isinstance(candidates, list), str(candidates)[:300])
    if code == 200:
        check("candidates are proposed and explained", all(c.get("status") in {"PROPOSED", "PROMOTED"} and c.get("origin") and c.get("reason") and c.get("source_key") and c.get("evidence_json") for c in candidates), "")
        keys = {(c.get("source_key"), c.get("process_step_id"), c.get("equipment_id"), c.get("origin")) for c in candidates}
        check("candidate deduplication", len(keys) == len(candidates), f"{len(candidates)} rows, {len(keys)} keys")
        check("rule trigger coverage", any(c.get("origin") == "RULE" and c.get("source_key") in {"stationary_fuel_combustion", "refrigerant_fugitive_emissions", "purchased_grid_electricity"} for c in candidates), "Expected at least one deterministic rule candidate")
        candidate_id = candidates[0].get("id") if candidates else None
    else:
        candidate_id = None

    code, checklist = request(args.base_url, "GET", f"/api/assessments/{aid}/checklist")
    check("read universal checklist", code == 200 and isinstance(checklist.get("items"), list) and len(checklist["items"]) >= 1, str(checklist)[:300])
    if code == 200:
        items = checklist["items"]
        check("unobserved sources are missing-information", all(i.get("status") != "0" for i in items), "No checklist item may use numeric zero")
        check("universal checklist has unique source keys", len({i.get("source_key") for i in items}) == len(items), "")

    if candidate_id:
        review = {"status": "CONFIRMED", "confirmation_note": "Phase 2 API verification", "confirmed_by": "phase2-test@example.com", "confirmed_at": datetime.now(timezone.utc).isoformat()}
        code, inventory = request(args.base_url, "POST", f"/api/assessments/{aid}/candidates/{candidate_id}/review", review)
        check("update source status and promote inventory", code == 201 and inventory.get("status") == "CONFIRMED" and inventory.get("candidate_id") == candidate_id, str(inventory))

    other = "00000000-0000-4000-8000-000000000099"
    code, foreign = request(args.base_url, "GET", f"/api/assessments/{other}/candidates")
    check("candidate ownership boundary", code == 200 and foreign == [], str(foreign))
    if run_id:
        code, run_read = request(args.base_url, "GET", f"/api/assessments/{aid}/identification-runs/{run_id}")
        check("read completed identification run", code == 200 and run_read.get("status") == "COMPLETED" and run_read.get("input_hash") and run_read.get("engine_version"), str(run_read))

    report = {"phase": "Phase 2", "assessment_id": aid, "passed": all(x["passed"] for x in results), "passed_count": sum(x["passed"] for x in results), "total": len(results), "tests": results}
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
