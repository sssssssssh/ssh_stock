"""PG17 synthetic-only observer. No application import, maintenance, or performance CLI."""

import signal
import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import UUID

from scripts.a4233_observation_contract import (
    TABLES,
    Activity,
    Analyze,
    Fault,
    Identity,
    Receipt,
    Relation,
    TableStats,
    Tick,
    Vacuum,
    check,
    correlate,
    digest,
    failure_code,
    seal,
    validate_ticks,
)
from scripts.ab_read_resources_v14_a4_2 import current_rss_bytes

# Values are selected in the database, not fetched broadly then redacted.
FIELDS = {
    'pg_stat_activity': dict(datid='oid',pid='integer',backend_type='text',
        backend_start='timestamp with time zone',query_start='timestamp with time zone',
        state='text',wait_event_type='text',wait_event='text'),
    'pg_stat_progress_vacuum': dict(pid='integer',datid='oid',relid='oid',phase='text',
        heap_blks_total='bigint',heap_blks_scanned='bigint',heap_blks_vacuumed='bigint',
        index_vacuum_count='bigint'),
    'pg_stat_progress_analyze': dict(pid='integer',datid='oid',relid='oid',phase='text',
        sample_blks_total='bigint',sample_blks_scanned='bigint',ext_stats_total='bigint',
        ext_stats_computed='bigint',child_tables_total='bigint',child_tables_done='bigint',
        current_child_table_relid='oid'),
    'pg_stat_user_tables': dict(relid='oid',schemaname='name',relname='name',
        last_autovacuum='timestamp with time zone',last_autoanalyze='timestamp with time zone',
        autovacuum_count='bigint',autoanalyze_count='bigint',n_live_tup='bigint',n_dead_tup='bigint',
        n_mod_since_analyze='bigint',n_ins_since_vacuum='bigint'),
}
IDENTITY_SQL = """SELECT current_setting('server_version_num') AS version,
    current_setting('v14.test_instance',true) AS marker,
    (SELECT system_identifier::text FROM pg_catalog.pg_control_system()) AS system_id,
    (SELECT oid FROM pg_catalog.pg_database WHERE datname=current_database()) AS datid"""
PREFLIGHT_SQL = """SELECT current_setting('transaction_read_only') AS readonly,
    current_setting('default_transaction_read_only') AS default_readonly,
    current_setting('statement_timeout') AS timeout,
    current_setting('TimeZone') AS timezone,
    current_setting('track_activities') AS track_activities,
    current_setting('track_counts') AS track_counts,
    r.rolsuper,r.rolcreaterole,r.rolcreatedb,r.rolreplication,r.rolbypassrls,
    pg_catalog.pg_has_role(current_user,'pg_read_all_stats','USAGE') AS stats_visible,
    pg_catalog.has_database_privilege(current_database(),'CREATE') AS database_create,
    pg_catalog.has_schema_privilege('public','CREATE') AS schema_create,
    EXISTS(SELECT 1 FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n
      ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname IN
      ('data_publication_row','signal_forward_eval','stock_opportunity_daily','stock_trade_status_daily')
      AND pg_catalog.has_table_privilege(c.oid,
          'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER,MAINTAIN'))
      AS table_access,
    EXISTS(SELECT 1 FROM pg_catalog.pg_roles p WHERE p.rolname IN
      ('pg_write_all_data','pg_read_all_data','pg_signal_backend','pg_maintain',
       'pg_monitor','pg_read_server_files','pg_write_server_files','pg_execute_server_program')
      AND pg_catalog.pg_has_role(current_user,p.oid,'MEMBER')) AS dangerous_role
    FROM pg_catalog.pg_roles r WHERE r.rolname=current_user"""
COLUMNS_SQL = """SELECT c.relname,a.attname,pg_catalog.format_type(a.atttypid,a.atttypmod) AS type
    FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
    JOIN pg_catalog.pg_attribute a ON a.attrelid=c.oid
    WHERE n.nspname='pg_catalog' AND c.relname IN
    ('pg_stat_activity','pg_stat_progress_vacuum','pg_stat_progress_analyze','pg_stat_user_tables')
    AND a.attnum>0 AND NOT a.attisdropped"""
RELATIONS_SQL = """WITH base AS (
    SELECT c.oid,c.reltoastrelid,c.relname FROM pg_catalog.pg_class c
    JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname='public' AND c.relkind IN ('r','p') AND c.relname IN
    ('data_publication_row','signal_forward_eval','stock_opportunity_daily','stock_trade_status_daily'))
    SELECT oid AS relid,relname AS "table",'TABLE' AS kind FROM base
    UNION ALL SELECT i.indexrelid,b.relname,'INDEX' FROM base b
    JOIN pg_catalog.pg_index i ON i.indrelid=b.oid
    UNION ALL SELECT reltoastrelid,relname,'TOAST' FROM base WHERE reltoastrelid<>0
    UNION ALL SELECT i.indexrelid,b.relname,'TOAST_INDEX' FROM base b
    JOIN pg_catalog.pg_index i ON i.indrelid=b.reltoastrelid"""


def projection(view):
    check(view in FIELDS, 'A4233_SQL_NOT_ALLOWED')
    return 'SELECT '+','.join(FIELDS[view])+' FROM pg_catalog.'+view


SQL = dict(identity=IDENTITY_SQL,preflight=PREFLIGHT_SQL,columns=COLUMNS_SQL,
    relations=RELATIONS_SQL,clock='SELECT pg_catalog.clock_timestamp() AS db_clock_timestamp',
    activity=projection('pg_stat_activity')+' WHERE backend_type=\'autovacuum worker\' '
        'OR pid IN (SELECT pid FROM pg_catalog.pg_stat_progress_vacuum UNION '
        'SELECT pid FROM pg_catalog.pg_stat_progress_analyze)',
    vacuum=projection('pg_stat_progress_vacuum'),analyze=projection('pg_stat_progress_analyze'),
    tables=projection('pg_stat_user_tables')+" WHERE schemaname='public' AND relname IN "
        "('data_publication_row','signal_forward_eval','stock_opportunity_daily','stock_trade_status_daily')")
SQL = {name:query+' LIMIT 129' for name,query in SQL.items()}


def connection_factory(url, marker, system_id):
    """Explicit loopback target only; never reads environment/Settings/dotenv."""
    from sqlalchemy.engine import make_url

    try:
        target = make_url(url)
        UUID(marker)
        check(str(system_id).isdigit() and target.get_backend_name() == 'postgresql'
              and target.host in ('127.0.0.1','localhost') and target.port is not None
              and (target.database or '').startswith('v14_')
              and (target.database or '').endswith('_test') and not target.query,
              'A4233_EXPLICIT_SYNTHETIC_TARGET_REQUIRED')
    except Fault:
        raise
    except Exception:
        raise Fault('A4233_EXPLICIT_SYNTHETIC_TARGET_REQUIRED') from None

    def connect():
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(host=target.host,port=target.port,dbname=target.database,
            user=target.username,password=target.password,autocommit=True,connect_timeout=2,
            options='-c default_transaction_read_only=on -c statement_timeout=100ms '
                    '-c TimeZone=UTC -c search_path=pg_catalog',row_factory=dict_row)
    return connect


def normalized(rows, model):
    result = []
    for row in rows:
        check(all(not isinstance(v,datetime) or v.tzinfo is not None for v in row.values()),
              'A4233_CLOCK_INVALID')
        converted = {k:(v.astimezone(UTC).isoformat() if isinstance(v,datetime) else v)
                     for k,v in row.items()}
        try:
            result.append(model.model_validate(converted))
        except Exception:
            raise Fault('A4233_REQUIRED_FIELD_INVALID') from None
    return result


class Observer:
    """Owns one connection/thread and at most eight micro-selftest ticks.

    Candidate 250/100/500/1024/2000 budgets are NOT an approved performance protocol.
    Any observed activity stops this selftest, retaining the complete captured tick.
    """
    def __init__(self, connect, *, marker, system_id, identity, planned_ticks=3):
        check(type(planned_ticks) is int and 2 <= planned_ticks <= 8,'A4233_MICRO_ONLY')
        check(isinstance(identity,Identity), 'A4233_IDENTITY_REQUIRED')
        UUID(marker)
        check(str(system_id).isdigit(), 'A4233_IDENTITY_REQUIRED')
        check(identity.instance_identity_sha256 == digest([marker,str(system_id)]),
              'A4233_IDENTITY_MISMATCH')
        self.connect,self.marker,self.system_id = connect,marker,str(system_id)
        self.identity,self.planned_ticks = identity,planned_ticks
        self.stop_event = threading.Event()
        self.thread = None
        self.ticks,self.relations = [],[]
        self.datid = None
        self.physical_verified = self.restricted_readonly_verified = False
        self.first_failure_code,self.cleanup_failure_codes = None,[]
        self.cleanup_complete = False
        self.failed_tick = None
        self.capacity = 1024

    def fail(self, code):
        if self.first_failure_code is None:
            self.first_failure_code = code
        self.stop_event.set()

    def read(self, db, name, windows=None):
        check(name in SQL, 'A4233_SQL_NOT_ALLOWED')
        start = time.monotonic_ns()
        primary = None
        try:
            # Fixed bound includes one sentinel row; never silently truncate.
            with db.execute(SQL[name],prepare=False) as cursor:
                rows = cursor.fetchmany(129)
            check(len(rows) <= 128,'A4233_ROW_BUFFER_FULL')
            return rows
        except BaseException as error:
            primary = error
            raise
        finally:
            end = time.monotonic_ns()
            if windows is not None:
                windows.append(dict(view=name,start_ns=start,end_ns=end,wall_ms=(end-start)/1e6))
            if primary is None:
                check(end >= start, 'A4233_CLOCK_BACKWARDS')
                check(end-start <= 100_000_000, 'A4233_SQL_BUDGET')

    def preflight(self, db):
        # Physical identity is the very first SELECT. Nothing else before it.
        rows = self.read(db,'identity')
        check(len(rows) == 1,'A4233_IDENTITY_REQUIRED')
        r = rows[0]
        check(int(r['version'])//10000 == 17, 'A4233_PG17_REQUIRED')
        check(r['marker'] == self.marker and r['system_id'] == self.system_id,
              'A4233_PHYSICAL_MISMATCH')
        check(type(r['datid']) is int and r['datid'] > 0,'A4233_IDENTITY_REQUIRED')
        self.datid,self.physical_verified = r['datid'],True
        clock = time.get_clock_info('monotonic')
        check(clock.monotonic and not clock.adjustable,'A4233_MONOTONIC_REQUIRED')
        check(db.autocommit is True, 'A4233_AUTOCOMMIT_REQUIRED')
        rows = self.read(db,'preflight')
        check(len(rows) == 1,'A4233_PERMISSION_REQUIRED')
        p = rows[0]
        check(p['stats_visible'] is True,'A4233_READ_ALL_STATS_REQUIRED')
        check(all(p[k] is False for k in ('rolsuper','rolcreaterole','rolcreatedb',
              'rolreplication','rolbypassrls','dangerous_role','database_create','schema_create',
              'table_access')), 'A4233_RESTRICTED_ROLE_REQUIRED')
        check(p['readonly'] == p['default_readonly'] == 'on' and p['timeout'] == '100ms'
              and p['timezone'] == 'UTC' and p['track_activities'] == p['track_counts'] == 'on',
              'A4233_READONLY_SETTINGS_REQUIRED')
        columns = self.read(db,'columns')
        actual = {(r['relname'],r['attname']):r['type'] for r in columns}
        check(all(actual.get((v,k)) == typ for v,cols in FIELDS.items()
                  for k,typ in cols.items()), 'A4233_PG17_FIELD_MISSING')
        self.relations = normalized(self.read(db,'relations'),Relation)
        check(len({r.relid for r in self.relations}) == len(self.relations)
              and {r.table for r in self.relations if r.kind == 'TABLE'} == set(TABLES),
              'A4233_MAPPING_INCOMPLETE')
        self.restricted_readonly_verified = True

    def tick(self, db):
        start,cpu,u = time.monotonic_ns(),time.thread_time(),datetime.now(UTC).isoformat()
        windows,parts = [],{}
        try:
            clock = self.read(db,'clock',windows)
            check(len(clock) == 1, 'A4233_CLOCK_INVALID')
            check(clock[0]['db_clock_timestamp'].tzinfo is not None,'A4233_CLOCK_INVALID')
            stamp = clock[0]['db_clock_timestamp'].astimezone(UTC).isoformat()
            for name,model in (('activity',Activity),('vacuum',Vacuum),('analyze',Analyze),
                               ('tables',TableStats)):
                parts[name] = normalized(self.read(db,name,windows),model)
            rss = current_rss_bytes()
            end,v = time.monotonic_ns(),datetime.now(UTC).isoformat()
            t = Tick(sequence=len(self.ticks),tick_started_monotonic_ns=start,
                tick_finished_monotonic_ns=end,tick_started_utc=u,tick_finished_utc=v,
                db_clock_timestamp=stamp,db_query_wall_ms=sum(w['wall_ms'] for w in windows),
                tick_total_wall_ms=(end-start)/1e6,cpu_seconds=max(0.0,time.thread_time()-cpu),
                rss_bytes=rss,windows=windows,events=[],**parts)
            t.events = correlate(t,self.datid,self.relations,self.ticks[-1] if self.ticks else None)
            check(len(self.ticks) < self.capacity, 'A4233_TICK_BUFFER_FULL')
            self.ticks.append(t)  # Preserve slow/ambiguous full tick before validation.
            validate_ticks(self.ticks,self.datid,self.relations)
            check(all(e.code == 'NOT_OBSERVED' for e in t.events),'A4233_ACTIVITY_STOP')
        except BaseException:
            # Partial view evidence stays typed/bounded; no raw driver text or values.
            self.failed_tick = dict(sequence=len(self.ticks),windows=windows,
                observations={k:[r.model_dump() for r in rows] for k,rows in parts.items()})
            raise

    def worker(self):
        db = None
        try:
            db = self.connect()
            self.preflight(db)
            due = time.monotonic_ns()
            for _ in range(self.planned_ticks):
                remaining = (due-time.monotonic_ns())/1e9
                if remaining > 0 and self.stop_event.wait(remaining):
                    break
                if self.stop_event.is_set():
                    break
                self.tick(db)
                due += 250_000_000
            if len(self.ticks) != self.planned_ticks and self.first_failure_code is None:
                self.fail('A4233_TICK_MISSING')
        except BaseException as error:
            self.fail(failure_code(error))
        finally:
            if db is not None:
                try:
                    db.close()
                except BaseException:
                    self.cleanup_failure_codes.append('A4233_CONNECTION_CLOSE_FAILED')

    def start(self):
        check(self.thread is None,'A4233_ALREADY_STARTED')
        self.thread = threading.Thread(target=self.worker,name='a4233-owned-observer',daemon=False)
        self.thread.start()
        return self

    def stop(self, error=None):
        start = time.monotonic_ns()
        if error is not None:
            self.fail(failure_code(error))
        self.stop_event.set()
        try:
            if self.thread is not None:
                self.thread.join(timeout=2)
                check(not self.thread.is_alive(),'A4233_JOIN_TIMEOUT')
            check(time.monotonic_ns()-start <= 2_000_000_000,'A4233_JOIN_TIMEOUT')
        except BaseException as caught:
            self.cleanup_failure_codes.append(failure_code(caught))
        self.cleanup_complete = not self.cleanup_failure_codes
        return self.receipt()

    def receipt(self):
        if self.thread is not None and self.thread.is_alive():
            # Do not iterate a buffer concurrently with a stuck owned worker.
            self.fail('A4233_THREAD_STILL_ACTIVE')
        complete = (self.thread is not None and not self.thread.is_alive()
            and self.physical_verified and self.restricted_readonly_verified
            and self.cleanup_complete and not self.first_failure_code
            and not self.cleanup_failure_codes and len(self.ticks) == self.planned_ticks)
        result = Receipt(**self.identity.model_dump(),datid=self.datid,
            relations=self.relations,planned_ticks=self.planned_ticks,ticks=self.ticks,
            physical_verified=self.physical_verified,
            restricted_readonly_verified=self.restricted_readonly_verified,
            cleanup_complete=self.cleanup_complete,first_failure_code=self.first_failure_code,
            cleanup_failure_codes=self.cleanup_failure_codes,
            failed_tick=self.failed_tick,
            status='COMPLETE_CONTRACT' if complete else 'INCOMPLETE_OBSERVABILITY',
            content_sha256='0'*64).model_dump()
        return seal(result)

    def run_micro(self):
        try:
            with termination_guard(self):
                self.start()
                # At most eight ticks, no performance workload, no retries.
                self.thread.join(timeout=4)
                if self.thread.is_alive():
                    self.fail('A4233_MICRO_DEADLINE')
        except BaseException as error:
            self.fail(failure_code(error))
        return self.stop()


@contextmanager
def termination_guard(observer):
    """Only the calling main thread's SIGTERM handler, restored on exit."""
    previous = signal.getsignal(signal.SIGTERM)
    def handler(signum, frame):
        observer.fail('A4233_SIGTERM')
        raise Fault('A4233_SIGTERM')
    signal.signal(signal.SIGTERM,handler)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM,previous)


def bracket(ticks, start_ns, end_ns):
    """Future host-monotonic lookup bracket; never a performance admission."""
    check(type(start_ns) is int and type(end_ns) is int and 0 <= start_ns <= end_ns,
          'A4233_BRACKET_INVALID')
    before = [t for t in ticks if t.tick_finished_monotonic_ns <= start_ns]
    after = [t for t in ticks if t.tick_started_monotonic_ns >= end_ns]
    check(before and after,'A4233_BRACKET_UNCOVERED')
    selected = [t for t in ticks if t.sequence >= before[-1].sequence
                and t.sequence <= after[0].sequence]
    check(all(b.sequence == a.sequence+1 and
              b.tick_started_monotonic_ns-a.tick_started_monotonic_ns <= 500_000_000
              for a,b in zip(selected,selected[1:],strict=False)), 'A4233_TICK_GAP')
    check(all(e.code == 'NOT_OBSERVED' for t in selected for e in t.events),
          'A4233_BRACKET_POSSIBLY_CONTAMINATED')
    return dict(status='NOT_OBSERVED',absence_proven=False,start_ns=start_ns,end_ns=end_ns,
                tick_sequences=[t.sequence for t in selected])
