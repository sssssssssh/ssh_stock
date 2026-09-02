import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class StockBasic(Base):
    __tablename__ = "stock_basic"

    ts_code: Mapped[str] = mapped_column(String(16), primary_key=True)
    symbol: Mapped[str | None] = mapped_column(String(8))
    name: Mapped[str | None] = mapped_column(String(64))
    market: Mapped[str | None] = mapped_column(String(32))
    exchange: Mapped[str | None] = mapped_column(String(8))
    industry: Mapped[str | None] = mapped_column(String(64))
    list_status: Mapped[str | None] = mapped_column(String(4))
    list_date: Mapped[date | None] = mapped_column(Date)
    delist_date: Mapped[date | None] = mapped_column(Date)
    is_hs: Mapped[str | None] = mapped_column(String(4))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TradeCalendar(Base):
    __tablename__ = "trade_calendar"

    cal_date: Mapped[date] = mapped_column(Date, primary_key=True)
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False)
    pretrade_date: Mapped[date | None] = mapped_column(Date)
    exchange: Mapped[str] = mapped_column(String(8), nullable=False, default="SSE")


class StockDaily(Base):
    __tablename__ = "stock_daily"
    __table_args__ = (
        PrimaryKeyConstraint("trade_date", "ts_code"),
        Index("idx_stock_daily_code_date", "ts_code", "trade_date"),
    )

    trade_date: Mapped[date] = mapped_column(Date)
    ts_code: Mapped[str] = mapped_column(String(16))
    open: Mapped[float | None] = mapped_column(Float)
    high: Mapped[float | None] = mapped_column(Float)
    low: Mapped[float | None] = mapped_column(Float)
    close: Mapped[float | None] = mapped_column(Float)
    pre_close: Mapped[float | None] = mapped_column(Float)
    change: Mapped[float | None] = mapped_column(Float)
    pct_chg: Mapped[float | None] = mapped_column(Float)
    vol: Mapped[float | None] = mapped_column(Float)
    amount: Mapped[float | None] = mapped_column(Float)
    source_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class StockAdjFactor(Base):
    __tablename__ = "stock_adj_factor"
    __table_args__ = (
        PrimaryKeyConstraint("trade_date", "ts_code"),
        Index("idx_stock_adj_factor_code_date", "ts_code", "trade_date"),
    )

    trade_date: Mapped[date] = mapped_column(Date)
    ts_code: Mapped[str] = mapped_column(String(16))
    adj_factor: Mapped[float | None] = mapped_column(Float)


class StockDailyBasic(Base):
    __tablename__ = "stock_daily_basic"
    __table_args__ = (
        PrimaryKeyConstraint("trade_date", "ts_code"),
        Index("idx_stock_daily_basic_code_date", "ts_code", "trade_date"),
    )

    trade_date: Mapped[date] = mapped_column(Date)
    ts_code: Mapped[str] = mapped_column(String(16))
    close: Mapped[float | None] = mapped_column(Float)
    turnover_rate: Mapped[float | None] = mapped_column(Float)
    turnover_rate_f: Mapped[float | None] = mapped_column(Float)
    volume_ratio: Mapped[float | None] = mapped_column(Float)
    pe: Mapped[float | None] = mapped_column(Float)
    pe_ttm: Mapped[float | None] = mapped_column(Float)
    pb: Mapped[float | None] = mapped_column(Float)
    ps: Mapped[float | None] = mapped_column(Float)
    ps_ttm: Mapped[float | None] = mapped_column(Float)
    total_share: Mapped[float | None] = mapped_column(Float)
    float_share: Mapped[float | None] = mapped_column(Float)
    free_share: Mapped[float | None] = mapped_column(Float)
    total_mv: Mapped[float | None] = mapped_column(Float)
    circ_mv: Mapped[float | None] = mapped_column(Float)


class IndexDaily(Base):
    __tablename__ = "index_daily"
    __table_args__ = (
        PrimaryKeyConstraint("trade_date", "ts_code"),
        Index("idx_index_daily_code_date", "ts_code", "trade_date"),
    )

    trade_date: Mapped[date] = mapped_column(Date)
    ts_code: Mapped[str] = mapped_column(String(16))
    open: Mapped[float | None] = mapped_column(Float)
    high: Mapped[float | None] = mapped_column(Float)
    low: Mapped[float | None] = mapped_column(Float)
    close: Mapped[float | None] = mapped_column(Float)
    pre_close: Mapped[float | None] = mapped_column(Float)
    pct_chg: Mapped[float | None] = mapped_column(Float)
    vol: Mapped[float | None] = mapped_column(Float)
    amount: Mapped[float | None] = mapped_column(Float)


class StockFactorDaily(Base):
    __tablename__ = "stock_factor_daily"
    __table_args__ = (
        PrimaryKeyConstraint("trade_date", "ts_code"),
        Index("idx_factor_date_eligible", "trade_date", "eligible"),
        Index("idx_factor_code_date", "ts_code", "trade_date"),
    )

    trade_date: Mapped[date] = mapped_column(Date)
    ts_code: Mapped[str] = mapped_column(String(16))
    adj_open: Mapped[float | None] = mapped_column(Float)
    adj_high: Mapped[float | None] = mapped_column(Float)
    adj_low: Mapped[float | None] = mapped_column(Float)
    adj_close: Mapped[float | None] = mapped_column(Float)
    ma5: Mapped[float | None] = mapped_column(Float)
    ma10: Mapped[float | None] = mapped_column(Float)
    ma20: Mapped[float | None] = mapped_column(Float)
    ma60: Mapped[float | None] = mapped_column(Float)
    ma120: Mapped[float | None] = mapped_column(Float)
    ma250: Mapped[float | None] = mapped_column(Float)
    return1: Mapped[float | None] = mapped_column(Float)
    return3: Mapped[float | None] = mapped_column(Float)
    return5: Mapped[float | None] = mapped_column(Float)
    return20: Mapped[float | None] = mapped_column(Float)
    return60: Mapped[float | None] = mapped_column(Float)
    return120: Mapped[float | None] = mapped_column(Float)
    return250: Mapped[float | None] = mapped_column(Float)
    ma20_slope5: Mapped[float | None] = mapped_column(Float)
    ma60_slope10: Mapped[float | None] = mapped_column(Float)
    atr20: Mapped[float | None] = mapped_column(Float)
    atr20_pct: Mapped[float | None] = mapped_column(Float)
    amount_ma20: Mapped[float | None] = mapped_column(Float)
    amount_ratio20: Mapped[float | None] = mapped_column(Float)
    prev_high20: Mapped[float | None] = mapped_column(Float)
    prev_high60: Mapped[float | None] = mapped_column(Float)
    prev_high120: Mapped[float | None] = mapped_column(Float)
    low20: Mapped[float | None] = mapped_column(Float)
    low60: Mapped[float | None] = mapped_column(Float)
    breakout20: Mapped[bool | None] = mapped_column(Boolean)
    breakout60: Mapped[bool | None] = mapped_column(Boolean)
    cross_above_ma20: Mapped[bool | None] = mapped_column(Boolean)
    cross_above_ma60: Mapped[bool | None] = mapped_column(Boolean)
    higher_low: Mapped[bool | None] = mapped_column(Boolean)
    higher_low_pct: Mapped[float | None] = mapped_column(Float)
    drawdown_high60: Mapped[float | None] = mapped_column(Float)
    drawdown_high120: Mapped[float | None] = mapped_column(Float)
    max_drawdown60: Mapped[float | None] = mapped_column(Float)
    trend_efficiency20: Mapped[float | None] = mapped_column(Float)
    rps20: Mapped[float | None] = mapped_column(Float)
    rps60: Mapped[float | None] = mapped_column(Float)
    rps120: Mapped[float | None] = mapped_column(Float)
    rps250: Mapped[float | None] = mapped_column(Float)
    rps20_delta5: Mapped[float | None] = mapped_column(Float)
    rps60_delta5: Mapped[float | None] = mapped_column(Float)
    relative_return20: Mapped[float | None] = mapped_column(Float)
    relative_return60: Mapped[float | None] = mapped_column(Float)
    eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    exclusion_reason: Mapped[str | None] = mapped_column(String(128))
    calc_version: Mapped[str | None] = mapped_column(String(32))
    config_hash: Mapped[str | None] = mapped_column(String(64))
    calc_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    calculated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MarketDaily(Base):
    __tablename__ = "market_daily"

    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    market_score: Mapped[float | None] = mapped_column(Float)
    regime: Mapped[str | None] = mapped_column(String(16))
    breadth20: Mapped[float | None] = mapped_column(Float)
    breadth60: Mapped[float | None] = mapped_column(Float)
    up_count: Mapped[int | None] = mapped_column(Integer)
    down_count: Mapped[int | None] = mapped_column(Integer)
    flat_count: Mapped[int | None] = mapped_column(Integer)
    up_rate: Mapped[float | None] = mapped_column(Float)
    new_high20_count: Mapped[int | None] = mapped_column(Integer)
    new_low20_count: Mapped[int | None] = mapped_column(Integer)
    new_high60_count: Mapped[int | None] = mapped_column(Integer)
    new_low60_count: Mapped[int | None] = mapped_column(Integer)
    total_amount: Mapped[float | None] = mapped_column(Float)
    amount_ratio20: Mapped[float | None] = mapped_column(Float)
    index_trend_score: Mapped[float | None] = mapped_column(Float)
    breadth_score: Mapped[float | None] = mapped_column(Float)
    ad_score: Mapped[float | None] = mapped_column(Float)
    new_high_low_score: Mapped[float | None] = mapped_column(Float)
    liquidity_score: Mapped[float | None] = mapped_column(Float)
    calc_version: Mapped[str | None] = mapped_column(String(32))
    config_hash: Mapped[str | None] = mapped_column(String(64))
    calc_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    calculated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Sector(Base):
    __tablename__ = "sector"
    __table_args__ = (UniqueConstraint("source", "source_code", name="uq_sector_source_code"),)

    sector_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    source_code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    level: Mapped[str | None] = mapped_column(String(16))
    parent_code: Mapped[str | None] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class SectorMember(Base):
    __tablename__ = "sector_member"
    __table_args__ = (
        UniqueConstraint("sector_id", "ts_code", "valid_from", name="uq_sector_member_from"),
        Index("idx_sector_member_stock", "ts_code", "is_latest"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sector_id: Mapped[int] = mapped_column(ForeignKey("sector.sector_id"), nullable=False)
    ts_code: Mapped[str] = mapped_column(String(16), nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)
    is_latest: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class SectorFactorDaily(Base):
    __tablename__ = "sector_factor_daily"
    __table_args__ = (
        PrimaryKeyConstraint("trade_date", "sector_id"),
        Index("idx_sector_factor_date_rank", "trade_date", "heat_rank"),
    )

    trade_date: Mapped[date] = mapped_column(Date)
    sector_id: Mapped[int] = mapped_column(ForeignKey("sector.sector_id"))
    member_count: Mapped[int | None] = mapped_column(Integer)
    eligible_member_count: Mapped[int | None] = mapped_column(Integer)
    return1: Mapped[float | None] = mapped_column(Float)
    return3: Mapped[float | None] = mapped_column(Float)
    return5: Mapped[float | None] = mapped_column(Float)
    return20: Mapped[float | None] = mapped_column(Float)
    excess_return5: Mapped[float | None] = mapped_column(Float)
    excess_return20: Mapped[float | None] = mapped_column(Float)
    breadth20: Mapped[float | None] = mapped_column(Float)
    breadth60: Mapped[float | None] = mapped_column(Float)
    up_rate: Mapped[float | None] = mapped_column(Float)
    new_high20_rate: Mapped[float | None] = mapped_column(Float)
    rps60_median: Mapped[float | None] = mapped_column(Float)
    rps60_top20_rate: Mapped[float | None] = mapped_column(Float)
    amount: Mapped[float | None] = mapped_column(Float)
    amount_ratio20: Mapped[float | None] = mapped_column(Float)
    limit_up_density: Mapped[float | None] = mapped_column(Float)
    moneyflow_score: Mapped[float | None] = mapped_column(Float)
    heat_score: Mapped[float | None] = mapped_column(Float)
    heat_momentum1: Mapped[float | None] = mapped_column(Float)
    heat_momentum3: Mapped[float | None] = mapped_column(Float)
    heat_rank: Mapped[int | None] = mapped_column(Integer)
    rank_change: Mapped[int | None] = mapped_column(Integer)
    lifecycle: Mapped[str | None] = mapped_column(String(32))
    calc_version: Mapped[str | None] = mapped_column(String(32))
    config_hash: Mapped[str | None] = mapped_column(String(64))
    calc_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    calculated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DataQualityDaily(Base):
    __tablename__ = "data_quality_daily"
    __table_args__ = (
        UniqueConstraint("trade_date", "dataset", name="uq_data_quality_daily_dataset_date"),
        Index("idx_data_quality_daily_date_status", "trade_date", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    dataset: Mapped[str] = mapped_column(String(64), nullable=False)
    expected_rows: Mapped[int | None] = mapped_column(Integer)
    actual_rows: Mapped[int | None] = mapped_column(Integer)
    coverage_rate: Mapped[float | None] = mapped_column(Float)
    missing_count: Mapped[int | None] = mapped_column(Integer)
    duplicate_count: Mapped[int | None] = mapped_column(Integer)
    null_count: Mapped[int | None] = mapped_column(Integer)
    warning_count: Mapped[int | None] = mapped_column(Integer)
    error_count: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    issue_codes: Mapped[dict | None] = mapped_column(JSONB)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class DataDirtyRange(Base):
    __tablename__ = "data_dirty_range"
    __table_args__ = (
        Index("idx_data_dirty_range_status_start", "status", "dirty_start_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    dataset: Mapped[str] = mapped_column(String(64), nullable=False)
    dirty_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    dirty_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(256))
    source_job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="OPEN")
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    last_failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StockStateDaily(Base):
    __tablename__ = "stock_state_daily"
    __table_args__ = (
        PrimaryKeyConstraint("trade_date", "ts_code", "algo_version"),
        Index("idx_stock_state_date_state", "trade_date", "state"),
        Index("idx_stock_state_date_score", "trade_date", "opportunity_score"),
    )

    trade_date: Mapped[date] = mapped_column(Date)
    ts_code: Mapped[str] = mapped_column(String(16))
    algo_version: Mapped[str] = mapped_column(String(32))
    previous_state: Mapped[str | None] = mapped_column(String(16))
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    state_day_count: Mapped[int | None] = mapped_column(Integer)
    is_new_state: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    right_side_score: Mapped[float | None] = mapped_column(Float)
    trend_score: Mapped[float | None] = mapped_column(Float)
    opportunity_score: Mapped[float | None] = mapped_column(Float)
    primary_sector_id: Mapped[int | None] = mapped_column(Integer)
    sector_heat: Mapped[float | None] = mapped_column(Float)
    market_score: Mapped[float | None] = mapped_column(Float)
    fast_transition: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reason_codes: Mapped[dict | None] = mapped_column(JSONB)


class StrategySignal(Base):
    __tablename__ = "strategy_signal"
    __table_args__ = (
        UniqueConstraint(
            "trade_date",
            "ts_code",
            "signal_type",
            "algo_version",
            name="uq_strategy_signal_natural",
        ),
        Index("idx_strategy_signal_date_type", "trade_date", "signal_type"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    ts_code: Mapped[str] = mapped_column(String(16), nullable=False)
    signal_type: Mapped[str] = mapped_column(String(32), nullable=False)
    score: Mapped[float | None] = mapped_column(Float)
    opportunity_score: Mapped[float | None] = mapped_column(Float)
    reason_codes: Mapped[dict | None] = mapped_column(JSONB)
    payload: Mapped[dict | None] = mapped_column(JSONB)
    algo_version: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SignalForwardEval(Base):
    __tablename__ = "signal_forward_eval"
    __table_args__ = (
        UniqueConstraint("signal_id", name="uq_signal_forward_eval_signal"),
        Index("idx_signal_forward_eval_type_version", "signal_type", "algo_version"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    signal_id: Mapped[int] = mapped_column(ForeignKey("strategy_signal.id"), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    ts_code: Mapped[str] = mapped_column(String(16), nullable=False)
    signal_type: Mapped[str] = mapped_column(String(32), nullable=False)
    algo_version: Mapped[str] = mapped_column(String(32), nullable=False)
    ret5: Mapped[float | None] = mapped_column(Float)
    ret10: Mapped[float | None] = mapped_column(Float)
    ret20: Mapped[float | None] = mapped_column(Float)
    ret60: Mapped[float | None] = mapped_column(Float)
    mfe20: Mapped[float | None] = mapped_column(Float)
    mae20: Mapped[float | None] = mapped_column(Float)
    evaluated_until_date: Mapped[date | None] = mapped_column(Date)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
