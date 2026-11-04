"""B0 exact-node shard execution and fail-closed coverage/JUnit aggregation."""

import argparse
import hashlib
import json
import os
import platform
import resource
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
MANIFEST = ROOT / ".github/ci-test-manifest.json"
PILOT = "tests/unit/test_m15_1_experiment_grid.py"
SHARDS = ("pilot", "serial")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity():
    return dict(
        head_sha=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        run_id=os.environ.get("GITHUB_RUN_ID", "local"),
        attempt=os.environ.get("GITHUB_RUN_ATTEMPT", "1"),
    )


def partition(nodes, manifest):
    if (
        manifest.get("schema") != "ci-opt-02.manifest.v1"
        or manifest.get("pilot_module") != PILOT
        or len(nodes) != len(set(nodes))
        or Counter(nodes) != Counter(manifest.get("nodes", []))
    ):
        return None
    return {
        k: sorted(n for n in nodes if (n.split("::")[0] == PILOT) == (k == "pilot")) for k in SHARDS
    }


def validate_results(receipts, nodes, expected):
    if (
        len(receipts) != 2
        or {r.get("shard") for r in receipts} != set(SHARDS)
        or len(nodes) != len(set(nodes))
    ):
        raise ValueError("CI_OPT_02_MISSING_SHARD")
    for r in receipts:
        if (
            any(r.get(k) != v for k, v in expected.items())
            or r.get("status") != "PASS"
            or r.get("exit_code") != 0
            or any(r.get(k) != 0 for k in ("failures", "errors", "skipped"))
        ):
            raise ValueError("CI_OPT_02_SHARD_NOT_SUCCESS")
    if Counter(n for r in receipts for n in r["nodes"]) != Counter(nodes):
        raise ValueError("CI_OPT_02_NODE_MULTISET_MISMATCH")


class Collection:
    def __init__(self):
        self.nodes = []

    def pytest_collection_finish(self, session):
        self.nodes = sorted(i.nodeid for i in session.items)


class Selection(Collection):
    def __init__(self, nodes):
        super().__init__()
        self.expected = nodes
        self.expected_set = set(nodes)

    def pytest_collection_modifyitems(self, session, config, items):
        selected = [i for i in items if i.nodeid in self.expected_set]
        if Counter(i.nodeid for i in selected) != Counter(self.expected):
            raise ValueError("CI_OPT_02_SELECTION_CHANGED")
        deselected = [i for i in items if i.nodeid not in self.expected_set]
        config.hook.pytest_deselected(items=deselected)
        items[:] = selected


def collect_here():
    import pytest

    plugin = Collection()
    code = pytest.main(["--collect-only", "-q"], plugins=[plugin])
    if code != 0:
        raise ValueError("CI_OPT_02_COLLECTION_FAILED")
    return plugin.nodes


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def run_shard(shard):
    # Collection cannot read a developer's .env or connect to any server.
    from app.core.config import Settings

    Settings.model_config["env_file"] = None
    import pytest

    out = ROOT / ".codex_tmp/ci-shards" / shard
    out.mkdir(parents=True, exist_ok=True)
    value = dict(
        identity(),
        shard=shard,
        status="INCOMPLETE",
        exit_code=None,
        nodes=[],
        failures=None,
        errors=None,
        skipped=None,
    )
    start, cpu = time.monotonic(), time.process_time()
    try:
        manifest = json.loads(MANIFEST.read_text())
        collection_log = out / "collect.log"
        with collection_log.open("w") as log:
            subprocess.run(
                [sys.executable, "-m", "scripts.ci_test_shards", "collect"],
                cwd=ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
                timeout=120,
            )
        nodes = json.loads((ROOT / ".codex_tmp/ci-shards/collection.json").read_text())
        groups = partition(nodes, manifest)
        hashes_ok = set(manifest["test_sha256"]) == {
            str(p.relative_to(ROOT)) for p in (ROOT / "tests").rglob("*.py")
        }
        hashes_ok = hashes_ok and all(
            (ROOT / p).is_file() and not (ROOT / p).is_symlink() and digest(ROOT / p) == h
            for p, h in manifest["test_sha256"].items()
        )
        hashes_ok = hashes_ok and all(
            (ROOT / p).is_file() and not (ROOT / p).is_symlink() and digest(ROOT / p) == h
            for p, h in manifest.get("pilot_source_sha256", {}).items()
        )
        if not hashes_ok:
            groups = None
        # A stale manifest executes the original unfiltered suite in serial;
        # pilot does not execute overlapping nodes. Aggregation still refuses
        # qualification as a successful partition and requires manifest review.
        fallback = groups is None
        selected = groups[shard] if groups else nodes if shard == "serial" else []
        value.update(nodes=selected, fallback=fallback, manifest_sha256=digest(MANIFEST))
        if not selected:
            value["status"] = "FALLBACK_NOT_QUALIFIED"
            return 1
        if shard == "serial":
            from scripts.v14_test_database import verified_test_url

            verified_test_url()
        else:
            import socket

            def deny(*args, **kwargs):
                raise RuntimeError("CI_OPT_02_PILOT_NETWORK_FORBIDDEN")

            socket.socket.connect = deny
        coverage = out / (".coverage." + shard)
        os.environ["COVERAGE_FILE"] = str(coverage)
        code = pytest.main(
            [
                "-p",
                "scripts.a42331_pytest_safety",
                "--tb=no",
                "--show-capture=no",
                "-rN",
                "--cov=backend/app",
                "--cov-report=",
                "--cov-fail-under=0",
                "--junitxml=" + str(out / "tests.xml"),
            ],
            plugins=[Selection(selected)],
        )
        value["exit_code"] = int(code)
        tree = ET.parse(out / "tests.xml")
        cases = list(tree.iter("testcase"))
        value.update(
            {
                key: sum(c.find(tag) is not None for c in cases)
                for key, tag in [
                    ("failures", "failure"),
                    ("errors", "error"),
                    ("skipped", "skipped"),
                ]
            }
        )
        if len(cases) != len(selected):
            raise ValueError("CI_OPT_02_JUNIT_COUNT_MISMATCH")
        value.update(coverage_sha256=digest(coverage), junit_sha256=digest(out / "tests.xml"))
        if (
            code == 0
            and not fallback
            and not any(value[k] for k in ("failures", "errors", "skipped"))
        ):
            value["status"] = "PASS"
        return 0 if value["status"] == "PASS" else 1
    finally:
        value.update(
            wall_seconds=time.monotonic() - start,
            process_cpu_seconds=time.process_time() - cpu,
            cpu_scope="PYTHON_PARENT_NOT_SERVER_OR_CHILD_PROCESSES",
            performance_eligible=False,
            cpu_count=os.cpu_count(),
            ram_bytes=os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE"),
            peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            * (1 if sys.platform == "darwin" else 1024),
            platform=platform.platform(),
            physical_instance={
                k: os.environ.get(k)
                for k in ("V14_TEST_INSTANCE", "V14_TEST_SYSTEM_IDENTIFIER", "V14_CONTAINER")
            },
        )
        save(out / "result.json", value)


def validate_junit(path, nodes):
    from _pytest.junitxml import mangle_test_address

    from scripts.a42331_ci_evidence import safe_identifier

    expected = []
    for node in nodes:
        parts = mangle_test_address(node)
        expected.append(
            (safe_identifier(".".join(parts[:-1])), safe_identifier(parts[-1], parameter=True))
        )
    root = ET.parse(path).getroot()
    cases = list(root.iter("testcase"))
    if Counter((c.get("classname"), c.get("name")) for c in cases) != Counter(expected) or any(
        c.find(tag) is not None for c in cases for tag in ("failure", "error", "skipped")
    ):
        raise ValueError("CI_OPT_02_JUNIT_NODE_OR_OUTCOME_MISMATCH")


def aggregate(directory, minimum):
    save(
        ROOT / ".codex_tmp/ci-shards/combined.json",
        dict(identity(), status="INCOMPLETE", performance_eligible=False),
    )
    manifest = json.loads(MANIFEST.read_text())
    receipts, paths = [], []
    for shard in SHARDS:
        matches = list(directory.rglob("result.json"))
        matches = [p for p in matches if json.loads(p.read_text()).get("shard") == shard]
        if len(matches) != 1:
            raise ValueError("CI_OPT_02_ARTIFACT_NOT_UNIQUE")
        path = matches[0].parent
        r = json.loads(matches[0].read_text())
        if (
            r.get("manifest_sha256") != digest(MANIFEST)
            or digest(path / "tests.xml") != r.get("junit_sha256")
            or digest(path / (".coverage." + shard)) != r.get("coverage_sha256")
        ):
            raise ValueError("CI_OPT_02_ARTIFACT_DIGEST_MISMATCH")
        groups = partition(manifest["nodes"], manifest)
        if groups is None or Counter(r["nodes"]) != Counter(groups[shard]):
            raise ValueError("CI_OPT_02_SHARD_OWNERSHIP_CHANGED")
        validate_junit(path / "tests.xml", r["nodes"])
        receipts.append(r)
        paths.append(path)
    validate_results(receipts, manifest["nodes"], identity())
    # Coverage's own database reader and path mapping handle real independent
    # data files; no percentage averaging or last-shard overwrite.
    import coverage

    cov = coverage.Coverage(source=["backend/app"])
    cov.combine(data_paths=[str(p) for p in paths], strict=True, keep=True)
    cov.save()
    percent = cov.report()
    cov.xml_report(outfile=".codex_tmp/ci-shards/coverage.xml")
    if percent < minimum:
        raise ValueError("CI_OPT_02_COMBINED_COVERAGE_BELOW_70")
    suites = ET.Element("testsuites")
    for path in paths:
        tree = ET.parse(path / "tests.xml").getroot()
        for suite in tree.iter("testsuite"):
            suites.append(suite)
    destination = ROOT / ".codex_tmp/m17_1_2-full.xml"
    destination.parent.mkdir(exist_ok=True)
    ET.ElementTree(suites).write(destination, encoding="utf-8", xml_declaration=True)
    save(
        ROOT / ".codex_tmp/ci-shards/combined.json",
        dict(
            identity(),
            status="FULL_PASS",
            nodes=len(manifest["nodes"]),
            coverage_percent=percent,
            shards=receipts,
            performance_eligible=False,
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("run", "aggregate", "collect", "manifest"))
    parser.add_argument("--shard", choices=SHARDS)
    parser.add_argument("--input", type=Path, default=Path(".codex_tmp/shard-input"))
    parser.add_argument("--cov-fail-under", type=int, choices=(70,), default=70)
    parser.add_argument("-p", choices=("scripts.a42331_pytest_safety",))
    args = parser.parse_args()
    if args.mode == "manifest":
        subprocess.run(
            [sys.executable, "-m", "scripts.ci_test_shards", "collect"],
            cwd=ROOT,
            check=True,
            timeout=120,
        )
        nodes = json.loads((ROOT / ".codex_tmp/ci-shards/collection.json").read_text())
        if len(nodes) != len(set(nodes)) or sum(n.split("::")[0] == PILOT for n in nodes) != 8:
            raise ValueError("CI_OPT_02_PILOT_OR_COLLECTION_REVIEW_REQUIRED")
        source = (
            "backend/app/core/portfolio_config.py",
            "backend/app/domain/experiment/__init__.py",
            "backend/app/domain/experiment/grid.py",
            "backend/app/domain/experiment/contracts.py",
        )
        save(
            MANIFEST,
            dict(
                schema="ci-opt-02.manifest.v1",
                nodes=nodes,
                pilot_module=PILOT,
                mode="B0",
                B1_enabled=False,
                test_sha256={
                    str(p.relative_to(ROOT)): digest(p)
                    for p in sorted((ROOT / "tests").rglob("*.py"))
                },
                pilot_source_sha256={p: digest(ROOT / p) for p in source},
            ),
        )
        return
    if args.mode == "collect":
        from app.core.config import Settings

        Settings.model_config["env_file"] = None
        import socket

        def deny(*args, **kwargs):
            raise RuntimeError("CI_OPT_02_COLLECTION_NETWORK_FORBIDDEN")

        socket.socket.connect = deny
        save(ROOT / ".codex_tmp/ci-shards/collection.json", collect_here())
        return
    if args.mode == "run":
        raise SystemExit(run_shard(args.shard))
    aggregate(args.input, args.cov_fail_under)


if __name__ == "__main__":
    main()
