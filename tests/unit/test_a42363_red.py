"""W00 engineering-gap regressions, recorded RED before implementation."""

import importlib

import pytest


@pytest.mark.parametrize(
    "module,symbol",
    [
        ("services", "METHODS"),
        ("services", "ServiceHost"),
        ("stores", "DomainStore"),
        ("owner", "RawOwnerBackend"),
        ("resources", "ResourceDriver"),
        ("resources", "ControllerService"),
        ("absence", "IndependentObserver"),
        ("supervisor", "CgroupScope"),
        ("supervisor", "ArtifactPublisher"),
        ("review", "Reviewer"),
    ],
)
def test_W00_missing_cross_domain_implementations(module, symbol):
    implementation = importlib.import_module("scripts.a42363_" + module)
    assert callable(getattr(implementation, symbol)) or symbol == "METHODS"
