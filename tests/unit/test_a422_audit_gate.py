"""Synthetic gate-control tests; never network audit or release evidence."""

import hashlib
import json
from pathlib import Path

import pytest

from scripts.a42_receipt_contract import ReceiptError
from scripts.ci_release_gate_v14_a4_2_1 import audit_receipt, lookup_receipt


@pytest.fixture
def audit_file(tmp_path, monkeypatch):
    monkeypatch.setenv('GITHUB_RUN_ID', '42')
    counts = {key:0 for key in ('info', 'low', 'moderate', 'high', 'critical', 'total')}
    audit = dict(exit_status=0, report=dict(auditReportVersion=2, vulnerabilities={},
                                          metadata=dict(vulnerabilities=counts)))
    receipt = dict(schema_version='m17.1-dependency-audit-v1', status='COMPLETE',
        head_sha='a'*40, run_id='42', attempt='1', node_version='v22.0.0',
        lock_sha256=hashlib.sha256(Path('frontend/package-lock.json').read_bytes()).hexdigest(),
        packages={}, all=audit, production=audit)
    target = tmp_path/'audit/m17_1-dependency-audit.json'
    target.parent.mkdir()
    target.write_text(json.dumps(receipt))
    return tmp_path, target, receipt


def test_complete_same_identity_audit_revalidated_with_actual_node_schema(audit_file):
    directory, _, _ = audit_file
    assert audit_receipt(directory, 'a'*40, '1')['all']['total'] == 0


@pytest.mark.parametrize('field,value', [('head_sha', 'b'*40), ('run_id', 'old'),
    ('attempt', '2'), ('status', 'INCOMPLETE'), ('lock_sha256', 'old'),
    ('node_version', 'v24.0.0')])
def test_old_partial_or_different_lock_evidence_rejected(audit_file, field, value):
    directory, target, receipt = audit_file
    receipt[field] = value
    target.write_text(json.dumps(receipt))
    with pytest.raises(ReceiptError):
        audit_receipt(directory, 'a'*40, '1')


def test_incomplete_sidecar_blocks_even_apparently_complete_inventory(audit_file):
    directory, target, _ = audit_file
    target.with_name('m17_1-dependency-audit-incomplete.json').write_text('{}')
    with pytest.raises(ReceiptError, match='MISSING_OR_INCOMPLETE'):
        audit_receipt(directory, 'a'*40, '1')


def test_tampered_counts_cannot_be_treated_as_zero(audit_file):
    directory, target, receipt = audit_file
    receipt['all']['report']['metadata']['vulnerabilities']['high'] = 1
    target.write_text(json.dumps(receipt))
    with pytest.raises(ReceiptError, match='REPORT_INVALID'):
        audit_receipt(directory, 'a'*40, '1')


def test_absent_lookup_receipt_is_blocking_not_optional(tmp_path):
    with pytest.raises(ReceiptError, match='LOOKUP_ARTIFACT_MISSING'):
        lookup_receipt(tmp_path, 'a'*40, '1')
