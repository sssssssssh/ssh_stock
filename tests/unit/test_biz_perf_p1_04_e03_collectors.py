"""Return-boundary collectors use only fake clocks and injected readers."""

import pytest

from scripts import biz_perf_p1_04_measure_wiring as w


def test_fetch_injection_closes_with_r2_return():
    clock = w.FakeClock()
    samples = []
    value = dict(observed_ms=2, rows=7)

    def fetch():
        samples.append(dict(value))
        return dict(value)

    executor = w.OfflineExecutor()
    sink = w.ListSink()
    recorder = w.OfflineRootRecorder(
        contract=w.build_preflight(), clock=clock, stats=w.ProcessStats(),
        sink=sink, executor=executor, fetch_reader=fetch,
    )
    executor.current_root_id = recorder.root_id_factory()
    recorder.run_offline(stages=w.DEFAULT_STAGES)
    value.update(observed_ms=99, rows=999)
    clock.advance(100)
    assert recorder.counts().begin("UPDATE") is False
    frozen = recorder.freeze_root()
    assert frozen["fetch_observed_ms"] == 2
    assert frozen["fetched_rows"] == 7
    assert frozen["elapsed_ms"] == 20
    assert samples == [dict(observed_ms=2, rows=7)]


@pytest.mark.parametrize("reader", [None, lambda: (_ for _ in ()).throw(OSError("PRIVATE")),
                                   lambda: -1, lambda: True])
def test_reader_failure_is_unknown(reader):
    from scripts.biz_perf_p1_04_e03_collectors import CollectorPorts

    ports = CollectorPorts(cpu_reader=reader, rss_reader=reader, fetch_reader=reader)
    assert ports.stats.cpu_ms() == "UNKNOWN"
    assert ports.stats.rss_peak_bytes() == "UNKNOWN"
    assert ports.fetch() == dict(observed_ms="UNKNOWN", rows="UNKNOWN")
    assert all(value in {"UNKNOWN", "NOT_INSTRUMENTED"}
               for value in ports.coverage.values())


def test_zero_and_cpu_delta_are_distinct_from_unknown():
    from scripts.biz_perf_p1_04_e03_collectors import CollectorPorts

    ports = CollectorPorts(cpu_reader=lambda: 0, rss_reader=lambda: 0,
                           fetch_reader=lambda: dict(observed_ms=0, rows=0))
    assert ports.stats.cpu_ms() == ports.stats.rss_peak_bytes() == 0
    assert ports.fetch() == dict(observed_ms=0, rows=0)
    assert set(ports.coverage.values()) == {"RECORDED"}


def test_fetch_reader_side_effects_cannot_enter_cpu_sql_or_wall():
    clock = w.FakeClock()
    cpu = [100]
    holder = []

    def fetch():
        cpu[0] = 900
        clock.advance(100)
        assert holder[0].counts().begin("UPDATE") is False
        return dict(observed_ms=1, rows=1)

    sink = w.ListSink()
    executor = w.OfflineExecutor()
    recorder = w.OfflineRootRecorder(
        contract=w.build_preflight(), clock=clock,
        stats=w.ProcessStats(cpu_reader=lambda: cpu[0]), sink=sink,
        fetch_reader=fetch, executor=executor,
    )
    holder.append(recorder)
    executor.current_root_id = recorder.root_id_factory()
    recorder.run_offline(stages=w.DEFAULT_STAGES)
    frozen = recorder.freeze_root()
    assert frozen["process_cpu_ms"] == 0
    assert frozen["sql_counts"] == {}
    assert frozen["elapsed_ms"] == 20
