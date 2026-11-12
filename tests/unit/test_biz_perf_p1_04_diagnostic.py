import hashlib
import json
from pathlib import Path

import pytest

from scripts import biz_perf_03_b_once as legacy
from scripts import biz_perf_p1_04_diagnostic as d
from scripts.business_sql_snapshot import RootCounts, validate

HEAD = "a" * 40
RUN = "00000000-0000-0000-0000-000000000001"
ROOT = "00000000-0000-0000-0000-000000000002"
OTHER_ROOT = "00000000-0000-0000-0000-000000000003"


@pytest.fixture
def bundle(tmp_path):
    source = tmp_path / "inputs"
    source.mkdir()
    instance = dict(scope="ISOLATED_SYNTHETIC", host="127.0.0.1",
                    database=f"v14_{'4' * 32}_test", pg_major=17, marker=OTHER_ROOT,
                    system_identifier="123", pgdata_sha256="1" * 64, network_sha256="2" * 64,
                    owner_sha256="3" * 64)
    contract = dict(
        schema_version=d.SCHEMA, evidence_kind=d.FIXTURE, design_baseline_sha=d.BASELINE,
        measurement_implementation_sha=HEAD, worktree="CLEAN",
        business_source_sha256=d.BUSINESS_SOURCE_SHA256,
        run_uuid=RUN, run_attempt=1, stocks=8, months=1, flags=dict.fromkeys(d.FLAGS, False),
        expected_instance=instance, observed_instance=instance.copy(), dataset_sha256="5" * 64,
        strategy_sha256="6" * 64, env_identity_digest="7" * 64, resource_budget_id="8" * 64,
    )
    stage = dict(started_ms=40, stage_name="factors.compute", instrumented=True,
                 coverage_reason="RECORDED", sql_execute_ms=d.UNKNOWN, sql_calls=d.UNKNOWN,
                 fetch_observed_ms=d.UNKNOWN, fetched_rows=d.UNKNOWN)
    events = [
        ("root_started", 10, {"preflight_sha256": d.preflight_digest(contract)}),
        ("worker_started", 30, {}),
        ("stage", 75, stage),
        ("stage", 85, dict(stage, stage_name="candidate_lookup_batch", started_ms=50)),
        ("root_frozen", 100, dict(sql_counts={"SELECT": 9, "WITH": 2}, process_cpu_ms=40,
                                  rss_peak_bytes=1000, fetch_observed_ms=20, fetched_rows=100)),
        ("post_root_validation", 130, dict(
            job_status="SUCCESS", publication_state="PUBLISHED", quality_verified=True,
            no_candidate_leak=True, atomic_publication_verified=True,
            tables_sha256=dict.fromkeys(d.TABLES, "a" * 64), source_mismatches=0,
        )),
        ("cleanup", 140, dict(cleanup_status="COMPLETE", instance=instance.copy())),
    ]
    rows = [dict(event_kind=kind, elapsed_ms=ms, seq=i, run_uuid=RUN, root_job_id=ROOT,
                 utc="2026-11-12T00:00:00Z", **values)
            for i, (kind, ms, values) in enumerate(events, 1)]
    return source, tmp_path / "output", contract, rows


def write_bundle(bundle, raw=None):
    source, _, contract, events = bundle
    (source / "preflight.json").write_text(json.dumps(contract), encoding="utf-8")
    payload = raw if raw is not None else b"".join(d.encode(event) for event in events)
    (source / "events.jsonl").write_bytes(payload)


def run(bundle):
    source, output, _, _ = bundle
    return d.validate_bundle(source, output, HEAD)


def read(path):
    return json.loads(path.read_bytes())


def rejected(bundle, code, *, raw=None):
    write_bundle(bundle, raw)
    with pytest.raises(d.Rejected, match=f"^{code}$"):
        run(bundle)
    output = bundle[1]
    failure = read(output / "failure_receipt.json")
    assert failure["status"] == code and failure["hotspot_decision"] == "NONE_PROVEN"
    assert not failure["evidence_complete"] and failure["root_attempts"] == 0
    assert not (output / "integrity.json").exists()
    return failure


def test_T01_execute_rejects_before_any_input_or_callback(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail("execute reached offline/file path")

    monkeypatch.setattr(d, "validate_bundle", forbidden)
    monkeypatch.setattr(d, "directory", forbidden)
    assert d.main(["execute"]) == 2
    assert capsys.readouterr().out == "AUTHORIZATION_PENDING\n"


@pytest.mark.parametrize("field,value,code", [
    ("design_baseline_sha", "c" * 40, "SOURCE_MISMATCH"),
    ("measurement_implementation_sha", "b" * 40, "SOURCE_MISMATCH"),
    ("business_source_sha256", "", "SOURCE_MISMATCH"),
    ("business_source_sha256", "0" * 64, "SOURCE_MISMATCH"),
    ("worktree", "DIRTY", "SOURCE_MISMATCH"),
    ("run_uuid", "invalid", "IDENTITY_REJECTED"),
    ("env_identity_digest", "", "IDENTITY_REJECTED"),
    ("expected_instance", None, "INSTANCE_REJECTED"),
    ("dataset_sha256", None, "IDENTITY_REJECTED"),
])
def test_T02_preflight_checks_source_and_identity(bundle, field, value, code):
    if value is None and field == "dataset_sha256":
        del bundle[2][field]
        code = "PREFLIGHT_REJECTED"
    else:
        bundle[2][field] = value
    rejected(bundle, code)


def test_T02_valid_format_with_wrong_input_digest_cannot_rebind_events(bundle):
    bundle[2]["dataset_sha256"] = "9" * 64
    assert rejected(bundle, "IDENTITY_REJECTED")["last_durable_seq"] == 0


def test_T03_old_protocol_is_never_an_eight_stock_authorization(bundle):
    old = legacy.protocol()  # Reads the frozen JSON only.
    assert (old["stocks"], old["total_seconds"], old["maximum_raw_rows"]) == (4, 420, 5000)
    bundle[2].clear()
    bundle[2].update(old)
    rejected(bundle, "LEGACY_PROTOCOL_REFUSED")


@pytest.mark.parametrize("flag", sorted(d.FLAGS - {"perf_diagnostics_enabled"}))
def test_T04_each_optimization_flag_refused(bundle, flag):
    bundle[2]["flags"][flag] = True
    rejected(bundle, "FLAG_MISMATCH")


def test_T05_perf_diagnostics_refused(bundle):
    bundle[2]["flags"]["perf_diagnostics_enabled"] = True
    rejected(bundle, "FLAG_MISMATCH")


def test_T06_offline_cli_reopens_a_complete_fixture_bundle(bundle, capsys):
    source, output, _, events = bundle
    payload = b"".join((json.dumps(event) + "\r\n").encode() for event in events)
    write_bundle(bundle, payload)
    assert d.main(["validate", "--input-dir", str(source), "--output-dir", str(output),
                   "--expected-implementation-sha", HEAD]) == 0
    assert capsys.readouterr().out == "OFFLINE_VALIDATED\n"
    expected_files = {"preflight.json", "raw_events.jsonl", "root_snapshot.json",
                      "post_root_validation.json", "summary.json"}
    manifest = read(output / "integrity.json")
    assert set(manifest) == expected_files
    for name, integrity in manifest.items():
        raw = (output / name).read_bytes()
        assert integrity == dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    assert (output / "raw_events.jsonl").read_bytes() == payload
    summary = read(output / "summary.json")
    assert summary["evidence_complete"] is True and summary["root_attempts"] == 0
    assert summary["hotspot_decision"] == "NONE_PROVEN"


def test_T07_frozen_root_excludes_post_root_validation_sql_and_time(bundle):
    counts = RootCounts()
    for operation in ("SELECT", "SELECT", "WITH"):
        assert counts.begin(operation)
        counts.end()
    bundle[3][4]["sql_counts"] = counts.freeze()
    assert not counts.begin("SELECT")  # Independent result read after root return.
    write_bundle(bundle)
    run(bundle)
    root = read(bundle[1] / "root_snapshot.json")
    post = read(bundle[1] / "post_root_validation.json")
    validate(root["sql_snapshot"])
    assert root["sql_snapshot"]["counts"] == {"SELECT": 2, "WITH": 1}
    assert root["root_elapsed_ms"] == 90 and root["execute_claimed_job_ms"] == 70
    assert post["post_root_validation_ms"] == 30 and "sql_counts" not in post


def test_T08_nested_inclusive_times_are_never_summed_into_root(bundle):
    bundle[3][2]["started_ms"] = 30
    bundle[3][3]["started_ms"] = 30
    write_bundle(bundle)
    result = run(bundle)
    stages = result["fixture_stage_top3"]
    assert [row["stage_inclusive_ms"] for row in stages] == [55, 45]
    assert sum(row["stage_inclusive_ms"] for row in stages) > 90
    assert result["aggregation"] == "INCLUSIVE_DO_NOT_SUM"
    assert read(bundle[1] / "root_snapshot.json")["root_elapsed_ms"] == 90


def test_T09_missing_fetch_stays_unknown_and_zero_stays_zero(bundle):
    bundle[3][4].update(fetch_observed_ms=d.UNKNOWN, fetched_rows=d.UNKNOWN)
    bundle[3][3].update(fetch_observed_ms=0, fetched_rows=0)
    write_bundle(bundle)
    result = run(bundle)
    root = read(bundle[1] / "root_snapshot.json")
    assert root["fetched_rows"] == root["fetch_observed_ms"] == d.UNKNOWN
    by_name = {row["stage_name"]: row for row in result["stage_observations"]}
    assert by_name["candidate_lookup_batch"]["fetched_rows"] == 0
    assert by_name["factors.stock_daily"]["coverage_reason"] == "NOT_INSTRUMENTED"
    assert by_name["factors.stock_daily"]["fetched_rows"] == d.UNKNOWN


def test_T10_zero_cpu_gives_undefined_and_no_hotspot_result(bundle):
    bundle[3][4]["process_cpu_ms"] = 0
    write_bundle(bundle)
    result = run(bundle)
    assert result["wall_per_cpu"] == "UNDEFINED" and result["hotspot_decision"] == "NONE_PROVEN"
    assert read(bundle[1] / "root_snapshot.json")["process_cpu_ms"] == 0


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_T10_nonfinite_cpu_is_rejected(bundle, value):
    bundle[3][4]["process_cpu_ms"] = value
    raw = b"".join((json.dumps(event) + "\n").encode() for event in bundle[3])
    assert rejected(bundle, "EVIDENCE_INVALID", raw=raw)["last_durable_seq"] == 4


def test_T11_derived_report_failure_leaves_durable_raw_and_root(bundle, monkeypatch):
    def failed_summary(self):
        assert (bundle[1] / "raw_events.jsonl").read_bytes().count(b"\n") == 7
        assert (bundle[1] / "root_snapshot.json").is_file()
        raise ArithmeticError("private diagnostic failure")

    monkeypatch.setattr(d.Replay, "summary", failed_summary)
    failure = rejected(bundle, "EVIDENCE_INCOMPLETE")
    assert failure["last_durable_seq"] == 7
    assert not (bundle[1] / "summary.json").exists()
    assert b"private" not in (bundle[1] / "failure_receipt.json").read_bytes()


def test_T11_snapshot_hash_mismatch_rejected_before_summary(bundle, monkeypatch):
    original = d.publish

    def tamper(path, value):
        result = original(path, value)
        if path.name == "root_snapshot.json":
            path.write_bytes(b"{}\n")
        return result

    monkeypatch.setattr(d, "publish", tamper)
    assert rejected(bundle, "EVIDENCE_INCOMPLETE")["last_durable_seq"] == 7
    assert not (bundle[1] / "summary.json").exists()


@pytest.mark.parametrize("fault", ["truncated", "duplicate-seq", "duplicate-key", "malformed"])
def test_T12_bad_jsonl_keeps_only_valid_prefix(bundle, fault):
    events = bundle[3][:2]
    tail = events[1].copy()
    raw = d.encode(tail)
    if fault == "truncated":
        raw = raw[:-1]
    elif fault == "duplicate-key":
        raw = raw[:-2] + b',"seq":2}\n'
    elif fault == "malformed":
        raw = b"not-json\n"
    prefix = d.encode(events[0])
    assert rejected(bundle, "EVIDENCE_INVALID", raw=prefix + raw if fault != "duplicate-seq"
                    else prefix + raw + raw)["last_durable_seq"] == (
                        2 if fault == "duplicate-seq" else 1)
    assert (bundle[1] / "raw_events.jsonl").read_bytes() == (
        prefix + raw if fault == "duplicate-seq" else prefix)


def test_T13_size_and_disk_write_failure(bundle, monkeypatch):
    write_bundle(bundle)
    original = d.sync_write
    writes = 0

    def fail_second_raw_write(stream, raw):
        nonlocal writes
        if Path(stream.name).name == "raw_events.jsonl":
            writes += 1
            if writes == 2:
                raise OSError("disk full")
        original(stream, raw)

    monkeypatch.setattr(d, "sync_write", fail_second_raw_write)
    assert rejected(bundle, "EVIDENCE_INCOMPLETE")["last_durable_seq"] == 1
    assert (bundle[1] / "raw_events.jsonl").read_bytes() == d.encode(bundle[3][0])
    new_bundle = (bundle[0], bundle[1].with_name("too-large"), *bundle[2:])
    monkeypatch.setattr(d, "MAX_RAW_BYTES", 16)
    assert rejected(new_bundle, "SIZE_LIMIT")["last_durable_seq"] == 0


def test_T13_output_link_and_traversal_refused_without_writing(bundle, monkeypatch):
    source, output, _, _ = bundle
    write_bundle(bundle)
    output.mkdir()
    marker = output / "owner-data"
    marker.write_bytes(b"untouched")
    with pytest.raises(d.Rejected, match="^OUTPUT_EXISTS$"):
        run(bundle)
    assert list(output.iterdir()) == [marker] and marker.read_bytes() == b"untouched"
    original = Path.is_junction
    monkeypatch.setattr(Path, "is_junction", lambda p: p == output or original(p))
    with pytest.raises(d.Rejected, match="^PATH_REJECTED$"):
        d.validate_bundle(source, output / "nested", HEAD)
    with pytest.raises(d.Rejected, match="^PATH_REJECTED$"):
        d.validate_bundle(source, output / ".." / "nested", HEAD)
    assert not (output / "nested").exists()


@pytest.mark.parametrize("fault", ["second-attempt", "second-root", "duplicate-start"])
def test_T14_single_attempt_no_retry(bundle, fault):
    if fault == "second-attempt":
        bundle[2]["run_attempt"] = 2
        expected = 0
    elif fault == "second-root":
        bundle[3][1]["root_job_id"] = OTHER_ROOT
        expected = 1
    else:
        bundle[3][1].update(event_kind="root_started",
                            preflight_sha256=bundle[3][0]["preflight_sha256"])
        expected = 1
    assert rejected(bundle, "ONE_ATTEMPT_CONSUMED")["last_durable_seq"] == expected


@pytest.mark.parametrize("fault", ["ledger", "missing-digest", "quality"])
def test_T15_success_requires_publication_and_all_validation(bundle, fault):
    post = bundle[3][5]
    if fault == "ledger":
        post["publication_state"] = "PREPARING"
    elif fault == "missing-digest":
        del post["tables_sha256"]["stock_factor_daily"]
    else:
        post["quality_verified"] = False
    failure = rejected(bundle, "BUSINESS_VALIDATION_FAILED")
    assert failure["job_status"] == "SUCCESS"
    assert failure["publication_state"] == post["publication_state"]


@pytest.mark.parametrize("state,code", [
    ("CANCELLED", "ROOT_CANCELLED"), ("FAILED", "ROOT_FAILED"), ("UNKNOWN", "ROOT_UNKNOWN"),
])
def test_T16_preserves_original_non_success_terminal_state(bundle, state, code):
    bundle[3][5].update(job_status=state, publication_state="ABORTED")
    failure = rejected(bundle, code)
    assert failure["job_status"] == state
    assert read(bundle[1] / "post_root_validation.json")["job_status"] == state
    assert not (bundle[1] / "summary.json").exists()


@pytest.mark.parametrize("code", ["TIMEOUT", "OOM", "ROOT_UNKNOWN", "ROOT_CANCELLED"])
def test_T16_interruption_retains_prefix_and_no_synthesized_terminal(bundle, code):
    failure = {key: bundle[3][2][key] for key in d.COMMON}
    failure.update(event_kind="failure", failure_code=code)
    bundle[3][2:] = [failure]
    assert rejected(bundle, code)["last_durable_seq"] == 3
    assert not (bundle[1] / "root_snapshot.json").exists()


def test_T16_missing_terminal_is_incomplete(bundle):
    bundle[3].pop()
    assert rejected(bundle, "EVIDENCE_INCOMPLETE")["last_durable_seq"] == 6


@pytest.mark.parametrize("field,value", [("marker", RUN), ("system_identifier", "456"),
                                         ("owner_sha256", "b" * 64)])
def test_T17_cleanup_rejects_instance_drift(bundle, field, value):
    bundle[3][-1]["instance"][field] = value
    assert rejected(bundle, "CLEANUP_BLOCKED")["last_durable_seq"] == 7


@pytest.mark.parametrize("field,value", [
    ("host", "production.internal"), ("host", "localhost"),
    ("database", "stocks"), ("scope", "PRODUCTION"), ("pg_major", 16),
    ("system_identifier", ""), ("marker", RUN),
])
def test_T17_nonisolated_or_mismatched_instance_rejected_before_events(bundle, field, value):
    bundle[2]["observed_instance"][field] = value
    rejected(bundle, "INSTANCE_REJECTED")
    assert not (bundle[1] / "raw_events.jsonl").exists()


@pytest.mark.parametrize("field", ["sql", "uri", "token", "environment", "traceback"])
def test_T18_disallowed_payload_is_never_copied_to_output(bundle, field):
    bundle[3][2][field] = "PRIVATE_SQL_AND_CREDENTIAL"
    rejected(bundle, "EVIDENCE_INVALID")
    for file in bundle[1].iterdir():
        assert b"PRIVATE_SQL_AND_CREDENTIAL" not in file.read_bytes()


def test_T18_arbitrary_sql_labels_are_refused(bundle):
    bundle[3][4]["sql_counts"]["PRIVATE_TOKEN"] = 1
    rejected(bundle, "EVIDENCE_INVALID")
    assert b"PRIVATE_TOKEN" not in (bundle[1] / "raw_events.jsonl").read_bytes()


def test_T18_cli_invalid_args_never_echo_payload(capsys):
    with pytest.raises(SystemExit) as caught:
        d.main(["execute", "--token", "PRIVATE_VALUE"])
    assert caught.value.code == 2
    assert capsys.readouterr().err == "CLI_ARGUMENTS_REJECTED\n"


def test_T19_fake_windows_reparse_point_requires_no_symlink_creation(bundle, monkeypatch):
    write_bundle(bundle)
    original = Path.is_junction
    monkeypatch.setattr(Path, "is_junction",
                        lambda p: p.name == "preflight.json" or original(p))
    with pytest.raises(d.Rejected, match="^PATH_REJECTED$"):
        run(bundle)
    assert read(bundle[1] / "failure_receipt.json")["last_durable_seq"] == 0


def test_T20_historical_p1_03_samples_cannot_be_ranked_as_current(bundle):
    bundle[2]["evidence_kind"] = "HISTORICAL_SYNTHETIC"
    for event, elapsed in zip(bundle[3][2:], (10.657, 2.984, 2.128), strict=False):
        event["elapsed_ms"] = elapsed * 1000
    rejected(bundle, "EVIDENCE_CLASS_REFUSED")
    assert not (bundle[1] / "raw_events.jsonl").exists()
