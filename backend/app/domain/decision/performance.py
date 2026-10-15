from decimal import Decimal

from app.domain.decision.contracts import PaperError, content_hash
from app.services.portfolio.ledger_precision import ratio


def metric_range(days):
    days = sorted(set(days))
    return [days[0], days[-1]] if days else None


def decision_metrics(proposals):
    counts, actions = {}, {}
    for proposal in proposals:
        counts[proposal["state"]] = counts.get(proposal["state"], 0) + 1
        actions[proposal["action"]] = actions.get(proposal["action"], 0) + 1
    total, approved = len(proposals), counts.get("APPROVED", 0)
    return {
        "eval_version": "m17-decision-count-v1",
        "date_range": metric_range(p["signal_date"] for p in proposals),
        "definition": "APPROVED_OVER_ALL_LEGAL_PROPOSALS_INCLUDING_WATCH",
        "denominator": {"legal_proposals": total},
        "approved_proposals": approved,
        "approval_rate": ratio(Decimal(approved) / total) if total else None,
        "counts": counts,
        "actions": actions,
        "source_hash": content_hash(proposals),
    }


def execution_metrics(orders):
    reached = [o for o in orders if o["status"] in ("FILLED", "SKIPPED", "EXPIRED")]
    stages, blocked, amounts = {}, {}, {}
    for order in reached:
        counts = stages.setdefault(order["stage"], {"orders": 0, "filled": 0})
        counts["orders"] += 1
        counts["filled"] += order["status"] == "FILLED"
        if order["reason_code"]:
            code = order["reason_code"]
            blocked[code] = blocked.get(code, 0) + 1
            group = amounts.setdefault(
                code, {"orders": 0, "known_amount_orders": 0, "estimated_gross_amount": None}
            )
            group["orders"] += 1
            amount = order["estimated_gross"]
            if amount is not None:
                amount = Decimal(amount)
                if not amount.is_finite() or amount < 0:
                    raise PaperError("PAPER_RECORD_INTEGRITY_ERROR")
                group["known_amount_orders"] += 1
                group["estimated_gross_amount"] = (
                    group["estimated_gross_amount"] or Decimal("0")
                ) + amount
    filled = sum(o["status"] == "FILLED" for o in reached)
    return {
        "eval_version": "m17-hypothetical-execution-v1",
        "date_range": metric_range(o["scheduled_date"] for o in reached),
        "denominator": {"reached_legal_orders": len(reached)},
        "source_hash": content_hash(orders),
        "reached_orders": len(reached),
        "filled_orders": filled,
        "hypothetical_fill_rate": ratio(Decimal(filled) / len(reached)) if reached else None,
        "blocked_reasons": blocked,
        "blocked_amounts": amounts,
        "amount_basis": "FROZEN_SIGNAL_SIZING_ESTIMATE_CNY_NOT_EXECUTED_PNL",
        "stages": stages,
        "interpretation": "POST_EOD_SIMULATION_NON_CAUSAL",
    }


def frozen_performance(
    rows, *, expected_dates, initial_cash, invalid_dates=(), completion_heads=()
):
    continuous = bool(rows) and [row["trade_date"] for row in rows] == list(expected_dates)
    continuous = continuous and not invalid_dates
    high, previous, costs, turnover = Decimal("1"), Decimal("1"), Decimal("0"), Decimal("0")
    maximum = Decimal("0")
    series = []
    for row in rows:
        nav = Decimal(row["nav"])
        high = max(high, nav)
        drawdown = ratio(nav / high - 1) if continuous and high > 0 else None
        if drawdown is not None:
            maximum = min(maximum, drawdown)
        daily_return = ratio(nav / previous - 1) if continuous and previous > 0 else None
        costs += Decimal(row["trading_cost"])
        turnover += Decimal(row["data"]["turnover"])
        series.append(
            {
                "trade_date": row["trade_date"],
                "nav": str(nav),
                "benchmark_nav": row["benchmark_nav"],
                "cash": row["cash"],
                "market_value": row["market_value"],
                "daily_return": daily_return,
                "drawdown": drawdown,
                "cumulative_cost": str(costs),
                "valid": row["trade_date"] not in invalid_dates,
            }
        )
        previous = nav
    by_date = {row["trade_date"]: row for row in series}
    series = [
        by_date.get(
            day,
            {
                "trade_date": day,
                "nav": None,
                "benchmark_nav": None,
                "cash": None,
                "market_value": None,
                "daily_return": None,
                "drawdown": None,
                "cumulative_cost": None,
                "valid": False,
            },
        )
        for day in sorted(set(expected_dates) | set(by_date))
    ]
    latest = rows[-1] if rows else None
    return {
        "eval_version": "m17-frozen-performance-v1",
        "source_hash": content_hash(
            {
                "rows": rows,
                "expected_dates": expected_dates,
                "initial_cash": initial_cash,
                "invalid_dates": sorted(invalid_dates),
                "completion_heads": completion_heads,
            }
        ),
        "mode": "PAPER",
        "continuous": continuous,
        "denominator": {
            "initial_cash": str(initial_cash),
            "settled_days": len(rows),
            "expected_days": len(expected_dates),
        },
        "date_range": metric_range(row["trade_date"] for row in rows),
        "cumulative_return": ratio(Decimal(latest["nav"]) - 1) if continuous else None,
        "maximum_drawdown": maximum if continuous else None,
        "cumulative_cost": str(costs),
        "cumulative_turnover": str(turnover),
        "series": series,
        "latest": latest,
        "reason_codes": [] if continuous else ["PAPER_NAV_SEQUENCE_UNAVAILABLE"],
        "benchmark_status": "READY"
        if rows and all(row["benchmark_nav"] is not None for row in rows)
        else "BENCHMARK_UNAVAILABLE",
    }
