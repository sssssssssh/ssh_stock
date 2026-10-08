import hashlib
import json
from datetime import date

from app.domain.walk_forward.contracts import WindowPlan, WindowPlanResult


class WindowPlanError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def date_set_hash(values: tuple[date, ...]) -> str:
    payload = json.dumps(
        [value.isoformat() for value in values], separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def plan_windows(
    open_dates: tuple[date, ...],
    *,
    mode: str,
    train_trade_days: int,
    test_trade_days: int,
    step_trade_days: int,
    minimum_windows: int,
    max_windows: int,
) -> WindowPlanResult:
    normalized_mode = mode.upper()
    if normalized_mode not in {"ROLLING", "EXPANDING"}:
        raise WindowPlanError("WALK_FORWARD_CONFIG_INVALID", "unsupported window mode")
    if train_trade_days <= 0 or test_trade_days <= 0:
        raise WindowPlanError(
            "WALK_FORWARD_CONFIG_INVALID", "trade-day counts must be positive"
        )
    if step_trade_days != test_trade_days:
        raise WindowPlanError(
            "WALK_FORWARD_CONFIG_INVALID",
            "walk_forward_v1 requires step_trade_days == test_trade_days",
        )
    if minimum_windows < 2 or max_windows < minimum_windows:
        raise WindowPlanError("WALK_FORWARD_CONFIG_INVALID", "invalid window limits")
    if tuple(sorted(set(open_dates))) != open_dates:
        raise WindowPlanError(
            "WALK_FORWARD_CALENDAR_INCOMPLETE",
            "open trade dates must be unique and strictly increasing",
        )

    available_after_train = max(0, len(open_dates) - train_trade_days)
    window_count = available_after_train // test_trade_days
    unused_tail = available_after_train % test_trade_days
    if window_count < minimum_windows:
        raise WindowPlanError(
            "WALK_FORWARD_INSUFFICIENT_WINDOWS",
            "calendar does not contain the minimum number of complete windows",
        )
    if window_count > max_windows:
        raise WindowPlanError(
            "WALK_FORWARD_WINDOW_LIMIT_EXCEEDED",
            "calendar produces more windows than configured",
        )

    windows: list[WindowPlan] = []
    for index in range(window_count):
        test_start = train_trade_days + index * test_trade_days
        test_end = test_start + test_trade_days
        train_start = index * test_trade_days if normalized_mode == "ROLLING" else 0
        train_dates = open_dates[train_start:test_start]
        if normalized_mode == "ROLLING":
            train_dates = train_dates[-train_trade_days:]
        test_dates = open_dates[test_start:test_end]
        if len(train_dates) < train_trade_days or len(test_dates) != test_trade_days:
            raise WindowPlanError(
                "WALK_FORWARD_CALENDAR_INCOMPLETE",
                "calendar cannot produce a complete deterministic window",
            )
        windows.append(
            WindowPlan(
                window_no=index + 1,
                train_trade_dates=train_dates,
                test_trade_dates=test_dates,
                train_date_hash=date_set_hash(train_dates),
                test_date_hash=date_set_hash(test_dates),
            )
        )
    for left, right in zip(windows, windows[1:], strict=False):
        if left.test_end_date >= right.test_start_date:
            raise WindowPlanError(
                "WALK_FORWARD_CALENDAR_INCOMPLETE", "test windows overlap"
            )
        left_last_index = open_dates.index(left.test_end_date)
        if open_dates[left_last_index + 1] != right.test_start_date:
            raise WindowPlanError(
                "WALK_FORWARD_CALENDAR_INCOMPLETE", "test windows contain a gap"
            )
    return WindowPlanResult(tuple(windows), unused_tail)
