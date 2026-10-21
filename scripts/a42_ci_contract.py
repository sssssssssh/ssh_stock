"""Versioned CI partition contract; pure stdlib, no Settings or DB imports.

The legacy census is independently reconstructed in tests from the frozen Git
workflow and AST. Auxiliary same-job controls never replace required legacy keys.
"""

import hashlib
import json
from dataclasses import asdict, dataclass, replace

BASELINE_SHA = "02c69c6127860f72adaf79071a9a11930b69e411"
SCHEMA_VERSION = "v14-a4-2.1-shard-v1"
MATRIX_VERSION = "a421-matrix-v1"
VARIANTS = ("Q0_LEGACY_RAW", "Q0_SERVICE_CONTROL", "Q0_SAFETY_EQUIVALENT",
            "Q1_CURRENT", "Q2_CURRENT", "S3", "S3_INLINE", "S3_KEYS", "S4", "S5")
FRACTIONS = ("0.1", "1.0")
WINDOWS = (None, 1, 3, 5, 10, 20)
COVERAGES = ("partial", "a_only", "b_only", "high", "mismatched")
TOMBSTONES = (0, 1, 10)
SHAPE_VARIANTS = ("Q0_SAFETY_EQUIVALENT", "Q1_CURRENT", "S3_KEYS", "S4", "S5")
READER_VARIANTS = ("Q0_SAFETY_EQUIVALENT", "Q1_CURRENT", "S3_KEYS", "S5")
EVENT_VARIANTS = ("Q0_SAFETY_EQUIVALENT", "Q1_CURRENT", "E3")
CAPACITY_LEVELS = {"L1": (10, 2), "L2": (5000, 20), "L3-scaled-10pct": (500, 120)}
SCALES = {"10k": (10000, 5253, 10895), "100k": (100000, 52529, 108949),
          "million": (2570000, 1350000, 2800000)}
MONTHLY_PLAN_GROUPS = (VARIANTS[1:4], VARIANTS[4:7], VARIANTS[7:10])


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class Group:
    scale: str
    kind: str
    variant: str
    fraction: str
    scope: str
    window_days: int | None = None
    repeat: int | None = None
    coverage: str = "partial"
    tombstones: int = 1
    readers: int = 0
    auxiliary: bool = False

    @property
    def id(self):
        return digest(asdict(self))


def primary_groups(scale):
    reads = {Group(scale, "read", v, f, "full", repeat=r)
             for v in VARIANTS for f in FRACTIONS for r in range(3)}
    reads |= {Group(scale, "read", "S3", f, "window_matrix", w, r)
              for f in FRACTIONS for w in WINDOWS for r in range(3)}
    reads |= {Group(scale, "read", v, "0.1", f"month_{m}", repeat=r)
              for v in VARIANTS[1:] for m in (1, 2, 3) for r in range(3)}
    return reads | {replace(g, kind="plan", repeat=None) for g in reads}


def legacy_groups():
    groups = set().union(*(primary_groups(s) for s in SCALES))
    # Shape partial/1 is a separate experiment, even though the fixture recipe
    # matches primary 10k. A separate scope prevents accidental deduplication.
    groups |= {Group("10k", "read", v, "0.1", "shape", repeat=r,
                     coverage=c, tombstones=t)
               for c in COVERAGES for t in TOMBSTONES for v in SHAPE_VARIANTS
               for r in range(3)}
    groups |= {Group("100k", "read", v, f, "event_full", repeat=r)
               for v in EVENT_VARIANTS for f in FRACTIONS for r in range(3)}
    groups |= {Group("100k", "read", v, "0.1", f"event_month_{m}", repeat=r)
               for v in EVENT_VARIANTS for m in (1, 2, 3) for r in range(3)}
    groups |= {Group("million", "read", v, f, "readers", repeat=r, readers=2)
               for v in READER_VARIANTS for f in FRACTIONS for r in range(3)}
    return groups


@dataclass(frozen=True)
class Shard:
    job_id: str
    scope: str
    scale: str
    timeout_minutes: int
    fraction: str | None = None
    coverage: str | None = None
    plan_kind: str | None = None
    plan_shard: int | None = None


def shards():
    result = [Shard(f"a42-small-{s}", "small", s, 120) for s in ("10k", "100k")]
    for n, f in enumerate(FRACTIONS):
        result += [Shard(f"a42-million-full-{n}", "million-full", "million", 240, f),
                   Shard(f"a42-million-window-{n}", "million-window", "million", 240, f)]
        for kind in ("full", "window_matrix"):
            result.append(Shard(f"a42-million-plans-{kind}-{n}", "million-plans",
                                "million", 240, f, plan_kind=kind))
    result += [Shard("a42-million-monthly", "million-monthly", "million", 300),
               Shard("a42-million-readers", "million-readers", "million", 240)]
    result += [Shard(f"a42-million-plans-monthly-{n}", "million-plans", "million", 240,
                     "0.1", plan_kind="monthly", plan_shard=n) for n in range(3)]
    result += [Shard(f"a42-shapes-{c}", "supplemental-shapes", "10k", 120, coverage=c)
               for c in COVERAGES]
    result.append(Shard("a42-event-prototype", "event-prototype", "100k", 120))
    return tuple(result)


def expected_groups(shard):
    primary = primary_groups(shard.scale)
    if shard.scope == "small":
        return primary
    if shard.scope == "million-full":
        return {g for g in primary if g.kind == "read" and g.scope == "full"
                and g.fraction == shard.fraction}
    if shard.scope == "million-window":
        windows = {g for g in primary if g.kind == "read" and g.scope == "window_matrix"
                   and g.fraction == shard.fraction}
        controls = {Group("million", "read", "Q0_SAFETY_EQUIVALENT", shard.fraction,
                          "window_baseline", repeat=r, auxiliary=True) for r in range(3)}
        return windows | controls
    if shard.scope == "million-monthly":
        return {g for g in primary if g.kind == "read" and g.scope.startswith("month_")}
    if shard.scope == "million-plans":
        if shard.plan_kind == "monthly":
            return {g for g in primary if g.kind == "plan" and g.scope.startswith("month_")
                    and g.variant in MONTHLY_PLAN_GROUPS[shard.plan_shard]}
        return {g for g in primary if g.kind == "plan" and g.scope == shard.plan_kind
                and g.fraction == shard.fraction}
    if shard.scope == "million-readers":
        return {g for g in legacy_groups() if g.scope == "readers"}
    if shard.scope == "supplemental-shapes":
        return {g for g in legacy_groups() if g.scope == "shape" and g.coverage == shard.coverage}
    if shard.scope == "event-prototype":
        return {g for g in legacy_groups() if g.scope.startswith("event_")}
    raise ValueError("A421_UNKNOWN_SCOPE")


def matrix():
    result = {s.job_id: expected_groups(s) for s in shards()}
    assigned = [g for groups in result.values() for g in groups if not g.auxiliary]
    if len(assigned) != len(set(assigned)) or set(assigned) != legacy_groups():
        raise ValueError("A421_PARTITION_NOT_EXACT")
    return result


def fixture_recipe(group):
    return dict(matrix_version=MATRIX_VERSION, scale=group.scale,
                counts=dict(zip(("a", "b", "other_b"), SCALES[group.scale], strict=True)),
                coverage=group.coverage, tombstones=group.tombstones,
                readers=group.readers, model="frozen-0058-stock-trade-status",
                layout="stock-major-257-typed-factor-other-root", statement_timeout_ms=300000,
                resource_class="a42-pg17-2cpu-3g", read_flag=False)


def as_json():
    return dict(schema_version=MATRIX_VERSION, baseline_sha=BASELINE_SHA,
                shards=[dict(**asdict(s), groups=[dict(id=g.id, **asdict(g)) for g in
                       sorted(expected_groups(s), key=lambda g:g.id)]) for s in shards()],
                mandatory_group_count=len(legacy_groups()),
                auxiliary_group_count=sum(g.auxiliary for v in matrix().values() for g in v),
                capacity={k: dict(stocks=v[0], days=v[1]) for k,v in CAPACITY_LEVELS.items()})


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Dump every versioned required key and owner")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    from scripts.a42_artifacts import atomic

    atomic(args.output, as_json())
