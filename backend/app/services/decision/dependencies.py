from datetime import date

from sqlalchemy import and_, func, literal, or_, select, union_all
from sqlalchemy.orm import aliased

from app.domain.decision.contracts import PaperError
from app.models.job import JobRun
from app.models.market_data import (
    DataDirtyRange,
    MarketDaily,
    SectorFactorDaily,
    SectorMember,
    StockDaily,
    StockFactorDaily,
    StockOpportunityDaily,
    StockStateDaily,
    StockTradeStatusDaily,
    TradeCalendar,
)
from app.services.analysis_filters import opportunity_identity_filters


def job_covers_scope(job, first, last, cutoff):
    if (
        job.status != "SUCCESS" or job.job_type not in ("daily", "recalculate", "catchup")
        or job.started_at is None or job.finished_at is None
        or not job.started_at <= job.finished_at <= cutoff
    ):
        return False
    if first == last == job.target_trade_date:
        return True
    try:
        start, end = date.fromisoformat(job.start), date.fromisoformat(job.end)
        if start.isoformat() != job.start or end.isoformat() != job.end or start > end:
            return False
        warmup = getattr(job, "analysis_start", None)
        if warmup is not None:
            effective_start = date.fromisoformat(warmup)
            if effective_start.isoformat() != warmup or effective_start > start:
                return False
        else:
            effective_start = start
        return effective_start <= first <= last <= end
    except (TypeError, ValueError):
        return False


def check_dirty_dependencies(db, day, cutoff, settings, versions, strategy_hash):
    first = db.scalar(select(func.min(DataDirtyRange.dirty_start_date)).where(
        DataDirtyRange.dirty_start_date <= day,
    ))
    if first is None:
        return
    cap = settings.paper_config.decision.max_source_rows
    calendar_days = (day - first).days + 1
    if calendar_days > cap:
        raise PaperError("DECISION_SOURCE_CAPACITY_EXCEEDED")
    known_days = db.scalar(select(func.count()).select_from(TradeCalendar).where(
        TradeCalendar.cal_date.between(first, day),
        TradeCalendar.exchange.in_(("SSE", "SZSE")),
    ))
    if known_days != calendar_days:
        raise PaperError("SOURCE_CALC_LINEAGE_UNAVAILABLE")

    def changes_on(value):
        return select(DataDirtyRange.id).where(DataDirtyRange.dirty_start_date <= value).exists()

    def relevant(model):
        filters = [model.trade_date.between(first, day)]
        if model in (StockStateDaily, StockOpportunityDaily):
            filters.append(model.algo_version == settings.algo_version)
        if model is StockOpportunityDaily:
            filters.append(model.trade_date == day)
        return filters

    models = (*versions, StockOpportunityDaily)
    scopes = union_all(*(
        select(model.calc_run_id.label("job_id"), model.trade_date.label("day"))
        .where(*relevant(model))
        for model in models
    )).subquery()
    grouped = select(
        scopes.c.job_id, func.min(scopes.c.day).label("first"),
        func.max(scopes.c.day).label("last"),
    ).group_by(scopes.c.job_id).subquery()
    if db.scalar(select(func.count()).select_from(grouped)) > cap:
        raise PaperError("DECISION_SOURCE_CAPACITY_EXCEEDED")
    jobs = db.execute(select(
        JobRun.id, JobRun.status, JobRun.job_type, JobRun.target_trade_date,
        JobRun.started_at, JobRun.finished_at,
        JobRun.job_metadata["start"].astext.label("start"),
        JobRun.job_metadata["end"].astext.label("end"), grouped.c.first, grouped.c.last,
        JobRun.job_metadata["analysis_warmup_start"].astext.label("analysis_start"),
    ).select_from(JobRun).join(grouped, JobRun.id == grouped.c.job_id)).all()
    valid_ids = [job.id for job in jobs if job_covers_scope(job, job.first, job.last, cutoff)]

    def invalid_proof(model, identity):
        changed_after_calculation = select(DataDirtyRange.id).where(
            DataDirtyRange.dirty_start_date <= model.trade_date,
            DataDirtyRange.created_at >= JobRun.started_at,
        ).exists().correlate(model, JobRun)
        return or_(
            model.calc_run_id.is_(None), model.calc_run_id.not_in(valid_ids),
            model.calculated_at.is_(None), model.calculated_at < JobRun.started_at,
            model.calculated_at > JobRun.finished_at, ~func.coalesce(and_(*identity), False),
            changed_after_calculation,
        )

    # Each raw instrument needs the actual repaired rolling/state inputs, not just a new D row.
    for model in (StockFactorDaily, StockStateDaily, StockTradeStatusDaily, StockOpportunityDaily):
        identity = (
            opportunity_identity_filters(settings) if model is StockOpportunityDaily else
            (model.calc_version == versions[model], model.config_hash == strategy_hash)
        )
        join = [model.trade_date == StockDaily.trade_date, model.ts_code == StockDaily.ts_code]
        if model in (StockStateDaily, StockOpportunityDaily):
            join.append(model.algo_version == settings.algo_version)
        stale = select(StockDaily.trade_date).outerjoin(model, and_(*join)).outerjoin(
            JobRun, JobRun.id == model.calc_run_id,
        ).where(
            StockDaily.trade_date.between(first, day), changes_on(StockDaily.trade_date),
            invalid_proof(model, identity),
        )
        if model is StockOpportunityDaily:
            stale = stale.where(StockDaily.trade_date == day)
        first_stale = db.scalar(stale.order_by(
            StockDaily.trade_date, StockDaily.ts_code,
        ).limit(1))
        if first_stale is not None:
            raise PaperError("SOURCE_DERIVED_STALE")
    for model in (MarketDaily, SectorFactorDaily):
        identity = (model.calc_version == versions[model], model.config_hash == strategy_hash)
        stale = select(model.trade_date).outerjoin(JobRun, JobRun.id == model.calc_run_id).where(
            *relevant(model), changes_on(model.trade_date), invalid_proof(model, identity),
        )
        if db.scalar(stale.order_by(model.trade_date).limit(1)) is not None:
            raise PaperError("SOURCE_DERIVED_STALE")

    market = select(MarketDaily.trade_date).where(
        MarketDaily.trade_date == TradeCalendar.cal_date,
    ).exists()
    raw = select(StockDaily.trade_date).where(
        StockDaily.trade_date == TradeCalendar.cal_date,
    ).exists()
    gap = select(TradeCalendar.cal_date).where(
        TradeCalendar.cal_date.between(first, day), TradeCalendar.is_open.is_(True),
        TradeCalendar.exchange.in_(("SSE", "SZSE")), changes_on(TradeCalendar.cal_date),
        or_(~market, ~raw),
    )
    if db.scalar(gap.order_by(TradeCalendar.cal_date).limit(1)) is not None:
        raise PaperError("SOURCE_DERIVED_STALE")
    # Same historical eligible membership contract as check_sector_factor_coverage.
    sector_present = select(SectorFactorDaily.sector_id).where(
        SectorFactorDaily.trade_date == StockFactorDaily.trade_date,
        SectorFactorDaily.sector_id == SectorMember.sector_id,
    ).exists().correlate(StockFactorDaily, SectorMember)
    sector_gap = select(StockFactorDaily.trade_date).join(
        SectorMember, SectorMember.ts_code == StockFactorDaily.ts_code,
    ).where(
        StockFactorDaily.trade_date.between(first, day), StockFactorDaily.eligible.is_(True),
        changes_on(StockFactorDaily.trade_date),
        SectorMember.valid_from <= StockFactorDaily.trade_date,
        or_(SectorMember.valid_to.is_(None), SectorMember.valid_to >= StockFactorDaily.trade_date),
        ~sector_present,
    )
    if db.scalar(sector_gap.order_by(StockFactorDaily.trade_date).limit(1)) is not None:
        raise PaperError("SOURCE_DERIVED_STALE")
    stale_raw = select(StockDaily.trade_date).join(StockFactorDaily, and_(
        StockFactorDaily.trade_date == StockDaily.trade_date,
        StockFactorDaily.ts_code == StockDaily.ts_code,
    )).where(
        StockDaily.trade_date.between(first, day), changes_on(StockDaily.trade_date),
        StockDaily.source_updated_at > StockFactorDaily.calculated_at,
    )
    if db.scalar(stale_raw.limit(1)) is not None:
        raise PaperError("SOURCE_DERIVED_STALE")
    _check_calculation_order(db, models, relevant)


def _check_calculation_order(db, models, relevant):
    stages = {StockTradeStatusDaily: 0, StockFactorDaily: 1, MarketDaily: 2,
              SectorFactorDaily: 2, StockStateDaily: 3, StockOpportunityDaily: 4}
    rows = union_all(*(
        select(model.trade_date.label("day"), model.calc_run_id.label("job_id"),
               literal(stages[model]).label("stage"), model.calculated_at.label("stamp"))
        .where(*relevant(model)) for model in models
    )).subquery()
    groups = select(
        rows.c.day, rows.c.job_id, rows.c.stage,
        func.min(rows.c.stamp).label("earliest"), func.max(rows.c.stamp).label("latest"),
    ).group_by(rows.c.day, rows.c.job_id, rows.c.stage).subquery()
    upstream, downstream = groups.alias("upstream"), groups.alias("downstream")
    up_job, down_job = aliased(JobRun), aliased(JobRun)
    depends = or_(
        and_(downstream.c.stage == 1, upstream.c.stage == 0),
        and_(downstream.c.stage == 2, upstream.c.stage == 1),
        and_(downstream.c.stage == 3, upstream.c.stage.in_((1, 2))),
        and_(downstream.c.stage == 3, upstream.c.stage == 3,
             upstream.c.day < downstream.c.day),
        and_(downstream.c.stage == 4, upstream.c.stage.in_((0, 1, 2, 3))),
    )
    stale = select(downstream.c.day).select_from(downstream).join(
        upstream, and_(upstream.c.day <= downstream.c.day, depends),
    ).join(up_job, up_job.id == upstream.c.job_id).join(
        down_job, down_job.id == downstream.c.job_id,
    ).where(or_(
        and_(upstream.c.job_id == downstream.c.job_id,
             upstream.c.latest > downstream.c.earliest),
        and_(upstream.c.job_id != downstream.c.job_id,
             up_job.finished_at > down_job.started_at),
    ))
    if db.scalar(stale.order_by(downstream.c.day).limit(1)) is not None:
        raise PaperError("SOURCE_DERIVED_STALE")
