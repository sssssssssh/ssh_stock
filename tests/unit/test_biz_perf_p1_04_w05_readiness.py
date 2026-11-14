"""W05 documentary checks only; all identities below are invented test data."""

import ast
import copy
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID

import pytest

SHA = "a" * 40
RUN = "00000000-0000-0000-0000-000000000001"


def request_fixture():
    """Invented declarations, deliberately capable of being entirely forged.

    This returns only an in-memory test object, never an approved credential.
    """
    w = module()
    return dict(
        schema=w.SCHEMA, implementation_sha=SHA, run_uuid=RUN, ack="NOT_STARTED",
        scope=dict(stocks=8, start="2025-01-01", end="2025-01-31", roots=1,
                   seed_history_days=900), flags=dict.fromkeys(w.d.FLAGS, False),
        resources=dict(platform="Linux", architecture="x86_64", pg_major=17,
                       new_instance=True, exclusive=True, version_ref="invented-version",
                       image_digest="b" * 64, marker=RUN, offline_system_identifier="123",
                       online_system_identifier="123", pgdata_ref="invented-pgdata",
                       volume_ref="invented-volume", network_ref="invented-network",
                       cgroup_ref="invented-cgroup", owner="fixture-resource-owner",
                       lease_uuid=RUN),
        fingerprints=dict.fromkeys(("business", "config", "strategy", "dataset",
                                    "table_manifest"), "c" * 64),
        budget=dict(**w.LIMITS, status="DRAFT_NOT_APPROVED", cpu_millis=2000,
                    disk_io_ref="invented-io-limit", cost_limit_minor=100,
                    cost_currency="CNY"),
        timing={phase: dict(seconds=seconds, in_total=True, separate_limit_seconds=0)
                for phase, seconds in zip(w.PHASES, (10, 60, 60, 600, 30, 300), strict=True)},
        people=dict(owner="fixture-owner", operator="fixture-operator",
                    reviewer="fixture-reviewer", cleanup_owner="fixture-cleaner",
                    cost_owner="fixture-payer", window_start="2026-11-20T00:00:00Z",
                    window_end="2026-11-20T01:00:00Z", stop_ref="invented-stop-plan",
                    retention_ref="invented-retention-plan"),
        evidence={kind: dict(source=source, sha=SHA, run_uuid=RUN,
                             reference="invented-reference") for kind, source in (
                                 ("ci", "GITHUB_ACTIONS"), ("review", "INDEPENDENT_REVIEW"),
                                 ("resource", "OPERATOR_OBSERVATION"))},
    )


def report_with(path, value):
    request = request_fixture()
    target = request
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return module().assess(request, SHA)


def blocked(report, code=None):
    assert report["status"] == "BLOCKED"
    assert report["approved"] is report["execution_available"] is False
    assert report["root_attempts"] == 0
    assert report["authorization"] == "AUTHORIZATION_PENDING"
    if code:
        assert report["blockers"] == [code]
    else:
        assert report["blockers"]


def cli(path, capsys):
    code = module().main(["review-offline", "--input", str(path), "--expected-sha", SHA])
    raw = capsys.readouterr().out
    assert len(raw.encode("ascii")) < 65536
    assert str(path) not in raw
    return code, json.loads(raw)


def module():
    return importlib.import_module("scripts.biz_perf_p1_04_w05_readiness")


def test_entry_exists():
    assert callable(module().assess)


def test_execute_process_refuses():
    process = subprocess.run([
        sys.executable, "-B", "-m", "scripts.biz_perf_p1_04_w05_readiness",
        "execute", "--allow", "--force", "--permit=FORGED",
    ], capture_output=True, text=True, timeout=10, check=False)
    assert process.returncode == 2 and process.stderr == ""
    assert json.loads(process.stdout)["authorization"] == "AUTHORIZATION_PENDING"


def test_fully_forged_document_stays_unverified_and_pure():
    request = request_fixture()
    before = copy.deepcopy(request)
    report = module().assess(request, SHA)
    assert report == module().assess(request, SHA) and request == before
    assert report["status"] == "REVIEWABLE_ONLY" and report["blockers"] == []
    assert report["mode"] == "DOCUMENTARY_READINESS_REVIEW"
    assert report["unverified_claims"] == module().UNVERIFIED
    assert report["owner_decisions"] == module().DECISIONS
    assert report["approved"] is report["execution_available"] is False
    assert report["root_attempts"] == 0 and report["hotspot"] == "NONE_PROVEN"
    assert report["b_gate"] == report["targeted_pg17_gate"] == "NOT_APPROVED"
    assert report["budget"] == "DRAFT_NOT_APPROVED"
    assert report["authorization"] == "AUTHORIZATION_PENDING"


@pytest.mark.parametrize("value", [None, [], True, "FORGED", 1])
def test_non_object_input(value):
    blocked(module().assess(value, SHA), "REQUEST_INVALID")


@pytest.mark.parametrize("sha", [None, True, "a" * 39, "A" * 40, "b" * 40])
def test_external_sha_must_match(sha):
    blocked(module().assess(request_fixture(), sha), "SHA_MISMATCH")


@pytest.mark.parametrize("path,value", [
    (("scope", "stocks"), 4), (("scope", "start"), "2025-02-01"),
    (("scope", "end"), "2025-02-28"), (("scope", "roots"), 2),
    (("scope", "seed_history_days"), 665), (("scope", "stocks"), True),
    (("scope", "seed_history_days"), "900"),
])
def test_fixed_scope(path, value):
    blocked(report_with(path, value), "SCOPE_MISMATCH")


@pytest.mark.parametrize("flag", sorted([
    "factor_input_reuse_enabled", "raw_preflight_batch_enabled",
    "factor_cpu_optimization_enabled", "ab_merge_read_enabled", "perf_diagnostics_enabled",
]))
def test_each_switch_must_be_off(flag):
    blocked(report_with(("flags", flag), True), "FLAGS_MISMATCH")


def test_zero_is_not_false_switch():
    blocked(report_with(("flags", "perf_diagnostics_enabled"), 0), "FLAGS_MISMATCH")


@pytest.mark.parametrize("key,value", [
    ("platform", "Windows"), ("architecture", "aarch64"), ("pg_major", 16),
    ("new_instance", False), ("exclusive", False), ("image_digest", "fake-signature"),
    ("online_system_identifier", "124"), ("offline_system_identifier", "0"),
    ("offline_system_identifier", str(2**64)), ("owner", ""),
])
def test_resource_declarations_rejected_without_inspection(key, value):
    blocked(report_with(("resources", key), value), "RESOURCE_INVALID")


def test_no_evidence_or_resource_reference_is_opened(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("pure assessor reached IO")

    monkeypatch.setattr(module().d, "read_file", forbidden)
    monkeypatch.setattr(module().d, "directory", forbidden)
    request = request_fixture()
    request["evidence"]["ci"]["reference"] = "nonexistent-evidence.json"
    assert module().assess(request, SHA)["status"] == "REVIEWABLE_ONLY"


@pytest.mark.parametrize("key,value", [
    ("total_seconds", 1201), ("cleanup_reserve_seconds", 299), ("worker_bytes", 3),
    ("pg_bytes", 4), ("volume_bytes", 10), ("output_bytes", 10),
    ("cpu_millis", True), ("cpu_millis", 64001), ("cost_limit_minor", 2**63),
    ("cost_limit_minor", -1), ("cost_currency", ""), ("disk_io_ref", ""),
    ("status", "APPROVED"),
])
def test_budget_fixed_draft_and_bounded_integers(key, value):
    blocked(report_with(("budget", key), value), "BUDGET_INVALID")


def test_budget_missing_cannot_be_ready():
    request = request_fixture()
    del request["budget"]
    blocked(module().assess(request, SHA), "REQUEST_INVALID")


def test_root_just_below_fifteen_minutes_with_separate_preparation():
    request = request_fixture()
    for phase in module().PHASES[:3]:
        request["timing"][phase].update(in_total=False, separate_limit_seconds=120)
    request["timing"]["root"]["seconds"] = 898
    request["timing"]["post"]["seconds"] = 1
    report = module().assess(request, SHA)
    assert report["status"] == "REVIEWABLE_ONLY"
    assert report["excluded_steps"] == ["create", "seed", "migrate_warmup"]
    assert "SEPARATE_PREPARATION_BUDGET" in report["owner_decisions"]


@pytest.mark.parametrize("seconds", [900, 901])
def test_root_at_or_over_fifteen_minutes(seconds):
    blocked(report_with(("timing", "root", "seconds"), seconds), "TIMING_INVALID")


def test_preparation_and_post_must_fit_before_cleanup_reserve():
    # root itself is <900; the full included pre-cleanup window reaches 900.
    blocked(report_with(("timing", "root", "seconds"), 740), "TIMING_INVALID")


def test_full_five_minutes_cleanup_is_valid_but_one_second_more_is_not():
    assert module().assess(request_fixture(), SHA)["status"] == "REVIEWABLE_ONLY"
    blocked(report_with(("timing", "cleanup", "seconds"), 301), "TIMING_INVALID")


@pytest.mark.parametrize("phase", ["seed", "create", "migrate_warmup", "post", "cleanup"])
def test_no_missing_timing_phase(phase):
    request = request_fixture()
    del request["timing"][phase]
    blocked(module().assess(request, SHA), "REQUEST_INVALID")


def test_seed_excluded_without_separate_budget_is_rejected():
    blocked(report_with(("timing", "seed", "in_total"), False), "TIMING_INVALID")


def test_explicit_separate_seed_budget_is_disclosed():
    request = request_fixture()
    request["timing"]["seed"].update(in_total=False, separate_limit_seconds=60)
    report = module().assess(request, SHA)
    assert report["status"] == "REVIEWABLE_ONLY" and report["excluded_steps"] == ["seed"]
    assert "SEPARATE_PREPARATION_BUDGET" in report["owner_decisions"]


@pytest.mark.parametrize("phase", ["root", "post", "cleanup"])
def test_measurement_and_cleanup_cannot_be_excluded(phase):
    request = request_fixture()
    request["timing"][phase].update(in_total=False, separate_limit_seconds=900)
    blocked(module().assess(request, SHA), "TIMING_INVALID")


@pytest.mark.parametrize("value", [0, -1, True, 1.5, 2**63, "60"])
def test_invalid_timing_number(value):
    blocked(report_with(("timing", "seed", "seconds"), value), "TIMING_INVALID")


@pytest.mark.parametrize("kind", ["ci", "review", "resource"])
def test_evidence_cross_sha(kind):
    blocked(report_with(("evidence", kind, "sha"), "b" * 40), "SHA_MISMATCH")


@pytest.mark.parametrize("kind", ["ci", "review", "resource"])
def test_evidence_cross_run(kind):
    blocked(report_with(("evidence", kind, "run_uuid"), str(UUID(int=2))),
            "RUN_MISMATCH")


def test_resource_lease_cross_run():
    blocked(report_with(("resources", "lease_uuid"), "other-run"), "RUN_MISMATCH")


def test_unknown_ci_source_is_not_authenticated_by_reference():
    blocked(report_with(("evidence", "ci", "source"), "UNKNOWN"), "CI_SOURCE_UNKNOWN")


@pytest.mark.parametrize("path,value", [
    (("approval",), True), (("permit",), "FORGED"), (("signature",), "forged-signature"),
    (("ci_status",), "SUCCESS"), (("evidence", "ci", "status"), "SUCCESS"),
    (("evidence", "review", "signature"), "forged-signature"),
    (("scope", "stock_day_rows"), 5320),
])
def test_no_authority_or_unknown_fields(path, value):
    blocked(report_with(path, value), "REQUEST_INVALID")


def test_ack_unknown_is_manual_stop_not_recoverable():
    blocked(report_with(("ack",), "UNKNOWN_ACK"), "MANUAL_STOP_REQUIRED")
    blocked(report_with(("ack",), "KNOWN_MOCK_RETURN"), "MANUAL_STOP_REQUIRED")
    request = request_fixture()
    request.update(ack="UNKNOWN_ACK", resume=True)
    blocked(module().assess(request, SHA), "REQUEST_INVALID")


@pytest.mark.parametrize("role", ["owner", "operator", "reviewer", "cleanup_owner", "cost_owner"])
def test_missing_named_person(role):
    blocked(report_with(("people", role), ""), "PEOPLE_INCOMPLETE")


@pytest.mark.parametrize("key,value", [
    ("window_end", "2026-11-20T00:19:59Z"),
    ("window_start", "2026-11-20T00:00:00"), ("window_end", "not-a-date"),
])
def test_window_must_be_explicit_and_cover_draft(key, value):
    blocked(report_with(("people", key), value))


def test_window_includes_separate_preparation_limits():
    request = request_fixture()
    request["people"]["window_end"] = "2026-11-20T00:20:00Z"
    request["timing"]["seed"].update(in_total=False, separate_limit_seconds=60)
    blocked(module().assess(request, SHA), "WINDOW_INVALID")


def test_fingerprint_presence_only_not_content_authentication():
    blocked(report_with(("fingerprints", "table_manifest"), "unknown"), "FINGERPRINT_INVALID")
    report = report_with(("fingerprints", "dataset"), "f" * 64)
    assert report["status"] == "REVIEWABLE_ONLY"
    assert "FINGERPRINT_CONTENT" in report["unverified_claims"]


@pytest.mark.parametrize("raw", [
    b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}', b'{"x":-Infinity}',
    b'{"x":1e999}', b'\xff', b'{', b'1' * 65537,
    b'{"x":' + b'9' * 5000 + b'}', b'[' * 2000 + b']' * 2000,
], ids=["duplicate", "nan", "inf", "negative-inf", "overflow", "utf8", "truncated",
        "oversize", "huge-int", "deep"])
def test_strict_json_refused(raw):
    with pytest.raises(ValueError, match="^REQUEST_INVALID$"):
        module().decode_request(raw)


def test_duplicate_nested_key_refused():
    with pytest.raises(ValueError, match="^REQUEST_INVALID$"):
        module().decode_request(b'{"budget":{"cpu_millis":1,"cpu_millis":2}}')


def test_sixty_four_kib_input_boundary():
    raw = b'{}' + b' ' * (65536 - 2)
    assert module().decode_request(raw) == {}
    with pytest.raises(ValueError):
        module().decode_request(raw + b' ')


@pytest.mark.parametrize("value", [float("nan"), float("inf"), 10**5000],
                         ids=["nan", "inf", "unbounded"])
def test_direct_nonfinite_and_unbounded_values_do_not_escape(value):
    blocked(report_with(("budget", "cpu_millis"), value), "REQUEST_INVALID")


def test_in_memory_cycle_is_refused():
    request = request_fixture()
    request["people"]["owner"] = request
    blocked(module().assess(request, SHA), "REQUEST_INVALID")


def test_read_only_cli_valid_document_is_bounded_and_redacted(tmp_path, capsys, monkeypatch):
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request_fixture()), encoding="utf-8")
    before = (path.stat().st_ino, path.stat().st_mtime_ns, path.read_bytes())

    def forbidden(*args, **kwargs):
        pytest.fail("CLI reached a writing validator")

    monkeypatch.setattr(module().d, "publish", forbidden)
    monkeypatch.setattr(module().d, "validate_bundle", forbidden)
    code, report = cli(path, capsys)
    assert code == 0 and report["status"] == "REVIEWABLE_ONLY"
    assert report["approved"] is False
    assert "fixture-owner" not in json.dumps(report) and SHA not in json.dumps(report)
    assert before == (path.stat().st_ino, path.stat().st_mtime_ns, path.read_bytes())
    assert list(tmp_path.iterdir()) == [path]


def test_bad_json_cli_never_echoes_private_payload(tmp_path, capsys):
    path = tmp_path / "private-name.json"
    path.write_text("PRIVATE-PASSWORD", encoding="utf-8")
    code, report = cli(path, capsys)
    assert code == 2 and report["blockers"] == ["INPUT_OR_ARGUMENTS_REJECTED"]
    assert "PRIVATE" not in json.dumps(report)


@pytest.mark.parametrize("args", [
    [], ["--help"], ["review-offline", "--unknown=PRIVATE"],
    ["execute", "--input=PRIVATE"], ["--allow"], ["--force=true"], ["--permit=FORGED"],
    ["review-offline", "--input=PRIVATE", "--force", "--expected-sha=" + SHA],
])
def test_cli_denials_precede_all_file_access(args, capsys, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("denied command read file")

    monkeypatch.setattr(module().d, "read_file", forbidden)
    assert module().main(args) == 2
    raw = capsys.readouterr().out
    blocked(json.loads(raw))
    assert "PRIVATE" not in raw and "FORGED" not in raw


@pytest.mark.parametrize("path", ["//server/share/request.json", r"\\server\request.json",
                                  ".env", "../request.json", "request.json:stream"])
def test_untrusted_cli_path_refused_before_read(path, capsys, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("untrusted path reached open")

    monkeypatch.setattr(module().d, "read_file", forbidden)
    code, report = cli(path, capsys)
    assert code == 2
    blocked(report)


def test_hardlink_input_refused(tmp_path, capsys):
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request_fixture()), encoding="utf-8")
    os.link(path, tmp_path / "link.json")
    code, report = cli(path, capsys)
    assert code == 2
    blocked(report)


def test_oversize_file_refused(tmp_path, capsys):
    path = tmp_path / "request.json"
    path.write_bytes(b" " * 65537)
    code, report = cli(path, capsys)
    assert code == 2
    blocked(report)


def test_only_small_read_only_import_surface():
    path = Path(module().__file__)
    source = path.read_text(encoding="utf-8")
    assert len(source.splitlines()) <= 250
    tree = ast.parse(source)
    imports = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    imports |= {alias.name for n in ast.walk(tree) if isinstance(n, ast.Import)
                for alias in n.names}
    assert imports == {"argparse", "re", "sys", "datetime", "pathlib", "scripts"}
    assert not any(isinstance(n, ast.Attribute) and n.attr in {
        "write_bytes", "write_text", "mkdir", "unlink", "connect", "create_and_claim",
        "execute_claimed_job", "publish", "validate_bundle",
    } for n in ast.walk(tree))


def test_real_cli_process_no_database_import_or_resource_contact(tmp_path):
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request_fixture()), encoding="utf-8")
    probe = '''
import os
import sys
def audit(event, args):
    if event.startswith(('socket.', 'subprocess.')) or event in ('os.system', 'os.mkdir'):
        raise AssertionError('RESOURCE_CONTACT')
    if event == 'open':
        if str(args[0]).endswith('.env') or args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT):
            raise AssertionError('WRITE_OR_ENV')
sys.addaudithook(audit)
from scripts import biz_perf_p1_04_w05_readiness as w
assert not any(k.split('.')[0] in ('app', 'psycopg', 'sqlalchemy', 'dotenv') for k in sys.modules)
raise SystemExit(w.main(['review-offline', '--input', sys.argv[1], '--expected-sha', 'a'*40]))
'''
    process = subprocess.run([sys.executable, "-B", "-c", probe, str(path)],
                             capture_output=True, text=True, timeout=10, check=False)
    assert process.returncode == 0 and process.stderr == ""
    assert json.loads(process.stdout)["status"] == "REVIEWABLE_ONLY"
