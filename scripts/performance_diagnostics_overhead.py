"""Fixed offline CPU fixture: timer overhead only, NOT root/PG performance acceptance."""

import argparse
import json
import statistics
import tempfile
from pathlib import Path
from time import perf_counter

from app.services.performance_diagnostics import Trace, active_trace, span


def measure():
    observations = []
    for pair in range(3):
        for enabled in ((False, True) if pair % 2 == 0 else (True, False)):
            began = perf_counter()
            trace = Trace("synthetic-cpu-fixture") if enabled else None
            token = active_trace.set(trace)
            try:
                with span("factor.compute"):
                    output = sum((i * i) % 7919 for i in range(2_000_000))
                if trace:
                    trace.status = "success"
                    with tempfile.TemporaryDirectory() as directory:
                        trace.flush(directory)
            finally:
                active_trace.reset(token)
            observations.append(dict(pair=pair + 1, enabled=enabled,
                                     wall_ms=(perf_counter() - began) * 1000, output=output))
    medians = {label: statistics.median(x["wall_ms"] for x in observations
        if x["enabled"] == enabled) for label, enabled in (("off", False), ("on", True))}
    return dict(evidence_kind="OFFLINE_CPU_TIMER_ONLY_NOT_ROOT_ACCEPTANCE",
        observations=observations, medians_ms=medians,
        overhead_percent=(medians["on"] / medians["off"] - 1) * 100,
        outputs_equal=len({x["output"] for x in observations}) == 1,
        database_calls=0, root_overhead_acceptance="NOT_MEASURED")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(measure(), handle, indent=2)


if __name__ == "__main__":
    main()
