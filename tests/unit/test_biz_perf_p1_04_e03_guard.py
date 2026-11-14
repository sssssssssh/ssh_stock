"""E03 contracts: pure data and offline doubles, never resource discovery."""

import copy
import importlib.util
import subprocess
import sys

import pytest


def test_e03_contract_exists_on_r2():
    assert importlib.util.find_spec("scripts.biz_perf_p1_04_e03_guard") is not None


def test_e03_execute_is_closed_on_r2():
    result = subprocess.run(
        [sys.executable, "-B", "-m", "scripts.biz_perf_p1_04_e03_guard", "execute"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 2
    assert result.stdout.strip() == "AUTHORIZATION_PENDING"


@pytest.fixture
def g():
    from scripts import biz_perf_p1_04_e03_guard

    return biz_perf_p1_04_e03_guard


@pytest.fixture
def plan(g):
    from scripts import biz_perf_p1_04_measure_wiring as w

    preflight = w.build_preflight(implementation_sha="a" * 40)
    preflight.pop("preflight_sha256")
    resources = dict(
        platform="Linux", architecture="x86_64", instance=preflight["expected_instance"],
        pgdata_new=True, pgdata_exclusive=True, database_new=True,
        database_owner_sha256="7" * 64, volume_sha256="8" * 64,
        lease_uuid=preflight["run_uuid"], lease_exclusive=True,
        offline_system_identifier=preflight["expected_instance"]["system_identifier"],
        online_system_identifier=preflight["expected_instance"]["system_identifier"],
        limits=dict(cpu_millis=2000, worker_bytes=3 * 1024**3, pg_bytes=4 * 1024**3,
                    volume_bytes=10 * 1024**3, output_bytes=10 * 1024**2,
                    total_ms=1_200_000, cleanup_reserve_ms=300_000),
    )
    return dict(
        schema=g.SCHEMA, evidence_kind="OFFLINE_FIXTURE", preflight=preflight,
        ci=dict(sha="a" * 40, status="SUCCESS", receipt_sha256="b" * 64),
        review=dict(sha="a" * 40, status="APPROVED", receipt_sha256="c" * 64,
                    reviewer_sha256="d" * 64, implementer_sha256="e" * 64),
        scope=dict(start="2025-01-01", end="2025-01-31", roots=1,
                   seed_history_days=900, seed_open_days=665, stock_day_rows=5320,
                   benchmark_count=3, row_budgets={
                       name: dict(max_rows=rows, content_sha256="f" * 64)
                       for name, rows in g.seed_rows(3).items()}),
        expected=dict(kind="EXPECTED", resources=copy.deepcopy(resources)),
        observed=dict(kind="OBSERVED_OFFLINE", resources=copy.deepcopy(resources)),
        budget_status="DRAFT_NOT_APPROVED",
    )


def test_default_ports_refuse_and_offline_proof_is_not_authority(g, plan):
    digest = g.validate_plan(plan, "a" * 40)
    assert len(digest) == 64
    with pytest.raises(g.Refused, match="INSPECTION_REFUSED"):
        g.OfflineGuard().inspect(plan, "a" * 40)
    assert g.execute() == 2


@pytest.mark.parametrize("path,value", [
    (("preflight", "measurement_implementation_sha"), "b" * 40),
    (("preflight", "worktree"), "DIRTY"),
    (("ci", "sha"), "b" * 40), (("ci", "status"), "IN_PROGRESS"),
    (("review", "sha"), "b" * 40), (("review", "status"), "PENDING"),
    (("review", "reviewer_sha256"), "e" * 64),
    (("preflight", "run_attempt"), True), (("preflight", "stocks"), 4),
    (("preflight", "months"), 3), (("scope", "roots"), 2),
    (("scope", "seed_open_days"), 900), (("scope", "stock_day_rows"), 5000),
    (("scope", "end"), "2025-02-28"),
    (("preflight", "flags", "perf_diagnostics_enabled"), True),
    (("preflight", "dataset_sha256"), "UNKNOWN"),
    (("budget_status",), "APPROVED"),
    (("observed", "kind"), "OBSERVED_LIVE"),
])
def test_bad_identity_and_scope(g, plan, path, value):
    target = plan
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(g.Refused):
        g.validate_plan(plan, "a" * 40)


@pytest.mark.parametrize("section", ["ci", "review", "scope", "preflight", "expected"])
def test_missing_or_extra_sections(g, plan, section):
    del plan[section]
    with pytest.raises(g.Refused):
        g.validate_plan(plan, "a" * 40)


@pytest.mark.parametrize("key,value", [
    ("platform", "Windows"), ("architecture", "aarch64"),
    ("pgdata_new", False), ("pgdata_exclusive", False), ("database_new", False),
    ("lease_exclusive", False), ("lease_uuid", "00000000-0000-0000-0000-000000000000"),
    ("database_owner_sha256", "9" * 64), ("volume_sha256", "9" * 64),
    ("online_system_identifier", "42"), ("offline_system_identifier", "42"),
])
def test_resource_mismatches(g, plan, key, value):
    plan["observed"]["resources"][key] = value
    with pytest.raises(g.Refused):
        g.validate_plan(plan, "a" * 40)
    assert g.cleanup_status(plan["expected"], plan["observed"]) == "CLEANUP_BLOCKED"


@pytest.mark.parametrize("key,value", [
    ("pg_major", 16), ("marker", "00000000-0000-0000-0000-000000000000"),
    ("system_identifier", "42"), ("pgdata_sha256", "9" * 64),
    ("network_sha256", "9" * 64), ("owner_sha256", "9" * 64),
])
def test_instance_mismatch(g, plan, key, value):
    plan["observed"]["resources"]["instance"][key] = value
    with pytest.raises(g.Refused):
        g.validate_plan(plan, "a" * 40)


@pytest.mark.parametrize("key", ["cpu_millis", "worker_bytes", "pg_bytes", "volume_bytes",
                                  "output_bytes", "total_ms", "cleanup_reserve_ms"])
def test_each_budget_mismatch(g, plan, key):
    plan["observed"]["resources"]["limits"][key] += 1
    with pytest.raises(g.Refused):
        g.validate_plan(plan, "a" * 40)


def test_table_budgets_are_not_a_scalar(g, plan):
    for value in (5320, {}, {"stock_daily": dict(max_rows=5320, content_sha256="f" * 64)}):
        changed = copy.deepcopy(plan)
        changed["scope"]["row_budgets"] = value
        with pytest.raises(g.Refused):
            g.validate_plan(changed, "a" * 40)


def test_unknown_keys_booleans_and_sensitive_text_never_authorize(g, plan):
    plan["allow"] = True
    with pytest.raises(g.Refused, match="PLAN_REJECTED"):
        g.validate_plan(plan, "a" * 40)
    assert g.main(["execute", "--allow=true"]) == 2


def test_bounded_strict_json(g):
    for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b" " * (g.MAX_PLAN_BYTES + 1)):
        with pytest.raises(g.Refused):
            g.decode_plan(raw)


class FixturePorts:
    """Pinned whole-plan mock attestation, explicitly no live authority."""

    def __init__(self, binding):
        self.binding = binding

    def inspect(self, plan, binding):
        assert binding == self.binding
        return dict(kind="OBSERVED_OFFLINE", binding_sha256=binding, status="OFFLINE_CHECKED")

    attest = verify = check = inspect


def test_plan_offline_proof_then_refusal_and_uuid_replay(g, plan, monkeypatch):
    ports = FixturePorts(g.validate_plan(plan, "a" * 40))
    journal = g.OfflineJournal()
    guard = g.OfflineGuard(inspector=ports, attestor=ports, approvals=ports, budgets=ports,
                           journal=journal)
    proof = guard.inspect(plan, "a" * 40)
    assert proof["status"] == "OFFLINE_PROOF_ONLY"
    assert proof["root_attempts"] == 0
    assert proof["b_gate"] == proof["targeted_pg17_gate"] == "NOT_APPROVED"
    assert "LIVE_VERIFIED" not in str(proof)
    with pytest.raises(g.Refused, match="RUN_UUID_REUSED"):
        guard.inspect(plan, "a" * 40)
    monkeypatch.setenv("E03_ALLOW", "true")
    monkeypatch.setenv("E03_PERMIT", "true")
    assert g.execute() == 2
    for action in (g.RefusedExecutor().create_and_claim,
                   g.RefusedExecutor().execute_claimed_job):
        with pytest.raises(g.Refused, match="EXECUTION_NOT_AVAILABLE"):
            action(proof)


@pytest.mark.parametrize("receipt", [True, {},
    dict(kind="OBSERVED_LIVE", status="LIVE_VERIFIED", binding_sha256="a" * 64),
    dict(kind="OBSERVED_OFFLINE", status="OFFLINE_CHECKED", binding_sha256="a" * 64)])
def test_forged_port_receipts(g, plan, receipt):
    class Forged:
        def inspect(self, *_args):
            return receipt

    with pytest.raises(g.Refused, match="PORT_REJECTED"):
        g.OfflineGuard(inspector=Forged()).inspect(plan, "a" * 40)


def test_changed_plan_cannot_reuse_attestation(g, plan):
    ports = FixturePorts(g.validate_plan(plan, "a" * 40))
    plan["preflight"]["strategy_sha256"] = "0" * 64
    with pytest.raises(g.Refused, match="PORT_REJECTED"):
        g.OfflineGuard(inspector=ports).inspect(plan, "a" * 40)


@pytest.mark.parametrize("which,code", [("attestor", "IDENTITY_REFUSED"),
                                        ("approvals", "APPROVAL_REFUSED"),
                                        ("budgets", "BUDGET_REFUSED")])
def test_each_default_port_refuses(g, plan, which, code):
    ports = FixturePorts(g.validate_plan(plan, "a" * 40))
    arguments = dict(inspector=ports, attestor=ports, approvals=ports, budgets=ports)
    del arguments[which]
    with pytest.raises(g.Refused, match=code):
        g.OfflineGuard(**arguments).inspect(plan, "a" * 40)


def test_cli_read_only_and_static_errors(g, plan, tmp_path, capsys):
    from scripts import biz_perf_p1_04_diagnostic as d

    path = tmp_path / "plan.json"
    path.write_bytes(d.encode(plan))
    for command in ("plan", "validate-offline"):
        assert g.main([command, "--input", str(path),
                       "--expected-implementation-sha", "a" * 40]) == 0
        result = d.decode(capsys.readouterr().out.encode())
        assert result["status"] == "OFFLINE_DECLARATIONS_ONLY"
        assert result["authorization"] == "AUTHORIZATION_PENDING"
    assert g.main(["inspect", "--input", str(path),
                   "--expected-implementation-sha", "a" * 40]) == 2
    assert capsys.readouterr().out.strip() == "INSPECTION_REFUSED"
    assert g.main(["PRIVATE_SECRET"]) == 2
    assert capsys.readouterr().out.strip() == "INPUT_REJECTED"
    assert list(tmp_path.iterdir()) == [path]


def test_seed_rows_match_historical_synthetic_calendar(g):
    from datetime import date, timedelta

    start, end = date(2025, 1, 1) - timedelta(days=900), date(2025, 1, 31)
    days = [start + timedelta(days=n) for n in range((end - start).days + 1)]
    assert len(days) == g.seed_rows(3)["trade_calendar"] == 931
    assert sum(day.weekday() < 5 for day in days) == 665
    assert g.seed_rows(3)["stock_daily"] == 8 * 665 == 5320


@pytest.mark.parametrize("key", ["cpu_millis", "worker_bytes", "pg_bytes", "volume_bytes",
                                  "output_bytes", "elapsed_ms"])
def test_budget_exhaustion_mock_checkpoints(g, plan, key):
    limits = plan["expected"]["resources"]["limits"]
    usage = dict.fromkeys(("cpu_millis", "worker_bytes", "pg_bytes", "volume_bytes",
                           "output_bytes", "elapsed_ms"), 0)
    assert g.check_offline_usage(limits, usage, phase="root") == "OFFLINE_BUDGET_CHECK_ONLY"
    usage[key] = 900_000 if key == "elapsed_ms" else limits[key] + 1
    with pytest.raises(g.Refused, match="BUDGET_REJECTED"):
        g.check_offline_usage(limits, usage, phase="root")
    if key == "elapsed_ms":
        assert g.check_offline_usage(limits, usage, phase="cleanup")
        usage[key] = 1_200_000
        with pytest.raises(g.Refused, match="BUDGET_REJECTED"):
            g.check_offline_usage(limits, usage, phase="cleanup")


@pytest.mark.parametrize("section", ["ci", "review", "scope", "expected", "observed"])
def test_nested_key_set_strict(g, plan, section):
    plan[section]["allow"] = True
    with pytest.raises(g.Refused):
        g.validate_plan(plan, "a" * 40)
