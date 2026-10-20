import pytest

from scripts.v14_test_database import verified_test_url


@pytest.mark.parametrize("url,marker", [
    ("", ""),
    ("postgresql+psycopg://stock:stock@business.example/stock_test", "bad"),
    ("postgresql+psycopg://stock:stock@127.0.0.1/stock", "bad"),
    ("sqlite://", "bad"),
])
def test_target_guard_refuses_before_business_settings(monkeypatch, url, marker):
    monkeypatch.setenv("TEST_DATABASE_URL", url)
    monkeypatch.setenv("V14_TEST_INSTANCE", marker)
    with pytest.raises(RuntimeError, match="V14_EXPLICIT_MARKED_PG17_REQUIRED"):
        verified_test_url()
