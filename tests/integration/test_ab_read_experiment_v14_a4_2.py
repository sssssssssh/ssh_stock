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
