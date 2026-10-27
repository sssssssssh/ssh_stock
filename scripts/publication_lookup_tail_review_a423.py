"""Offline historical evidence replay, not a new measurement or capacity receipt.

No application imports, environment-file loading, database connection, GC changes,
or performance retries. The pinned archive is read in memory, never extracted.
"""

import argparse
import hashlib
import json
import math
import statistics
import sys
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.a42_artifacts import atomic, header  # noqa: E402
from scripts.a42_receipt_contract import physical, require  # noqa: E402
from scripts.publication_lookup_diagnostic_a422 import (  # noqa: E402
    TABLES,
    VARIANTS,
    performance_decision,
    summarize,
    whole_workloads,
)

SOURCE_SHA = "44e46b0cf4b52b2e7008e1f9ed842cd251971864"
SOURCE_RUN = "39785757520"
SOURCE_ARTIFACT = 12429939366
SOURCE_DIGEST = "e2ceaf9137e0ce52c0d91201329bf0de15a4cd14ab6321aaebf74e069ba4eceb"
C0_SOURCE = "7708d91c831a64093f18aa4f8515789492762f464ccfe202ee0219b756f32976"
C1_SOURCE = "5409c99ed43ca4d306e441a12736fb866c9f920e38e4b81d9d465a242eb18964"
INPUT_HASHES = {
    "stock_opportunity_daily": "e227f85d7f5c18420f7bf08f6af6f41c1c78d225e52e6dd2013324918d768e67",
    "signal_forward_eval": "764100b8d53aad66754c512fe775d4d68e8601f9dae4706392c8781b63bfa524",
    "stock_trade_status_daily": "f7a11ade5c21e70867378f342946f570fb914ffdbd73b385adaea91846e51ed3",
}
REGIMES = ("as_seeded", "analyzed")
METRICS = ("execute_seconds", "buffered_row_materialization_seconds",
           "python_json_seconds", "gc_seconds", "gc_count")
BLOCKERS = ("HISTORICAL_EVIDENCE_ONLY", "P95_REGRESSION", "CORRELATED_NOT_CAUSAL",
            "NO_APPROVED_REPAIR_CANDIDATE", "PRODUCTION_NOT_VERIFIED_CANDIDATE")


def load_source(archive):
    require(archive.stat().st_size < 10_000_000, "A423_ARCHIVE_TOO_LARGE")
    require(hashlib.sha256(archive.read_bytes()).hexdigest() == SOURCE_DIGEST,
            "A423_ARCHIVE_DIGEST_MISMATCH")
    with ZipFile(archive) as zipped:
        require(zipped.namelist().count("lookup/lookup.json") == 1,
                "A423_SOURCE_FILE_AMBIGUOUS")
        member = zipped.getinfo("lookup/lookup.json")
        require(member.file_size < 20_000_000, "A423_SOURCE_TOO_LARGE")
        raw = zipped.read(member)
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def expected_order():
    result = []
    variants = list(VARIANTS)
    for regime in REGIMES:
        for table in TABLES:
            for repeat in range(100 if table == TABLES[2] else 5):
                rotation = repeat % len(variants)
                for variant in variants[rotation:]+variants[:rotation]:
                    result.append((regime, table, variant, repeat))
    return result


def quantiles(values):
    require(len(values) >= 5, "A423_MISSING_REPEATS")
    cuts = statistics.quantiles(values, n=100, method="inclusive")
    return dict(p50=statistics.median(values), p90=cuts[89], p95=cuts[94], p99=cuts[98])


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate_source(value):
    require(value.get("head_sha") == SOURCE_SHA and value.get("run_id") == SOURCE_RUN
            and str(value.get("attempt")) == "1"
            and value.get("job_id") == "a422-lookup-diagnosis"
            and value.get("working_tree_dirty") is False
            and value.get("status") == "COMPLETE"
            and value.get("artifact_kind") == "DIAGNOSTIC_ONLY"
            and value.get("formal_capacity_complete") is False, "A423_SOURCE_IDENTITY_MISMATCH")
    physical(value)
    require(str(value.get("postgres_version", "")).startswith("17."), "A423_NOT_PG17")
    require(value.get("production_source_sha256") == C0_SOURCE
            and value.get("proposed_source_sha256") == C1_SOURCE
            and value.get("production_matches_candidate") is False,
            "A423_SOURCE_HASH_MISMATCH")
    require(value.get("public_stocks") == 5000 and value.get("public_days") == 20
            and value.get("public_total_rows") == 603040
            and sum(value.get("public_counts", {}).values()) == 603040
            and sum(value.get("candidate_rows", {}).values()) == 503020
            and value.get("input_key_sha256") == INPUT_HASHES
            and value.get("candidate_key_hits") == {t:1000 if t in TABLES[:2] else 2000
                                                    for t in TABLES}, "A423_FIXTURE_MISMATCH")
    samples = value.get("samples", [])
    require([(s["statistics"], s["table"], s["variant"], s["repeat"]) for s in samples]
            == expected_order(), "A423_SAMPLE_COHORT_OR_ORDER_MISMATCH")
    for sample in samples:
        metrics = sample.get("metrics", {})
        require(sample.get("golden") == "PASS" and sample.get("keys") == 2000
                and sample.get("batch_size") == VARIANTS[sample["variant"]]
                and finite(sample.get("wall_seconds")) and sample["wall_seconds"] > 0
                and finite(sample.get("client_cpu_seconds"))
                and sample["client_cpu_seconds"] >= 0
                and len(sample.get("batch_seconds", [])) == math.ceil(
                    2000 / sample["batch_size"])
                and all(finite(metrics.get(k)) and metrics[k] >= 0 for k in METRICS),
                "A423_SAMPLE_INVALID")
    summary, workloads = summarize(samples), whole_workloads(samples)
    require(summary == value.get("summary") and workloads == value.get("whole_workloads")
            and performance_decision(summary, workloads) == value.get("decision"),
            "A423_RECOMPUTATION_MISMATCH")
    require(value["decision"]["performance_eligible"] is False
            and value["decision"]["reasons"] == ["P95_REGRESSION"],
            "A423_HISTORICAL_FAILURE_NOT_PRESERVED")
    require({(p["statistics"], p["table"], p["variant"], p["case"])
             for p in value.get("plans", [])} == {
                (r, t, v, c) for r in REGIMES for t in TABLES for v in VARIANTS
                for c in ("b_present", "late_keys")}
            and len(value["plans"]) == 60, "A423_PLANS_INCOMPLETE")
    for regime in REGIMES:
        cases = value.get("actual_execution_probes", {}).get(regime, {}).get("cases", [])
        require(len(cases) == 18 and {(p["table"], p["variant"], p["case"]) for p in cases}
                == {(t, v, c) for t in TABLES for v in ("C0", "C1", "C2")
                    for c in ("b_present", "late_keys")}
                and all(p.get("plan") and p.get("golden") == "PASS" for p in cases),
                "A423_ACTUAL_PROBES_INCOMPLETE")
    return summary, workloads


def project(sample):
    """Explicit numeric whitelist; never export SQL, bind values or raw logs."""
    before, after = sample["backend_before"], sample["backend_after"]
    telemetry = sample["telemetry"]
    statements_before = {r["queryid"]:r for r in sample["database_before"]["lookup_statements"]}
    statements_after = sample["database_after"]["lookup_statements"]
    counters = ("calls", "shared_blks_hit", "shared_blks_read", "temp_blks_read",
                "temp_blks_written", "wal_bytes")
    deltas = {key:sum(float(r[key])-float(statements_before.get(r["queryid"], {}).get(key, 0))
                      for r in statements_after) for key in counters}
    return {**{k:sample[k] for k in ("statistics", "table", "variant", "repeat", "started_at",
        "finished_at", "wall_seconds", "client_cpu_seconds", "batch_seconds", "golden")},
        **{key:sample["metrics"][key] for key in METRICS},
        "backend_cpu_seconds":after["cpu_seconds"]-before["cpu_seconds"],
        "backend_rss_before":before["current_rss_bytes"],
        "backend_rss_after":after["current_rss_bytes"],
        "backend_process_lifetime_hwm":after["process_lifetime_peak_rss_bytes"],
        "client_sampled_rss_lower_bound":telemetry["sampled_peak_rss_lower_bound"],
        "sample_errors":telemetry["sample_errors"],
        "blocker_samples":[w["blockers"] for w in telemetry["writer_wait_samples"]],
        "wait_samples":[{k:w[k] for k in ("state", "wait_event_type", "wait_event")}
                        for w in telemetry["writer_wait_samples"]],
        "queryid_window_deltas":deltas,
        "attribution":"GC_NESTED_NOT_ADDITIVE; PID_INTERVAL_INCLUDES_OBSERVERS; "
                      "COUNTERS_INCLUDE_ALL_LOOKUP_QUERIES_IN_WINDOW"}


def review(value, raw_digest):
    summary, workloads = validate_source(value)
    timelines, rankings, failure_samples, groups = [], [], [], []
    for regime in REGIMES:
        baseline = next(r for r in summary if r["statistics"] == regime
                        and r["table"] == TABLES[2] and r["variant"] == "C0")
        for variant in ("C0", "C1"):
            rows = [project(s) for s in value["samples"] if s["statistics"] == regime
                    and s["table"] == TABLES[2] and s["variant"] == variant]
            q = quantiles([s["wall_seconds"] for s in rows])
            ranked = sorted(rows, key=lambda r:r["wall_seconds"], reverse=True)
            groups.append(dict(statistics=regime, variant=variant, count=len(rows), **q,
                gc_samples=sum(r["gc_count"] > 0 for r in rows),
                gc_events=sum(r["gc_count"] for r in rows),
                gc_seconds=sum(r["gc_seconds"] for r in rows),
                c0_p95_limit=baseline["p95"]*1.1,
                over_c0_p95_limit=sum(r["wall_seconds"] > baseline["p95"]*1.1 for r in rows)))
            timelines.extend(rows)
            rankings.append(dict(statistics=regime, variant=variant,
                                 repeats_descending=[r["repeat"] for r in ranked]))
            if variant == "C1":
                failure_samples.extend(r for r in rows
                                       if r["wall_seconds"] > baseline["p95"]*1.1)
    # Full original plan/probe bytes remain in the pinned archive; no raw logs exported.
    return dict(schema_version="v14-a423-tail-baseline-v1", evidence_kind="HISTORICAL",
        formal_acceptance=False, source_sha=SOURCE_SHA, source_run_id=SOURCE_RUN, source_attempt=1,
        source_artifact_id=SOURCE_ARTIFACT, source_zip_sha256=SOURCE_DIGEST,
        source_lookup_json_sha256=raw_digest, model_hash=value["model_hash"],
        production_source_sha256=C0_SOURCE, proposed_source_sha256=C1_SOURCE,
        input_key_sha256=INPUT_HASHES, database_instance=value["database_instance"],
        physical_system_identifier=value["physical_system_identifier"],
        isolation=value["isolation"], environments=value["environments"],
        resources=value["resources"], source_host=value["host"],
        sample_count=len(value["samples"]), cohort_order_sha256=hashlib.sha256(
            json.dumps(expected_order(), separators=(",", ":")).encode()).hexdigest(),
        summary=summary, whole_workloads=workloads, decision=value["decision"],
        groups=groups, control_timelines=timelines, rankings=rankings,
        c1_samples_over_c0_p95_limit=failure_samples,
        all_slow_c0_c1_samples=[project(s) for s in value["samples"]
                               if s["table"] in TABLES[:2] and s["variant"] in ("C0", "C1")],
        plan_count=len(value["plans"]), actual_probe_count=36,
        tail_causality="CORRELATED_NOT_CAUSAL", p1="NOT_AUTHORIZED",
        p2="NOT_AUTHORIZED", p3="NOT_AUTHORIZED",
        measurement_caveat="No per-generation GC/allocation stack or observer-on/off "
                           "counterfactual exists. Global GC time cannot identify "
                           "allocation owner.")


def blocked_readiness(baseline):
    require(baseline.get("evidence_kind") == "HISTORICAL"
            and baseline.get("source_zip_sha256") == SOURCE_DIGEST
            and baseline.get("decision", {}).get("performance_eligible") is False,
            "A423_BASELINE_NOT_VERIFIED")
    current = hashlib.sha256(
        (ROOT/"backend/app/services/data_publication.py").read_bytes()).hexdigest()
    from scripts.business_source_contract import source_versions

    versions = source_versions(["backend/app/services/data_publication.py"])
    versions["source_contract_version"] = versions.pop("schema_version")
    for field in ("capacity_ready", "performance_eligible",
                  "production_read_authorized"):
        versions.pop(field)
    return dict(**header("a423-capacity-admission"), **versions,
        admission_schema_version="v14-a423-capacity-admission-v1",
        status="CAPACITY_NOT_AUTHORIZED",
        evidence_kind="DIAGNOSTIC_ONLY", capacity_ready=False,
        performance_eligible=False, production_matches_candidate=current == C1_SOURCE,
        production_source_sha256=current, proposed_source_sha256=C1_SOURCE,
        reasons=list(BLOCKERS), source_evidence_kind="HISTORICAL",
        source_sha=SOURCE_SHA, source_zip_sha256=SOURCE_DIGEST,
        formal_capacity_complete=False, p2="NOT_AUTHORIZED", p3="NOT_AUTHORIZED")


def baseline_markdown(baseline):
    lines = ["# A4-2.3 P0：历史尾延迟证据确定性复核", "",
        "状态：HISTORICAL / PERFORMANCE_OPEN。不是新 SHA 性能证据，不授权生产或 L2。", "",
        f"来源：`{SOURCE_SHA}` / run `{SOURCE_RUN}` / attempt 1 / artifact `{SOURCE_ARTIFACT}`。",
        f"ZIP SHA256：`{SOURCE_DIGEST}`。", "",
        "从下载的完整原始 JSON 重新计算，不复制 README 结论。1100 样本的身份、顺序、键摘要、",
        "Golden、summary/whole_workloads/decision、60 份计划、36 份实际连接探针均核对。",
        "快表 2×5×100=1000，慢表 2×2×5×5=100；原始五方案全部保留。", "",
        "完整脱敏数值、400 点 C0/C1 快表时间序列、40 点慢表 C0/C1、全部排名及资源差量见",
        "[JSON](evidence/v14_a423_tail_baseline.json)。",
        "计划完整字节保留于上述摘要绑定的原工件。", "",
        "## 分位数复算", "",
        "使用 Python statistics.quantiles(n=100, method='inclusive')，不删样本、不扣 GC。", "",
        "| 统计状态 | 方案 | 次数 | P50 | P90 | P95 | P99 | GC 次数 | 超 C0 P95×1.10 样本数 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for group in baseline["groups"]:
        lines.append(f"| {group['statistics']} | {group['variant']} | 100 | "
            + " | ".join(f"{group[key]:.12f}" for key in ("p50", "p90", "p95", "p99"))
            + f" | {group['gc_events']} | {group['over_c0_p95_limit']} |")
    lines.extend(["", "ANALYZE 后 C1/C0 P95≈2.159，仍失败。原统计通过不抵消另一状态失败。", "",
        "## 全部超过 C0 P95×1.10 的 C1 样本（不是删除清单）", "",
        "| 状态 | repeat（0 起） | wall | execute | 行物化 | JSON | GC（嵌套） "
        "| client CPU | backend CPU |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|"])
    for row in baseline["c1_samples_over_c0_p95_limit"]:
        lines.append(f"| {row['statistics']} | {row['repeat']} | " + " | ".join(
            f"{row[key]:.9f}" for key in ("wall_seconds", "execute_seconds",
                "buffered_row_materialization_seconds", "python_json_seconds", "gc_seconds",
                "client_cpu_seconds", "backend_cpu_seconds")) + " |")
    lines.extend(["", "## 归因审阅", "",
        "结论 CORRELATED_NOT_CAUSAL：6 个 analyzed C1 样本伴随约 0.127–0.144 秒 GC，",
        "其中 repeat66 的 GC 不主要落在 next(rows) 计时里；另一个 repeat81 以 execute 增长为主。",
        "C0 同样存在 GC 尖峰；每个控制样本 gc_count=16，次数不能区分哪种分代/哪个分配者。",
        "不能把 GC 全部归因 C1、行物化或采样器，更不能从 wall 中扣除它。", "",
        "原执行顺序：regime→table→repeat→旋转方案；旋转起点 repeat%5。",
        "慢表先测，快表后测，观察器与历史输出对象持续累积，未捕获分配栈/分代。",
        "同一主 Session/连接运行；ANALYZE 后显式 commit 再设原 300s timeout。",
        "Telemetry entry/exit、进度写盘、资源快照、Golden 比较在 wall 外；",
        "wall 保留完整 workload、SQL/JSON/行迭代和原 Python 映射；长查询内后台轮询可能重叠。",
        "wrapper 的 Rows/Proxy 动态类与临时 json namespace 可产生额外对象，",
        "但 C0/C1 对称，现有资料不能证明其对差异的因果性。成功/异常恢复与单次迭代有回归测试。", "",
        "GC callback 在 observe_gc finally 解除；新测试只模拟回调事件，不执行 gc.collect，",
        "不修改 GC 开关或阈值。原实验不重写；回调计时与其他阶段可能嵌套，绝不相加。", "",
        "暂无获得因果证明并获准的唯一修复候选。按任务书 W1/W2，P1/P2/P3 均 NOT_AUTHORIZED。",
        "不为通过门槛再跑 100 次，不改 observer 计时合同或强推 C2。",
        "[协议](v14_a4_2_3_protocol.md) / "
        "[ADR](../design/adr_v14_a4_2_3_c1_tail_decision.md)。", "",
        "## C0/C1 快表完整逐样本表", "",
        "所有 400 个样本按各组原始 repeat 顺序列出；P50/P95 使用全部 100 次。",
        "单位秒；backend CPU 含计时外观察区间；RSS/VmHWM/等待/计数完整值见 JSON。"])
    for group in baseline["groups"]:
        lines.extend(["", f"### {group['statistics']} / {group['variant']}", "",
            "| repeat | wall | execute | 行物化 | JSON | GC（嵌套） "
            "| GC count | client CPU | backend CPU |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|"])
        for row in baseline["control_timelines"]:
            if (row["statistics"], row["variant"]) != (group["statistics"], group["variant"]):
                continue
            lines.append(f"| {row['repeat']} | " + " | ".join(f"{row[key]:.9f}" for key in (
                "wall_seconds", "execute_seconds", "buffered_row_materialization_seconds",
                "python_json_seconds", "gc_seconds")) + f" | {row['gc_count']} | "
                + f"{row['client_cpu_seconds']:.9f} | {row['backend_cpu_seconds']:.9f} |")
    return "\n".join(lines)+"\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--readiness-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    parser.add_argument("--expected-baseline", type=Path)
    args = parser.parse_args()
    require(not args.output.exists() and (not args.readiness_output
            or not args.readiness_output.exists()) and (not args.markdown_output
            or not args.markdown_output.exists()), "A423_OUTPUT_EXISTS_NO_OVERWRITE")
    source, digest = load_source(args.archive)
    result = review(source, digest)
    if args.expected_baseline:
        require(result == json.loads(args.expected_baseline.read_text()),
                "A423_COMMITTED_BASELINE_MISMATCH")
    atomic(args.output, result)
    if args.markdown_output:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(baseline_markdown(result))
    if args.readiness_output:
        atomic(args.readiness_output, blocked_readiness(result))
        # Only deny; this offline replay can never authorize capacity, even if
        # someone edits a summary, changes production or sets environment flags.
        import os

        if os.environ.get("GITHUB_OUTPUT"):
            with Path(os.environ["GITHUB_OUTPUT"]).open("a") as stream:
                stream.write("capacity_ready=false\n")
    print(json.dumps(dict(status="HISTORICAL_REPLAY_COMPLETE", samples=result["sample_count"],
        performance_eligible=False, capacity_ready=False, reasons=list(BLOCKERS))))


if __name__ == "__main__":
    main()
