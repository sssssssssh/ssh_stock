"""AT06,31–36: bounded IO and data validation are never an execution grant."""

import json
import os

import pytest

from scripts import a4235_capability_guard as guard
from scripts import a4236_cli as cli
from scripts import a4236_evidence as e
from scripts import a4236_mock as m
from scripts.a4235_calibration_adapter_contract import Safety, digest
from scripts.a4236_g1_harness_contract import Fault, Status, checked
from scripts.a4236_g1_probe import Reply, run_live


@pytest.fixture
def ctx(monkeypatch):
    """Pure IO tests use a model Git service; real byte binding tested separately."""
    c = m.context()
    monkeypatch.setattr(guard, "expected_identity", lambda **kw: c.identity)
    monkeypatch.setattr(guard, "overlay_fingerprint", lambda: c.overlay_sha256)
    return c


@pytest.fixture
def bundle(ctx, tmp_path):
    directory = tmp_path / "bundle"
    e.write_bundle(directory, m.run_case(ctx), ctx)
    return directory


def test_AT31_mock_positive_and_probe_cleanup_failure_do_not_pass(ctx, bundle):
    review = e.review_bundle(bundle, ctx)
    assert review["offline_contract_validated"] and review["physical_capabilities"] == "NOT_PROVEN"
    assert review["g1_probe_status"] == "G1_NOT_RUN_NOT_AUTHORIZED"
    assert all(review[k] == v for k, v in Safety().model_dump().items())
    for replies, cleanup_failure, first in [
        ((Reply(failure_code="A4236_SQL_TIMEOUT"),), False, "A4236_SQL_TIMEOUT"),
        ((), True, "A4236_CLEANUP_NOT_VERIFIED"),
        ((Reply(failure_code="A4236_SQL_TIMEOUT"),), True, "A4236_SQL_TIMEOUT"),
    ]:
        rows = m.run_case(ctx, replies=replies, cleanup_failure=cleanup_failure)
        e.validate(rows, ctx)
        assert rows["failure.json"].first_error == first
        assert rows["cleanup.json"].mock_cleanup_complete == (not cleanup_failure)
        assert not rows["capability-review.json"].performance_eligible


def test_AT31_cleanup_codes_bounded_deduplicated_first_error_sticky(ctx):
    codes = (
        "A4236_CLEANUP_TIMEOUT",
        "A4236_ABSENCE_NOT_VERIFIED",
        "A4236_JOIN_TIMEOUT",
        "A4236_CLEANUP_IDENTITY_DRIFT",
        "A4236_CLEANUP_AUDIT_UNAVAILABLE",
        "A4236_CLEANUP_NOT_VERIFIED",
    )
    result = e.failure(ctx, "A4236_SQL_TIMEOUT", codes + codes)
    assert result.first_error == "A4236_SQL_TIMEOUT"
    assert result.cleanup_codes == codes[:4] and result.cleanup_omitted == 2
    assert e.failure(ctx, None, codes).first_error == codes[0]


@pytest.mark.parametrize("part", ["creation", "cleanup"])
def test_AT31_fixture_events_must_bracket_probe_lifecycle(ctx, part):
    rows = m.run_case(ctx)
    if part == "creation":
        record = rows["fixture.json"]
        creation = tuple(
            r.model_copy(update={"observed_ns": 20_000_000 + i})
            for i, r in enumerate(record.mock_creation)
        )
        rows["fixture.json"] = record.model_copy(update={"mock_creation": creation})
    else:
        record = rows["cleanup.json"]
        receipts = tuple(
            r.model_copy(update={"observed_ns": 100 + i})
            for i, r in enumerate(record.mock_receipts)
        )
        rows["cleanup.json"] = record.model_copy(update={"mock_receipts": receipts})
    with pytest.raises(Fault):
        e.validate(rows, ctx)


@pytest.mark.parametrize(
    "change",
    [
        "first",
        "snapshot",
        "row",
        "sequence",
        "context",
        "sqlhash",
        "continued",
        "negative_time",
        "cleanup_green",
        "absence_missing",
        "cleanup_first",
        "unknown_cleanup",
        "consumed_identity",
    ],
)
def test_AT31_AT34_rehashed_contradictory_evidence_rejected(ctx, change):
    rows = m.run_case(ctx, replies=(Reply(failure_code="A4236_SQL_TIMEOUT"),), cleanup_failure=True)
    probe, failure = rows["probe-events.json"], rows["failure.json"]
    event = probe.events[-1]
    if change == "first":
        rows["failure.json"] = failure.model_copy(update={"first_error": "A4236_CLEANUP_TIMEOUT"})
    elif change == "snapshot":
        rows["failure.json"] = failure.model_copy(update={"last_snapshot_sha256": "f" * 64})
    elif change in ("row", "sequence", "context", "sqlhash", "negative_time"):
        update = {
            "row": {"failure_code": None, "row_count": 2},
            "sequence": {"sequence": 2},
            "context": {"context": ctx.model_copy(update={"marker_sha256": "f" * 64})},
            "sqlhash": {"request_sha256": "f" * 64},
            "negative_time": {"finished_ns": event.started_ns - 1},
        }[change]
        event = event.model_copy(update=update)
        rows["probe-events.json"] = probe.model_copy(update={"events": (event,)})
        rows["failure.json"] = failure.model_copy(
            update={"last_snapshot_sha256": digest(event.model_dump())}
        )
    elif change == "continued":
        rows["probe-events.json"] = probe.model_copy(update={"events": (event, event)})
    elif change == "cleanup_green":
        rows["cleanup.json"] = rows["cleanup.json"].model_copy(
            update={"mock_cleanup_complete": True}
        )
    elif change == "absence_missing":
        rows = m.run_case(ctx)
        rows["cleanup.json"] = rows["cleanup.json"].model_copy(update={"mock_receipts": ()})
    elif change == "cleanup_first":
        rows = m.run_case(ctx, cleanup_failure=True)
        rows["failure.json"] = rows["failure.json"].model_copy(
            update={"first_error": "A4236_SQL_TIMEOUT"}
        )
    elif change == "unknown_cleanup":
        rows["failure.json"] = failure.model_copy(update={"cleanup_codes": ("A4236_FAKE",)})
    else:
        audit = rows["grant-audit.json"]
        rows["grant-audit.json"] = audit.model_copy(
            update={
                "mock_consumption": audit.mock_consumption.model_copy(
                    update={
                        "context": ctx.model_copy(
                            update={"nonce": "33333333-3333-4333-8333-333333333333"}
                        )
                    }
                )
            }
        )
    with pytest.raises(Fault):
        e.validate(rows, ctx)


@pytest.mark.parametrize("field", list(Safety.model_fields))
def test_AT34_all_inherited_capability_flags_false_only(ctx, field):
    value = e.Capability(context=ctx, offline_contract_status="MOCK_ONLY")
    bad = True if Safety.model_fields[field].default is False else "C1"
    with pytest.raises(Fault):
        checked(e.Capability, value.model_copy(update={field: bad}))


def test_AT32_exclusive_owner_only_exact_names_never_overwrite(ctx, bundle):
    assert set(p.name for p in bundle.iterdir()) == e.ALL_NAMES
    assert bundle.stat().st_mode & 0o777 == 0o700
    original = {p.name: p.read_bytes() for p in bundle.iterdir()}
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in bundle.iterdir())
    with pytest.raises(Fault, match="ARTIFACT_WRITE_FAILED"):
        e.write_bundle(bundle, m.run_case(ctx), ctx)
    assert {p.name: p.read_bytes() for p in bundle.iterdir()} == original


@pytest.mark.parametrize(
    "kind",
    [
        "missing",
        "extra",
        "symlink",
        "fifo",
        "hardlink",
        "directory_link",
        "traversal",
        "duplicate",
        "nan",
        "inf",
        "oversize",
        "hash",
        "world_file",
        "world_directory",
        "manifest_extra",
        "forged_payload",
    ],
)
def test_AT32_unsafe_file_and_json_cannot_be_reviewed(ctx, bundle, tmp_path, kind):
    name = bundle / "failure.json"
    path = bundle
    if kind == "missing":
        name.unlink()
    elif kind == "extra":
        (bundle / "extra.txt").write_text("extra")
    elif kind in ("symlink", "fifo", "hardlink"):
        name.unlink()
        if kind == "symlink":
            name.symlink_to(bundle / "cleanup.json")
        elif kind == "fifo":
            os.mkfifo(name, 0o600)
        else:
            os.link(bundle / "cleanup.json", name)
    elif kind == "directory_link":
        path = tmp_path / "link"
        path.symlink_to(bundle, target_is_directory=True)
    elif kind == "traversal":
        path = bundle / ".." / "bundle"
    elif kind == "duplicate":
        name.write_bytes(b'{"a":1,"a":2}')
    elif kind in ("nan", "inf"):
        name.write_bytes(b'{"a":' + (b"NaN" if kind == "nan" else b"Infinity") + b"}")
    elif kind == "oversize":
        name.write_bytes(b"x" * 1_000_001)
    elif kind == "hash":
        name.write_bytes(name.read_bytes() + b" ")
    elif kind == "world_file":
        name.chmod(0o644)
    elif kind == "world_directory":
        bundle.chmod(0o755)
    elif kind == "manifest_extra":
        manifest = json.loads((bundle / "manifest.json").read_bytes())
        manifest["files"]["../failure.json"] = manifest["files"]["failure.json"]
        (bundle / "manifest.json").write_bytes(e.encode(manifest))
    else:
        value = json.loads((bundle / "capability-review.json").read_bytes())
        value["execution_enabled"] = True
        target = bundle / "capability-review.json"
        target.write_bytes(e.encode(value))
        manifest = json.loads((bundle / "manifest.json").read_bytes())
        manifest["files"][target.name] = e.proof(target.read_bytes()).model_dump()
        (bundle / "manifest.json").write_bytes(e.encode(manifest))
    with pytest.raises(Fault, match="^A4236_"):
        e.review_bundle(path, ctx)


@pytest.mark.parametrize(
    "point",
    [
        "first_fsync",
        "manifest_fsync",
        "parent_fsync",
        "write",
        "unlink",
        "early_timeout",
        "late_timeout",
    ],
)
def test_AT33_write_fsync_deadline_or_commit_failure_cannot_leave_acceptable_bundle(
    ctx, tmp_path, monkeypatch, point
):
    path = tmp_path / "interrupted"
    if point in ("early_timeout", "late_timeout"):
        counter = iter(
            [0, 3_000_000_000] if point == "early_timeout" else [0] * 8 + [3_000_000_000]
        )
        monkeypatch.setattr(e.time, "monotonic_ns", lambda: next(counter))
    elif point == "unlink":
        monkeypatch.setattr(e.os, "unlink", lambda *a, **kw: (_ for _ in ()).throw(OSError()))
    elif point == "write":
        original = e.os.open

        def fail_open(name, *args, **kwargs):
            if name == "fixture.json":
                raise OSError("SECRET_DSN")
            return original(name, *args, **kwargs)

        monkeypatch.setattr(e.os, "open", fail_open)
    else:
        original = e.os.fsync
        calls = 0
        fail_at = {"first_fsync": 1, "manifest_fsync": 7, "parent_fsync": 9}[point]

        def fail_sync(fd):
            nonlocal calls
            calls += 1
            if calls == fail_at:
                raise OSError("SECRET_DSN")
            return original(fd)

        monkeypatch.setattr(e.os, "fsync", fail_sync)
    with pytest.raises(Fault, match="^A4236_") as error:
        e.write_bundle(path, m.run_case(ctx), ctx)
    assert "SECRET_DSN" not in str(error.value)
    assert (path / ".incomplete").exists()
    with pytest.raises(Fault):
        e.review_bundle(path, ctx)
    if (path / "failure.json").exists():
        assert json.loads((path / "failure.json").read_bytes())["first_error"] is None


def test_AT05_AT32_bundle_expected_identity_must_be_independent(ctx, bundle):
    for value in [
        ctx.model_copy(update={"overlay_sha256": "f" * 64}),
        ctx.model_copy(
            update={"identity": ctx.identity.model_copy(update={"source_sha256": "f" * 64})}
        ),
    ]:
        with pytest.raises(Fault, match="UNTRUSTED_EXPECTED"):
            e.review_bundle(bundle, value)


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["--live"],
        ["--execute"],
        ["--G1"],
        ["--G2", "16"],
        ["--G3", "128"],
        ["--token", "SECRET_DSN"],
        ["--approve"],
        ["--directory", "--execute"],
        ["--check-static", "--execute"],
    ],
)
@pytest.mark.parametrize("event", ["push", "workflow_dispatch"])
def test_AT06_any_live_cli_event_env_claim_denied_before_read(args, event, monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_EVENT_NAME", event)
    monkeypatch.setenv("G1_APPROVED", "1")
    monkeypatch.setenv("DATABASE_URL", "postgresql://SECRET_DSN")
    monkeypatch.setenv("G1_TOKEN", "SECRET_DSN")
    monkeypatch.setattr(cli, "expected_from_git", lambda: pytest.fail("must reject before Git/env"))
    assert cli.main(args) == 1
    output = capsys.readouterr()
    assert not output.err and "SECRET_DSN" not in output.out
    value = json.loads(output.out)
    assert value["first_error"] == "A4236_G1_NOT_RUN_NOT_AUTHORIZED"
    assert value["g1_probe_status"] == "G1_NOT_RUN_NOT_AUTHORIZED"
    with pytest.raises(Fault, match="^A4236_G1_NOT_RUN_NOT_AUTHORIZED$"):
        run_live(object(), token="SECRET_DSN")


def test_AT36_offline_design_has_no_grant_fixture_or_real_actions(
    ctx, tmp_path, monkeypatch, capsys
):
    c = ctx.model_copy(update={"evidence_kind": "OFFLINE_DESIGN"})
    rows = m.offline_design(c)
    assert rows["fixture.json"].spec is None and rows["grant-audit.json"].mock_consumption is None
    path = tmp_path / "design"
    e.write_bundle(path, rows, c)
    monkeypatch.setattr(cli, "expected_from_git", lambda: c)
    assert cli.main(["--directory", str(path)]) == 3
    result = json.loads(capsys.readouterr().out)
    assert result["g2_protocol_decision"] == "PENDING" and result["effective_warmups_total"] == 8
    assert result["g3_formal_calibration"] == "NOT_AUTHORIZED" and result["real_sql_executed"] == 0
    assert result["cleanup_status"] == "NOT_APPLICABLE_NO_FIXTURE"
    assert Status().physical_identity_status == "PHYSICAL_NOT_PROVEN"


def test_AT34_model_copy_unknown_root_and_nested_fields_never_silently_drop(ctx):
    for bad in [
        ctx.model_copy(update={"secret": "SECRET_DSN"}),
        ctx.model_copy(
            update={"identity": ctx.identity.model_copy(update={"secret": "SECRET_DSN"})}
        ),
    ]:
        with pytest.raises(Fault, match="SCHEMA_INVALID") as error:
            checked(type(ctx), bad)
        assert "SECRET_DSN" not in str(error.value)
