"""Explicit one-node historical routing; no assertion changes or skipped tests."""

from pathlib import Path

import pytest

from scripts.source_contract_governance import HISTORICAL, HISTORICAL_NODES, HISTORICAL_SHA
from scripts.source_contract_history import run

ROUTED = pytest.StashKey[list[str]]()


class R1HistoricalItem(pytest.Item):
    """Collected before unittest setup; the child runs original setup/body/teardown."""

    def runtest(self):
        from scripts.source_contract_governance import R1_HISTORICAL_SHA, R1_HISTORICAL_VERSION

        self.user_properties.extend((
            ("source_contract_version", R1_HISTORICAL_VERSION),
            ("source_contract_sha", R1_HISTORICAL_SHA),
            ("source_contract_scope", "HISTORICAL_ONLY_NOT_CURRENT_AUTHORITY"),
        ))
        receipt = run(Path(self.config.rootpath), node=self.nodeid)
        assert receipt["passed"] == 1 and receipt["exit_code"] == 0
        assert receipt["source_sha"] == R1_HISTORICAL_SHA

    def reportinfo(self):
        return self.path, 0, self.nodeid


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(items):
    from scripts.source_contract_governance import R1_HISTORICAL_NODE

    for index, item in enumerate(items):
        if item.nodeid == R1_HISTORICAL_NODE:
            # A Module parent avoids unittest Class setup/teardown in this process.
            parent = item.parent
            while not isinstance(parent, pytest.Module):
                parent = parent.parent
            items[index] = R1HistoricalItem.from_parent(
                parent, name=item.name, nodeid=item.nodeid)


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
