"""Post-collection drift review cannot promote a completed collector to PASS."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.publication_tail_attribution_review_a4231 import (
    classification,
    review,
    statistics_drift,
)


def environment():
    return dict(index_definition_sha256='same-index', settings_sha256='same-settings',
        environment=dict(tables=[dict(relname=name, reltuples=-1, relpages=0,
            last_analyze=None, last_autoanalyze=None, n_live_tup=100000)
            for name in ('a','b','c','d')]))


def test_background_autoanalyze_is_drift_despite_identical_data_snapshot():
    before = environment()
    after = deepcopy(before)
    after['environment']['tables'][0].update(reltuples=100000, relpages=2041,
        last_autoanalyze='2026-10-22 17:15:44+00:00')
    drift = statistics_drift(before, after)
    assert {d['field'] for d in drift} == {'reltuples','relpages','last_autoanalyze'}
    result = classification(drift, {'all_preregistered_conditions_met':True})
    assert result['collection_status'] == 'COMPLETE'
    assert result['analysis_status'] == 'INCOMPLETE_ENVIRONMENT_DRIFT'
    assert result['root_cause'] == 'INSUFFICIENT_EVIDENCE'
    assert result['capacity_ready'] is False
    assert result['p2'] == result['p3'] == 'NOT_AUTHORIZED'
    assert result['excluded_samples'] == result['repeated_experiments'] == 0


def test_table_order_and_live_tuple_estimate_are_not_planner_identity():
    before = environment()
    after = deepcopy(before)
    after['environment']['tables'].reverse()
    after['environment']['tables'][0]['n_live_tup'] = 99999
    assert statistics_drift(before, after) == []


@pytest.mark.parametrize('field', ['index_definition_sha256','settings_sha256'])
def test_settings_or_index_mismatch_fails_closed(field):
    before, after = environment(), environment()
    after[field] = 'changed'
    with pytest.raises(ValueError, match='INDEX_OR_SETTINGS_DRIFT'):
        statistics_drift(before, after)


def test_missing_statistics_is_not_stability():
    before, after = environment(), environment()
    del after['environment']['tables'][0]['last_autoanalyze']
    with pytest.raises(ValueError, match='STATISTICS_FIELD_MISSING'):
        statistics_drift(before, after)


def test_even_all_positive_checks_do_not_authorize_repair_or_capacity():
    result = classification([], {'all_preregistered_conditions_met':True})
    assert result['root_cause'] == 'REQUIRES_MANUAL_CAUSAL_REVIEW'
    assert result['unique_repair_candidate'] is None
    assert result['capacity_ready'] is False and result['performance_eligible'] is False
    result = classification([], {'all_preregistered_conditions_met':False})
    assert result['root_cause'] == 'INSUFFICIENT_EVIDENCE'


def test_wrong_archive_fails_before_json_or_database_access(tmp_path):
    archive = tmp_path/'not-the-frozen-archive.zip'
    archive.write_bytes(b'wrong-sha-and-missing-samples')
    with pytest.raises(ValueError, match='ZIP_DIGEST_MISMATCH'):
        review(archive)


def test_committed_review_keeps_all_counterexamples_and_denies_admission():
    data = json.loads(Path('docs/acceptance/evidence/a4231_attribution_review.json').read_text())
    assert data['sample_count'] == 128 and data['excluded_samples'] == 0
    assert len(data['statistics_drift']) == 3
    assert data['analysis_status'] == 'INCOMPLETE_ENVIRONMENT_DRIFT'
    assert data['root_cause'] == 'INSUFFICIENT_EVIDENCE'
    assert len(data['generation2_events']) == 4
    assert {e['variant'] for e in data['generation2_events']} == {'C0'}
    assert {e['observer_mode'] for e in data['generation2_events']} == {'full','minimal'}
    checks = data['h3_preregistered_checks']
    assert len(checks['checks']) == 8 and checks['all_preregistered_conditions_met'] is False
    assert data['capacity_ready'] is False and data['unique_repair_candidate'] is None
