import importlib
import json
import os
import subprocess
import sys

import pytest

from scripts import biz_perf_p1_04_diagnostic as d
from scripts import biz_perf_p1_04_measure_wiring as wiring

SHA = "a" * 40


@pytest.fixture
def sample(tmp_path):
    source = tmp_path / "fixture"
    wiring.emit_fixture(source, contract=wiring.build_preflight(implementation_sha=SHA))
    # emit_fixture's create/claim double consumes no clock time. Give this
    # reporting fixture a distinct five-ms create/claim interval, so accidental
    # root + worker or root + post arithmetic cannot pass unnoticed.
    events = rows(source)
    for row in events[1:]:
        row["elapsed_ms"] += 5
        if row["event_kind"] == "stage":
            row["started_ms"] += 5
    save(source, events)
    return source


def module():
    return importlib.import_module("scripts.biz_perf_p1_04_pretest_report")


def rows(source):
    return [d.decode(line) for line in (source / "events.jsonl").read_bytes().splitlines()]


def save(source, events):
    (source / "events.jsonl").write_bytes(b"".join(d.encode(event) for event in events))


def event(source, kind):
    return next(row for row in rows(source) if row["event_kind"] == kind)


def reject(source, expected=SHA):
    with pytest.raises(module().ReportRejected, match="^PRETEST_EVIDENCE_REJECTED$"):
        module().summarize_offline(source, expected)


def change(source, kind, **values):
    events = rows(source)
    next(row for row in events if row["event_kind"] == kind).update(values)
    save(source, events)


def contract_change(source, **values):
    path = source / "preflight.json"
    value = d.decode(path.read_bytes())
    value.update(values)
    path.write_bytes(d.encode(value))


def test_report_entry_exists():
    report = importlib.import_module("scripts.biz_perf_p1_04_pretest_report")
    assert callable(report.summarize_offline)


def test_execute_refuses_without_reading(capsys):
    report = importlib.import_module("scripts.biz_perf_p1_04_pretest_report")
    assert report.main(["execute", "--permit=MOCK"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["authorization"] == "AUTHORIZATION_PENDING"
    assert result["root_attempts"] == 0


def test_complete_wiring_fixture_replays_read_only(sample, monkeypatch):
    before = {p.name: (p.stat().st_ino, p.stat().st_mtime_ns, p.read_bytes())
              for p in sample.iterdir()}

    def forbidden(*args, **kwargs):
        pytest.fail("report reached a write or recorder port")

    monkeypatch.setattr(d, "validate_bundle", forbidden)
    monkeypatch.setattr(d, "publish", forbidden)
    monkeypatch.setattr(wiring, "OfflineRootRecorder", forbidden)
    result = module().summarize_offline(sample, SHA)
    assert result["status"] == "HYPOTHESIS_ONLY"
    assert result["source_evidence_kind"] == "OFFLINE_FIXTURE"
    assert result["hotspot_decision"] == "NONE_PROVEN"
    assert result["evidence_complete"] is True
    assert result["b_gate"] == result["targeted_pg17_gate"] == "NOT_APPROVED"
    assert result["budget"] == "DRAFT_NOT_APPROVED"
    assert result["root_attempts"] == 0
    assert all(row["status"] == "HYPOTHESIS" for row in result["investigation_priorities"])
    after = {p.name: (p.stat().st_ino, p.stat().st_mtime_ns, p.read_bytes())
             for p in sample.iterdir()}
    assert before == after


def test_root_post_and_worker_are_separate_not_added(sample):
    result = module().summarize_offline(sample, SHA)
    frozen = event(sample, "root_frozen")["elapsed_ms"]
    started = event(sample, "root_started")["elapsed_ms"]
    worker = event(sample, "worker_started")["elapsed_ms"]
    post = event(sample, "post_root_validation")["elapsed_ms"]
    assert result["root_elapsed_ms"] == frozen - started
    assert result["execute_claimed_job_ms"] == frozen - worker
    assert result["post_root_validation_ms"] == post - frozen == 7
    assert result["root_elapsed_ms"] > result["execute_claimed_job_ms"] > 0
    assert "overall_ms" not in result and "total_elapsed_ms" not in result


def test_post_interval_cannot_inflate_root_or_root_sql(sample):
    before = module().summarize_offline(sample, SHA)
    events = rows(sample)
    for row in events:
        if row["event_kind"] in ("post_root_validation", "cleanup"):
            row["elapsed_ms"] += 300
    save(sample, events)
    after = module().summarize_offline(sample, SHA)
    assert after["post_root_validation_ms"] == before["post_root_validation_ms"] + 300
    for key in ("root_elapsed_ms", "execute_claimed_job_ms", "sql_snapshot"):
        assert after[key] == before[key]


def test_overlapping_stages_sorted_only_as_fixture_inclusive(sample):
    events = rows(sample)
    original = next(row for row in events if row["event_kind"] == "stage")
    worker_ms = event(sample, "worker_started")["elapsed_ms"]
    freeze_ms = event(sample, "root_frozen")["elapsed_ms"]
    original.update(started_ms=worker_ms, elapsed_ms=freeze_ms)
    second = dict(original, stage_name="candidate_store_batch")
    events.insert(events.index(original) + 1, second)
    for seq, row in enumerate(events, 1):
        row["seq"] = seq
    save(sample, events)
    result = module().summarize_offline(sample, SHA)
    ranked = result["fixture_stage_top3"]
    assert sum(row["stage_inclusive_ms"] for row in ranked) > result["root_elapsed_ms"]
    assert [row["stage_name"] for row in ranked] == ["candidate_store_batch", "factors.compute"]
    assert result["aggregation"] == "INCLUSIVE_DO_NOT_SUM"
    assert result["hotspot_decision"] == "NONE_PROVEN"
    assert "STAGE_INCLUSIVE_OVERLAP_DO_NOT_SUM_OR_TREAT_AS_GLOBAL_SHARES" in result["limitations"]


@pytest.mark.parametrize("cpu,ratio", [(0, "UNDEFINED"), ("UNKNOWN", "UNDEFINED")])
def test_zero_or_unobserved_cpu_not_a_zero_ratio(sample, cpu, ratio):
    change(sample, "root_frozen", process_cpu_ms=cpu)
    result = module().summarize_offline(sample, SHA)
    assert result["process_cpu_ms"] == cpu
    assert result["wall_per_cpu"] == ratio


def test_absent_cpu_field_is_corruption_not_an_observed_zero(sample):
    events = rows(sample)
    next(row for row in events if row["event_kind"] == "root_frozen").pop("process_cpu_ms")
    save(sample, events)
    reject(sample)


@pytest.mark.parametrize("value", ["UNKNOWN", 0])
def test_fetch_unobserved_and_observed_zero_remain_distinct(sample, value):
    change(sample, "root_frozen", fetch_observed_ms=value, fetched_rows=value)
    result = module().summarize_offline(sample, SHA)
    assert result["fetch_observed_ms"] == result["fetched_rows"] == value
    assert result["sql_calls"] == 11
    assert result["sql_execute_ms"] == "UNKNOWN"


def test_sql_fetch_overlap_never_subtracted_from_wall(sample):
    change(sample, "stage", sql_execute_ms=20, fetch_observed_ms=20)
    result = module().summarize_offline(sample, SHA)
    row = result["diagnostic_positions"]["factors.compute"][0]
    assert row["stage_inclusive_ms"] == row["sql_execute_ms"] == row["fetch_observed_ms"] == 20
    assert "SQL_AND_FETCH_MAY_OVERLAP_DO_NOT_SUM" in result["limitations"]
    assert "residual_ms" not in row and "exclusive_ms" not in row


def test_missing_focus_stages_and_input_verify_are_not_zero(sample):
    positions = module().summarize_offline(sample, SHA)["diagnostic_positions"]
    for name in ("candidate_lookup_batch", "candidate_store_batch", "publication.verify"):
        assert positions[name][0]["stage_inclusive_ms"] == "UNKNOWN"
        assert positions[name][0]["coverage_reason"] == "NOT_INSTRUMENTED"
    assert positions["factors.input_verify"]["coverage_reason"] == "NOT_INSTRUMENTED"
    assert "ABSENT_FROM_FROZEN_STAGE_ALLOWLIST" in positions["factors.input_verify"]["mapping"]


def test_lookup_observed_does_not_imply_store_observed(sample):
    change(sample, "stage", stage_name="candidate_lookup_batch", sql_calls=0,
           sql_execute_ms=0, fetch_observed_ms=0, fetched_rows=0)
    positions = module().summarize_offline(sample, SHA)["diagnostic_positions"]
    assert positions["candidate_lookup_batch"][0]["sql_calls"] == 0
    assert positions["candidate_store_batch"][0]["sql_calls"] == "UNKNOWN"


@pytest.mark.parametrize("kind,values", [
    ("root_frozen", {"sql_counts": {}}),
    ("stage", {"instrumented": False, "coverage_reason": "NOT_INSTRUMENTED",
               "sql_execute_ms": "UNKNOWN", "sql_calls": "UNKNOWN",
               "fetch_observed_ms": "UNKNOWN", "fetched_rows": "UNKNOWN"}),
    ("post_root_validation", {"quality_verified": False}),
    ("post_root_validation", {"job_status": "UNKNOWN"}),
    ("cleanup", {"cleanup_status": "BLOCKED"}),
    ("stage", {"stage_name": "factors.input_verify"}),
], ids=["no-sql", "no-instrumented-stage", "bad-quality", "unknown-root",
        "cleanup-blocked", "unsupported-stage"])
def test_frozen_completion_and_stage_allowlist_cannot_be_bypassed(sample, kind, values):
    change(sample, kind, **values)
    reject(sample)


def test_rss_is_not_distributed_to_stages(sample):
    result = module().summarize_offline(sample, SHA)
    assert result["rss_peak_bytes"] == 1024
    assert all("rss_peak_bytes" not in row for row in result["stage_observations"])
    assert "RSS_IS_PROCESS_LIFETIME_HIGH_WATER_MARK_NOT_STAGE_ALLOCATION" in result["limitations"]


@pytest.mark.parametrize("expected", ["b" * 40, "a" * 39, None, True])
def test_external_sha_required(sample, expected):
    reject(sample, expected)


def test_cross_run_uuid_refused(sample):
    change(sample, "stage", run_uuid="00000000-0000-0000-0000-000000000002")
    reject(sample)


def test_cross_root_refused(sample):
    change(sample, "stage", root_job_id="00000000-0000-0000-0000-000000000002")
    reject(sample)


@pytest.mark.parametrize("kind", ["cleanup", "root_frozen", "post_root_validation"])
def test_missing_terminal_evidence_never_partial_success(sample, kind):
    events = [row for row in rows(sample) if row["event_kind"] != kind]
    for seq, row in enumerate(events, 1):
        row["seq"] = seq
    save(sample, events)
    reject(sample)


@pytest.mark.parametrize("value", [-1, 1_200_001, True])
def test_out_of_bounds_elapsed_refused(sample, value):
    change(sample, "stage", elapsed_ms=value)
    reject(sample)


def test_stage_cannot_start_before_worker(sample):
    change(sample, "stage", started_ms=event(sample, "root_started")["elapsed_ms"])
    reject(sample)


@pytest.mark.parametrize("payload", [
    b'{"seq":1,"seq":2}\n', b'{"x":NaN}\n', b'{"x":Infinity}\n',
    b'{"x":1e999}\n', b'\xff\n', b'[]\n',
], ids=["duplicate", "nan", "infinity", "overflow", "utf8", "array"])
def test_malformed_events_fixed_code(sample, payload):
    (sample / "events.jsonl").write_bytes(payload)
    reject(sample)


def test_missing_lf_refused(sample):
    path = sample / "events.jsonl"
    path.write_bytes(path.read_bytes().rstrip(b"\n"))
    reject(sample)


def test_bad_preflight_binding_digest_refused(sample):
    change(sample, "root_started", preflight_sha256="0" * 64)
    reject(sample)


def test_rebound_wrong_source_digest_still_refused(sample):
    contract_change(sample, business_source_sha256="0" * 64)
    contract = d.decode((sample / "preflight.json").read_bytes())
    change(sample, "root_started", preflight_sha256=d.preflight_digest(contract))
    reject(sample)


@pytest.mark.parametrize("key,value", [
    ("evidence_kind", "REAL"), ("source_role", "OWNER"), ("permit", "APPROVED"),
])
def test_source_role_and_authority_self_claim_refused(sample, key, value):
    contract_change(sample, **{key: value})
    reject(sample)


def test_old_03b_schema_refused(sample):
    (sample / "preflight.json").write_bytes(d.encode({"schema": d.LEGACY_SCHEMA}))
    reject(sample)


def test_forged_summary_object_is_not_an_input():
    reject({"evidence_complete": True, "status": "OFFLINE_VALIDATED"})


@pytest.mark.parametrize("name", ["events.jsonl", "preflight.json"])
def test_missing_fixed_file_refused(sample, name):
    (sample / name).unlink()
    reject(sample)


@pytest.mark.parametrize("name,limit", [
    ("events.jsonl", d.MAX_RAW_BYTES), ("preflight.json", d.MAX_LINE_BYTES),
])
def test_oversize_input_refused_before_replay(sample, name, limit):
    (sample / name).write_bytes(b"x" * (limit + 1))
    reject(sample)


def test_oversize_line_refused(sample):
    (sample / "events.jsonl").write_bytes(b" " * d.MAX_LINE_BYTES + b"\n")
    reject(sample)


def test_path_traversal_refused(sample):
    reject(sample / ".." / sample.name)


def test_hardlinked_event_file_refused(sample, tmp_path):
    os.link(sample / "events.jsonl", tmp_path / "extra-link")
    reject(sample)


def test_cli_success_is_bounded_no_raw_events_or_writes(sample, capsys):
    before = sorted(p.name for p in sample.iterdir())
    assert module().main([
        "summarize-offline", "--input-dir", str(sample),
        "--expected-implementation-sha", SHA,
    ]) == 0
    raw = capsys.readouterr().out
    result = json.loads(raw)
    assert len(raw.encode("ascii")) <= module().MAX_REPORT_BYTES
    assert result["authorization"] == "AUTHORIZATION_PENDING"
    assert "event_kind" not in raw and "expected_instance" not in raw and str(sample) not in raw
    assert sorted(p.name for p in sample.iterdir()) == before


def test_cli_corrupt_input_has_no_partial_metrics_or_exception(sample, capsys):
    (sample / "events.jsonl").write_bytes(b"private-secret-invalid-json\n")
    assert module().main([
        "summarize-offline", "--input-dir", str(sample),
        "--expected-implementation-sha", SHA,
    ]) == 2
    raw = capsys.readouterr().out
    result = json.loads(raw)
    assert result["error_code"] == "PRETEST_EVIDENCE_REJECTED"
    assert result["evidence_complete"] is False
    assert "root_elapsed_ms" not in result
    assert "secret" not in raw and str(sample) not in raw


@pytest.mark.parametrize("argv", [
    [], ["audit"], ["--help"], ["summarize-offline", "--output-dir", "private"],
    ["summarize-offline", "--permit=APPROVED"],
])
def test_cli_unknown_modes_cannot_supply_authority(argv, capsys):
    assert module().main(argv) == 2
    raw = capsys.readouterr().out
    assert json.loads(raw)["error_code"] == "PRETEST_ARGUMENTS_REJECTED"
    assert "private" not in raw


def test_execute_cannot_read_fixture_even_with_mock_permit(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail("execute read input")

    monkeypatch.setattr(d, "directory", forbidden)
    assert module().main(["execute", "--input-dir=secret", "--permit=MOCK", "--force"]) == 2
    raw = capsys.readouterr().out
    assert json.loads(raw)["error_code"] == "AUTHORIZATION_PENDING"
    assert "secret" not in raw


def test_real_cli_process_stays_offline_and_refuses_execute():
    probe = (
        "import sys; from scripts import biz_perf_p1_04_pretest_report as r; "
        "assert not any(k.split('.')[0] in ('app','psycopg','sqlalchemy','dotenv') "
        "for k in sys.modules); raise SystemExit(r.main(['execute','--permit=MOCK']))"
    )
    process = subprocess.run([sys.executable, "-B", "-c", probe], capture_output=True,
                             text=True, timeout=10, check=False)
    assert process.returncode == 2 and process.stderr == ""
    assert json.loads(process.stdout)["authorization"] == "AUTHORIZATION_PENDING"


def test_module_cli_process_summarizes_only_explicit_fixture(sample):
    process = subprocess.run([
        sys.executable, "-B", "-m", "scripts.biz_perf_p1_04_pretest_report",
        "summarize-offline", "--input-dir", str(sample), "--expected-implementation-sha", SHA,
    ], capture_output=True, text=True, timeout=10, check=False)
    assert process.returncode == 0 and process.stderr == ""
    result = json.loads(process.stdout)
    assert result["status"] == "HYPOTHESIS_ONLY" and result["root_attempts"] == 0
    assert result["root_elapsed_ms"] == 25
