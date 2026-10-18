"""Pure synthetic comparison against the frozen V1.1 source; no DB or Provider IO."""

import argparse
import ast
import json
import subprocess
import sys
import types
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

BASELINE = "f3158dd5317f1da2ba950522b300f66b70d9f901"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def engine(name, *, baseline=False):
    path = f"backend/app/services/{name}/engine.py"
    key = f"cold_start_{name}_{'baseline' if baseline else 'current'}"
    module = types.ModuleType(key)
    sys.modules[key] = module
    source = (
        subprocess.check_output(["git", "show", f"{BASELINE}:{path}"], cwd=ROOT, text=True)
        if baseline
        else (ROOT / path).read_text()
    )
    exec(compile(source, path, "exec"), module.__dict__)
    return module


def factor_inputs():
    days = list(pd.bdate_range("2025-01-01", periods=270).date)
    rows = []
    for code, slope in (("A.SZ", 0.2), ("B.SZ", 0.35), ("C.SZ", 0.1)):
        for index, day in enumerate(days):
            close = 10 + slope * index
            rows.append(
                dict(
                    trade_date=day,
                    ts_code=code,
                    open=close - 0.1,
                    high=close + 0.1,
                    low=close - 0.2,
                    close=close,
                    vol=1000,
                    amount=100000,
                )
            )
    daily = pd.DataFrame(rows)
    return dict(
        daily=daily,
        adj_factor=daily[["trade_date", "ts_code"]].assign(adj_factor=1.0),
        stock_basic=pd.DataFrame(
            [
                dict(ts_code=code, list_date=date(2020, 1, 1), delist_date=None)
                for code in ("A.SZ", "B.SZ", "C.SZ")
            ]
        ),
        index_daily=pd.DataFrame(
            [
                dict(trade_date=day, ts_code="000300.SH", close=100 + 0.1 * index)
                for index, day in enumerate(days)
            ]
        ),
        benchmark_code="000300.SH",
        start=days[-1],
        end=days[-1],
    )


def status_for(daily):
    return daily[["trade_date", "ts_code"]].assign(
        is_active=True,
        is_suspended=False,
        is_st=False,
        st_status_unknown=False,
    )


def opportunity_inputs():
    # Three complete numerical samples: left, newly right-confirmed, strong trend.
    days = list(pd.bdate_range("2025-01-01", periods=70).date)
    rows, states = [], []
    for code, state in (("A.SZ", "S2"), ("B.SZ", "S3"), ("C.SZ", "S5")):
        for index, day in enumerate(days):
            rows.append(
                dict(
                    trade_date=day,
                    ts_code=code,
                    eligible=True,
                    adj_close=10.0,
                    ma20=9.9,
                    ma60=9.5,
                    return20=-0.05 + index / 1000,
                    ma20_slope5=0.01,
                    atr20_pct=0.02,
                    amount_ratio20=1.2,
                    cross_above_ma20=True,
                    cross_above_ma60=False,
                    higher_low=True,
                    higher_low_pct=0.06,
                    drawdown_high60=-0.15,
                    rps20=85.0,
                    rps60=75.0,
                    rps120=65.0,
                    rps20_delta5=10.0,
                    rps60_delta5=8.0,
                )
            )
            states.append(
                dict(
                    trade_date=day,
                    ts_code=code,
                    state=state,
                    previous_state="S2",
                    state_day_count=1,
                    is_new_state=True,
                    right_side_score=92.0,
                    trend_score=90.0,
                )
            )
    return dict(
        factors=pd.DataFrame(rows),
        states=pd.DataFrame(states),
        market=pd.DataFrame([dict(trade_date=day, market_score=70.0) for day in days]),
        sector_members=pd.DataFrame(),
        sector_factors=pd.DataFrame(),
        themes=pd.DataFrame(),
        theme_members=pd.DataFrame(),
        theme_factors=pd.DataFrame(),
        start=days[-1],
        end=days[-1],
        algo_version="v1.0",
    )


def evaluate(module, kind, scenario):
    if kind == "factors":
        kwargs = factor_inputs()
        status = status_for(kwargs["daily"])
        if scenario == "partial":
            status = status[status.ts_code != "C.SZ"]
        elif scenario == "missing":
            status = status.iloc[:0]
        return module.calculate_stock_factors(
            **kwargs,
            config=module.FactorConfig(),
            trade_status=status,
        )
    kwargs = opportunity_inputs()
    if scenario != "complete":
        for col in (
            "rps20_delta5",
            "rps60_delta5",
            "atr20_pct",
            "higher_low",
            "cross_above_ma20",
            "cross_above_ma60",
        ):
            kwargs["factors"][col] = None if scenario == "missing" else pd.NA
    return module.calculate_opportunities(
        **kwargs,
        config=module.OpportunityConfig.from_dict(
            {
                "left_reversal": {
                    "watch_score": 60,
                    "strong_score": 75,
                    "weights": {
                        "stabilization": 0.15,
                        "ma20_turn": 0.20,
                        "higher_low": 0.15,
                        "rps_recovery": 0.20,
                        "price_recovery": 0.15,
                        "volatility_contraction": 0.10,
                        "volume_structure": 0.05,
                    },
                },
                "trend_pool": {
                    "weights": {
                        "trend_score": 0.55,
                        "rps60": 0.20,
                        "rps120": 0.10,
                        "context": 0.10,
                        "market": 0.05,
                    }
                },
            }
        ),
    )


def downstream_signals(factors):
    from app.services.trend.engine import (
        TrendConfig,
        calculate_stock_states,
        generate_strategy_signals,
    )

    config = TrendConfig.from_strategy(yaml.safe_load((ROOT / "config/strategy.yaml").read_text()))
    states = calculate_stock_states(
        factors,
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(),
        factors.trade_date.min(),
        factors.trade_date.max(),
        config,
    )
    signals = generate_strategy_signals(states, config)
    return dict(
        state_rows=len(states),
        signal_rows=len(signals),
        states=json.loads(states.to_json(orient="records", date_format="iso", double_precision=15)),
        signals=json.loads(
            signals.to_json(orient="records", date_format="iso", double_precision=15)
        ),
    )


def report():
    result = dict(baseline=BASELINE, pandas=pd.__version__, numpy=np.__version__, cases=[])
    result["head_sha"] = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    result["working_tree_dirty"] = bool(subprocess.check_output(["git", "status", "--porcelain"]))
    result["object_mask_reproduction"] = (~pd.Series([True, False], dtype=object)).tolist()
    from app.services.analysis_identity import analysis_strategy_hash
    from app.services.calc_metadata import config_hash

    result["identities"] = {}
    for label, baseline in (("old", True), ("new", False)):

        def source(path, baseline=baseline):
            return (
                subprocess.check_output(["git", "show", f"{BASELINE}:{path}"], cwd=ROOT, text=True)
                if baseline
                else (ROOT / path).read_text()
            )

        tree = ast.parse(source("backend/app/services/analysis_identity.py"))
        versions = {
            node.targets[0].id: ast.literal_eval(node.value)
            for node in tree.body
            if isinstance(node, ast.Assign)
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id.endswith("CALC_VERSION")
        }
        result["identities"][label] = dict(
            versions=versions,
            analysis_config_hash=analysis_strategy_hash(
                yaml.safe_load(source("config/strategy.yaml"))
            ),
            opportunity_config_hash=config_hash(yaml.safe_load(source("config/opportunity.yaml"))),
        )
    for kind in ("factors", "opportunity"):
        old, new = engine(kind, baseline=True), engine(kind)
        for scenario in ("complete", "partial", "missing"):
            entry = dict(kind=kind, scenario=scenario)
            outputs = {}
            for label, module in (("old", old), ("new", new)):
                try:
                    frame = evaluate(module, kind, scenario)
                    outputs[label] = frame
                    entry[label] = dict(
                        rows=len(frame),
                        records=json.loads(
                            frame.to_json(orient="records", date_format="iso", double_precision=15)
                        ),
                    )
                    if "opportunity_stage" in frame:
                        entry[label]["stage_counts"] = (
                            frame.opportunity_stage.value_counts().to_dict()
                        )
                        entry[label]["ranked_codes"] = frame.sort_values(
                            ["opportunity_score", "ts_code"], ascending=[False, True]
                        ).ts_code.tolist()
                    if kind == "factors":
                        entry[label]["downstream"] = downstream_signals(frame)
                except (TypeError, ValueError, pd.errors.DataError) as exc:
                    entry[label] = dict(error_type=type(exc).__name__, error=str(exc))
            if len(outputs) == 2:
                a, b = outputs["old"], outputs["new"]
                try:
                    pd.testing.assert_frame_equal(a, b, rtol=1e-12, atol=1e-12)
                    entry["equal_rtol_atol_1e_12"] = True
                except AssertionError:
                    entry["equal_rtol_atol_1e_12"] = False
                entry["changed_columns"] = [c for c in a if not a[c].equals(b[c])]
                changed = pd.Series(False, index=a.index)
                for column in entry["changed_columns"]:
                    changed |= ~(a[column].eq(b[column]) | (a[column].isna() & b[column].isna()))
                entry["affected_stocks"] = sorted(a.loc[changed, "ts_code"].unique())
                entry["affected_dates"] = sorted(
                    str(d) for d in a.loc[changed, "trade_date"].unique()
                )
            result["cases"].append(entry)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    value = report()
    encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n")
    print(
        json.dumps(
            {
                **value,
                "cases": [
                    {k: v for k, v in case.items() if k not in {"old", "new"}}
                    | {
                        label: {k: v for k, v in case[label].items() if k != "records"}
                        for label in ("old", "new")
                    }
                    for case in value["cases"]
                ],
            },
            ensure_ascii=False,
        )
    )
