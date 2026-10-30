"""Execute unchanged source-contract tests in their immutable Git version."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from xml.etree import ElementTree

from scripts.source_contract_governance import (
    HISTORICAL,
    HISTORICAL_MODULES,
    HISTORICAL_NODES,
    HISTORICAL_SHA,
    require_historical_source,
)


def validate_result(returncode, xml, expected):
    suites = ElementTree.fromstring(xml)
    cases = list(suites.iter("testcase"))
    totals = list(suites.iter("testsuite"))
    if (returncode != 0 or len(cases) != expected
            or len(totals) != 1 or int(totals[0].get("tests", "-1")) != expected
            or any(int(totals[0].get(k, "-1")) != 0 for k in ("failures", "errors", "skipped"))
            or len({(c.get("classname"), c.get("name")) for c in cases}) != expected
            or any(c.find(tag) is not None for c in cases
                   for tag in ("failure", "error", "skipped"))):
        raise ValueError("SOURCE_CONTRACT_HISTORICAL_TEST_FAILED")
    return dict(passed=len(cases), failed=0, errors=0, skipped=0, exit_code=returncode,
                source_sha=HISTORICAL_SHA, performance_eligible=False, g1_authorized=False)


def verify_test_sources(root, paths):
    from scripts.business_source_contract import git

    for path in paths:
        if path not in HISTORICAL_MODULES:
            raise ValueError("SOURCE_CONTRACT_UNREGISTERED_HISTORICAL_TEST")
        original = git(root, "show", HISTORICAL_SHA + ":" + path)
        current = Path(root) / path
        if (git(root, "show", "HEAD:" + path) != original or current.is_symlink()
                or current.read_bytes() != original):
            raise ValueError("SOURCE_CONTRACT_HISTORICAL_TEST_SOURCE_CHANGED")


def run(root, *, node=None):
    root = Path(root).resolve()
    if node is not None and node not in HISTORICAL_NODES:
        raise ValueError("SOURCE_CONTRACT_UNREGISTERED_HISTORICAL_NODE")
    verify_test_sources(root, HISTORICAL_MODULES if node is None else (node.split("::")[0],))
    parent = root / ".codex_tmp"
    parent.mkdir(exist_ok=True)
    if parent.is_symlink() or not parent.resolve().is_relative_to(root):
        raise ValueError("SOURCE_CONTRACT_UNSAFE_HISTORY_DIRECTORY")
    # Only a freshly owned child of the verified temporary directory is cleaned.
    with tempfile.TemporaryDirectory(prefix="source-history-", dir=parent) as name:
        directory = Path(name).resolve()
        if not directory.is_relative_to(parent.resolve()):
            raise ValueError("SOURCE_CONTRACT_UNSAFE_HISTORY_DIRECTORY")
        checkout = directory / "repo"
        subprocess.run(["git", "-c", "core.autocrlf=false", "clone", "--shared",
                        "--no-checkout", "--", str(root), str(checkout)],
                       check=True, capture_output=True, timeout=60)
        subprocess.run(["git", "-C", str(checkout), "-c", "core.autocrlf=false",
                        "checkout", "--detach", HISTORICAL_SHA],
                       check=True, capture_output=True, timeout=60)
        require_historical_source(checkout, HISTORICAL_SHA)
        from scripts.business_source_contract import verify

        if len(verify(checkout, version=HISTORICAL, expected_sha=HISTORICAL_SHA)) != 64:
            raise ValueError("SOURCE_CONTRACT_HISTORICAL_ROUTE_FAILED")
        if (checkout / ".env").exists():
            raise ValueError("SOURCE_CONTRACT_HISTORY_DOTENV_REJECTED")
        env = {k: v for k, v in os.environ.items()
               if not k.startswith("PG") and k not in (
                   "DATABASE_URL", "TEST_DATABASE_URL", "PYTEST_ADDOPTS", "PYTEST_PLUGINS")}
        env.update(PYTHONPATH=os.pathsep.join((str(checkout), str(checkout / "backend"))),
                   LLM_ENABLED="false", PYTEST_ADDOPTS="")
        output = directory / "historical.xml"
        result = subprocess.run(
            [sys.executable, "-m", "pytest", *(HISTORICAL_MODULES if node is None else (node,)),
             "-v", "--tb=long", "--junitxml=" + str(output)],
            cwd=checkout, env=env, capture_output=True, text=True, timeout=600)
        print(result.stdout, end="")
        print(result.stderr, end="", file=sys.stderr)
        if not output.is_file():
            raise ValueError("SOURCE_CONTRACT_HISTORICAL_JUNIT_MISSING")
        return validate_result(result.returncode, output.read_bytes(), 73 if node is None else 1)


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if args:
        print(json.dumps(dict(error="SOURCE_CONTRACT_ARGUMENTS_REJECTED",
                              scope="HISTORICAL_TEST_ONLY", g1_authorized=False)))
        return 1
    print(json.dumps(run(Path(__file__).resolve().parents[1]), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
