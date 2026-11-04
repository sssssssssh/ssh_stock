"""Shard contracts reject incomplete collections and untrusted execution receipts."""

from collections import Counter

import pytest

from scripts.ci_test_shards import partition, validate_results


def test_partition_keeps_every_node_exactly_once_and_new_nodes_fall_back():
    nodes = [
        "tests/unit/test_m15_1_experiment_grid.py::test_a",
        "tests/integration/test_x.py::test_b",
    ]
    expected = dict(
        schema="ci-opt-02.manifest.v1",
        nodes=nodes,
        pilot_module="tests/unit/test_m15_1_experiment_grid.py",
    )
    groups = partition(nodes, expected)
    assert Counter(n for g in groups.values() for n in g) == Counter(nodes)
    assert groups["pilot"] == nodes[:1]
    assert partition(nodes + ["tests/new.py::test_new"], expected) is None
    assert partition(nodes * 2, expected) is None
    assert partition(nodes[:-1], expected) is None


def fixture():
    identity = dict(head_sha="a" * 40, run_id="1", attempt="1")
    nodes = ["tests/a.py::test_a", "tests/b.py::test_b"]
    receipts = [
        dict(
            **identity,
            shard=k,
            exit_code=0,
            status="PASS",
            nodes=[n],
            failures=0,
            errors=0,
            skipped=0,
            coverage_sha256="b" * 64,
            junit_sha256="c" * 64,
        )
        for k, n in zip(("pilot", "serial"), nodes, strict=True)
    ]
    return identity, nodes, receipts


def test_complete_receipts_require_exact_multiset():
    identity, nodes, receipts = fixture()
    validate_results(receipts, nodes, identity)
    receipts[1]["nodes"] = receipts[0]["nodes"]
    with pytest.raises(ValueError):
        validate_results(receipts, nodes, identity)


@pytest.mark.parametrize(
    "field,value",
    [
        ("exit_code", 1),
        ("status", "INCOMPLETE"),
        ("skipped", 1),
        ("errors", 1),
        ("failures", 1),
        ("head_sha", "d" * 40),
        ("attempt", "2"),
        ("run_id", "2"),
    ],
)
def test_failure_missing_or_other_attempt_cannot_pass(field, value):
    identity, nodes, receipts = fixture()
    receipts[0][field] = value
    with pytest.raises(ValueError):
        validate_results(receipts, nodes, identity)


def test_missing_shard_cannot_pass():
    identity, nodes, receipts = fixture()
    with pytest.raises(ValueError):
        validate_results(receipts[:1], nodes, identity)


def test_junit_cannot_claim_different_nodes_or_success(tmp_path):
    from scripts.ci_test_shards import validate_junit

    path = tmp_path / "tests.xml"
    path.write_text(
        '<testsuites><testsuite><testcase classname="tests.a" name="test_a"/>'
        "</testsuite></testsuites>"
    )
    validate_junit(path, ["tests/a.py::test_a"])
    with pytest.raises(ValueError):
        validate_junit(path, ["tests/a.py::test_b"])
    path.write_text(
        '<testsuites><testsuite><testcase classname="tests.a" name="test_a">'
        "<skipped/></testcase></testsuite></testsuites>"
    )
    with pytest.raises(ValueError):
        validate_junit(path, ["tests/a.py::test_a"])


@pytest.mark.parametrize("result", ["failure", "skipped", "cancelled", "timed_out"])
def test_full_workflow_never_accepts_failed_shard_job(result):
    from scripts.ci_status_summary import verify_workflow

    env = {"GITHUB_SHA": "a" * 40}
    outputs = dict(ci_opt_verified="true", ci_opt_head="a" * 40, ci_opt_scope="full")
    needs = {
        name: dict(result="success", outputs=outputs)
        for name in ["test", "lookup-diagnosis", "workflow-contracts", "dependency-audit"]
    }
    needs["python-scope"] = dict(result="success", outputs=dict(head="a" * 40, scope="full"))
    needs["python-tests"] = dict(result=result)
    with pytest.raises(ValueError):
        verify_workflow("ci.yml", needs, env)


def test_docs_mode_requires_skipped_shards_and_verified_identical_route():
    from scripts.ci_status_summary import verify_workflow

    env = {"GITHUB_SHA": "a" * 40}
    outputs = dict(ci_opt_verified="true", ci_opt_head="a" * 40, ci_opt_scope="docs")
    needs = {
        name: dict(result="success", outputs=outputs)
        for name in ["test", "lookup-diagnosis", "workflow-contracts", "dependency-audit"]
    }
    needs["python-scope"] = dict(result="success", outputs=dict(head="a" * 40, scope="docs"))
    needs["python-tests"] = dict(result="skipped")
    assert verify_workflow("ci.yml", needs, env) == "docs"
    needs["python-scope"]["outputs"]["scope"] = "full"
    with pytest.raises(ValueError):
        verify_workflow("ci.yml", needs, env)


def test_real_coverage_combine_requires_both_artifacts(tmp_path, monkeypatch):
    import hashlib
    import json
    import runpy

    import coverage

    from scripts import ci_test_shards as shards

    monkeypatch.chdir(tmp_path)
    source = tmp_path / "backend/app/tiny.py"
    source.parent.mkdir(parents=True)
    source.write_text("def f(flag):\n    if flag:\n        return 1\n    return 2\n")
    nodes = [shards.PILOT + "::test_a", "tests/b.py::test_b"]
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(dict(schema="ci-opt-02.manifest.v1", nodes=nodes, pilot_module=shards.PILOT))
    )
    ident = dict(head_sha="a" * 40, run_id="1", attempt="1")
    monkeypatch.setattr(shards, "ROOT", tmp_path)
    monkeypatch.setattr(shards, "MANIFEST", manifest)
    monkeypatch.setattr(shards, "identity", lambda: ident)
    incoming = tmp_path / "inputs"
    for index, shard in enumerate(shards.SHARDS):
        path = incoming / shard
        path.mkdir(parents=True)
        data = path / (".coverage." + shard)
        cov = coverage.Coverage(data_file=str(data), source=["backend/app"])
        cov.start()
        runpy.run_path(str(source))["f"](index == 0)
        cov.stop()
        cov.save()
        from _pytest.junitxml import mangle_test_address

        parts = mangle_test_address(nodes[index])
        xml = path / "tests.xml"
        from xml.etree import ElementTree as ET

        root = ET.Element("testsuites")
        suite = ET.SubElement(root, "testsuite", tests="1", failures="0", errors="0", skipped="0")
        ET.SubElement(suite, "testcase", classname=".".join(parts[:-1]), name=parts[-1])
        ET.ElementTree(root).write(xml)

        def sha(p):
            return hashlib.sha256(p.read_bytes()).hexdigest()

        (path / "result.json").write_text(
            json.dumps(
                dict(
                    **ident,
                    shard=shard,
                    status="PASS",
                    exit_code=0,
                    failures=0,
                    errors=0,
                    skipped=0,
                    nodes=[nodes[index]],
                    coverage_sha256=sha(data),
                    junit_sha256=sha(xml),
                    manifest_sha256=sha(manifest),
                )
            )
        )
    (tmp_path / ".codex_tmp/ci-shards").mkdir(parents=True)
    shards.aggregate(incoming, 70)
    result = json.loads((tmp_path / ".codex_tmp/ci-shards/combined.json").read_text())
    assert result["status"] == "FULL_PASS" and result["coverage_percent"] == 100
    assert len(list(ET.parse(tmp_path / ".codex_tmp/m17_1_2-full.xml").iter("testcase"))) == 2
    (incoming / "pilot/.coverage.pilot").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="DIGEST"):
        shards.aggregate(incoming, 70)
    assert (
        json.loads((tmp_path / ".codex_tmp/ci-shards/combined.json").read_text())["status"]
        == "INCOMPLETE"
    )
