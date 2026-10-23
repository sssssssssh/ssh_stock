"""Synthetic injection only; no database, performance workload, or Settings."""

import json
import signal
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import a4233_background_observer as ob
from scripts import a4233_observation_review as off
from scripts.a4233_observation_contract import (
    DRAFT,
    TABLES,
    Activity,
    Analyze,
    Fault,
    Identity,
    Receipt,
    Relation,
    Tick,
    Vacuum,
    correlate,
    digest,
    seal,
    validate,
    validate_ticks,
    write_new,
)

ROOT = Path(__file__).resolve().parents[2]
MARKER,SYSTEM = 'b3be8f37-21a9-46d6-ab46-e8320ad29ad8','123456789'


def identity():
    return Identity(head_sha='a'*40,run_id='123',attempt=1,
        instance_identity_sha256=digest([MARKER,SYSTEM]),source_sha256='b'*64,
        protocol_sha256='c'*64)


def relations():
    return [Relation(relid=i+10,table=t,kind='TABLE') for i,t in enumerate(TABLES)]


def stats():
    return [dict(relid=r.relid,schemaname='public',relname=r.table,last_autovacuum=None,
        last_autoanalyze=None,autovacuum_count=0,autoanalyze_count=0,n_live_tup=0,
        n_dead_tup=0,n_mod_since_analyze=0,n_ins_since_vacuum=0) for r in relations()]


def tick(seq=0):
    start = 1_000_000_000+seq*250_000_000
    u = datetime(2026,10,23,tzinfo=UTC)+timedelta(milliseconds=seq*250)
    value = Tick(sequence=seq,tick_started_monotonic_ns=start,
        tick_finished_monotonic_ns=start+10_000_000,tick_started_utc=u.isoformat(),
        tick_finished_utc=(u+timedelta(milliseconds=10)).isoformat(),db_clock_timestamp=u.isoformat(),
        db_query_wall_ms=5.0,tick_total_wall_ms=10.0,cpu_seconds=.001,rss_bytes=1000,
        windows=[dict(view=v,start_ns=start+i*1_000_000,end_ns=start+(i+1)*1_000_000,
            wall_ms=1.0) for i,v in enumerate(('clock','activity','vacuum','analyze','tables'))],
        activity=[],vacuum=[],analyze=[],tables=stats(),events=[])
    value.events = correlate(value,7,relations())
    return value


def receipt():
    r = Receipt(**identity().model_dump(),datid=7,relations=relations(),planned_ticks=2,
        ticks=[tick(),tick(1)],physical_verified=True,restricted_readonly_verified=True,
        cleanup_complete=True,status='COMPLETE_CONTRACT',content_sha256='0'*64)
    return seal(r.model_dump())


class Cursor:
    def __init__(self, rows):
        self.rows = rows
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def fetchmany(self, count):
        return self.rows[:count]


class Database:
    autocommit = True
    def __init__(self):
        self.calls,self.closed = [],False
        self.values = dict(identity=[dict(version='170011',marker=MARKER,system_id=SYSTEM,datid=7)],
            preflight=[dict(readonly='on',default_readonly='on',timeout='100ms',timezone='UTC',
                track_activities='on',track_counts='on',rolsuper=False,rolcreaterole=False,
                rolcreatedb=False,rolreplication=False,rolbypassrls=False,stats_visible=True,
                dangerous_role=False,database_create=False,schema_create=False,table_access=False)],
            columns=[dict(relname=v,attname=k,type=typ)
                    for v,fields in ob.FIELDS.items() for k,typ in fields.items()],
            relations=[r.model_dump() for r in relations()],activity=[],vacuum=[],analyze=[],
            tables=stats())
    def execute(self, sql, prepare):
        assert prepare is False
        name = next(k for k,v in ob.SQL.items() if v == sql)
        self.calls.append(name)
        rows = ([dict(db_clock_timestamp=datetime.now(UTC))] if name == 'clock'
                else self.values[name])
        if isinstance(rows,BaseException):
            raise rows
        return Cursor(rows)
    def close(self):
        self.closed = True


def observer(db=None):
    db = db or Database()
    return ob.Observer(lambda:db,marker=MARKER,system_id=SYSTEM,identity=identity(),planned_ticks=2)


def active(pid=55, **overrides):
    return Activity(**(dict(datid=7,pid=pid,backend_type='autovacuum worker',
        backend_start='2026-10-23T00:00:00+00:00',query_start='2026-10-23T00:01:00+00:00',
        state='active',wait_event_type=None,wait_event=None)|overrides))


def vacuum(**overrides):
    return Vacuum(**(dict(pid=55,datid=7,relid=10,phase='scanning heap',heap_blks_total=10,
        heap_blks_scanned=1,heap_blks_vacuumed=0,index_vacuum_count=0)|overrides))


def analyze(**overrides):
    return Analyze(**(dict(pid=55,datid=7,relid=10,phase='acquiring sample rows',
        sample_blks_total=10,sample_blks_scanned=1,ext_stats_total=0,ext_stats_computed=0,
        child_tables_total=0,child_tables_done=0,current_child_table_relid=0)|overrides))


@pytest.mark.parametrize('version',['160009','180000'])
def test_other_pg_major_fails_before_any_observation(version):
    db = Database()
    db.values['identity'][0]['version'] = version
    o = observer(db)
    o.worker()
    assert o.first_failure_code == 'A4233_PG17_REQUIRED'
    assert db.calls == ['identity'] and db.closed


@pytest.mark.parametrize('field,value',[('marker','wrong'),('system_id','999')])
def test_physical_mismatch_zero_subsequent_operations(field,value):
    db = Database()
    db.values['identity'][0][field] = value
    o = observer(db)
    o.worker()
    assert o.first_failure_code == 'A4233_PHYSICAL_MISMATCH'
    assert db.calls == ['identity'] and db.closed
    assert o.receipt()['status'] == 'INCOMPLETE_OBSERVABILITY'


@pytest.mark.parametrize('field,value,code',[
    ('stats_visible',False,'READ_ALL_STATS_REQUIRED'),('rolsuper',True,'RESTRICTED_ROLE_REQUIRED'),
    ('rolcreatedb',True,'RESTRICTED_ROLE_REQUIRED'),('rolcreaterole',True,'RESTRICTED_ROLE_REQUIRED'),
    ('rolbypassrls',True,'RESTRICTED_ROLE_REQUIRED'),('dangerous_role',True,'RESTRICTED_ROLE_REQUIRED'),
    ('readonly','off','READONLY_SETTINGS_REQUIRED'),('default_readonly','off','READONLY_SETTINGS_REQUIRED'),
    ('timeout','0','READONLY_SETTINGS_REQUIRED'),('timezone','Asia/Shanghai','READONLY_SETTINGS_REQUIRED'),
    ('track_counts','off','READONLY_SETTINGS_REQUIRED'),('track_activities','off','READONLY_SETTINGS_REQUIRED')])
def test_restricted_permissions_and_session_preflight(field,value,code):
    db = Database()
    db.values['preflight'][0][field] = value
    o = observer(db)
    o.worker()
    assert o.first_failure_code == 'A4233_'+code
    assert db.calls == ['identity','preflight']


@pytest.mark.parametrize('view',list(ob.FIELDS))
def test_missing_required_field_or_view_not_silently_omitted(view):
    db = Database()
    db.values['columns'] = [r for r in db.values['columns'] if r['relname'] != view]
    o = observer(db)
    o.worker()
    assert o.first_failure_code == 'A4233_PG17_FIELD_MISSING'
    assert 'relations' not in db.calls


def test_read_only_fixed_sql_allowlist_and_bounded_fetch():
    import re

    for sql in ob.SQL.values():
        assert sql.lstrip().startswith(('SELECT','WITH'))
        # Privilege-name string literals include INSERT/MAINTAIN, not commands.
        executable = re.sub(r"'(?:[^']|'')*'", "''", sql)
        assert not re.search(r'\b(query|client_addr|usename|grant|alter|vacuum|analyze|insert|'
                             r'delete|update|drop|truncate|pg_cancel_backend|set_config)\b',
                             executable,re.I)
        assert not re.search(r'SELECT\s+\*',sql,re.I)
    db = Database()
    db.values['activity'] = [{}]*129
    with pytest.raises(Fault,match='ROW_BUFFER_FULL'):
        observer(db).read(db,'activity')
    with pytest.raises(Fault,match='SQL_NOT_ALLOWED'):
        observer(db).read(db,'secret')


@pytest.mark.parametrize('url',[
    'postgresql://x:x@external.invalid:5432/v14_x_test',
    'postgresql://x:x@127.0.0.1:5432/business',
    'postgresql://x:x@127.0.0.1:5432/v14_test?options=secret',
    'sqlite:///v14_test','postgresql://x:x@127.0.0.1/v14_test'])
def test_external_targets_rejected_without_connecting(url):
    with pytest.raises(Fault,match='EXPLICIT_SYNTHETIC_TARGET_REQUIRED'):
        ob.connection_factory(url,MARKER,SYSTEM)


@pytest.mark.parametrize('kind,expected',[(vacuum,'VACUUM_OBSERVED'),(analyze,'ANALYZE_OBSERVED')])
def test_progress_pid_datid_relid_join(kind,expected):
    t = tick()
    t.activity = [active()]
    if kind == vacuum:
        t.vacuum = [kind()]
    else:
        t.analyze = [kind()]
    e = correlate(t,7,relations())[0]
    assert e.code == expected and e.relation.table == TABLES[0]
    assert e.pid == 55 and e.backend_start == active().backend_start
    assert e.window_start_ns == t.tick_started_monotonic_ns


@pytest.mark.parametrize('change',[dict(relid=99),dict(datid=8)])
def test_unknown_relation_and_other_database_not_mapped(change):
    t = tick()
    t.activity = [active(datid=change.get('datid',7))]
    t.vacuum = [vacuum(**change)]
    e = correlate(t,7,relations())[0]
    assert e.code == 'UNKNOWN_RELATION'
    assert e.relation is None


def test_approved_index_toast_mapping_and_unknown_child():
    t = tick()
    t.activity,t.vacuum = [active()],[vacuum(relid=88)]
    mapping = relations()+[Relation(relid=88,table=TABLES[0],kind='TOAST_INDEX')]
    assert correlate(t,7,mapping)[0].relation.kind == 'TOAST_INDEX'
    t.vacuum,t.analyze = [],[analyze(current_child_table_relid=99)]
    assert correlate(t,7,mapping)[0].code == 'UNKNOWN_RELATION'


@pytest.mark.parametrize('case',['missing_activity','idle','both_progress','pid_reused','datid_mismatch'])
def test_cross_view_races_are_ambiguous(case):
    t,p = tick(1),tick()
    t.activity,t.vacuum = [active()],[vacuum()]
    if case == 'missing_activity':
        t.activity = []
    elif case == 'idle':
        t.activity = [active(state='idle')]
    elif case == 'both_progress':
        t.analyze = [analyze()]
    elif case == 'datid_mismatch':
        t.activity = [active(datid=8)]
    else:
        p.activity = [active(backend_start='2026-10-22T00:00:00+00:00')]
    result = correlate(t,7,relations(),p)
    assert all(e.code == 'AMBIGUOUS_EVENT' for e in result)
    if case == 'idle':
        assert result[0].active_query_start_candidate is None


def test_worker_count_only_cannot_be_labeled_analyze():
    t = tick()
    t.activity = [active(state='idle')]
    e = correlate(t,7,relations())[0]
    assert e.code == 'ENVIRONMENT_ACTIVITY_ONLY'
    assert e.relid is e.relation is e.active_query_start_candidate is None


def test_cumulative_stats_only_possible_delayed_bracket():
    p,t = tick(),tick(1)
    t.tables[0].autoanalyze_count += 1
    t.tables[0].last_autoanalyze = '2026-10-22T00:00:00+00:00'  # delayed earlier event
    e = correlate(t,7,relations(),p)[0]
    assert e.code == 'POSSIBLE_IN_BRACKET' and e.pid is None
    assert e.active_query_start_candidate is None
    assert e.window_start_ns == p.tick_started_monotonic_ns


def test_no_observed_progress_never_proves_absence():
    r = off.review(receipt(),identity())
    assert r['observed_event_codes'] == ['NOT_OBSERVED']
    assert r['absence_proven'] is False and r['causality'] == 'NOT_EVALUATED'


@pytest.mark.parametrize('field,value',[("backend_start",None),("state","secret-token!"),
                                       ('pid',None),('unexpected','secret')])
def test_null_or_unapproved_fields_fail_without_exporting_values(field,value):
    raw = active().model_dump() | {field:value}
    with pytest.raises(Fault,match='REQUIRED_FIELD_INVALID') as error:
        ob.normalized([raw],Activity)
    assert 'secret' not in str(error.value)


@pytest.mark.parametrize('mutation,code',[
    (lambda t:setattr(t,'sequence',2),'TICK_MISSING'),
    (lambda t:setattr(t,'tick_finished_monotonic_ns',0),'CLOCK_BACKWARDS'),
    (lambda t:setattr(t,'tick_finished_utc','2026-10-23T00:10:00+00:00'),'CLOCK_DRIFT'),
    (lambda t:setattr(t,'db_clock_timestamp','2026-10-23T00:10:00+00:00'),'DB_CLOCK_DRIFT'),
    (lambda t:setattr(t,'db_query_wall_ms',55.0),'SQL_WALL_MISMATCH'),
    (lambda t:setattr(t,'tables',t.tables[:3]),'TABLE_STATS_MISSING')])
def test_tick_time_and_completeness_fail_closed(mutation,code):
    t = tick()
    mutation(t)
    with pytest.raises(Fault,match=code):
        validate_ticks([t],7,relations())


def test_gap_and_sql_budget_not_relaxed():
    with pytest.raises(Fault,match='TICK_GAP'):
        validate_ticks([tick(),tick(3).model_copy(update={'sequence':1})],7,relations())
    t = tick()
    t.windows[0].end_ns += 100_000_000
    t.windows[0].wall_ms += 100.0
    t.tick_finished_monotonic_ns += 110_000_000
    t.tick_total_wall_ms += 110.0
    t.tick_finished_utc = '2026-10-23T00:00:00.120000+00:00'
    with pytest.raises(Fault,match='SQL_BUDGET'):
        validate_ticks([t],7,relations())


def test_actual_owned_thread_micro_lifecycle_no_lookup():
    db = Database()
    o = observer(db)
    r = o.run_micro()
    assert validate(r,identity()).status == 'COMPLETE_CONTRACT'
    assert db.closed and not o.thread.is_alive() and len(o.ticks) == 2


def test_thread_exception_keeps_sanitized_first_and_close_failure():
    db = Database()
    db.values['activity'] = RuntimeError('postgresql://secret token SQL')
    def broken_close():
        raise RuntimeError('secret cleanup')
    db.close = broken_close
    r = observer(db).run_micro()
    assert r['first_failure_code'] == 'A4233_OBSERVER_EXCEPTION'
    assert r['cleanup_failure_codes'] == ['A4233_CONNECTION_CLOSE_FAILED']
    assert 'secret' not in json.dumps(r) and r['status'] == 'INCOMPLETE_OBSERVABILITY'
    assert r['failed_tick'] is not None


def test_buffer_full_does_not_overwrite_prior_ticks():
    db,o = Database(),observer()
    o.preflight(db)
    o.capacity = 0
    with pytest.raises(Fault,match='TICK_BUFFER_FULL'):
        o.tick(db)
    assert o.ticks == [] and o.failed_tick['observations']['tables']


def test_unknown_activity_stops_without_selecting_out_sample():
    db = Database()
    db.values['activity'] = [active().model_dump()]
    o = observer(db)
    r = o.run_micro()
    assert r['first_failure_code'] == 'A4233_ACTIVITY_STOP'
    assert len(r['ticks']) == 1 and len(r['ticks'][0]['events']) == 1


def test_join_timeout_and_primary_failure_both_preserved():
    o = observer()
    o.thread = SimpleNamespace(join=lambda timeout:None,is_alive=lambda:True)
    o.cleanup_failure_codes.append('A4233_CONNECTION_CLOSE_FAILED')
    r = o.stop(Fault('A4233_SIGTERM'))
    assert r['first_failure_code'] == 'A4233_SIGTERM'
    assert r['cleanup_failure_codes'] == ['A4233_CONNECTION_CLOSE_FAILED','A4233_JOIN_TIMEOUT']
    assert not r['cleanup_complete']


def test_sigterm_guard_restores_handler_and_stops_only_owned_observer():
    o = observer()
    prior = signal.getsignal(signal.SIGTERM)
    with pytest.raises(Fault,match='SIGTERM'),ob.termination_guard(o):
        signal.getsignal(signal.SIGTERM)(signal.SIGTERM,None)
    assert signal.getsignal(signal.SIGTERM) == prior
    assert o.stop_event.is_set() and o.first_failure_code == 'A4233_SIGTERM'


def test_sql_timeout_retains_code_not_driver_message():
    error = RuntimeError('password=secret SELECT values')
    error.sqlstate = '57014'
    db = Database()
    db.values['clock'] = error
    # clock has a generated value in the fake adapter; inject at activity instead.
    db.values['activity'] = error
    r = observer(db).run_micro()
    assert r['first_failure_code'] == 'A4233_SQL_TIMEOUT'
    assert 'secret' not in json.dumps(r)


def test_slow_sql_raises_budget_failure_and_keeps_partial_view_window(monkeypatch):
    db,o = Database(),observer()
    o.preflight(db)
    moments = iter([1_000_000_000,1_101_000_000])
    monkeypatch.setattr(ob.time,'monotonic_ns',lambda:next(moments))
    windows = []
    with pytest.raises(Fault,match='SQL_BUDGET'):
        o.read(db,'activity',windows)
    assert windows == [dict(view='activity',start_ns=1_000_000_000,end_ns=1_101_000_000,
                            wall_ms=101.0)]


def test_driver_first_failure_not_masked_by_wall_budget_cleanup(monkeypatch):
    db,o = Database(),observer()
    error = RuntimeError('secret SQL')
    error.sqlstate = '57014'
    db.values['activity'] = error
    moments = iter([1_000_000_000,1_110_000_000])
    monkeypatch.setattr(ob.time,'monotonic_ns',lambda:next(moments))
    with pytest.raises(RuntimeError) as caught:
        o.read(db,'activity',[])
    assert caught.value is error and ob.failure_code(caught.value) == 'A4233_SQL_TIMEOUT'


def test_naive_datetime_is_not_silently_assumed_utc():
    raw = active().model_dump() | dict(backend_start=datetime(2026,10,23))
    with pytest.raises(Fault,match='CLOCK_INVALID'):
        ob.normalized([raw],Activity)


@pytest.mark.parametrize('key,value',[
    ('head_sha','d'*40),('run_id','999'),('attempt',2),('source_sha256','d'*64),
    ('protocol_sha256','d'*64),('instance_identity_sha256','d'*64)])
def test_independent_review_identity_binding(key,value):
    r = receipt()
    r[key] = value
    with pytest.raises(Fault,match='IDENTITY_MISMATCH'):
        off.review(seal(r),identity())


@pytest.mark.parametrize('key,value',[
    ('capacity_ready',True),('production_read_authorized',True),('performance_eligible',True),
    ('unique_repair_candidate','candidate'),('extra_token','secret'),('pg_major',18)])
def test_unapproved_schema_claims_never_allowed(key,value):
    with pytest.raises(Fault,match='SCHEMA_INVALID'):
        off.review(seal(receipt()|{key:value}),identity())


@pytest.mark.parametrize('key,value',[
    ('ticks',[]),('physical_verified',False),('restricted_readonly_verified',False),
    ('cleanup_complete',False),('first_failure_code','A4233_SIGTERM'),
    ('cleanup_failure_codes',['A4233_JOIN_TIMEOUT'])])
def test_forged_complete_rejected(key,value):
    with pytest.raises(Fault,match='FALSE_COMPLETE'):
        off.review(seal(receipt()|{key:value}),identity())


def test_raw_tampering_and_event_forgery_rejected():
    r = receipt()
    r['ticks'][0]['rss_bytes'] += 1
    with pytest.raises(Fault,match='DIGEST_MISMATCH'):
        off.review(r,identity())
    r = receipt()
    r['ticks'][0]['events'] = []
    with pytest.raises(Fault,match='FALSE_COMPLETE'):
        off.review(seal(r),identity())


def test_artifact_bundle_atomic_hash_review_and_corruption(tmp_path):
    d = tmp_path/'a4233'
    off.bundle(d,receipt(),identity())
    assert off.review_bundle(d,identity())['status'] == 'COMPLETE_CONTRACT'
    with pytest.raises(Fault,match='OUTPUT_EXISTS'):
        off.bundle(d,receipt(),identity())
    (d/'ticks.json').write_text('{}')
    with pytest.raises(Fault,match='ARTIFACT_CORRUPT'):
        off.review_bundle(d,identity())


def test_serialization_and_disk_failures_never_succeed(tmp_path,monkeypatch):
    with pytest.raises(Fault,match='ARTIFACT_WRITE_FAILED'):
        write_new(tmp_path/'bad.json',{'not_serializable':object()})
    def disk_error(*args,**kwargs):
        raise OSError('token secret')
    monkeypatch.setattr('scripts.a42_artifacts.os.replace',disk_error)
    with pytest.raises(Fault,match='ARTIFACT_WRITE_FAILED') as error:
        off.bundle(tmp_path/'a4233',receipt(),identity())
    assert 'secret' not in str(error.value)


def test_duplicate_keys_and_nonfinite_input_are_invalid(tmp_path):
    p = tmp_path/'input.json'
    for data in ('{"a":1,"a":2}','{"x":NaN}'):
        p.write_text(data)
        with pytest.raises(Fault):
            off.load(p)


def test_offline_review_import_has_no_database_or_application_side_effects():
    # AST-level dependency graph is intentionally small and explicit.
    import ast

    for name in ('a4233_observation_review','a4233_observation_contract'):
        tree = ast.parse((ROOT/'scripts'/f'{name}.py').read_text())
        imports = [n.module or '' for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
        assert not any(x.startswith(('app','sqlalchemy','psycopg','dotenv')) for x in imports)
    assert off.review(receipt(),identity())['observer_overhead_calibration'] == (
        'NOT_RUN_NOT_AUTHORIZED')


def test_bracket_requires_coverage_no_missing_ticks_and_no_absence_claim():
    ts = [tick(i) for i in range(3)]
    result = ob.bracket(ts,1_020_000_000,1_240_000_000)
    assert result['absence_proven'] is False and result['tick_sequences'] == [0,1]
    with pytest.raises(Fault,match='BRACKET_UNCOVERED'):
        ob.bracket(ts,0,1)
    ts[1].events = correlate(ts[1].model_copy(update={'activity':[active()]}),7,relations())
    with pytest.raises(Fault,match='BRACKET_POSSIBLY_CONTAMINATED'):
        ob.bracket(ts,1_020_000_000,1_240_000_000)


def test_frozen_baseline_bytes_and_old_workflows_unchanged():
    manifest = json.loads((ROOT/'docs/acceptance/evidence/a4233_frozen_manifest.json').read_text())
    import hashlib

    assert manifest['baseline_sha'] == '73a3273301502822dc7a881a64dfdca45db4d063'
    for p,h in manifest['files'].items():
        assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest() == h
        assert hashlib.sha256(subprocess.check_output(['git','show',manifest['baseline_sha']+':'+p],
                                                       cwd=ROOT)).hexdigest() == h
    assert subprocess.run(['git','diff','--quiet',manifest['baseline_sha'],'--',
        'backend','config','migrations','frontend'],cwd=ROOT).returncode == 0


def test_new_workflow_has_one_contracts_job_and_no_measurement_entry():
    import yaml

    workflow = yaml.safe_load((ROOT/'.github/workflows/a4233-observer-contracts.yml').read_text())
    assert set(workflow['jobs']) == {'contracts'}
    assert set(workflow['on']) == {'push','pull_request'}
    serialized = json.dumps(workflow)
    for forbidden in ('workflow_dispatch','seed_candidates','--level','--scope','capacity-ready',
                      'statstable-once','attribution-once','resource-class: capacity'):
        assert forbidden not in serialized
    assert DRAFT in (ROOT/'docs/acceptance/v14_a4_2_3_3_observation_protocol_draft.md').read_text()
