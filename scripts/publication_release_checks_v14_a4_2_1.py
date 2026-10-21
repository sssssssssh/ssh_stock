"""Original publication release assertions extracted unchanged from baseline CI."""

import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path


def validate(core, capacity, head):
    previous = Path.cwd()
    try:
        os.chdir(core)
        Path(".codex_tmp").mkdir(exist_ok=True)
        Path(".codex_tmp/cold-start-capacity.json").write_text(json.dumps(capacity))
        assert head == os.environ["GITHUB_SHA"]
        containers = json.loads(Path(".codex_tmp/data-queue-containers.json").read_text())
        browser = json.loads(Path(
            "frontend/coverage/runtime-reliability-browser/result.json").read_text())
        assert containers["head_sha"] == browser["head_sha"] == head
        assert not containers["working_tree_dirty"] and not browser["working_tree_dirty"]
        assert len(containers["results"]) == 3
        assert all(r["max_top_level_running"] == 1 for r in containers["results"])
        assert any(r["workers"] == 2 and r["atomic_publication"] and r["completed"] == 7
                   for r in containers["results"])
        assert len(browser["results"]) == 28 and all(r["passed"] for r in browser["results"])
        suites = {}
        for name in ("data-publication-targeted", "m17_1_2-full"):
            root = ET.parse(f".codex_tmp/{name}.xml").getroot()
            cases = list(root.iter("testcase"))
            assert cases and not any(list(c.iter("failure")) or list(c.iter("error"))
                                     or list(c.iter("skipped")) for c in cases)
            suites[name] = len(cases)
        capacity = json.loads(Path(".codex_tmp/cold-start-capacity.json").read_text())
        assert capacity["head_sha"] == head and not capacity["working_tree_dirty"]
        assert [r["level"] for r in capacity["results"]] == ["L1", "L2", "L3-scaled-10pct"]
        assert all(not r["reader_errors"] and r["max_running"] <= 1
                   and r["rows"] < r["row_budget"]
                   and r["publish_seconds"] < r["merge_timeout_ms"] / 1000
                   for r in capacity["results"])
        assert all(r["final_root_status"] == "SUCCESS" and r["final_ledger_state"] == "PUBLISHED"
            and len(r["rollback_probes"]) == 2 and all(
            p["a_digest_unchanged"] and p["queue_slot_held"]
            and p["a_before"] == p["a_after"]
            and p["root_status"] == "RUNNING" and p["ledger_state"] == "PREPARING"
            for p in r["rollback_probes"]) for r in capacity["results"])
        comparison = json.loads(Path(".codex_tmp/cold-start-comparison.json").read_text())
        assert comparison["head_sha"] == head and not comparison["working_tree_dirty"]
        assert all(r.get("equal_rtol_atol_1e_12") for r in comparison["cases"]
                   if r["scenario"] == "complete")
        assert all("error_type" not in r["new"] for r in comparison["cases"])
        cold = ET.parse(".codex_tmp/cold-start-targeted.xml").getroot()
        cold_cases = list(cold.iter("testcase"))
        assert cold_cases and not any(list(c.iter("failure")) or list(c.iter("error"))
                                     or list(c.iter("skipped")) for c in cold_cases)
        suites["cold-start-targeted"] = len(cold_cases)
        Path(".codex_tmp/data-publication-release.json").write_text(json.dumps({
            "schema_version": "data-publication-v1.1", "head_sha": head,
            "ci_run_url": (f"https://github.com/{os.environ['GITHUB_REPOSITORY']}/actions/runs/"
                           f"{os.environ['GITHUB_RUN_ID']}"),
            "suites": suites, "browser_scenarios": 28, "containers": containers,
            "cold_start_capacity": capacity,
            "production_validation": "PENDING_SEPARATE_APPROVAL",
        }, indent=2) + "\n")
        return json.loads(Path(".codex_tmp/data-publication-release.json").read_text())
    finally:
        os.chdir(previous)
