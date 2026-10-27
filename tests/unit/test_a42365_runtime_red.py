"""A42365 W00: missing implementations, not successful denials dressed as RED."""

import importlib

import pytest


@pytest.mark.parametrize(
    "module,member",
    [
        ("runtime_factory", "build_installed_runtime"),
        ("writer_broker", "InstalledWriterBroker"),
        ("budget", "BudgetService"),
        ("lifecycle", "ResourceLifecycle"),
        ("provisioner", "ReadOnlyProvisioner"),
        ("supervisor", "InstalledSupervisor"),
        ("owner", "AuditConnectionFactory"),
        ("runtime", "RuntimeCoordinator"),
    ],
)
def test_W00_mandatory_runtime_implementation_exists(module, member):
    value = importlib.import_module("scripts.a42365_" + module)
    implementation = getattr(value, member)
    assert callable(implementation)
    assert implementation.__module__ == value.__name__
