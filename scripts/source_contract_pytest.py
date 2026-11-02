"""Explicit one-node historical routing; no assertion changes or skipped tests."""

from pathlib import Path

import pytest

from scripts.source_contract_governance import HISTORICAL, HISTORICAL_NODES, HISTORICAL_SHA
from scripts.source_contract_history import run

ROUTED = pytest.StashKey[list[str]]()


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem):
    if pyfuncitem.nodeid not in HISTORICAL_NODES:
        return None
    root = Path(pyfuncitem.config.rootpath)
    print(f"Historical source-contract node: {HISTORICAL}@{HISTORICAL_SHA}")
    pyfuncitem.user_properties.extend((
        ("source_contract_version", HISTORICAL), ("source_contract_sha", HISTORICAL_SHA),
        ("source_contract_scope", "HISTORICAL_TEST_ONLY_NOT_CURRENT_AUTHORITY"),
    ))
    pyfuncitem.config.stash.setdefault(ROUTED, []).append(pyfuncitem.nodeid)
    result = run(root, node=pyfuncitem.nodeid)
    assert result["passed"] == 1 and result["exit_code"] == 0
    return True


def pytest_terminal_summary(terminalreporter, config):
    nodes = config.stash.get(ROUTED, [])
    if nodes:
        terminalreporter.write_sep("-", f"{len(nodes)} unchanged historical source-contract "
                                  f"node(s) executed at {HISTORICAL_SHA}; not current capacity")
