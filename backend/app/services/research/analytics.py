from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping
from datetime import date
from statistics import mean, median
from typing import Any

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.models.market_data import OpportunityForwardEval, ResearchTransitionEval, ThemeForwardEval
from app.services.analysis_identity import (
    OPPORTUNITY_CALC_VERSION,
    RESEARCH_EVAL_VERSION,
    RESEARCH_VERSION,
    THEME_CALC_VERSION,
    TREND_CALC_VERSION,
    analysis_strategy_hash,
)
from app.services.calc_metadata import config_hash

HORIZONS = (5, 10, 20, 60)
OPPORTUNITY_GROUPS = (
    "opportunity_stage",
    "market_regime",
    "industry_lifecycle",
    "primary_theme_lifecycle",
    "extension_risk",
)
OPPORTUNITY_BUCKETS = (
    "left_reversal_score",
    "right_side_score",
    "trend_score",
    "trend_rank_score",
    "position_score",
    "opportunity_score",
    "context_score",
    "market_score",
    "industry_heat",
    "primary_theme_heat",
)
THEME_GROUPS = ("lifecycle",)
THEME_BUCKETS = (
    "heat_score",
    "moneyflow_score",
    "limit_strength_score",
    "heat_momentum1",
    "heat_momentum3",
)
BUCKET_FIELDS = {
    **{field: {"bounded_100": True} for field in OPPORTUNITY_BUCKETS},
    "heat_score": {"bounded_100": True},
    "moneyflow_score": {"bounded_100": True},
    "limit_strength_score": {"bounded_100": True},
    "heat_momentum1": {"bounded_100": False},
    "heat_momentum3": {"bounded_100": False},
}
RESEARCH_TYPES = ("ALL", "LEFT", "RIGHT", "TREND", "POSITION")


class Cohort:
    def __init__(self, min_sample_warning: int) -> None:
        self.event_count = 0
        self.min_sample_warning = min_sample_warning
        self.mature = defaultdict(int)
        self.entry = defaultdict(int)
        self.exit = defaultdict(int)
        self.returns: dict[int, list[float]] = defaultdict(list)
        self.benchmarks: dict[int, list[float]] = defaultdict(list)
        self.excess: dict[int, list[float]] = defaultdict(list)
        self.mark_returns: dict[int, list[float]] = defaultdict(list)
        self.delayed_returns: dict[int, list[float]] = defaultdict(list)
        self.net_returns: dict[int, list[float]] = defaultdict(list)
        self.net_delayed_returns: dict[int, list[float]] = defaultdict(list)
        self.exit_delays: dict[int, list[float]] = defaultdict(list)
        self.final_exit_unresolved = defaultdict(int)
        self.non_executable = defaultdict(int)
        self.mfe: list[float] = []
        self.mae: list[float] = []

    def add(self, row: Mapping[str, Any]) -> None:
        self.event_count += 1
        entry_ok = row.get("entry_executable") is True
        for horizon in HORIZONS:
            if not row.get(f"mature{horizon}"):
                continue
            self.mature[horizon] += 1
            if not entry_ok:
                continue
            self.entry[horizon] += 1
            mark_return = row.get(f"mark_ret{horizon}")
            if mark_return is not None:
                self.mark_returns[horizon].append(float(mark_return))
            delayed_return = row.get(f"delayed_exit_ret{horizon}")
            if delayed_return is not None:
                self.delayed_returns[horizon].append(float(delayed_return))
            elif row.get(f"delayed_exit_window_mature{horizon}") is True:
                self.final_exit_unresolved[horizon] += 1
            net_delayed = row.get(f"net_delayed_exit_ret{horizon}")
            if net_delayed is not None:
                self.net_delayed_returns[horizon].append(float(net_delayed))
            delay_days = row.get(f"delayed_exit_delay_days{horizon}")
            if delay_days is not None:
                self.exit_delays[horizon].append(float(delay_days))
            if row.get(f"exit_executable{horizon}") is not True:
                self.non_executable[horizon] += 1
                continue
            self.exit[horizon] += 1
            value = row.get(f"ret{horizon}")
            if value is None:
                continue
            self.returns[horizon].append(float(value))
            net_return = row.get(f"net_ret{horizon}")
            if net_return is not None:
                self.net_returns[horizon].append(float(net_return))
            benchmark = row.get(f"benchmark_ret{horizon}")
            excess = row.get(f"excess_ret{horizon}")
            if benchmark is not None and excess is not None:
                self.benchmarks[horizon].append(float(benchmark))
                self.excess[horizon].append(float(excess))
        if row.get("mature20") and entry_ok:
            if row.get("mfe20") is not None:
                self.mfe.append(float(row["mfe20"]))
            if row.get("mae20") is not None:
                self.mae.append(float(row["mae20"]))

    def result(self) -> dict[str, Any]:
        return {
            "event_count": self.event_count,
            "horizons": [self.horizon_result(horizon) for horizon in HORIZONS],
        }

    def horizon_result(self, horizon: int) -> dict[str, Any]:
        returns = self.returns[horizon]
        excess = self.excess[horizon]
        mark_returns = self.mark_returns[horizon]
        delayed_returns = self.delayed_returns[horizon]
        net_returns = self.net_returns[horizon]
        net_delayed_returns = self.net_delayed_returns[horizon]
        positive_delays = [delay for delay in self.exit_delays[horizon] if delay > 0]
        final_exit_unresolved_count = self.final_exit_unresolved[horizon]
        final_exit_completed_count = len(delayed_returns) + final_exit_unresolved_count
        final_exit_pending_count = max(
            self.entry[horizon] - final_exit_completed_count, 0
        )
        return {
            "horizon": horizon,
            "event_count": self.event_count,
            "mature_count": self.mature[horizon],
            "entry_executable_count": self.entry[horizon],
            "exit_executable_count": self.exit[horizon],
            "return_sample_count": len(returns),
            "mark_sample_count": len(mark_returns),
            "delayed_exit_sample_count": len(delayed_returns),
            "net_return_sample_count": len(net_returns),
            "net_delayed_exit_sample_count": len(net_delayed_returns),
            "excess_sample_count": len(excess),
            "avg_return": _mean(returns),
            "median_return": median(returns) if returns else None,
            "p25_return": _quantile(returns, 0.25),
            "p75_return": _quantile(returns, 0.75),
            "win_rate": _rate(value > 0 for value in returns),
            "avg_benchmark_return": _mean(self.benchmarks[horizon]),
            "avg_excess_return": _mean(excess),
            "median_excess_return": median(excess) if excess else None,
            "excess_win_rate": _rate(value > 0 for value in excess),
            "avg_mark_return": _mean(mark_returns),
            "median_mark_return": median(mark_returns) if mark_returns else None,
            "mark_win_rate": _rate(value > 0 for value in mark_returns),
            "avg_delayed_exit_return": _mean(delayed_returns),
            "median_delayed_exit_return": (
                median(delayed_returns) if delayed_returns else None
            ),
            "delayed_exit_win_rate": _rate(value > 0 for value in delayed_returns),
            "avg_net_return": _mean(net_returns),
            "avg_net_delayed_exit_return": _mean(net_delayed_returns),
            "avg_exit_delay_days": _mean(self.exit_delays[horizon]),
            "delayed_exit_count": len(positive_delays),
            "delayed_exit_rate": (
                len(positive_delays) / len(delayed_returns) if delayed_returns else None
            ),
            "avg_positive_exit_delay_days": _mean(positive_delays),
            "final_exit_success_rate": (
                len(delayed_returns) / final_exit_completed_count
                if final_exit_completed_count
                else None
            ),
            "final_exit_completed_count": final_exit_completed_count,
            "final_exit_unresolved_count": final_exit_unresolved_count,
            "unresolved_exit_rate": (
                final_exit_unresolved_count / final_exit_completed_count
                if final_exit_completed_count
                else None
            ),
            "final_exit_pending_count": final_exit_pending_count,
            "pending_exit_rate": (
                final_exit_pending_count / self.entry[horizon]
                if self.entry[horizon]
                else None
            ),
            "non_executable_rate": (
                self.non_executable[horizon] / self.entry[horizon]
                if self.entry[horizon]
                else None
            ),
            "avg_mfe20": _mean(self.mfe) if horizon == 20 else None,
            "avg_mae20": _mean(self.mae) if horizon == 20 else None,
            "return_sample_warning": len(returns) < self.min_sample_warning,
            "mark_sample_warning": len(mark_returns) < self.min_sample_warning,
            "delayed_exit_sample_warning": len(delayed_returns) < self.min_sample_warning,
            "sample_warning": len(returns) < self.min_sample_warning,
        }


def _mean(values: list[float]) -> float | None:
    return mean(values) if values else None


def _rate(values: Iterable[bool]) -> float | None:
    items = list(values)
    return sum(items) / len(items) if items else None


def _quantile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    if low == high:
        return ordered[low]
    return ordered[low] * (high - position) + ordered[high] * (position - low)


def _identity_filters(model: type, settings: Any) -> list[Any]:
    filters = [
        model.research_version == RESEARCH_VERSION,
        model.research_config_hash == config_hash(settings.research_config),
    ]
    if model is OpportunityForwardEval or model is ThemeForwardEval:
        filters.append(model.eval_version == RESEARCH_EVAL_VERSION)
        filters.append(model.strategy_config_hash == analysis_strategy_hash(settings.strategy))
    filters.append(model.opportunity_config_hash == config_hash(settings.opportunity_config))
    if model is OpportunityForwardEval or model is ResearchTransitionEval:
        filters.append(model.algo_version == settings.algo_version)
    if model is OpportunityForwardEval:
        filters.append(model.opportunity_calc_version == OPPORTUNITY_CALC_VERSION)
    if model is ThemeForwardEval:
        filters.append(model.theme_calc_version == THEME_CALC_VERSION)
    if model is ResearchTransitionEval:
        filters.append(model.strategy_config_hash == analysis_strategy_hash(settings.strategy))
        filters.append(model.trend_calc_version == TREND_CALC_VERSION)
        filters.append(model.opportunity_calc_version == OPPORTUNITY_CALC_VERSION)
    return filters


def _date_filters(column: Any, start: date | None, end: date | None) -> list[Any]:
    filters = []
    if start:
        filters.append(column >= start)
    if end:
        filters.append(column <= end)
    return filters


def _read_rows(
    db: Session,
    model: type,
    settings: Any,
    start: date | None,
    end: date | None,
    *,
    columns: tuple[str, ...] = (),
    extra_filters: tuple[Any, ...] = (),
    order_by: tuple[Any, ...] = (),
) -> Iterator[Mapping[str, Any]]:
    date_column = model.event_trade_date if model is ResearchTransitionEval else model.trade_date
    metric_columns = (
        (
            "entry_executable",
            "mfe20",
            "mae20",
            *(
                field + str(horizon)
                for horizon in HORIZONS
                for field in (
                    "mature",
                    "exit_executable",
                    "ret",
                    "benchmark_ret",
                    "excess_ret",
                    "mark_ret",
                    "delayed_exit_ret",
                    "delayed_exit_delay_days",
                    "net_ret",
                    "net_delayed_exit_ret",
                )
            ),
        )
        if model is not ResearchTransitionEval
        else ()
    )
    selected = tuple(dict.fromkeys((*columns, *metric_columns)))
    stmt = select(*(getattr(model, key) for key in selected)).where(
        *_identity_filters(model, settings),
        *_date_filters(date_column, start, end),
        *extra_filters,
    )
    if order_by:
        stmt = stmt.order_by(*order_by)
    return db.execute(stmt).mappings().yield_per(2000)


def grouped_stats(
    rows: Iterable[Mapping[str, Any]],
    group_field: str | None,
    min_sample: int,
    *,
    all_groups: list[str] | None = None,
) -> list[dict[str, Any]]:
    groups: dict[str, Cohort] = {}
    for row in rows:
        label = str(row.get(group_field) if group_field else "ALL")
        if label in {"None", ""}:
            label = "UNKNOWN"
        groups.setdefault(label, Cohort(min_sample)).add(row)
    if not groups:
        return []
    for label in all_groups or []:
        groups.setdefault(label, Cohort(min_sample))
    return [{"group": label, **cohort.result()} for label, cohort in sorted(groups.items())]


def opportunity_stats(
    db: Session,
    settings: Any,
    start: date | None,
    end: date | None,
    *,
    stage: str | None = None,
    filters: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    extra = []
    if stage:
        extra.append(OpportunityForwardEval.opportunity_stage == stage)
    for key, value in (filters or {}).items():
        if key not in OPPORTUNITY_GROUPS:
            raise ValueError(f"unsupported context filter: {key}")
        extra.append(getattr(OpportunityForwardEval, key) == value)
    return grouped_stats(
        _read_rows(db, OpportunityForwardEval, settings, start, end, extra_filters=tuple(extra)),
        None,
        settings.research_config["min_sample_warning"],
        all_groups=["ALL"],
    )


def bucket_stats(
    db: Session,
    settings: Any,
    start: date | None,
    end: date | None,
    *,
    model: type,
    field: str,
    research_type: str = "ALL",
) -> list[dict[str, Any]]:
    allowed = OPPORTUNITY_BUCKETS if model is OpportunityForwardEval else THEME_BUCKETS
    if field not in allowed:
        raise ValueError(f"unsupported bucket field: {field}")
    if research_type not in RESEARCH_TYPES:
        raise ValueError(f"unsupported research_type: {research_type}")
    bucket_states = {
        "LEFT": ("S1", "S2"),
        "RIGHT": ("S3",),
        "TREND": ("S4", "S5"),
        "POSITION": ("S4", "S5"),
    }
    extra = (
        (OpportunityForwardEval.state.in_(bucket_states[research_type]),)
        if model is OpportunityForwardEval and research_type != "ALL"
        else ()
    )
    size = settings.research_config["score_bucket_size"]
    groups: dict[int | None, Cohort] = {}
    for row in _read_rows(db, model, settings, start, end, columns=(field,), extra_filters=extra):
        score = row[field]
        if score is None:
            lower = None
        elif BUCKET_FIELDS[field]["bounded_100"] and float(score) == 100:
            lower = ((100 - 1) // size) * size
        else:
            lower = int(float(score) // size) * size
        groups.setdefault(lower, Cohort(settings.research_config["min_sample_warning"])).add(row)
    result = []
    for lower, cohort in sorted(groups.items(), key=lambda item: (item[0] is None, item[0] or 0)):
        if lower is None:
            label = "UNKNOWN"
        else:
            upper = min(lower + size, 100) if BUCKET_FIELDS[field]["bounded_100"] else lower + size
            label = f"{lower}-{upper}"
        result.append({"group": label, **cohort.result()})
    return result


def _universe_filters(settings: Any, research_type: str) -> tuple[Any, ...]:
    if research_type not in RESEARCH_TYPES:
        raise ValueError(f"unsupported research_type: {research_type}")
    forward = OpportunityForwardEval
    if research_type == "ALL":
        return ()
    if research_type in {"TREND", "POSITION"}:
        return (forward.state.in_(("S4", "S5")),)
    if research_type == "LEFT":
        event_type = "LEFT_THRESHOLD_CROSS"
        event_key = f"LEFT_{settings.opportunity_config['left_reversal']['strong_score']}"
    else:
        event_type = "RIGHT_SIDE_NEW"
        event_key = "RIGHT_SIDE_NEW"
    event = ResearchTransitionEval
    return (
        exists(
            select(event.id).where(
                event.event_trade_date == forward.trade_date,
                event.ts_code == forward.ts_code,
                event.algo_version == forward.algo_version,
                event.strategy_config_hash == forward.strategy_config_hash,
                event.opportunity_calc_version == forward.opportunity_calc_version,
                event.opportunity_config_hash == forward.opportunity_config_hash,
                event.research_version == forward.research_version,
                event.research_config_hash == forward.research_config_hash,
                event.event_type == event_type,
                event.event_key == event_key,
                event.trend_calc_version == TREND_CALC_VERSION,
            )
        ),
    )


def topn_stats(
    db: Session,
    settings: Any,
    start: date | None,
    end: date | None,
    *,
    theme: bool,
) -> list[dict[str, Any]]:
    model = ThemeForwardEval if theme else OpportunityForwardEval
    code = "theme_code" if theme else "ts_code"
    rank = "heat_rank" if theme else "trend_rank_score"
    topns = settings.research_config["theme_topn" if theme else "trend_topn"]
    extra = () if theme else (OpportunityForwardEval.state.in_(("S4", "S5")),)
    order = (
        model.trade_date,
        getattr(model, rank).asc() if theme else getattr(model, rank).desc(),
        getattr(model, code).asc(),
    )
    rows = _read_rows(
        db,
        model,
        settings,
        start,
        end,
        columns=("trade_date", code, rank),
        extra_filters=extra,
        order_by=order,
    )
    groups = {f"TOP{n}": Cohort(settings.research_config["min_sample_warning"]) for n in topns}
    groups["ALL"] = Cohort(settings.research_config["min_sample_warning"])
    current_date: date | None = None
    position = 0
    for row in rows:
        if row["trade_date"] != current_date:
            current_date = row["trade_date"]
            position = 0
        if row[rank] is None:
            continue
        position += 1
        groups["ALL"].add(row)
        for n in topns:
            if position <= n:
                groups[f"TOP{n}"].add(row)
    if groups["ALL"].event_count == 0:
        return []
    return [{"group": key, **value.result()} for key, value in groups.items()]


def context_stats(
    db: Session,
    settings: Any,
    start: date | None,
    end: date | None,
    group_by: str,
    research_type: str = "ALL",
) -> list[dict[str, Any]]:
    if group_by not in {
        "market_regime",
        "industry_lifecycle",
        "primary_theme_lifecycle",
        "extension_risk",
    }:
        raise ValueError(f"unsupported group_by: {group_by}")
    return grouped_stats(
        _read_rows(
            db,
            OpportunityForwardEval,
            settings,
            start,
            end,
            columns=(group_by,),
            extra_filters=_universe_filters(settings, research_type),
        ),
        group_by,
        settings.research_config["min_sample_warning"],
    )


def position_stats(db: Session, settings: Any, start: date | None, end: date | None):
    return grouped_stats(
        _read_rows(
            db,
            OpportunityForwardEval,
            settings,
            start,
            end,
            columns=("extension_risk",),
            extra_filters=(OpportunityForwardEval.state.in_(("S4", "S5")),),
        ),
        "extension_risk",
        settings.research_config["min_sample_warning"],
        all_groups=["PULLBACK", "NORMAL", "EXTENDED", "EXTREME", "BROKEN"],
    )


def theme_stats(
    db: Session, settings: Any, start: date | None, end: date | None, lifecycle: str | None = None
) -> list[dict[str, Any]]:
    extra = (ThemeForwardEval.lifecycle == lifecycle,) if lifecycle else ()
    return grouped_stats(
        _read_rows(db, ThemeForwardEval, settings, start, end, extra_filters=extra),
        None,
        settings.research_config["min_sample_warning"],
        all_groups=["ALL"],
    )


def theme_lifecycle_stats(db: Session, settings: Any, start: date | None, end: date | None):
    return grouped_stats(
        _read_rows(db, ThemeForwardEval, settings, start, end, columns=("lifecycle",)),
        "lifecycle",
        settings.research_config["min_sample_warning"],
    )


def transition_stats(
    db: Session,
    settings: Any,
    start: date | None,
    end: date | None,
    *,
    left: bool,
) -> list[dict[str, Any]]:
    transition = ResearchTransitionEval
    forward = OpportunityForwardEval
    event_type = "LEFT_THRESHOLD_CROSS" if left else "RIGHT_SIDE_NEW"
    stmt = (
        select(transition, forward)
        .join(
            forward,
            (forward.trade_date == transition.event_trade_date)
            & (forward.ts_code == transition.ts_code)
            & (forward.algo_version == transition.algo_version)
            & (forward.strategy_config_hash == transition.strategy_config_hash)
            & (forward.opportunity_calc_version == transition.opportunity_calc_version)
            & (forward.opportunity_config_hash == transition.opportunity_config_hash)
            & (forward.research_version == transition.research_version)
            & (forward.research_config_hash == transition.research_config_hash)
            & (forward.eval_version == RESEARCH_EVAL_VERSION),
        )
        .where(
            *_identity_filters(transition, settings),
            transition.event_type == event_type,
            *_date_filters(transition.event_trade_date, start, end),
        )
    )
    groups: dict[str, dict[str, Any]] = {}
    for event, outcome in db.execute(stmt).yield_per(1000):
        key = event.event_key
        if key not in groups:
            groups[key] = {
                "cohort": Cohort(settings.research_config["min_sample_warning"]),
                "mature": defaultdict(int),
                "hits": defaultdict(int),
                "days": defaultdict(list),
            }
        group = groups[key]
        group["cohort"].add(outcome.__dict__)
        for horizon in (5, 10, 20):
            if getattr(event, f"mature{horizon}"):
                group["mature"][horizon] += 1
                for target in ("s3", "s4plus", "s5"):
                    group["hits"][(target, horizon)] += (
                        getattr(event, f"reached_{target}_{horizon}") is True
                    )
        if event.mature20:
            for target in ("s0", "s6", "below_s3"):
                key_name = {"s0": "hit_s0_20", "s6": "hit_s6_20", "below_s3": "fell_below_s3_20"}[
                    target
                ]
                group["hits"][(target, 20)] += getattr(event, key_name) is True
            for target in ("s3", "s4plus", "s5"):
                value = getattr(event, f"days_to_{target}")
                if value is not None:
                    group["days"][target].append(value)
    result = []
    keys = (
        [f"LEFT_{value}" for value in settings.research_config["left_thresholds"]]
        if left
        else ["RIGHT_SIDE_NEW"]
    )
    for key in keys:
        group = groups.get(key) or {
            "cohort": Cohort(settings.research_config["min_sample_warning"]),
            "mature": defaultdict(int),
            "hits": defaultdict(int),
            "days": defaultdict(list),
        }
        row = {"group": key, **group["cohort"].result()}
        for horizon in (5, 10, 20):
            denominator = group["mature"][horizon]
            for target in ("s3", "s4plus", "s5"):
                row[f"reached_{target}_{horizon}"] = (
                    group["hits"][(target, horizon)] / denominator if denominator else None
                )
        denominator20 = group["mature"][20]
        for target, field in (
            ("s0", "hit_s0_20"),
            ("s6", "hit_s6_20"),
            ("below_s3", "fell_below_s3_20"),
        ):
            row[field] = group["hits"][(target, 20)] / denominator20 if denominator20 else None
        for target in ("s3", "s4plus", "s5"):
            row[f"avg_days_to_{target}"] = _mean(group["days"][target])
        result.append(row)
    return result


def research_status(db: Session, settings: Any) -> dict[str, Any]:
    models = (OpportunityForwardEval, ThemeForwardEval, ResearchTransitionEval)
    result: dict[str, Any] = {
        "research_version": RESEARCH_VERSION,
        "research_config_hash": config_hash(settings.research_config),
        "benchmark_code": settings.research_config["benchmark_code"],
    }
    for model, prefix in zip(models, ("opportunity", "theme", "transition"), strict=True):
        date_column = (
            model.event_trade_date if model is ResearchTransitionEval else model.trade_date
        )
        count, latest = db.execute(
            select(func.count(), func.max(date_column)).where(*_identity_filters(model, settings))
        ).one()
        result[f"{prefix}_eval_rows"] = count
        result[f"latest_{prefix}_eval_base_date"] = latest
    for horizon in (5, 20, 60):
        result[f"mature{horizon}_rows"] = sum(
            db.scalar(
                select(func.count())
                .select_from(model)
                .where(
                    *_identity_filters(model, settings),
                    getattr(model, f"mature{horizon}").is_(True),
                )
            )
            or 0
            for model in (OpportunityForwardEval, ThemeForwardEval)
        )
    evaluated_dates = [
        db.scalar(
            select(func.max(model.evaluated_until_date)).where(*_identity_filters(model, settings))
        )
        for model in (OpportunityForwardEval, ThemeForwardEval)
    ]
    result["latest_evaluated_market_date"] = max(
        (day for day in evaluated_dates if day is not None), default=None
    )
    return result
