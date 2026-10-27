"""Exact frozen boundary and contracts-only A4234 blocked-stage CI evidence."""

import ast
import json
import subprocess
from pathlib import Path

import yaml

from scripts import a4234_calibration_contract as contract

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ('ci.yml', 'ab-read-a4-baseline.yml', 'ab-read-a4-2.yml',
             'publication-v13.yml', 'a4232-statistics-tail-diagnostic.yml')

# A42341 explicitly authorized ONLY these three additions. Old assertions below remain.
A42341_ADDITIONS = [
    dict(name='A42341 proposal and pure mock contracts only',
        env={'A42341_ARTIFACT_ROOT': '.codex_tmp/a42341'},
        run='python -m pytest -p scripts.a42331_pytest_safety --tb=no --show-capture=no -rN '
            'tests/unit/test_a42341_prepared_capability.py '
            'tests/unit/test_a42341_runner_review.py tests/unit/test_a42341_environment_guard.py '
            '--junitxml=.codex_tmp/a42341-internal/tests.xml'),
    dict(name='A42341 sanitized unit counts (never calibration)', **{'if': 'always()'},
        run='python -m scripts.a42341_calibration_guard '
            '--tests .codex_tmp/a42341-internal/tests.xml --output .codex_tmp/a42341/tests.json'),
    dict(uses='actions/upload-artifact@v4', **{'if': 'always()', 'with': {
        'name': 'a42341-contract-${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}',
        'path': '.codex_tmp/a42341', 'include-hidden-files': True, 'if-no-files-found': 'error'}}),
]


def frozen(path):
    return subprocess.check_output(['git', 'show', contract.BASELINE + ':' + path], cwd=ROOT)


def test_all_production_old_scripts_evidence_gates_and_one_shots_frozen():
    from scripts.business_source_contract import historical_bytes, verify

    for prefix in ('backend', 'config', 'migrations', 'frontend', 'docs/acceptance/evidence',
                   '.github/actions'):
        names = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', contract.BASELINE,
                                         prefix], cwd=ROOT, text=True).splitlines()
        assert names
        for name in names:
            assert historical_bytes(name) == frozen(name), name
    for name in WORKFLOWS:
        path = '.github/workflows/' + name
        assert historical_bytes(path) == frozen(path)
    for name in subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', contract.BASELINE,
                                         'scripts'], cwd=ROOT, text=True).splitlines():
        assert historical_bytes(name) == frozen(name), name
    for name in ('a4233_1_ci_remediation.md', 'v14_a4_2_3_1_attribution_protocol.md',
                 'v14_a4_2_3_2_protocol.md'):
        path = 'docs/acceptance/' + name
        assert historical_bytes(path) == frozen(path)

    assert len(verify()) == 64


def test_only_two_offline_preparation_modules_exist_no_sampler_or_reviewer():
    assert {str(p.relative_to(ROOT)) for p in (ROOT / 'scripts').glob('a4234_*.py')} == (
        set(contract.SOURCES))
    for source in contract.SOURCES:
        tree = ast.parse((ROOT / source).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports = [v.name for v in node.names]
            elif isinstance(node, ast.ImportFrom):
                imports = [node.module or '']
            else:
                imports = []
            assert not any(n.startswith(('app', 'psycopg', 'sqlalchemy', 'gc', 'threading',
                                          'multiprocessing', 'dotenv')) for n in imports)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in ('connect', 'cursor', 'execute', 'collect',
                    'disable', 'set_threshold', 'Popen', 'spawn', 'Thread')


def test_additive_low_cost_workflow_keeps_old_steps_and_uploads_and_budgets():
    path = '.github/workflows/a4233-observer-contracts.yml'
    old, current = yaml.safe_load(frozen(path)), yaml.safe_load((ROOT / path).read_text())
    assert set(current['on']) == {'push', 'pull_request'}
    assert current['permissions'] == old['permissions'] == {'contents': 'read'}
    assert current['concurrency'] == old['concurrency']
    assert set(current['jobs']) == {'contracts'}
    before, after = old['jobs']['contracts'], current['jobs']['contracts']
    assert after['timeout-minutes'] == before['timeout-minutes'] == 12
    assert all(after['steps'].count(s) == 1 for s in A42341_ADDITIONS)
    projected_steps = [s for s in after['steps'] if s not in A42341_ADDITIONS]
    original_steps = iter(projected_steps)
    for step in before['steps']:
        assert any(s == step for s in original_steps), step
    additions = [s for s in projected_steps if s not in before['steps']]
    assert len(additions) == 3
    run = next(s for s in additions if 'pytest' in s.get('run', ''))
    assert 'test_a4234_calibration_guard.py' in run['run']
    assert 'test_a4234_ci_governance.py' in run['run']
    assert '-p scripts.a42331_pytest_safety' in run['run']
    assert '--tb=no --show-capture=no -rN' in run['run']
    receipt = next(s for s in additions
                   if '-m scripts.a4234_calibration_guard' in s.get('run', ''))
    assert receipt['if'] == 'always()' and '--tests' in receipt['run']
    upload = next(s for s in additions if 'upload-artifact' in s.get('uses', ''))
    assert upload['if'] == 'always()'
    assert upload['with']['name'].startswith('a4234-contract-${{ github.sha }}-')
    assert 'github.run_id' in upload['with']['name']
    assert 'github.run_attempt' in upload['with']['name']
    assert upload['with']['path'] == '.codex_tmp/a4234'
    assert upload['with']['if-no-files-found'] == 'error'
    for event in current['on'].values():
        assert 'scripts/a4234_*.py' in event['paths']
        assert 'tests/**/test_a4234*.py' in event['paths']
    for forbidden in ('workflow_dispatch', 'schedule', '--execute', '--approve',
                      'seed_candidates', '--level', '--scope'):
        assert forbidden not in json.dumps(current)


def test_historical_acceptance_and_current_blockage_are_not_mixed():
    final = (ROOT / 'docs/acceptance/a4233_1_final_review.md').read_text()
    ready = (ROOT / 'docs/acceptance/a4234_calibration_readiness.md').read_text()
    assert 'CODE_ACCEPTED / PERFORMANCE_NOT_AUTHORIZED' in final
    assert '39999398934' in final and '39999398924' in final and 'OFFLINE_REVERIFIED' in final
    assert contract.BLOCKED in ready and 'W03' in ready and 'W05' in ready
    assert 'NOT_RUN_NOT_AUTHORIZED' in ready and 'AT06' in ready and 'AT18' in ready
    assert '全批共8次' in ready and 'METRIC_UNAVAILABLE' in ready
