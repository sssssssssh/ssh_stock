"""Explicit opt-in migration fixture; never changes global SessionLocal/Settings."""

import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.main import app
from app.services.auth.dependencies import require_authenticated_user

from scripts.a42_artifacts import atomic
from scripts.a42331_migration_contract import owned_migration_database


@pytest.fixture(autouse=True)
def authenticated_business_api_tests():
    app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(
        username="test-admin", must_change_password=False
    )
    yield
    app.dependency_overrides.pop(require_authenticated_user, None)


@pytest.fixture
def archive_migration_database():
    owned = None
    try:
        with owned_migration_database() as owned:
            yield owned
    finally:
        directory = os.environ.get('A42331_MIGRATION_EVIDENCE_DIR')
        if directory and owned is not None:
            atomic(Path(directory)/(owned.name+'.json'),dict(
                schema_version='a42331.migration-contract.v1',evidence_kind='DIAGNOSTIC_ONLY',
                head_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
                run_id=os.environ.get('GITHUB_RUN_ID','local'),
                attempt=os.environ.get('GITHUB_RUN_ATTEMPT','1'),
                evidence=owned.evidence,capacity_ready=False,performance_eligible=False,
                production_read_authorized=False))
