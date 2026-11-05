"""Explicit offline-only synthetic data. No application, DB or Provider imports."""

import argparse
import hashlib
import json
import math
import resource
import sys
from datetime import date, timedelta
from itertools import islice
from pathlib import Path
from time import monotonic, process_time

VERSION = 'biz-perf-04-b.generator.v1'
CALENDAR = 'synthetic-weekdays.v1'  # Not a real exchange holiday calendar.
FROZEN = '2026-10-27T00:00:00+00:00'
SCALES = {'S1': 4, 'S2': 150, 'S3': 752, 'S4': 2165}
INDICES = ('000001.SH', '000300.SH', '000852.SH')
TABLES = ('trade_calendar', 'stock_basic', 'sector', 'sector_member', 'stock_daily',
          'stock_adj_factor', 'stock_daily_basic', 'stock_limit_daily', 'index_daily',
          'stock_st_daily', 'stock_suspend_daily', 'data_quality_daily')
START, END = date(2025, 1, 1), date(2025, 1, 31)
FIRST = START - timedelta(days=900)
DAYS = tuple(FIRST + timedelta(days=i) for i in range((END - FIRST).days + 1))
OPENS = tuple(d for d in DAYS if d.weekday() < 5)


def require(value):
    if not value:
        raise ValueError('BIZ04_DATASET_CONTRACT_INVALID')


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
            .encode() + b'\n')


def sha(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def config(scale):
    require(type(scale) is str and scale in SCALES)
    return dict(dataset_id='biz04-constant-' + scale.lower(), schema_version='biz04.dataset.v1',
                scale=scale, stocks=SCALES[scale], trading_days=len(OPENS),
                requested_start=START.isoformat(), requested_end=END.isoformat(),
                history_calendar_days=900, warmup_trading_days=250, lookback_calendar_days=430,
                expected_raw_rows=SCALES[scale] * len(OPENS), seed=0,
                generator_version=VERSION, calendar_version=CALENDAR)


def validate_config(value):
    require(isinstance(value, dict) and value == config(value.get('scale')))
    require(all(type(value[k]) is int for k in ('stocks', 'trading_days', 'seed',
                'expected_raw_rows', 'history_calendar_days', 'warmup_trading_days',
                'lookback_calendar_days')))


def rows(table, cfg):
    """Stable table order; business payload only, excluding DB-generated IDs/defaults."""
    validate_config(cfg)
    require(table in TABLES)
    n = cfg['stocks']
    if table == 'trade_calendar':
        for day in DAYS:
            yield dict(cal_date=day.isoformat(), is_open=day.weekday() < 5, exchange='SSE')
    elif table == 'sector':
        yield dict(sector_id=101, source='SW', source_code='BIZ', name='synthetic', level='L1')
    elif table in ('stock_basic', 'sector_member'):
        for i in range(1, n + 1):
            code = f'{i:06d}.SZ'
            if table == 'stock_basic':
                yield dict(ts_code=code, name='synthetic', list_status='L',
                           list_date=FIRST.isoformat(), exchange='SZSE', updated_at=FROZEN)
            else:
                yield dict(sector_id=101, ts_code=code, valid_from=FIRST.isoformat())
    elif table not in ('stock_st_daily', 'stock_suspend_daily'):
        for day in OPENS:
            if table == 'data_quality_daily':
                for dataset in ('stock_st', 'suspend_d'):
                    yield dict(trade_date=day.isoformat(), dataset=dataset, status='PASS',
                               expected_rows=0, actual_rows=0, checked_at=FROZEN)
                continue
            codes = INDICES if table == 'index_daily' else (
                f'{i:06d}.SZ' for i in range(1, n + 1))
            for code in codes:
                row = dict(trade_date=day.isoformat(), ts_code=code)
                if table in ('stock_daily', 'index_daily'):
                    row.update(open=20, high=20.1, low=19.9, close=20, pre_close=20,
                               pct_chg=0, vol=100000, amount=1000000)
                    if table == 'stock_daily':
                        row['source_updated_at'] = FROZEN
                elif table == 'stock_adj_factor':
                    row['adj_factor'] = 1
                elif table == 'stock_daily_basic':
                    row.update(close=20, total_mv=1000000, circ_mv=1000000)
                elif table == 'stock_limit_daily':
                    row.update(pre_close=20, up_limit=22, down_limit=18,
                               created_at=FROZEN, updated_at=FROZEN)
                yield row


def chunks(stream, size):
    require(type(size) is int and 1 <= size <= 4096)
    while block := list(islice(stream, size)):
        yield block


def expected_counts(cfg):
    n, d = cfg['stocks'], len(OPENS)
    return dict(zip(TABLES, (len(DAYS), n, 1, n, n*d, n*d, n*d, n*d,
                             len(INDICES)*d, 0, 0, 2*d), strict=True))


def generate(cfg, output, *, chunk_size=256):
    validate_config(cfg)
    require(type(chunk_size) is int and 1 <= chunk_size <= 4096)
    output = Path(output)
    output.mkdir(exist_ok=False)
    wall, cpu = monotonic(), process_time()
    tables = {}
    for table in TABLES:
        h, count, length = hashlib.sha256(), 0, 0
        with (output / (table + '.jsonl')).open('xb') as f:
            for block in chunks(rows(table, cfg), chunk_size):
                for row in block:
                    data = canonical(row)
                    f.write(data)
                    h.update(data)
                    count += 1
                    length += len(data)
        require(count == expected_counts(cfg)[table])
        tables[table] = dict(rows=count, bytes=length, sha256=h.hexdigest())
    identity = dict(config=cfg, tables=tables)
    manifest = dict(**identity, dataset_sha256=sha(identity), total_rows=sum(
        t['rows'] for t in tables.values()), total_bytes=sum(t['bytes'] for t in tables.values()))
    # Resource metrics are observations, deliberately excluded from dataset identity.
    manifest['generation'] = dict(wall_seconds=monotonic()-wall, cpu_seconds=process_time()-cpu,
        peak_process_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (
            1 if sys.platform == 'darwin' else 1024), chunk_size=chunk_size)
    (output / 'manifest.json').write_bytes(canonical(manifest))
    return manifest


def validate_dataset(output):
    """Stream exact versioned business contract: detects missing/duplicate/out-of-order
    keys, bad ranges/nulls, and broken cross-table references without million-key sets.
    All supported datasets are fixed profiles; arbitrary distributions are unsupported.
    """
    output = Path(output)
    require(not output.is_symlink())
    require({p.name for p in output.iterdir()} == {'manifest.json'} | {
        t + '.jsonl' for t in TABLES})
    mpath = output / 'manifest.json'
    require(not mpath.is_symlink() and mpath.stat().st_size <= 65536)
    m = json.loads(mpath.read_bytes())
    require(set(m) == {'config', 'tables', 'dataset_sha256',
                       'total_rows', 'total_bytes', 'generation'})
    validate_config(m['config'])
    require(set(m['tables']) == set(TABLES))
    for record in m['tables'].values():
        require(isinstance(record, dict) and set(record) == {'rows', 'bytes', 'sha256'})
        require(all(type(record[k]) is int and record[k] >= 0 for k in ('rows', 'bytes')))
    require(all(type(m[k]) is int and m[k] >= 0 for k in ('total_rows', 'total_bytes')))
    generation = m['generation']
    require(isinstance(generation, dict) and set(generation) == {
        'wall_seconds', 'cpu_seconds', 'peak_process_rss_bytes', 'chunk_size'})
    require(all(type(generation[k]) in (float, int) and math.isfinite(generation[k])
                and generation[k] >= 0 for k in ('wall_seconds', 'cpu_seconds')))
    require(type(generation['peak_process_rss_bytes']) is int
            and generation['peak_process_rss_bytes'] > 0)
    require(type(generation['chunk_size']) is int and 1 <= generation['chunk_size'] <= 4096)
    for table in TABLES:
        path = output / (table + '.jsonl')
        require(path.is_file() and not path.is_symlink())
        h, count, length = hashlib.sha256(), 0, 0
        with path.open('rb') as f:
            for expected in rows(table, m['config']):
                data = f.readline(4096)
                # Canonical byte equality also refuses non-finite, unknown fields,
                # duplicate JSON keys, invalid stock/date/sector references and types.
                require(data == canonical(expected))
                h.update(data)
                count += 1
                length += len(data)
            require(not f.read(1))
        require(m['tables'][table] == dict(rows=count, bytes=length, sha256=h.hexdigest()))
    require(m['dataset_sha256'] == sha(dict(config=m['config'], tables=m['tables'])))
    require(m['total_rows'] == sum(expected_counts(m['config']).values())
            and m['total_bytes'] == sum(t['bytes'] for t in m['tables'].values()))
    return m


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scale', choices=tuple(SCALES))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--chunk-size', type=int, default=256)
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()
    if not args.validate_only:
        require(args.scale is not None)
        generate(config(args.scale), args.output, chunk_size=args.chunk_size)
    result = validate_dataset(args.output)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
