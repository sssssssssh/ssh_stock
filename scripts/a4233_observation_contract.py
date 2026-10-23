"""Strict, bounded diagnostic evidence; no app/config/database imports."""

import hashlib
import json
import math
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

BASELINE = '73a3273301502822dc7a881a64dfdca45db4d063'
TABLES = ('data_publication_row', 'signal_forward_eval',
          'stock_opportunity_daily', 'stock_trade_status_daily')
PROTOCOL = 'docs/acceptance/v14_a4_2_3_3_observation_protocol_draft.md'
DRAFT = 'DRAFT / NOT APPROVED / NO PERFORMANCE MEASUREMENT EXECUTED'
SOURCES = ('scripts/a4233_observation_contract.py', 'scripts/a4233_background_observer.py',
           'scripts/a4233_observation_review.py', 'scripts/a4233_test_receipt.py')
Hash = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
Positive = Annotated[int, Field(strict=True, gt=0)]
Counter = Annotated[int, Field(strict=True, ge=0)]
Label = Annotated[str, Field(pattern=r'^[A-Za-z][A-Za-z0-9_ /:-]{0,79}$')]
Code = Annotated[str, Field(pattern=r'^A4233_[A-Z0-9_]{1,80}$')]
EventCode = Literal['VACUUM_OBSERVED', 'ANALYZE_OBSERVED', 'ENVIRONMENT_ACTIVITY_ONLY',
                    'POSSIBLE_IN_BRACKET', 'UNKNOWN_RELATION', 'NOT_OBSERVED', 'AMBIGUOUS_EVENT']


class Fault(RuntimeError):
    def __init__(self, code):
        # Only fixed application codes may ever become exception text.
        self.code = code if re.fullmatch(r'A4233_[A-Z0-9_]{1,80}', code) else 'A4233_INTERNAL'
        super().__init__(self.code)


def check(condition, code):
    if not condition:
        raise Fault(code)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def utc(value):
    try:
        stamp = datetime.fromisoformat(value)
        check(stamp.tzinfo is not None and stamp.utcoffset().total_seconds() == 0,
              'A4233_CLOCK_INVALID')
        return stamp.astimezone(UTC)
    except (TypeError, ValueError, AttributeError):
        raise Fault('A4233_CLOCK_INVALID') from None


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)


class Identity(Strict):
    head_sha: Annotated[str, Field(pattern=r'^[0-9a-f]{40}$')]
    run_id: Annotated[str, Field(pattern=r'^(local|[0-9]{1,24})$')]
    attempt: Positive
    instance_identity_sha256: Hash
    source_sha256: Hash
    protocol_sha256: Hash


class Relation(Strict):
    relid: Positive
    table: Literal['data_publication_row', 'signal_forward_eval',
                   'stock_opportunity_daily', 'stock_trade_status_daily']
    kind: Literal['TABLE', 'INDEX', 'TOAST', 'TOAST_INDEX']


class Activity(Strict):
    datid: Positive | None
    pid: Positive
    backend_type: Literal['autovacuum worker','client backend',
                          'parallel worker','background worker']
    backend_start: str
    query_start: str | None
    state: Literal['active', 'idle', 'idle in transaction',
                   'idle in transaction (aborted)', 'fastpath function call', 'disabled'] | None
    wait_event_type: Label | None
    wait_event: Label | None


class Vacuum(Strict):
    pid: Positive
    datid: Positive
    relid: Positive
    phase: Literal['initializing', 'scanning heap', 'vacuuming indexes',
                   'vacuuming heap', 'cleaning up indexes', 'truncating heap',
                   'performing final cleanup']
    heap_blks_total: Counter
    heap_blks_scanned: Counter
    heap_blks_vacuumed: Counter
    index_vacuum_count: Counter


class Analyze(Strict):
    pid: Positive
    datid: Positive
    relid: Positive
    phase: Literal['initializing', 'acquiring sample rows', 'acquiring inherited sample rows',
                   'computing statistics', 'computing extended statistics', 'finalizing analyze']
    sample_blks_total: Counter
    sample_blks_scanned: Counter
    ext_stats_total: Counter
    ext_stats_computed: Counter
    child_tables_total: Counter
    child_tables_done: Counter
    current_child_table_relid: Counter


class TableStats(Strict):
    relid: Positive
    schemaname: Literal['public']
    relname: Literal['data_publication_row', 'signal_forward_eval',
                     'stock_opportunity_daily', 'stock_trade_status_daily']
    last_autovacuum: str | None
    last_autoanalyze: str | None
    autovacuum_count: Counter
    autoanalyze_count: Counter
    n_live_tup: Counter
    n_dead_tup: Counter
    n_mod_since_analyze: Counter
    n_ins_since_vacuum: Counter


class Window(Strict):
    view: Literal['clock', 'activity', 'vacuum', 'analyze', 'tables']
    start_ns: Counter
    end_ns: Counter
    wall_ms: Annotated[float, Field(ge=0)]


class Event(Strict):
    code: EventCode
    pid: Positive | None = None
    backend_start: str | None = None
    relid: Positive | None = None
    relation: Relation | None = None
    active_query_start_candidate: str | None = None
    phase: Label | None = None
    # All times are observation brackets, not true operation begin/end.
    window_start_ns: Counter
    window_end_ns: Counter


class Tick(Strict):
    sequence: Counter
    tick_started_monotonic_ns: Counter
    tick_finished_monotonic_ns: Counter
    tick_started_utc: str
    tick_finished_utc: str
    db_clock_timestamp: str
    db_query_wall_ms: Annotated[float, Field(ge=0)]
    tick_total_wall_ms: Annotated[float, Field(ge=0)]
    cpu_seconds: Annotated[float, Field(ge=0)]
    rss_bytes: Positive
    phase: Literal['CONTRACT_SELFTEST'] = 'CONTRACT_SELFTEST'
    error_code: None = None
    windows: Annotated[list[Window], Field(min_length=5, max_length=5)]
    activity: Annotated[list[Activity], Field(max_length=128)]
    vacuum: Annotated[list[Vacuum], Field(max_length=128)]
    analyze: Annotated[list[Analyze], Field(max_length=128)]
    tables: Annotated[list[TableStats], Field(min_length=4, max_length=4)]
    events: Annotated[list[Event], Field(max_length=400)]


class PartialObservations(Strict):
    activity: Annotated[list[Activity], Field(max_length=128)] = Field(default_factory=list)
    vacuum: Annotated[list[Vacuum], Field(max_length=128)] = Field(default_factory=list)
    analyze: Annotated[list[Analyze], Field(max_length=128)] = Field(default_factory=list)
    tables: Annotated[list[TableStats], Field(max_length=4)] = Field(default_factory=list)


class PartialTick(Strict):
    sequence: Counter
    windows: Annotated[list[Window], Field(max_length=5)]
    observations: PartialObservations


class Receipt(Identity):
    schema_version: Literal['a4233.observer.v1'] = 'a4233.observer.v1'
    evidence_kind: Literal['DIAGNOSTIC_ONLY'] = 'DIAGNOSTIC_ONLY'
    protocol_status: Literal['DRAFT / NOT APPROVED / NO PERFORMANCE MEASUREMENT EXECUTED'] = DRAFT
    data_source: Literal['SYNTHETIC_MICRO_SELFTEST'] = 'SYNTHETIC_MICRO_SELFTEST'
    status: Literal['INCOMPLETE_OBSERVABILITY', 'COMPLETE_CONTRACT'] = 'INCOMPLETE_OBSERVABILITY'
    pg_major: Literal[17] = 17
    datid: Positive | None
    relations: Annotated[list[Relation], Field(max_length=128)]
    planned_ticks: Annotated[int, Field(strict=True, ge=2, le=8)]
    ticks: Annotated[list[Tick], Field(max_length=1024)] = Field(default_factory=list)
    failed_tick: PartialTick | None = None
    physical_verified: bool = False
    restricted_readonly_verified: bool = False
    cleanup_complete: bool = False
    first_failure_code: Code | None = None
    cleanup_failure_codes: Annotated[list[Code], Field(max_length=4)] = Field(default_factory=list)
    # Measured by the artifact writer in manifest.json, outside observer CPU/SQL.
    artifact_cost_location: Literal['manifest.json'] = 'manifest.json'
    cost_scope: Literal['NESTED_WALL_NOT_CPU_OR_IO_CALIBRATION'] = (
        'NESTED_WALL_NOT_CPU_OR_IO_CALIBRATION')
    production_read_authorized: Literal[False] = False
    capacity_ready: Literal[False] = False
    performance_eligible: Literal[False] = False
    unique_repair_candidate: None = None
    content_sha256: Hash


def correlate(tick, datid, relations, previous=None):
    """Conservative cross-view associations; absence never proves inactivity."""
    start, end = tick.tick_started_monotonic_ns, tick.tick_finished_monotonic_ns
    result = []
    mapping = {r.relid: r for r in relations}
    activities = {a.pid: a for a in tick.activity}
    if len(activities) != len(tick.activity):
        result.append(Event(code='AMBIGUOUS_EVENT', window_start_ns=start, window_end_ns=end))
    progressed = set()
    for kind, rows in (('VACUUM_OBSERVED', tick.vacuum), ('ANALYZE_OBSERVED', tick.analyze)):
        for row in rows:
            a = activities.get(row.pid)
            progressed.add(row.pid)
            other = tick.analyze if kind == 'VACUUM_OBSERVED' else tick.vacuum
            ambiguous = (a is None or a.datid != row.datid or a.state != 'active'
                         or a.query_start is None
                         or any(p.pid == row.pid for p in other))
            if a is not None and previous is not None:
                ambiguous |= any(p.pid == a.pid and p.backend_start != a.backend_start
                                 for p in previous.activity)
            child = getattr(row, 'current_child_table_relid', 0)
            unknown = (row.datid != datid or row.relid not in mapping
                       or child and child not in mapping)
            code = 'AMBIGUOUS_EVENT' if ambiguous else 'UNKNOWN_RELATION' if unknown else kind
            result.append(Event(code=code, pid=row.pid,
                backend_start=a.backend_start if a else None, relid=row.relid,
                relation=mapping.get(row.relid) if row.datid == datid else None,
                active_query_start_candidate=a.query_start if a and a.state == 'active' else None,
                phase=row.phase, window_start_ns=start, window_end_ns=end))
    for a in tick.activity:
        if a.backend_type == 'autovacuum worker' and a.pid not in progressed:
            result.append(Event(code='ENVIRONMENT_ACTIVITY_ONLY' if a.datid == datid
                else 'UNKNOWN_RELATION', pid=a.pid, backend_start=a.backend_start,
                window_start_ns=start, window_end_ns=end))
    if previous is not None:
        before = {r.relid:r for r in previous.tables}
        for row in tick.tables:
            p = before.get(row.relid)
            if p and any(getattr(row,k) != getattr(p,k) for k in
                ('last_autovacuum','last_autoanalyze','autovacuum_count','autoanalyze_count')):
                result.append(Event(code='POSSIBLE_IN_BRACKET', relid=row.relid,
                    relation=mapping.get(row.relid),
                    window_start_ns=previous.tick_started_monotonic_ns, window_end_ns=end))
    return result or [Event(code='NOT_OBSERVED', window_start_ns=start, window_end_ns=end)]


def validate_ticks(ticks, datid, relations):
    previous = None
    for i,t in enumerate(ticks):
        check(t.sequence == i, 'A4233_TICK_MISSING')
        start,end = t.tick_started_monotonic_ns,t.tick_finished_monotonic_ns
        check(end >= start, 'A4233_CLOCK_BACKWARDS')
        check(abs((end-start)/1e6-t.tick_total_wall_ms) < .001, 'A4233_WALL_MISMATCH')
        check(t.tick_total_wall_ms <= 250, 'A4233_TICK_OVERRUN')
        u,v,db = utc(t.tick_started_utc),utc(t.tick_finished_utc),utc(t.db_clock_timestamp)
        check(abs((v-u).total_seconds()*1000-t.tick_total_wall_ms) <= 50,
              'A4233_CLOCK_DRIFT')
        check(u.timestamp()-.05 <= db.timestamp() <= v.timestamp()+.05, 'A4233_DB_CLOCK_DRIFT')
        if previous:
            gap = (start-previous.tick_started_monotonic_ns)/1e6
            check(start >= previous.tick_finished_monotonic_ns and 200 <= gap <= 500,
                  'A4233_TICK_GAP')
            check(abs((u-utc(previous.tick_started_utc)).total_seconds()*1000-gap) <= 50,
                  'A4233_CLOCK_DRIFT')
        check([w.view for w in t.windows] == ['clock','activity','vacuum','analyze','tables'],
              'A4233_VIEW_MISSING')
        boundary = start
        for w in t.windows:
            check(boundary <= w.start_ns <= w.end_ns <= end
                  and abs((w.end_ns-w.start_ns)/1e6-w.wall_ms) < .001,
                  'A4233_VIEW_WINDOW_INVALID')
            check(w.wall_ms <= 100, 'A4233_SQL_BUDGET')
            boundary = w.end_ns
        check(abs(sum(w.wall_ms for w in t.windows)-t.db_query_wall_ms) < .001,
              'A4233_SQL_WALL_MISMATCH')
        check({r.relname for r in t.tables} == set(TABLES)
              and len({r.relid for r in t.tables}) == 4, 'A4233_TABLE_STATS_MISSING')
        for row in t.tables:
            check(any(r.relid == row.relid and r.table == row.relname and r.kind == 'TABLE'
                      for r in relations), 'A4233_RELATION_MISMATCH')
            for k in ('last_autovacuum','last_autoanalyze'):
                if getattr(row,k) is not None:
                    utc(getattr(row,k))
        for a in t.activity:
            utc(a.backend_start)
            if a.query_start is not None:
                utc(a.query_start)
        check(t.events == correlate(t,datid,relations,previous), 'A4233_EVENT_MISMATCH')
        previous = t


def seal(receipt):
    value = dict(receipt)
    value.pop('content_sha256',None)
    value['content_sha256'] = digest(value)
    return value


def validate(value, expected):
    try:
        receipt = Receipt.model_validate(value)
        for k,v in expected.model_dump().items():
            check(getattr(receipt,k) == v, 'A4233_IDENTITY_MISMATCH')
        check(receipt.content_sha256 == digest({k:v for k,v in receipt.model_dump().items()
            if k != 'content_sha256'}), 'A4233_DIGEST_MISMATCH')
        check(len({r.relid for r in receipt.relations}) == len(receipt.relations),
              'A4233_MAPPING_INCOMPLETE')
        try:
            validate_ticks(receipt.ticks,receipt.datid,receipt.relations)
        except Fault as error:
            # A failed measured tick remains raw evidence, not a qualified tick.
            check(receipt.status == 'INCOMPLETE_OBSERVABILITY'
                  and receipt.first_failure_code == error.code, 'A4233_FALSE_COMPLETE')
        if receipt.status == 'COMPLETE_CONTRACT':
            check(receipt.physical_verified and receipt.restricted_readonly_verified
                  and receipt.cleanup_complete and not receipt.first_failure_code
                  and not receipt.cleanup_failure_codes
                  and receipt.failed_tick is None and receipt.datid is not None
                  and len(receipt.ticks) == receipt.planned_ticks
                  and {r.table for r in receipt.relations if r.kind == 'TABLE'} == set(TABLES),
                  'A4233_FALSE_COMPLETE')
            check(all(e.code == 'NOT_OBSERVED' for t in receipt.ticks for e in t.events),
                  'A4233_UNQUALIFIED_ACTIVITY')
        return receipt
    except Fault:
        raise
    except Exception:
        # Pydantic/JSON errors may include injected secrets; never expose them.
        raise Fault('A4233_SCHEMA_INVALID') from None


def write_new(path, value):
    from scripts.a42_artifacts import atomic

    path = Path(path)
    check(not path.exists() and not path.with_suffix(path.suffix+'.tmp').exists(),
          'A4233_OUTPUT_EXISTS')
    # No default=str, unknown object conversion, or silent pruning.
    try:
        json.dumps(value,allow_nan=False)
        return atomic(path,value)
    except Fault:
        raise
    except Exception:
        raise Fault('A4233_ARTIFACT_WRITE_FAILED') from None


def failure_code(error):
    if isinstance(error,Fault):
        return error.code
    state = getattr(error,'sqlstate',None)
    return 'A4233_SQL_TIMEOUT' if state == '57014' else 'A4233_OBSERVER_EXCEPTION'


def finite_ms(seconds):
    check(math.isfinite(seconds) and seconds >= 0, 'A4233_CLOCK_INVALID')
    return float(seconds*1000)
