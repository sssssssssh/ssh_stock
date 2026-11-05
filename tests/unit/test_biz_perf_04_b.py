"""Offline small-profile contracts; large generation is explicit CLI only."""

import ast
import copy
import json
import tracemalloc
from datetime import UTC, datetime, timedelta
from itertools import islice
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import business_synthetic_dataset as d


@pytest.mark.parametrize('scale,n', [('S1', 2660), ('S2', 99750),
                                    ('S3', 500080), ('S4', 1439725)])
def test_profiles(scale, n):
    cfg = d.config(scale)
    d.validate_config(cfg)
    assert cfg['expected_raw_rows'] == n
    assert len(d.OPENS) == 665
    assert (d.START - d.FIRST).days == 900
    assert sum(day < d.START for day in d.OPENS) >= 250
    assert d.FIRST <= d.START.replace(day=1) - timedelta(days=430)
    assert d.expected_counts(cfg)['stock_daily'] == n


def test_s1_matches_original_seed_business_payload_without_database():
    from app.models import market_data as m
    from sqlalchemy import DateTime, insert

    source = ast.parse(Path('scripts/business_recalc_measure.py').read_text())
    seed = next(n for n in ast.walk(source) if isinstance(n, ast.FunctionDef)
                and n.name == 'seed_rows')
    block = next(n for n in ast.walk(source) if isinstance(n, ast.With)
                 and ast.unparse(n.items[0].context_expr) == 'factory()'
                 and any(isinstance(x, ast.For) and 'day_index' in ast.unparse(x.target)
                         for x in n.body))
    captured = {name: [] for name in d.TABLES}

    class DB:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, stmt, rows):
            # ORM bulk insert only persists mapped table fields.
            captured[stmt.table.name].extend(copy.deepcopy([
                {k: v for k, v in row.items() if k in stmt.table.c} for row in rows]))

        def flush(self):
            pass

        def commit(self):
            pass

        def scalar(self, *args):
            return '17'

    env = dict(DateTime=DateTime, insert=insert, m=m, factory=DB,
               frozen=datetime(2026, 10, 27, tzinfo=UTC), first=d.FIRST,
               days=d.DAYS, opens=d.OPENS, codes=[f'{i:06d}.SZ' for i in range(1, 5)],
               settings=SimpleNamespace(strategy={'benchmark': {'market_indices': d.INDICES}}),
               report={}, channel=None, text=lambda s: s)
    exec(compile(ast.Module(body=[seed, block], type_ignores=[]), 'old-seed', 'exec'), env)
    for row in captured['trade_calendar']:
        row['exchange'] = 'SSE'  # ORM default, not an extra business fact.
    for table in d.TABLES:
        old = json.loads(json.dumps(captured[table], default=lambda x: x.isoformat()))
        assert old == list(d.rows(table, d.config('S1')))


def test_chunk_size_and_repeat_do_not_change_digest(tmp_path):
    manifests = [d.generate(d.config('S1'), tmp_path / str(i), chunk_size=n)
                 for i, n in enumerate((1, 17, 4096))]
    assert len({m['dataset_sha256'] for m in manifests}) == 1
    for i, m in enumerate(manifests):
        assert d.validate_dataset(tmp_path / str(i)) == m
        assert m['total_rows'] == 14905


@pytest.mark.parametrize('field,value', [('stocks', 5), ('seed', 1), ('seed', False),
    ('generator_version', 'other'), ('calendar_version', 'real'),
    ('expected_raw_rows', 0), ('requested_start', '2024-01-01')])
def test_unregistered_input_refused(field, value):
    cfg = d.config('S1')
    cfg[field] = value
    with pytest.raises(ValueError):
        d.validate_config(cfg)


@pytest.mark.parametrize('size', [0, -1, 4097, True, 1.5])
def test_chunk_limit(size):
    with pytest.raises(ValueError):
        next(d.chunks(iter([1]), size))


@pytest.mark.parametrize('mutation',
                         ['duplicate', 'missing', 'price', 'reference', 'hash', 'extra'])
def test_corruption_refused(tmp_path, mutation):
    root = tmp_path / 'data'
    manifest = d.generate(d.config('S1'), root)
    path = root / ('sector_member.jsonl' if mutation == 'reference' else 'stock_daily.jsonl')
    lines = path.read_bytes().splitlines(keepends=True)
    if mutation == 'duplicate':
        lines[1] = lines[0]
    elif mutation == 'missing':
        lines.pop()
    elif mutation in ('price', 'reference'):
        row = json.loads(lines[0])
        row['sector_id' if mutation == 'reference' else 'close'] = -1
        lines[0] = d.canonical(row)
    elif mutation == 'hash':
        manifest['dataset_sha256'] = '0' * 64
        (root / 'manifest.json').write_bytes(d.canonical(manifest))
    else:
        (root / 'unknown').write_text('unexpected')
    path.write_bytes(b''.join(lines))
    with pytest.raises(ValueError):
        d.validate_dataset(root)


def test_buffer_bound_not_dataset_size():
    tracemalloc.start()
    try:
        # S4 producer is lazy, test only a prefix in ordinary CI.
        for block in islice(d.chunks(d.rows('stock_daily', d.config('S4')), 17), 100):
            assert len(block) == 17
        _, peak = tracemalloc.get_traced_memory()
        assert peak < 2 * 1024**2
    finally:
        tracemalloc.stop()


def test_generator_has_no_business_or_database_imports():
    source = ast.parse(Path(d.__file__).read_text())
    names = [n.module for n in ast.walk(source) if isinstance(n, ast.ImportFrom)]
    assert not any(n and n.startswith(('app', 'sqlalchemy', 'psycopg')) for n in names)
    assert not hasattr(d, 'execute_claimed_job')


@pytest.mark.parametrize('mutation', ['boolean_count', 'nonfinite_resource', 'bad_chunk'])
def test_manifest_metadata_is_typed_and_bounded(tmp_path, mutation):
    root = tmp_path / 'data'
    m = d.generate(d.config('S1'), root)
    if mutation == 'boolean_count':
        m['tables']['stock_st_daily']['rows'] = False
    elif mutation == 'nonfinite_resource':
        m['generation']['wall_seconds'] = float('nan')
    else:
        m['generation']['chunk_size'] = 999999
    (root / 'manifest.json').write_text(json.dumps(m))
    with pytest.raises(ValueError):
        d.validate_dataset(root)
