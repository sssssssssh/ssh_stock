"""Fail-closed lab contract; no database or business configuration required."""

import ast
import subprocess
from pathlib import Path

import pytest

from scripts import publication_lookup_diagnostic_a422 as lab


def frozen_sql():
    source = subprocess.check_output(['git', 'show', lab.BASELINE+
        ':backend/app/services/data_publication.py'], text=True)
    method = next(n for n in ast.walk(ast.parse(source))
                  if isinstance(n, ast.FunctionDef) and n.name == '_lookup_batch')
    sql = next(n.args[0] for n in ast.walk(method) if isinstance(n, ast.Call)
               and isinstance(n.func, ast.Name) and n.func.id == 'text')
    # Exact f-string SQL, with safe placeholders for the other dynamic fields.
    return eval(compile(ast.Expression(sql), '<frozen-sql>', 'eval'), {}, dict(
        name='stock_opportunity_daily', key_columns='KEYS', selected='COLUMNS',
        keys=('trade_date', 'ts_code'), key_sql='i."trade_date",i."ts_code"', join='PUBLIC_KEYS'))


@pytest.mark.parametrize('variant', lab.VARIANTS)
def test_rewrites_only_candidate_predicate_or_candidate_join(variant):
    sql = frozen_sql()
    rewritten = lab.rewrite(sql, ('trade_date', 'ts_code'), variant)
    assert 'CAST(:keys AS jsonb)' in rewritten
    assert 'CASE WHEN c.publication_id IS NOT NULL THEN NOT c.is_deleted' in rewritten
    assert 'to_jsonb(p) AS _publication_base,now() AS _transaction_now' in rewritten
    assert 'WHERE PUBLIC_KEYS OFFSET 0) p ON true' in rewritten
    assert 'jsonb_populate_record(NULL::public.' in rewritten
    assert rewritten == sql if variant == 'C0' else 'c.row_key=jsonb_build_array' in rewritten
    assert rewritten.count('LEFT JOIN LATERAL') == (1 if variant == 'C2' else 2)


def test_unknown_or_drifted_source_is_not_silently_rewritten():
    with pytest.raises(ValueError, match='UNKNOWN_VARIANT'):
        lab.rewrite(frozen_sql(), (), 'C4')
    with pytest.raises(ValueError, match='BASELINE_SQL_CHANGED'):
        lab.rewrite('SELECT 1', (), 'C1')
    assert lab.candidate_source().count('AND c.row_key=jsonb_build_array({key_sql})') == 1


def test_plan_redaction_retains_nodes_and_observed_counters():
    plan = [{'Plan': {'Actual Rows': 500, 'Shared Hit Blocks': 12,
        'Filter': "keys = '[{\"ts_code\":\"synthetic\"}]'::jsonb"},
        'Query Parameters': 'DO_NOT_WRITE', 'Settings': {'work_mem': '4MB'}}]
    result = lab.redact_plan(plan)
    assert 'DO_NOT_WRITE' not in str(result) and 'synthetic\\' not in str(result)
    assert result[0]['Plan']['Actual Rows'] == 500
    assert result[0]['Settings'] == plan[0]['Settings']


def test_actual_log_parser_discards_raw_log_and_bind_blocks():
    import json

    value = {'Query Text': 'WITH input_keys AS (SELECT $1) SELECT * FROM input_keys',
        'Plan': {'Actual Rows': 500, 'Rows Removed by Filter': 100000},
        'Query Parameters': 'PRIVATE_BIND'}
    result = lab.logged_plans('PRIVATE_LOG\nLOG: plan:\n'+json.dumps(value)+'\nEND')
    assert len(result) == 1 and 'PRIVATE' not in str(result)
    assert result[0]['Plan']['Rows Removed by Filter'] == 100000
    assert lab.logged_plans('{malformed\n{"Plan":{}}') == []


def test_standalone_runtime_disables_dotenv_and_checks_ci_before_setup():
    source = Path(lab.__file__).read_text()
    assert "Settings.model_config['env_file'] = None" in source
    assert source.index('A422_MEASUREMENTS_REQUIRE_ISOLATED_CI_RUNNER') < source.index(
        'proof, c, candidate = setup_runtime()')
    assert source.index("'log_parameter_max_length':'0'") < source.index(
        "'log_min_duration':'0ms'")


def test_backend_cpu_is_container_pid_not_host_pid_and_hwm_is_not_per_query():
    fields = ['0']*24
    fields[11:13] = ['125', '75']
    raw = '42 (postgres) '+' '.join(fields)+'\nVmRSS:\t100 kB\nVmHWM:\t200 kB\n'
    receipt = lab.parse_backend_process(raw, 100)
    assert receipt['cpu_seconds'] == 2
    assert receipt['current_rss_bytes'] == 102400
    assert receipt['process_lifetime_peak_rss_bytes'] == 204800
    assert 'PROCESS_LIFETIME' in receipt['scope']


def comparison():
    return [dict(statistics=regime, table=table, variant=variant,
                 **lab.distribution([10 if variant == 'C0' else 6]*5))
            for regime in ('as_seeded', 'analyzed') for table in lab.TABLES
            for variant in ('C0', 'C1')]


def test_thresholds_require_every_table_both_regimes_and_five_repeats():
    workloads = [dict(statistics=r, variant=v, **lab.distribution([s]*5))
                 for r in ('as_seeded', 'analyzed') for v, s in [('C0', 30), ('C1', 18)]]
    assert lab.performance_decision(comparison(), workloads)['performance_eligible']
    assert not lab.performance_decision(comparison()[:-1], workloads)['performance_eligible']
    rows = comparison()
    rows[1]['median'] = 7.01
    assert not lab.performance_decision(rows, workloads)['performance_eligible']
    with pytest.raises(ValueError, match='FIVE_REPEATS'):
        lab.distribution([1]*4)


def test_whole_workload_uses_per_repeat_sum_not_sum_of_table_medians():
    samples = [dict(statistics='analyzed', variant='C0', table=table, repeat=i,
                    wall_seconds=1+i) for i in range(5) for table in lab.TABLES]
    assert lab.whole_workloads(samples)[0]['samples'] == [3, 6, 9, 12, 15]
    with pytest.raises(ValueError, match='INCOMPLETE'):
        lab.whole_workloads(samples[:-1])
    with pytest.raises(ValueError, match='DUPLICATE'):
        lab.whole_workloads(samples+samples[:1])


def test_fixed_control_tail_keeps_every_sample_without_extending_slow_workload():
    samples = [dict(statistics='analyzed', variant='C0', table=table, repeat=i,
                    wall_seconds=1+i) for table in lab.TABLES
               for i in range(lab.CONTROL_REPEATS if table == lab.TABLES[2] else 5)]
    summary = lab.summarize(samples)
    assert len(next(r for r in summary if r['table'] == lab.TABLES[2])['samples']) == 100
    assert lab.whole_workloads(samples)[0]['samples'] == [3, 6, 9, 12, 15]
    with pytest.raises(ValueError, match='DUPLICATE'):
        lab.whole_workloads(samples+samples[-1:])


def test_gc_is_observed_not_disabled_or_forced_and_callback_is_restored():
    import gc

    original = list(gc.callbacks)
    metrics = dict(gc_seconds=0.0, gc_count=0)
    with lab.observe_gc(metrics):
        gc.collect()
    assert metrics['gc_count'] >= 1 and metrics['gc_seconds'] >= 0
    assert gc.callbacks == original


def test_fast_control_and_tail_regression_block_eligibility():
    rows = comparison()
    rows[5].update(median=11.1, p95=11.1)
    decision = lab.performance_decision(rows)
    assert not decision['performance_eligible']
    assert {'CONTROL_REGRESSION', 'P95_REGRESSION'} <= set(decision['reasons'])


def test_no_production_path_or_formal_capacity_replacement():
    source = Path(lab.__file__).read_text()
    assert 'A422_MEASUREMENTS_REQUIRE_ISOLATED_CI_RUNNER' in source
    assert 'formal_capacity_complete=False' in source
    assert 'public_total_rows=603040' in source
    assert 'c.seed(factory, 5000, days)' in source
    assert 'else 5' in source and 'CONTROL_REPEATS = 100' in source
    assert "statement_timeout='300s'" in source
    assert 'ANALYZE, BUFFERS, VERBOSE, SETTINGS' in source
    assert 'SET enable_seqscan' not in source


def test_a41_startup_changes_only_socket_readiness_not_identity_resources_or_scope():
    import yaml

    filename = '.github/workflows/ab-read-a4-baseline.yml'
    old = yaml.safe_load(subprocess.check_output([
        'git', 'show', lab.BASELINE+':'+filename], text=True))
    current = yaml.safe_load(Path(filename).read_text())
    name = 'Dedicated physical PG17, fixed resources, I/O and statement evidence'
    before = next(s for s in old['jobs']['isolated-baseline']['steps'] if s.get('name') == name)
    after = next(s for s in current['jobs']['isolated-baseline']['steps'] if s.get('name') == name)
    expected = before['run'].replace('pg_isready -U synthetic -d a4_test',
        'pg_isready -h 127.0.0.1 -U synthetic -d a4_test').replace(
        'docker exec a4-isolated-pg17 psql -U synthetic',
        'docker exec -e PGPASSWORD=synthetic a4-isolated-pg17 psql -h 127.0.0.1 -U synthetic')
    assert after == {**before, 'run': expected}
