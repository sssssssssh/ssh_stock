"""Offline reader ports; never install hooks or discover a process/database.

Clock: injected monotonic integer milliseconds. CPU: cumulative process CPU ms,
delta computed by R2. RSS: process-lifetime high-water mark observed at return,
not an allocation attributed exclusively to the root. SQL: existing RootCounts
attempts; driver FETCH: independent aggregate observations, never stage sums.
Inclusive stages and SQL/FETCH may overlap: DO_NOT_SUM.
"""

from typing import Protocol

from scripts import biz_perf_p1_04_measure_wiring as w


class ClockPort(Protocol):
    def ms(self) -> int: ...


class CumulativeCpuPort(Protocol):
    def __call__(self) -> int | str: ...


class PeakRssPort(Protocol):
    def __call__(self) -> int | str: ...


class DriverFetchPort(Protocol):
    def __call__(self) -> dict: ...


class RootSqlPort(Protocol):
    def begin(self, operation: str) -> bool: ...
    def end(self) -> None: ...
    def freeze(self) -> dict: ...


def _uint(value):
    return type(value) is int and 0 <= value <= 2**63 - 1


class CollectorPorts:
    """Missing/failed reads preserve UNKNOWN, including a valid numeric zero.

    Coverage is sticky on read failure. Readers are trusted, synchronous offline
    injections, not background samplers. R2 owns their return boundary and calls
    them only once there (plus CPU at root start). No post-return re-sampling.
    """

    def __init__(self, *, cpu_reader: CumulativeCpuPort | None = None,
                 rss_reader: PeakRssPort | None = None,
                 fetch_reader: DriverFetchPort | None = None):
        self._cpu = cpu_reader
        self._rss = rss_reader
        self._fetch = fetch_reader
        self.coverage = dict.fromkeys(("cpu", "rss", "fetch"), "NOT_INSTRUMENTED")
        self._failed = set()
        self.stats = w.ProcessStats(cpu_reader=lambda: self._read("cpu", self._cpu),
                                    rss_reader=lambda: self._read("rss", self._rss))

    def _read(self, name, reader):
        if reader is None or name in self._failed:
            return w.UNKNOWN
        try:
            result = reader()
            if not _uint(result):
                raise ValueError
        except Exception:
            self._failed.add(name)
            self.coverage[name] = w.UNKNOWN
            return w.UNKNOWN
        self.coverage[name] = w.RECORDED
        return result

    def fetch(self):
        unknown = dict(observed_ms=w.UNKNOWN, rows=w.UNKNOWN)
        if self._fetch is None or "fetch" in self._failed:
            return unknown
        try:
            result = self._fetch()
            if (type(result) is not dict or set(result) != {"observed_ms", "rows"}
                    or not all(_uint(value) for value in result.values())
                    or result["observed_ms"] > w.MAX_ELAPSED_MS):
                raise ValueError
        except Exception:
            self._failed.add("fetch")
            self.coverage["fetch"] = w.UNKNOWN
            return unknown
        self.coverage["fetch"] = w.RECORDED
        return dict(result)
