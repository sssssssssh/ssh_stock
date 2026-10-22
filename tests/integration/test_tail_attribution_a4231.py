"""PG17 preflight for snapshot import; no diagnostic performance samples here."""

import pytest
from sqlalchemy import text

from scripts.publication_lookup_tail_attribution_a4231 import import_snapshot
from scripts.v14_test_database import isolated_v14_database, verified_test_url


@pytest.fixture
def attribution_database(monkeypatch):
    verified_test_url()  # Before business Settings imports, never local fallback.
    from app.core.config import Settings, get_settings

    with monkeypatch.context() as patch:
        patch.setitem(Settings.model_config, 'env_file', None)
        get_settings.cache_clear()
        try:
            with isolated_v14_database(patch) as database:
                yield database
        finally:
            get_settings.cache_clear()


def test_exported_snapshot_imports_same_data_read_only_and_keeps_300s(attribution_database):
    from tests.integration import test_data_publication as original

    factory, _ = attribution_database
    original.seed_published(factory)
    with factory() as exporter:
        exporter.connection(execution_options={'isolation_level':'REPEATABLE READ'})
        exporter.execute(text('SET TRANSACTION READ ONLY'))
        snapshot = exporter.scalar(text('SELECT pg_export_snapshot()'))
        census = exporter.scalar(text('SELECT count(*) FROM public.stock_trade_status_daily'))
        with factory() as child:
            import_snapshot(child, snapshot)
            assert child.scalar(text('SHOW transaction_read_only')) == 'on'
            assert child.scalar(text('SHOW transaction_isolation')) == 'repeatable read'
            assert child.scalar(text("SELECT setting::int FROM pg_settings "
                                     "WHERE name='statement_timeout'")) == 300000
            count = child.scalar(text('SELECT count(*) FROM public.stock_trade_status_daily'))
            assert count == census
            assert census > 0
