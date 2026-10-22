"""Passive, bounded diagnostic metrics; no GC policy changes or app imports."""

import gc
import re
import statistics
import sys
import tracemalloc
from time import perf_counter

from scripts.a42_receipt_contract import require

CONDITIONS = (("C0", "full"), ("C1", "full"), ("C0", "minimal"), ("C1", "minimal"))
WILLIAMS = ((0, 1, 3, 2), (1, 2, 0, 3), (2, 3, 1, 0), (3, 0, 2, 1))
REGIMES = ("as_seeded", "analyzed")
ROUNDS = 8


def schedule(block):
    require(block in (0, 1), "A4231_UNREGISTERED_BLOCK")
    return [(round_, position, *CONDITIONS[condition]) for round_ in range(ROUNDS)
            for position, condition in enumerate(
                WILLIAMS[round_ % 4] if block == 0 else reversed(WILLIAMS[round_ % 4]))]


def function_labels():
    """Only bounded identifier names, never locals, arguments, paths or source."""
    labels = []
    frame = sys._getframe(1)
    try:
        for _ in range(6):
            if frame is None:
                break
            name = frame.f_code.co_name
            labels.append(name if re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]{0,63}", name)
                          else "GENERATED_FUNCTION")
            frame = frame.f_back
    finally:
        del frame
    return labels


class NaturalGC:
    """Record natural events; callbacks never throw or inspect a whole heap."""

    def __init__(self):
        self.events, self.pending = [], None
        self.phase, self.overflow, self.invalid = "outside_wall", 0, False

    def callback(self, phase, info):
        if phase == "start":
            if self.pending is not None:
                self.invalid = True
            self.pending = (perf_counter(), info["generation"], self.phase,
                            sys.getallocatedblocks(), function_labels())
        elif phase == "stop":
            ended = perf_counter()
            if self.pending is None:
                self.invalid = True
                return
            started, generation, label, blocks, stack = self.pending
            self.pending = None
            if len(self.events) >= 256:
                self.overflow += 1
                return
            self.events.append(dict(started=started, ended=ended, seconds=ended-started,
                generation=generation, phase=label, allocated_blocks_start=blocks,
                collected=info["collected"], uncollectable=info["uncollectable"],
                function_labels=stack))

    def __enter__(self):
        self.enabled, self.thresholds = gc.isenabled(), gc.get_threshold()
        self.registered = self.callback
        gc.callbacks.append(self.registered)
        return self

    def __exit__(self, *error):
        gc.callbacks.remove(self.registered)
        self.registered = None
        require(gc.isenabled() == self.enabled and gc.get_threshold() == self.thresholds,
                "A4231_GC_POLICY_CHANGED")
        require(not self.invalid and self.pending is None and not self.overflow,
                "A4231_GC_EVENTS_INCOMPLETE")

    def wall_events(self, started, ended):
        return [dict(**event, fully_inside_wall=event["started"] >= started
                     and event["ended"] <= ended) for event in self.events]


def memory_state():
    from scripts.ab_read_resources_v14_a4_2 import current_rss_bytes

    current, peak = tracemalloc.get_traced_memory()
    return dict(gc_enabled=gc.isenabled(), gc_thresholds=gc.get_threshold(),
        gc_count=gc.get_count(), generation_stats=gc.get_stats(),
        allocated_blocks=sys.getallocatedblocks(), traced_current_bytes=current,
        process_traced_peak_bytes=peak, current_rss_bytes=current_rss_bytes(),
        object_count="NOT_AVAILABLE_NO_FULL_HEAP_ENUMERATION",
        scope="PROCESS_STATE_OUTSIDE_WALL_PEAK_IS_PROCESS_LIFETIME")


def allocation_summary():
    """One end-of-process snapshot, only paths normalized to safe module labels."""
    rows = []
    for stat in tracemalloc.take_snapshot().statistics("lineno")[:8]:
        frame = stat.traceback[0]
        name = frame.filename.replace("\\", "/")
        if "/site-packages/" in name:
            name = name.split("/site-packages/", 1)[1]
        elif "/scripts/" in name:
            name = "scripts/"+name.rsplit("/scripts/", 1)[1]
        else:
            name = name.rsplit("/", 1)[-1]
        if not re.fullmatch(r"[A-Za-z0-9_./-]{1,160}", name):
            name = "GENERATED_OR_OTHER_MODULE"
        rows.append(dict(module=name, line=frame.lineno, bytes=stat.size, blocks=stat.count))
    return rows


def distribution(values):
    require(len(values) >= 5, "A4231_TOO_FEW_DIAGNOSTIC_SAMPLES")
    cuts = statistics.quantiles(values, n=100, method="inclusive")
    return dict(count=len(values), p50=statistics.median(values),
                p90=cuts[89], p95=cuts[94], p99=cuts[98])


def summarize(samples):
    groups = []
    for regime in REGIMES:
        for variant, mode in CONDITIONS:
            rows = [s for s in samples if (s["statistics"], s["variant"], s["observer_mode"])
                    == (regime, variant, mode)]
            if rows:
                groups.append(dict(statistics=regime, variant=variant, observer_mode=mode,
                    **distribution([s["wall_seconds"] for s in rows]),
                    gc_generations={str(g):sum(e["generation"] == g and e["fully_inside_wall"]
                        for s in rows for e in s["gc_events"]) for g in range(3)},
                    scope="A4231_DIAGNOSTIC_ONLY_NOT_FORMAL_P95_ACCEPTANCE"))
    return groups


def telemetry_checks(samples):
    """Frozen mechanistic checks, not automatic causal or production approval."""
    checks = []
    for regime in REGIMES:
        for block in (0, 1):
            for variant in ("C0", "C1"):
                rows = {mode:[s for s in samples if (s["statistics"], s["block"], s["variant"],
                    s["observer_mode"]) == (regime, block, variant, mode)]
                    for mode in ("full", "minimal")}
                require(all(len(r) == ROUNDS for r in rows.values()), "A4231_BLOCK_INCOMPLETE")
                p95 = {mode:distribution([r["wall_seconds"] for r in values])["p95"]
                       for mode, values in rows.items()}
                burden = {mode:sum(e["seconds"] for r in values for e in r["gc_events"]
                    if e["fully_inside_wall"] and e["generation"] == 2)
                    for mode, values in rows.items()}
                long_full = sum(e["seconds"] >= .05 and e["generation"] == 2
                    and e["fully_inside_wall"] for r in rows["full"] for e in r["gc_events"])
                allocated = {mode:statistics.median([
                    r["memory_after_enter"]["allocated_blocks"]
                    - r["memory_before_enter"]["allocated_blocks"] for r in values])
                    for mode, values in rows.items()}
                checks.append(dict(statistics=regime, block=block, variant=variant,
                    p95=p95, generation2_wall_seconds=burden, full_long_gen2_events=long_full,
                    observer_enter_allocated_blocks=allocated,
                    preregistered_check_pass=(p95["full"]-p95["minimal"] >= .04
                        and long_full > 0 and burden["full"] > burden["minimal"]
                        and allocated["full"] > allocated["minimal"])))
    return dict(checks=checks, all_preregistered_conditions_met=all(
        c["preregistered_check_pass"] for c in checks),
        conclusion="REQUIRES_MECHANISM_AND_COUNTEREXAMPLE_REVIEW_NOT_AUTOMATIC_CAUSAL_CLAIM")
