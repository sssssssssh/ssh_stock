"""Run C1/C2 against original safety cases on a doubly verified disposable PG17."""

import pytest
from app.services.data_publication import PublicationWorkspace
from sqlalchemy import select, update

from scripts.publication_lookup_diagnostic_a422 import lookup
from scripts.v14_test_database import isolated_v14_database
from tests.integration import test_data_publication as original


@pytest.fixture(params=('C1', 'C2'))
def candidate_database(request, monkeypatch):
    with isolated_v14_database(monkeypatch) as database:
        monkeypatch.setattr(PublicationWorkspace, '_lookup_batch',
            lambda ws, model, payload: lookup(ws, model, payload, request.param))
        yield database


@pytest.mark.parametrize('case', [
    'successful_candidate_publishes_all_tables_and_stable_signal_id',
    'old_a_does_not_validate_an_incomplete_b',
    'public_read_snapshot_never_mixes_a_and_b_across_queries',
    'missing_a_is_not_replaced_by_in_progress_b_and_cleanup_does_not_leak',
    'legacy_null_provenance_survives_cancel',
    'signal_delete_archives_evaluation_and_terminal_evidence_is_immutable',
    'candidate_mutation_invalidates_its_prior_quality_certificate',
])
def test_original_publication_safety_with_candidate_lookup(candidate_database, case):
    getattr(original, 'test_'+case)(candidate_database)


@pytest.mark.parametrize('status', ['FAILED', 'CANCELLED', 'PARTIAL'])
def test_failed_cancelled_partial_keep_a(candidate_database, status):
    original.test_failed_or_cancelled_candidate_never_replaces_a(candidate_database, status)


@pytest.mark.parametrize('mode', ['budget', 'timeout', 'identity', 'changed_base', 'missing_stage'])
def test_publish_guards_unchanged(candidate_database, monkeypatch, mode):
    original.test_publish_fails_closed_without_changing_a(candidate_database, monkeypatch, mode)


@pytest.mark.parametrize('case', [
    'disconnect_mid_publication_rolls_back_a_and_holds_slot',
    'committed_publish_response_loss_never_rewrites_success',
    'cancelled_recalculation_keeps_previously_published_same_key',
])
def test_disconnect_unknown_commit_and_cancellation(candidate_database, monkeypatch, case):
    getattr(original, 'test_'+case)(candidate_database, monkeypatch)


def test_typed_golden_empty_duplicates_new_rows_json_nulls_and_tombstones(monkeypatch):
    from app.models.data_publication import DataPublicationRow
    from app.repositories.upsert import upsert_rows
    from app.services.data_publication import KEYS, MODELS

    with isolated_v14_database(monkeypatch) as (factory, engine):
        original.seed_published(factory, legacy_null=True)
        with original.candidate(factory, engine) as (db, job):
            ws = db.info['publication_workspace']
            for model in MODELS[:8]:
                payload = original.sample_row(model, job.id, 23)
                if 'reason_codes' in model.__table__.c:
                    payload['reason_codes'] = {'nested': [None, 0, False, '合成']}
                new = {**payload}
                if 'ts_code' in new:
                    new['ts_code'] = 'NEW.SZ'
                else:
                    new['trade_date'] = original.DAY.replace(day=2)
                requested = [payload, new, payload]
                for phase in ('a_only', 'b_overrides_a', 'tombstone'):
                    if phase == 'b_overrides_a':
                        upsert_rows(db, model, [payload, new], KEYS[model.__tablename__])
                        db.commit()
                    elif phase == 'tombstone':
                        db.execute(update(DataPublicationRow).where(
                            DataPublicationRow.publication_id == job.id,
                            DataPublicationRow.table_name == model.__tablename__,
                        ).values(is_deleted=True, row_data=None))
                        db.commit()
                    expected = lookup(ws, model, requested, 'C0')
                    for variant in ('C1', 'C2', 'C3_100', 'C3_1000'):
                        assert lookup(ws, model, requested, variant) == expected
                        assert lookup(ws, model, [], variant) == ({}, {}, None)
                    if phase == 'tombstone':
                        assert expected[0] == {} and expected[1]
                # First public preimage stays immutable despite repeated B writes.
                bases = db.scalars(select(DataPublicationRow.base_row).where(
                    DataPublicationRow.publication_id == job.id,
                    DataPublicationRow.table_name == model.__tablename__)).all()
                assert any(base is not None for base in bases)
