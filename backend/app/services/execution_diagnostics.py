"""Opt-in bounded timing evidence; no SQL, rows, parameters or connection data."""

import math
import re
import threading
from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar
from time import monotonic

active_diagnostics = ContextVar("execution_diagnostics", default=None)
PHASES = frozenset(("query", "fetch", "frame", "compute", "prepare", "store", "commit",
                   "lookup_candidate", "lookup_published", "replace", "materialize"))
TABLES = frozenset(("stock_daily", "stock_basic", "stock_st_daily", "stock_suspend_daily",
    "stock_limit_daily", "stock_trade_status_daily", "stock_factor_daily", "market_daily",
    "sector_factor_daily", "theme_factor_daily", "stock_state_daily", "stock_opportunity_daily",
    "strategy_signal", "signal_forward_eval", "data_quality_daily", "adj_factor", "daily_basic",
    "trade_status", "index_daily", "factors", "members", "theme_daily", "theme_moneyflow_daily",
    "theme_limit_daily", "theme_members", "sector_members", "sector_factors", "previous_states",
    "market", "compute", "signals", "rows", "replace", "commit", "input_verify", "input_frame",
    "raw_prerequisites", "cross_table_quality", "signal_eval", "verify", "count", "tables",
    "states", "stock_factors"))
ALLOWED_NAMES = TABLES | frozenset(f"{domain}.{label}" for domain in (
    "trade_status", "factors", "market", "sector", "theme", "trend", "opportunity",
    "recalculation", "publication") for label in TABLES)


class ExecutionDiagnostics:
    def __init__(self):
        self.totals = {}
        self.recent = deque(maxlen=32)
        self._lock = threading.RLock()
        self.dropped_metrics = 0

    def record(self, name, phase, seconds, *, rows=0, error=None):
        if (not re.fullmatch(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)?", name)
                or len(name) > 80 or name not in ALLOWED_NAMES or phase not in PHASES
                or type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0
                or type(rows) is not int or rows < 0):
            raise ValueError("DIAGNOSTIC_LABEL_INVALID")
        with self._lock:
            self._record(name, phase, seconds, rows, error)

    def _record(self, name, phase, seconds, rows, error):
        key = (name, phase)
        if key not in self.totals and len(self.totals) >= 128:
            self.dropped_metrics += 1
            return
        code = getattr(getattr(error, "orig", None), "sqlstate", None)
        code = code if isinstance(code, str) and re.fullmatch(r"[A-Z0-9]{5}", code) else None
        metric = self.totals.setdefault(key, dict(calls=0, seconds=0.0, rows=0, failures=0))
        metric["calls"] += 1
        metric["seconds"] += seconds
        metric["rows"] += rows
        metric["failures"] += int(error is not None)
        self.recent.append(dict(name=name, phase=phase, seconds=seconds, rows=rows,
                                failed=error is not None, sqlstate=code))

    def snapshot(self):
        from app.services.calculation_memory import available_memory_bytes, process_memory_bytes

        rss, peak = process_memory_bytes()
        with self._lock:
            phases = [dict(name=name, phase=phase, **value)
                      for (name, phase), value in self.totals.items()]
            recent = [dict(event) for event in self.recent]
            dropped = self.dropped_metrics
        coverage = {}
        for label, predicate in {
            "raw_preflight": lambda x: x["name"] in {
                "raw_prerequisites", "recalculation.raw_prerequisites"},
            "trade_status_read": lambda x: x["name"].startswith("trade_status.")
                and x["phase"] in {"query", "fetch", "frame"},
            "trade_status_compute": lambda x: x["name"] == "trade_status.compute",
            "trade_status_materialize": lambda x: x["name"] == "trade_status.rows",
            "trade_status_replace": lambda x: x["name"] == "trade_status.replace",
            "candidate_lookup": lambda x: x["name"] in TABLES
                and x["phase"] == "lookup_candidate",
            "candidate_store": lambda x: x["name"] in TABLES and x["phase"] == "store",
            "factor_window": lambda x: x["name"] in {"factors.input_verify", "factors.input_frame"},
            "factor_compute": lambda x: x["name"] == "factors.compute",
            "publish": lambda x: x["name"].startswith("publication."),
        }.items():
            coverage[label] = ("RECORDED" if any(predicate(x) for x in phases)
                               else "NOT_INSTRUMENTED")
        return dict(phases=phases, recent=recent, coverage=coverage,
                    dropped_metrics=dropped,
                    aggregation="NESTED_PHASES_DO_NOT_SUM",
                    fetch_semantics="SERVER_CURSOR_TRANSPORT_AND_PYTHON_MATERIALIZATION",
                    rss_bytes=rss, peak_rss_bytes=peak,
                    available_memory_bytes=available_memory_bytes(),
                    memory_kind="POSIX_PEAK_IS_CONSERVATIVE_ON_MACOS")


def record_duration(name, phase, seconds, *, rows=0, error=None):
    observer = active_diagnostics.get()
    if observer is not None:
        try:
            observer.record(name, phase, seconds, rows=rows, error=error)
        except ValueError:
            # Unregistered/invalid evidence stays missing, never modifies results
            # or masks the original failure/cancellation during observer cleanup.
            with observer._lock:
                observer.dropped_metrics += 1


@contextmanager
def operation(name, phase):
    if active_diagnostics.get() is None:
        yield
        return
    started, error = monotonic(), None
    try:
        yield
    except BaseException as exc:
        error = exc
        raise
    finally:
        record_duration(name, phase, monotonic()-started, error=error)
