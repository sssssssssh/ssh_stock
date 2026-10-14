from datetime import date

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.domain.decision.contracts import PaperError, content_hash
from app.models.job import JobRun
from app.models.market_data import (
    DataDirtyRange,
    DataQualityDaily,
    IndexDaily,
    MarketDaily,
    SectorFactorDaily,
    StockAdjFactor,
    StockBasic,
    StockDaily,
    StockDailyBasic,
    StockFactorDaily,
    StockLimitDaily,
    StockOpportunityDaily,
    StockStateDaily,
    StockStDaily,
    StockSuspendDaily,
    StockTradeStatusDaily,
    TradeCalendar,
)
from app.services.analysis_filters import opportunity_identity_filters
from app.services.analysis_identity import (
    FACTOR_CALC_VERSION,
    MARKET_CALC_VERSION,
    SECTOR_CALC_VERSION,
    TRADE_STATUS_CALC_VERSION,
    TREND_CALC_VERSION,
    analysis_strategy_hash,
)
from app.services.paper.records import close_cutoff, source_value
from app.services.portfolio.candidates import OpportunityCandidateProvider
from app.services.portfolio.source_integrity import check_portfolio_source_integrity
from app.services.quality.raw_completeness import check_raw_completeness


class DecisionSourceReadiness:
    def __init__(self, db, settings):
        self.db, self.settings = db, settings

    def capture(self, day: date, *, cutoff, include_codes=(), market_codes=(), benchmark_code=None):
        if cutoff.utcoffset() is None or cutoff < close_cutoff(day):
            raise PaperError("SOURCE_EOD_NOT_READY")
        # One repeatable, read-only DB snapshot; no ingestion or network side effects.
        with Session(bind=self.db.get_bind()) as source:
            source.connection(execution_options={"isolation_level": "REPEATABLE READ"})
            source.execute(text("SET TRANSACTION READ ONLY"))
            result = self._capture(source, day, cutoff, include_codes)
            if benchmark_code is not None:
                result["execution_input"] = self._execution_input(
                    source, day, market_codes, benchmark_code
                )
            return result

    def _execution_input(self, db, day, codes, benchmark_code):
        calendar = db.get(TradeCalendar, day)
        facts = {}
        for model in (StockDaily, StockAdjFactor, StockLimitDaily, StockTradeStatusDaily):
            facts[model.__tablename__] = {
                row.ts_code: source_value(
                    {c.name: getattr(row, c.name) for c in model.__table__.columns}
                )
                for row in db.scalars(
                    select(model)
                    .where(model.trade_date == day, model.ts_code.in_(codes))
                    .order_by(model.ts_code)
                )
            }
        facts["stock_basic"] = {
            row.ts_code: {"exchange": row.exchange, "market": row.market}
            for row in db.scalars(select(StockBasic).where(StockBasic.ts_code.in_(codes)))
        }
        facts["previous_adj"] = {
            row.ts_code: source_value(row.adj_factor)
            for row in db.scalars(
                select(StockAdjFactor).where(
                    StockAdjFactor.trade_date == calendar.pretrade_date,
                    StockAdjFactor.ts_code.in_(codes),
                )
            )
        }
        benchmark = db.get(IndexDaily, (day, benchmark_code))
        facts["benchmark"] = (
            None
            if benchmark is None
            else source_value(
                {
                    "code": benchmark.ts_code,
                    "close": benchmark.close,
                    "pre_close": benchmark.pre_close,
                }
            )
        )
        facts["calendar"] = {
            "trade_date": day,
            "previous_date": calendar.pretrade_date,
            "exchange": calendar.exchange,
            "is_open": calendar.is_open,
        }
        return facts

    def _capture(self, db, day, cutoff, include_codes):
        settings = self.settings
        config = settings.paper_config.decision
        calendar = db.get(TradeCalendar, day)
        if calendar is None or calendar.exchange not in ("SSE", "SZSE"):
            raise PaperError("PAPER_CALENDAR_UNAVAILABLE")
        if not calendar.is_open:
            raise PaperError("DECISION_NON_TRADING_DAY", status_code=422)
        dirty = db.scalar(
            select(DataDirtyRange.id)
            .where(
                DataDirtyRange.dirty_start_date <= day,
                DataDirtyRange.status.in_(("OPEN", "PROCESSING", "FAILED")),
            )
            .limit(1)
        )
        if dirty:
            raise PaperError("SOURCE_DIRTY_RANGE")
        count = db.scalar(
            select(func.count()).select_from(StockDaily).where(StockDaily.trade_date == day)
        )
        if count > config.max_source_rows:
            raise PaperError("DECISION_SOURCE_CAPACITY_EXCEEDED")
        integrity = check_portfolio_source_integrity(db, day, settings=settings)
        if not integrity.is_ready:
            raise PaperError("SOURCE_NOT_READY")
        quality = check_raw_completeness(db, day, strategy=settings.strategy, persist=False)
        if quality.overall_status == "ERROR":
            raise PaperError("SOURCE_RAW_INCOMPLETE")
        strategy = analysis_strategy_hash(settings.strategy)
        candidate_config = settings.portfolio_config.candidate.model_copy(
            update={
                "allowed_stages": list(config.allowed_stages),
                "min_score": config.min_score,
                "top_n": config.top_n,
            }
        )
        portfolio = settings.portfolio_config.model_copy(update={"candidate": candidate_config})
        batch = OpportunityCandidateProvider(db, settings).list_candidates(day, portfolio)
        if not batch.source_ready:
            raise PaperError("SOURCE_NOT_READY")
        models = (
            StockDaily,
            StockAdjFactor,
            StockDailyBasic,
            StockLimitDaily,
            StockStDaily,
            StockSuspendDaily,
            IndexDaily,
            StockFactorDaily,
            StockStateDaily,
            StockOpportunityDaily,
            StockTradeStatusDaily,
            MarketDaily,
            SectorFactorDaily,
            DataQualityDaily,
        )
        identity_versions = {
            StockFactorDaily: FACTOR_CALC_VERSION,
            StockStateDaily: TREND_CALC_VERSION,
            StockTradeStatusDaily: TRADE_STATUS_CALC_VERSION,
            MarketDaily: MARKET_CALC_VERSION,
            SectorFactorDaily: SECTOR_CALC_VERSION,
        }
        layers, rows_by_model, calc_ids, ready_times = {}, {}, set(), []
        for model in models:
            query = select(model).where(model.trade_date == day)
            if model == StockOpportunityDaily:
                query = query.where(*opportunity_identity_filters(settings))
            elif model in identity_versions:
                query = query.where(
                    model.calc_version == identity_versions[model], model.config_hash == strategy
                )
                if model == StockStateDaily:
                    query = query.where(model.algo_version == settings.algo_version)
            rows = list(
                db.scalars(
                    query.order_by(*model.__table__.primary_key.columns).limit(
                        config.max_source_rows + 1
                    )
                )
            )
            if len(rows) > config.max_source_rows:
                raise PaperError("DECISION_SOURCE_CAPACITY_EXCEEDED")
            rows_by_model[model] = rows
            payloads = []
            for row in rows:
                payload = source_value(
                    {column.name: getattr(row, column.name) for column in model.__table__.columns}
                )
                payloads.append(payload)
                if model in identity_versions or model == StockOpportunityDaily:
                    if (
                        row.calc_run_id is None
                        or row.calculated_at is None
                        or row.calculated_at > cutoff
                    ):
                        raise PaperError("SOURCE_CALC_LINEAGE_UNAVAILABLE")
                    calc_ids.add(row.calc_run_id)
                    ready_times.append(row.calculated_at)
            layers[model.__tablename__] = content_hash(payloads)
        jobs = list(db.scalars(select(JobRun).where(JobRun.id.in_(calc_ids))))
        if len(jobs) != len(calc_ids):
            raise PaperError("SOURCE_CALC_LINEAGE_UNAVAILABLE")
        for job in jobs:
            metadata = job.job_metadata or {}
            covers = job.target_trade_date == day
            if not covers:
                try:
                    covers = (
                        date.fromisoformat(metadata["start"])
                        <= day
                        <= date.fromisoformat(metadata["end"])
                    )
                except (KeyError, TypeError, ValueError):
                    covers = False
            if (
                job.status != "SUCCESS"
                or job.finished_at is None
                or job.finished_at > cutoff
                or not covers
                or job.job_type not in ("daily", "recalculate", "catchup")
            ):
                raise PaperError("SOURCE_JOB_NOT_READY")
            ready_times.append(job.finished_at)
        finished = {job.id: job.finished_at for job in jobs}
        for model, rows in rows_by_model.items():
            if model in identity_versions or model == StockOpportunityDaily:
                if any(row.calculated_at > finished[row.calc_run_id] for row in rows):
                    raise PaperError("SOURCE_JOB_NOT_READY")
        layers["jobs"] = content_hash(
            sorted(
                [
                    {
                        "id": job.id,
                        "type": job.job_type,
                        "status": job.status,
                        "finished_at": job.finished_at,
                    }
                    for job in jobs
                ],
                key=lambda row: str(row["id"]),
            )
        )
        raw = {row.ts_code: row for row in rows_by_model[StockDaily]}
        statuses = {row.ts_code: row for row in rows_by_model[StockTradeStatusDaily]}
        factors = {row.ts_code: row for row in rows_by_model[StockFactorDaily]}
        states = {row.ts_code: row for row in rows_by_model[StockStateDaily]}
        opportunities = {row.ts_code: row for row in rows_by_model[StockOpportunityDaily]}
        if not raw.keys() <= statuses.keys():
            raise PaperError("SOURCE_TRADE_STATUS_INCOMPLETE")
        for code, row in raw.items():
            if (
                row.source_updated_at > cutoff
                or row.source_updated_at > factors[code].calculated_at
            ):
                raise PaperError("SOURCE_DERIVED_STALE")
            if states[code].state != opportunities[code].state:
                raise PaperError("SOURCE_STATE_MISMATCH")
        selected = [
            item.ts_code
            for item in sorted(batch.candidates, key=lambda item: (-item.score, item.ts_code))[
                : config.top_n
            ]
        ]
        codes = list(dict.fromkeys(selected + sorted(include_codes)))
        basics = {
            row.ts_code: row
            for row in db.scalars(select(StockBasic).where(StockBasic.ts_code.in_(codes)))
        }
        layers["stock_basic_selected"] = content_hash(
            [
                {
                    key: getattr(basics[code], key)
                    for key in ("ts_code", "name", "exchange", "market", "list_date", "delist_date")
                }
                for code in sorted(basics)
            ]
        )
        candidates = []
        for code in codes:
            if code not in raw or code not in opportunities or code not in basics:
                raise PaperError("DECISION_SECURITY_UNAVAILABLE")
            opportunity, status, daily = opportunities[code], statuses[code], raw[code]
            if daily.close is None or daily.close <= 0 or opportunity.opportunity_score is None:
                raise PaperError("SOURCE_PRICE_OR_SCORE_UNAVAILABLE")
            reasons = opportunity.reason_codes or {}
            reasons = (
                sorted(reasons)
                if isinstance(reasons, list)
                else sorted(key for key, value in reasons.items() if value)
            )
            blockers = []
            for condition, reason in (
                (code not in selected, "CONTEXT_ONLY"),
                (opportunity.opportunity_stage == "LEFT_WATCH", "WATCH_ONLY"),
                (opportunity.extension_risk in ("HIGH", "EXTREME"), "EXTENSION_RISK"),
                (not status.is_active, "NOT_ACTIVE"),
                (status.is_suspended, "SUSPENDED"),
                (status.is_st is True, "ST_BLOCKED"),
                (status.is_st is None or status.st_status_unknown, "ELIGIBILITY_UNKNOWN"),
                (not status.strategy_eligible or not status.tradable, "NOT_ELIGIBLE"),
                (daily.vol is None or daily.vol <= 0, "ZERO_OR_UNKNOWN_VOLUME"),
            ):
                if condition:
                    blockers.append(reason)
            fields = (
                "trade_date",
                "ts_code",
                "opportunity_stage",
                "opportunity_score",
                "trend_rank_score",
                "state",
                "industry_sector_id",
                "industry_heat",
                "industry_lifecycle",
                "primary_theme_code",
                "primary_theme_heat",
                "primary_theme_lifecycle",
                "extension_risk",
                "calc_version",
                "config_hash",
                "source_strategy_config_hash",
                "calc_run_id",
            )
            candidates.append(
                source_value(
                    {
                        **{key: getattr(opportunity, key) for key in fields},
                        "reason_codes": reasons,
                        "risk_codes": blockers,
                        "rule_status": "BLOCKED" if blockers else "READY",
                        "close": daily.close,
                        "vol": daily.vol,
                        "exchange": basics[code].exchange,
                        "market": basics[code].market,
                        "name": basics[code].name,
                    }
                )
            )
        policy = {
            "version": config.version,
            "top_n": config.top_n,
            "min_score": config.min_score,
            "allowed_stages": config.allowed_stages,
        }
        identity = {
            "algo_version": settings.algo_version,
            "strategy_hash": strategy,
            "candidate_config": candidate_config.model_dump(mode="python"),
            "rule": policy,
        }
        return {
            "source_hash": content_hash(layers),
            "strategy_identity_hash": content_hash(identity),
            "source_identity": identity,
            "layer_hashes": layers,
            "candidates": candidates,
            "candidate_snapshot_hash": content_hash(candidates),
            "ready_at": max(ready_times),
            "cutoff": cutoff,
            "signal_date": day,
            "include_codes": list(include_codes),
            "raw_count": len(raw),
            "quality_status": quality.overall_status,
        }
