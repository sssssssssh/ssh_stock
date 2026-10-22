"""Statistics/plan identity for a newly owned synthetic PG17, never app code."""

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from time import sleep

from scripts.a42_artifacts import failure, header, isolation, model_hash, now
from scripts.a42_receipt_contract import require
from scripts.a4231_attribution_metrics import NaturalGC, distribution
from scripts.a4231_attribution_metrics import schedule as old_schedule
from scripts.publication_lookup_tail_attribution_a4231 import describe
from scripts.publication_lookup_tail_review_a423 import C0_SOURCE, C1_SOURCE

ROOT = Path(__file__).resolve().parents[1]
BASELINE = '29ee84548a4254c646b30305ed620ae0fdd2f49c'
PREREGISTERED = 'da97cbe63b57499c4b3705ba671c179e4440fd0e'
PROTOCOL = 'docs/acceptance/v14_a4_2_3_2_protocol.md'
PROTOCOL_HASH = '047db54f9ac95b1729afa30e221f0fbd7013013db5fa4bf6f6302c4645affb39'
MODEL_HASH = 'f8bb5cf42d3f38757eda46ff149239789638f3aabe14434cda6ed7fe9daee20f'
VERSION = 'A4232_STATS_STABLE_V2_TELEMETRY_INTERVENTION'
CONTROL = 'stock_trade_status_daily'
TABLES = ('stock_opportunity_daily', 'signal_forward_eval', CONTROL, 'data_publication_row')
PUBLIC = dict(stock_trade_status_daily=100000, stock_factor_daily=100000, market_daily=20,
    sector_factor_daily=1000, theme_factor_daily=2000, stock_state_daily=100000,
    stock_opportunity_daily=100000, strategy_signal=100000, signal_forward_eval=100000,
    data_quality_daily=20)
CANDIDATE = {k:(50000 if k in TABLES[:2] else v) for k,v in PUBLIC.items()
             if k != 'data_quality_daily'}
TEMPLATE_HASHES = dict(
    C0='1b19ae3a8b492895c0b15c0f05adcff034b673a8fb4407bc4b4cdbec7635559a',
    C1='b792c8641cc98c1cba20dc9537ee5db911d804511787be7fe19cdeb042562ecc')
SAFE_PLAN_FIELDS = ('Node Type', 'Strategy', 'Partial Mode', 'Parallel Aware', 'Join Type',
    'Scan Direction', 'Relation Name', 'Index Name', 'Alias', 'Parent Relationship',
    'Subplan Name', 'CTE Name', 'Function Name')


def schedule(block):
    require(isinstance(block,int) and not isinstance(block,bool) and block in range(4),
            'A4232_UNREGISTERED_BLOCK')
    return old_schedule(block % 2)


def guard():
    require(os.environ.get('GITHUB_ACTIONS') == 'true'
            and os.environ.get('GITHUB_RUN_ATTEMPT') == '1', 'A4232_ONE_CI_ATTEMPT_ONLY')
    subject = subprocess.check_output(['git','log','-1','--format=%s'], text=True)
    require('[a4232-statstable-once]' in subject, 'A4232_NOT_SINGLE_DISPATCH_COMMIT')
    raw = (ROOT/PROTOCOL).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == PROTOCOL_HASH
            and raw == subprocess.check_output(['git','show',PREREGISTERED+':'+PROTOCOL]),
            'A4232_PROTOCOL_NOT_PREREGISTERED')
    require(subprocess.run(['git','merge-base','--is-ancestor',PREREGISTERED,'HEAD'])
            .returncode == 0, 'A4232_PREREGISTRATION_NOT_ANCESTOR')
    require(subprocess.run(['git','diff','--quiet',BASELINE,'--','backend','config','migrations',
        'frontend','scripts/publication_lookup_diagnostic_a422.py',
        'scripts/publication_lookup_tail_attribution_a4231.py','scripts/a4231_attribution_metrics.py',
        'docs/acceptance/evidence/a4231_historical_replay.json',
        'docs/acceptance/evidence/a4231_attribution_review.json']).returncode == 0,
        'A4232_FROZEN_TREE_CHANGED')
    require(hashlib.sha256((ROOT/'backend/app/services/data_publication.py').read_bytes())
            .hexdigest() == C0_SOURCE and model_hash() == MODEL_HASH, 'A4232_C0_OR_MODEL_CHANGED')
    receipt = header('a4232-statistics-tail-diagnostic')
    require(not receipt['working_tree_dirty'], 'A4232_DIRTY_TREE')
    return dict(**receipt, review_baseline_sha=BASELINE, preregistered_sha=PREREGISTERED,
        protocol_sha256=PROTOCOL_HASH, measurement_version=VERSION, evidence_kind='DIAGNOSTIC_ONLY',
        status='INCOMPLETE', samples=[], capacity_ready=False, performance_eligible=False,
        production_matches_candidate=False, unique_repair_candidate=None,
        production_source_sha256=C0_SOURCE, proposed_source_sha256=C1_SOURCE,
        p2='NOT_AUTHORIZED', p3='NOT_AUTHORIZED', started_at=now())


def owned(db, expected_database):
    """Only called with the database returned by our isolated context, before DDL."""
    from sqlalchemy import text

    proof = isolation()  # Explicit marked target, before any statistics-changing statement.
    actual = db.scalar(text('SELECT current_database()'))
    require(re.fullmatch(r'v14_[0-9a-f]{32}_test', expected_database or '')
            and actual == expected_database, 'A4232_NOT_NEW_OWNED_DATABASE')
    require(str(db.scalar(text('SELECT system_identifier FROM pg_control_system()')))
            == proof['physical_system_identifier']
            and db.scalar(text("SELECT current_setting('v14.test_instance')"))
            == proof['database_instance'], 'A4232_DDL_PHYSICAL_TARGET_MISMATCH')
    return proof


def count_snapshot(db):
    from sqlalchemy import text

    public = {name:db.scalar(text(f'SELECT count(*) FROM public."{name}"')) for name in PUBLIC}
    candidate = dict(db.execute(text('SELECT table_name,count(*) FROM public.data_publication_row '
                                     'GROUP BY table_name')).all())
    return dict(public=public, candidate=candidate)


def assert_counts(value):
    require(value == dict(public=PUBLIC,candidate=CANDIDATE),'A4232_COUNT_DRIFT')


def statistics_snapshot(db):
    from sqlalchemy import text

    db.execute(text('SELECT pg_stat_clear_snapshot()'))
    base = describe(db)
    rows = [dict(r) for r in db.execute(text("""SELECT c.relname,c.reltuples,c.relpages,
        c.reloptions,s.last_analyze,s.last_autoanalyze,
        (SELECT count(*) FROM pg_statistic t WHERE t.starelid=c.oid) AS statistic_count,
        (SELECT encode(sha256(convert_to(coalesce(jsonb_agg(to_jsonb(t)
            ORDER BY t.staattnum,t.stainherit)::text,'[]'),'UTF8')),'hex')
         FROM pg_statistic t WHERE t.starelid=c.oid) AS statistic_sha256
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        LEFT JOIN pg_stat_user_tables s ON s.relid=c.oid
        WHERE n.nspname='public' AND c.relname IN
        ('stock_opportunity_daily','signal_forward_eval','stock_trade_status_daily',
         'data_publication_row') ORDER BY c.relname""")).mappings()]
    active = db.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database()"
                            " AND backend_type='autovacuum worker'"))
    settings = dict(db.execute(text("SELECT name,setting FROM pg_settings WHERE name IN "
        "('plan_cache_mode','autovacuum','autovacuum_analyze_threshold',"
        "'autovacuum_analyze_scale_factor') ORDER BY name")).all())
    return dict(observed_at=now(), relations=rows,
        index_sha256=base['index_definition_sha256'], settings=base['environment']['settings'],
        planner_settings=settings, active_autovacuum_workers=active)


def stable_identity(value):
    require(isinstance(value.get('relations'),list)
            and {r.get('relname') for r in value['relations']} == set(TABLES)
            and len(value['relations']) == 4 and all(
                set(('reltuples','relpages','last_analyze','last_autoanalyze','reloptions',
                     'statistic_count','statistic_sha256')) <= set(r)
                and r['last_analyze'] is not None and r['statistic_count'] > 0
                and re.fullmatch(r'[0-9a-f]{64}',r['statistic_sha256'])
                for r in value['relations']) and set(('index_sha256','settings',
                    'planner_settings','active_autovacuum_workers')) <= set(value),
            'A4232_STATISTICS_MISSING')
    return json.loads(json.dumps({k:v for k,v in value.items() if k != 'observed_at'}, default=str))


def assert_stable(expected, actual):
    left, right = stable_identity(expected), stable_identity(actual)
    if left != right or actual['active_autovacuum_workers']:
        error = ValueError('A4232_ENVIRONMENT_DRIFT')
        error.a4232_drift = dict(before=expected, after=actual)
        raise error


def stabilize(db, expected_database, observe):
    """Default ANALYZE, at most one preregistered pre-measurement fallback."""
    from sqlalchemy import text

    attempts = []
    for fallback in (False, True):
        owned(db, expected_database)
        if fallback:
            for name in TABLES:
                db.execute(text(f'ALTER TABLE public."{name}" SET (autovacuum_enabled=false)'))
            db.commit()
        for name in TABLES:
            db.execute(text(f'ANALYZE public."{name}"'))
        db.execute(text('SELECT pg_stat_force_next_flush()'))
        db.commit()
        samples = []
        for index in range(4):
            if index:
                sleep(2)
            sample = observe()
            stable_identity(sample)  # Missing fields are not an excuse to tune/fallback.
            samples.append(sample)
        valid = all(stable_identity(s) == stable_identity(samples[0])
                    and s['active_autovacuum_workers'] == 0 for s in samples)
        attempts.append(dict(table_autovacuum_disabled=fallback, snapshots=samples,
                             valid=valid, measured_samples=0))
        if valid:
            return dict(status='STABLE', identity=samples[-1], attempts=attempts,
                environment_kind='CONTROLLED_SYNTHETIC_TABLE_AUTOVACUUM_OFF' if fallback
                                 else 'MANUAL_ANALYZE_DEFAULT_TABLE_OPTIONS')
    error = ValueError('A4232_ENVIRONMENT_DRIFT')
    error.a4232_drift = dict(preflight_attempts=attempts)
    raise error


def plan_structure(node):
    require(isinstance(node, dict) and isinstance(node.get('Node Type'), str),
            'A4232_PLAN_MISSING')
    selected = {}
    for key in SAFE_PLAN_FIELDS:
        if key not in node:
            continue
        value = node[key]
        require(isinstance(value,bool) or isinstance(value,str)
                and re.fullmatch(r'[A-Za-z0-9_ .-]{1,100}',value), 'A4232_UNSAFE_PLAN_LABEL')
        selected[key] = value
    require(isinstance(node.get('Plans',[]), list), 'A4232_PLAN_CHILDREN_MISSING')
    if 'Plans' in node:
        selected['Plans'] = [plan_structure(child) for child in node['Plans']]
    return selected


class PassiveGC(NaturalGC):
    def callback(self, phase, info):
        try:
            super().callback(phase, info)
        except BaseException as error:
            self.callback_error = type(error).__name__
            self.callback_failure = failure(error)

    def __exit__(self, *error):
        terminal = None
        try:
            super().__exit__(*error)
        except BaseException as caught:
            terminal = caught
        if getattr(self,'callback_error',None):
            caught = ValueError('A4232_GC_CALLBACK_FAILED')
            caught.a4232_first_failure = self.callback_failure
            caught.a4232_cleanup_failures = [failure(terminal)] if terminal else []
            raise caught from None
        if terminal:
            raise terminal


def summarize(samples):
    return [dict(variant=v, observer_mode=m, **distribution([
        s['wall_seconds'] for s in samples if s['variant'] == v and s['observer_mode'] == m]))
        for v in ('C0','C1') for m in ('full','minimal')]


def causal_checks(samples):
    import statistics

    checks = []
    for block in range(4):
        for variant in ('C0','C1'):
            groups = {m:[s for s in samples if (s['block'],s['variant'],s['observer_mode'])
                         == (block,variant,m)] for m in ('full','minimal')}
            require(all(len(s) == 8 for s in groups.values()), 'A4232_BLOCK_INCOMPLETE')
            p95 = {m:distribution([s['wall_seconds'] for s in rows])['p95']
                   for m,rows in groups.items()}
            burden = {m:sum(e['seconds'] for s in rows for e in s['gc_events']
                       if e['generation'] == 2 and e['fully_inside_wall'])
                      for m,rows in groups.items()}
            allocated = {m:statistics.median(s['memory_after_enter']['allocated_blocks']
                - s['memory_before_enter']['allocated_blocks'] for s in rows)
                for m,rows in groups.items()}
            long = sum(e['generation'] == 2 and e['fully_inside_wall'] and e['seconds'] >= .05
                       for s in groups['full'] for e in s['gc_events'])
            checks.append(dict(block=block,variant=variant,p95=p95,generation2_wall=burden,
                observer_enter_blocks=allocated,full_long_gen2=long,
                met=p95['full']-p95['minimal'] >= .04 and long > 0
                    and burden['full'] > burden['minimal']
                    and allocated['full'] > allocated['minimal']))
    return dict(checks=checks, all_met=all(c['met'] for c in checks),
                conclusion='REQUIRES_COUNTEREXAMPLE_REVIEW_NOT_AUTOMATIC_CAUSALITY')
