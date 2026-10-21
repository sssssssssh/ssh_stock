"""Actual PG17 counterexamples, not mocked success or production patches."""

import pytest
from app.models.market_data import StockTradeStatusDaily as Model
from app.repositories import ab_merge_read as ab
from app.services.data_publication import workspace
from sqlalchemy import text

from scripts.ab_read_evidence_v14_a4_2 import (
    EventEvidence,
    UnsafeCandidateCertificate,
    UnsafeFingerprintMemo,
    generations,
    install_events,
)
from scripts.v14_test_database import isolated_v14_database
from tests.integration import test_ab_merge_read_v14 as golden
from tests.integration import test_data_publication as support


@pytest.fixture
def database(monkeypatch):
    with isolated_v14_database(monkeypatch) as value:
        yield value


def prepare(db):
    ab._prepare_candidate_read(db, workspace(db), ab.ReadWindow(support.DAY, support.DAY))


def test_e1_cached_sha_accepts_changed_intermediate_a_and_restored_final_a(database, monkeypatch):
    factory, engine = database
    support.seed_published(factory)
    original = ab._public_fingerprints
    memo = UnsafeFingerprintMemo(original)
    with support.candidate(factory, engine) as (db, job):
        monkeypatch.setattr(ab, "_public_fingerprints", memo)
        prepare(db)
        db.commit()
        with factory.begin() as outsider:
            outsider.execute(text("UPDATE public.stock_trade_status_daily SET is_st=true"))
        prepare(db)  # Deliberate unsafe prototype: did NOT reject changed source.
        assert db.scalar(text("SELECT is_st FROM public.stock_trade_status_daily")) is True
        db.commit()
        with factory.begin() as outsider:
            outsider.execute(text("UPDATE public.stock_trade_status_daily SET is_st=NULL"))
        monkeypatch.setattr(ab, "_public_fingerprints", original)
        ab.verify_public_read_evidence(db, workspace(db))  # final SHA alone misses intermediate A'.


def test_e2_caller_generation_does_not_invalidate_for_direct_candidate_sql(database, monkeypatch):
    factory, engine = database
    support.seed_published(factory)
    with support.candidate(factory, engine) as (db, job):
        workspace(db).upsert(Model, [support.sample_row(Model, job.id)], ("trade_date", "ts_code"))
        db.commit()
        certificate, original = UnsafeCandidateCertificate(), db.scalar

        def scalar(statement, params=None, **kwargs):
            if str(statement).lstrip().startswith("SELECT EXISTS(SELECT 1 FROM"):
                return certificate.check(original, statement, params)
            return original(statement, params, **kwargs)

        monkeypatch.setattr(db, "scalar", scalar)
        prepare(db)
        db.commit()
        with factory.begin() as outsider:
            outsider.execute(text("UPDATE public.data_publication_row SET entity_key='CORRUPT'"))
        prepare(db)  # Counterexample: cache trusts old validation across a real direct UPDATE.
        db.rollback()
        monkeypatch.setattr(db, "scalar", original)
        with pytest.raises(ValueError, match="AB_READ_CANDIDATE_INVALID"):
            prepare(db)  # The unchanged E0 guard DOES detect it.


@pytest.mark.parametrize("operation", ["update", "delete", "insert", "aba"])
def test_e3_observes_committed_a_dml_and_aba_across_commits(database, operation):
    factory, engine = database
    support.seed_published(factory)
    with support.candidate(factory, engine) as (db, job):
        install_events(db)
        evidence = EventEvidence()
        evidence.prepare(db, workspace(db), ab.ReadWindow(support.DAY, support.DAY))
        db.commit()
        with factory.begin() as outsider:
            if operation in {"update", "aba"}:
                outsider.execute(text("UPDATE public.stock_trade_status_daily SET is_st=true"))
                if operation == "aba":
                    outsider.execute(text("UPDATE public.stock_trade_status_daily SET is_st=NULL"))
            elif operation == "delete":
                outsider.execute(text("DELETE FROM public.stock_trade_status_daily"))
            else:
                outsider.add(Model(**{**support.sample_row(Model, None), "ts_code": "NEW.SZ"}))
        with pytest.raises(ValueError, match="A42_SOURCE_EVENT_CHANGED"):
            evidence.prepare(db, workspace(db), ab.ReadWindow(support.DAY, support.DAY))
        db.rollback()
        with pytest.raises(ValueError, match="A42_SOURCE_EVENT_CHANGED"):
            evidence.verify(db)


def test_e3_rollback_does_not_create_false_generation_and_same_tx_reuse_is_real(database):
    factory, engine = database
    support.seed_published(factory)
    with support.candidate(factory, engine) as (db, job):
        install_events(db)
        evidence = EventEvidence()
        window = ab.ReadWindow(support.DAY, support.DAY)
        evidence.prepare(db, workspace(db), window)
        before = generations(db)
        evidence.prepare(db, workspace(db), window)
        assert generations(db) == before
        db.commit()
        with factory() as outsider:
            outsider.execute(text("UPDATE public.stock_trade_status_daily SET is_st=true"))
            outsider.rollback()
        evidence.prepare(db, workspace(db), window)
        assert generations(db) == before


def test_e3_direct_b_update_invalidates_certificate_and_rechecks_all_b(database):
    factory, engine = database
    support.seed_published(factory)
    with support.candidate(factory, engine) as (db, job):
        workspace(db).upsert(Model, [support.sample_row(Model, job.id)], ("trade_date", "ts_code"))
        db.commit()
        install_events(db)
        evidence = EventEvidence()
        evidence.prepare(db, workspace(db), ab.ReadWindow(support.DAY, support.DAY))
        db.commit()
        with factory.begin() as outsider:
            outsider.execute(text("UPDATE public.data_publication_row SET trade_date='2020-01-01'"))
        with pytest.raises(ValueError, match="AB_READ_CANDIDATE_INVALID"):
            evidence.prepare(db, workspace(db), ab.ReadWindow(support.DAY, support.DAY))


def test_e3_privileged_trigger_bypass_is_explicit_counterexample_not_safe_equivalence(database):
    factory, engine = database
    support.seed_published(factory)
    with support.candidate(factory, engine) as (db, job):
        install_events(db)
        evidence = EventEvidence()
        window = ab.ReadWindow(support.DAY, support.DAY)
        evidence.prepare(db, workspace(db), window)
        db.commit()
        with factory.begin() as outsider:
            outsider.execute(text("ALTER TABLE public.stock_trade_status_daily "
                                  "DISABLE TRIGGER a42_event"))
            outsider.execute(text("UPDATE public.stock_trade_status_daily SET is_st=true"))
            outsider.execute(text("ALTER TABLE public.stock_trade_status_daily "
                                  "ENABLE TRIGGER a42_event"))
        evidence.prepare(db, workspace(db), window)  # E3 alone missed privileged bypass.
        with pytest.raises(ValueError, match="AB_READ_PUBLISHED_INPUT_CHANGED"):
            ab.verify_public_read_evidence(db, workspace(db))  # Keep original T8 in experiments.


def substitute_sql(monkeypatch, variant):
    from scripts.ab_read_experiment_v14_a4_2 import sql

    original = ab.trade_status_statement

    def statement(*, candidate, columns=ab.FACTOR_COLUMNS):
        return sql(variant, columns) if candidate else original(candidate=False, columns=columns)

    monkeypatch.setattr(ab, "trade_status_statement", statement)
    monkeypatch.setattr(golden, "trade_status_statement", statement)


@pytest.mark.parametrize("variant", ["S3", "S3_INLINE", "S3_KEYS", "S4", "S5"])
@pytest.mark.parametrize("mode", ["a_only", "overwrite", "delete", "wrong_version", "wrong_hash",
                                 "rebuild", "new", "empty", "null", "other_root"])
def test_sql_candidates_reuse_exact_frozen_all_field_golden(database, monkeypatch, variant, mode):
    substitute_sql(monkeypatch, variant)
    golden.test_frozen_q0_all_columns_and_factor_types(database, monkeypatch, mode)


@pytest.mark.parametrize("days", [1, 3, 5, 10, 20])
def test_no_sql_sort_keeps_closed_days_month_year_null_dtype_and_global_order(
    database, monkeypatch, days,
):
    substitute_sql(monkeypatch, "S5")
    golden.test_windows_preserve_full_keys_null_dtype_and_closed_day_rows(database, days)


@pytest.mark.parametrize("corruption", ["date", "entity", "payload_date", "missing_identity",
                                        "tombstone_date"])
def test_candidate_keys_must_be_validated_before_bounded_cte(database, monkeypatch, corruption):
    substitute_sql(monkeypatch, "S3")
    golden.test_bad_redundant_keys_and_missing_identity_fail_closed(database, corruption)


@pytest.mark.parametrize("fault,expected", [
    ("cancel","CANCELLED"),("timeout","FAILED"),("disconnect","RUNNING")])
@pytest.mark.parametrize("variant", ["S3","S4","S5"])
def test_sql_candidates_keep_real_worker_abort_and_unknown_execution(
    database, monkeypatch, variant, fault, expected,
):
    substitute_sql(monkeypatch, variant)
    golden.test_real_worker_window_failure_keeps_public_a_and_execution_safety(
        database, monkeypatch, fault, expected)


@pytest.mark.parametrize("variant", ["S3","S4","S5"])
def test_sql_candidates_reject_wrong_execution_token(database, monkeypatch, variant):
    substitute_sql(monkeypatch, variant)
    golden.test_wrong_execution_token_cannot_read_candidate(database)


@pytest.mark.parametrize("variant", ["S3","S4","S5"])
def test_sql_candidates_reject_read_only_warmup_source_change_at_publication(
    database, monkeypatch, variant,
):
    substitute_sql(monkeypatch, variant)
    golden.test_final_publication_checks_read_only_warmup_a_not_just_candidate_base(database)


def test_e3_self_mutation_rebuild_and_savepoint_preserve_first_preimage(database):
    factory, engine = database
    support.seed_published(factory)
    with support.candidate(factory, engine) as (db, job):
        install_events(db)
        ws, evidence = workspace(db), EventEvidence()
        window = ab.ReadWindow(support.DAY, support.DAY)
        row = support.sample_row(Model, job.id)
        ws.upsert(Model, [row], ("trade_date","ts_code"))
        original = db.scalar(text("SELECT base_row FROM public.data_publication_row"))
        evidence.prepare(db, ws, window)
        seen = generations(db)["B"]
        with db.begin_nested() as savepoint:
            ws.upsert(Model, [{**row,"is_st":True}], ("trade_date","ts_code"))
            assert generations(db)["B"] > seen
            savepoint.rollback()
        assert generations(db)["B"] == seen
        for _ in range(2):
            ws.delete_keys(Model, [(support.DAY,row["ts_code"])])
            evidence.prepare(db, ws, window)
            ws.upsert(Model, [{**row,"is_st":True}], ("trade_date","ts_code"))
            evidence.prepare(db, ws, window)
            assert db.scalar(text("SELECT base_row FROM public.data_publication_row")) == original


def test_e3_savepoint_generation_reuse_is_an_explicit_unsafe_certificate_counterexample(database):
    factory, engine = database
    support.seed_published(factory)
    with support.candidate(factory, engine) as (db, job):
        ws = workspace(db)
        ws.upsert(Model, [support.sample_row(Model, job.id)], ("trade_date","ts_code"))
        db.commit()
        install_events(db)
        evidence = EventEvidence()
        with db.begin_nested() as savepoint:
            db.execute(text("UPDATE public.data_publication_row SET entity_key=entity_key"))
            evidence.prepare(db, ws, ab.ReadWindow(support.DAY, support.DAY))
            assert evidence.seen["B"] == 1
            savepoint.rollback()
        assert generations(db)["B"] == 0
        db.execute(text("UPDATE public.data_publication_row SET entity_key='CORRUPT'"))
        assert generations(db)["B"] == 1  # The rolled-back number has been reused.
        evidence.prepare(db, ws, ab.ReadWindow(support.DAY, support.DAY))  # Prototype misses this.
        with pytest.raises(ValueError, match="AB_READ_CANDIDATE_INVALID"):
            prepare(db)  # Original validation correctly refuses the same corrupted B.


@pytest.mark.parametrize("variant", ["S3_KEYS","S4","S5"])
def test_experiment_sql_preserves_real_engine_ten_table_publication_golden(monkeypatch, variant):
    substitute_sql(monkeypatch, variant)
    golden.test_real_engine_and_atomic_publication_equal_legacy_full_path(monkeypatch)


def test_native_all_field_read_preserves_decimal_projection_and_other_types(database):
    from decimal import Decimal

    import pandas as pd
    from app.repositories.calculation_frame import read_calculation_frame

    from scripts.ab_read_experiment_v14_a4_2 import sql

    factory, engine = database
    support.seed_published(factory)
    with support.candidate(factory, engine) as (db, job):
        row = {**support.sample_row(Model, job.id),"up_limit":11.12345678,"is_st":None}
        workspace(db).upsert(Model,[row],("trade_date","ts_code"))
        values = dict(lo=support.DAY,hi=support.DAY,root=job.id,
            version=row["calc_version"],hash=row["config_hash"])
        old = "SELECT * FROM stock_trade_status_daily WHERE trade_date BETWEEN :lo AND :hi " \
              "AND calc_version=:version AND config_hash=:hash"
        frames = []
        for query in (old,str(sql("S5",Model.__table__.c.keys()))):
            statement = text("SELECT v.*,CAST(up_limit AS numeric(20,8)) AS decimal_probe "
                             f"FROM ({query}) v")
            bind = {key:value for key,value in values.items() if f":{key}" in str(statement)}
            frames.append(read_calculation_frame(db,statement.bindparams(**bind),name="test.decimal"))
        pd.testing.assert_frame_equal(frames[0],frames[1],check_exact=True)
        assert frames[1].iloc[0]["decimal_probe"] == Decimal("11.12345678")


@pytest.mark.parametrize("damage", ["marker","system_id"])
def test_physical_mismatch_fails_before_child_database_ddl(database, monkeypatch, damage):
    from scripts.v14_test_database import isolated_v14_database

    factory, _ = database
    with factory() as db:
        before = db.scalar(text("SELECT count(*) FROM pg_database"))
    with monkeypatch.context() as patch:
        patch.setenv("V14_TEST_INSTANCE" if damage=="marker" else "V14_TEST_SYSTEM_IDENTIFIER",
                     "00000000-0000-0000-0000-000000000000" if damage=="marker" else "0")
        with pytest.raises(RuntimeError, match="V14_PHYSICAL_INSTANCE"):
            with isolated_v14_database(patch):
                raise AssertionError("must not create the child database")
    with factory() as db:
        assert db.scalar(text("SELECT count(*) FROM pg_database")) == before
