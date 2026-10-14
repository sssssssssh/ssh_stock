from decimal import Decimal

from app.services.portfolio.ledger_precision import ratio


def frozen_performance(rows, *, expected_dates, initial_cash, invalid_dates=()):
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
        "mode": "PAPER",
        "continuous": continuous,
        "denominator": {
            "initial_cash": str(initial_cash),
            "settled_days": len(rows),
            "expected_days": len(expected_dates),
        },
        "date_range": [rows[0]["trade_date"], rows[-1]["trade_date"]] if rows else None,
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
