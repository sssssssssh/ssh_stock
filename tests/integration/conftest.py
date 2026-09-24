from types import SimpleNamespace

import pytest
from app.main import app
from app.services.auth.dependencies import require_authenticated_user


@pytest.fixture(autouse=True)
def authenticated_business_api_tests():
    app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(
        username="test-admin", must_change_password=False
    )
    yield
    app.dependency_overrides.pop(require_authenticated_user, None)
