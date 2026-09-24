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


class StockStDaily(Base):
    __tablename__ = "stock_st_daily"
    __table_args__ = (PrimaryKeyConstraint("trade_date", "ts_code"),)

    trade_date: Mapped[date] = mapped_column(Date)
    ts_code: Mapped[str] = mapped_column(String(16))
    name: Mapped[str | None] = mapped_column(String(64))
    st_type: Mapped[str | None] = mapped_column(String(32))
    st_type_name: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class StockSuspendDaily(Base):
    __tablename__ = "stock_suspend_daily"
    __table_args__ = (PrimaryKeyConstraint("trade_date", "ts_code", "suspend_type"),)

    trade_date: Mapped[date] = mapped_column(Date)
    ts_code: Mapped[str] = mapped_column(String(16))
    suspend_type: Mapped[str] = mapped_column(String(8))
    suspend_timing: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class StockLimitDaily(Base):
    __tablename__ = "stock_limit_daily"
    __table_args__ = (PrimaryKeyConstraint("trade_date", "ts_code"),)

    trade_date: Mapped[date] = mapped_column(Date)
    ts_code: Mapped[str] = mapped_column(String(16))
    pre_close: Mapped[float | None] = mapped_column(Float)
    up_limit: Mapped[float | None] = mapped_column(Float)
    down_limit: Mapped[float | None] = mapped_column(Float)
    asset_type: Mapped[str | None] = mapped_column(String(16))
    exchange: Mapped[str | None] = mapped_column(String(8))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


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
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    issue_codes: Mapped[dict | None] = mapped_column(JSONB)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class DataDirtyRange(Base):
    __tablename__ = "data_dirty_range"
    __table_args__ = (Index("idx_data_dirty_range_status_start", "status", "dirty_start_date"),)

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
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StockTradeStatusDaily(Base):
    __tablename__ = "stock_trade_status_daily"
    __table_args__ = (
        PrimaryKeyConstraint("trade_date", "ts_code"),
        Index("idx_trade_status_date_tradable", "trade_date", "tradable"),
        Index("idx_trade_status_date_eligible", "trade_date", "strategy_eligible"),
    )

    trade_date: Mapped[date] = mapped_column(Date)
    ts_code: Mapped[str] = mapped_column(String(16))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_suspended: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_st: Mapped[bool | None] = mapped_column(Boolean)
    st_status_unknown: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    up_limit: Mapped[float | None] = mapped_column(Float)
    down_limit: Mapped[float | None] = mapped_column(Float)
    is_limit_up_close: Mapped[bool | None] = mapped_column(Boolean)
    is_limit_down_close: Mapped[bool | None] = mapped_column(Boolean)
    tradable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    strategy_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status_reason: Mapped[str | None] = mapped_column(String(256))
    calc_version: Mapped[str] = mapped_column(String(32), nullable=False)
    config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    calc_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


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
    calc_version: Mapped[str | None] = mapped_column(String(32))
    config_hash: Mapped[str | None] = mapped_column(String(64))
    calc_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    calculated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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
    calc_version: Mapped[str | None] = mapped_column(String(32))
    config_hash: Mapped[str | None] = mapped_column(String(64))
    calc_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    calculated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SignalForwardEval(Base):
    __tablename__ = "signal_forward_eval"
    __table_args__ = (
        UniqueConstraint(
            "signal_id",
            "eval_version",
            "entry_basis",
            name="uq_signal_forward_eval_version_basis",
        ),
        Index("idx_signal_forward_eval_type_version", "signal_type", "algo_version"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    signal_id: Mapped[int] = mapped_column(
        ForeignKey("strategy_signal.id", ondelete="CASCADE"), nullable=False
    )
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    ts_code: Mapped[str] = mapped_column(String(16), nullable=False)
    signal_type: Mapped[str] = mapped_column(String(32), nullable=False)
    algo_version: Mapped[str] = mapped_column(String(32), nullable=False)
    eval_version: Mapped[str] = mapped_column(String(16), nullable=False, default="eval_v3")
    entry_basis: Mapped[str] = mapped_column(String(16), nullable=False, default="NEXT_OPEN")
    horizon_basis: Mapped[str] = mapped_column(
        String(32), nullable=False, default="MARKET_TRADING_DAY"
    )
    entry_trade_date: Mapped[date | None] = mapped_column(Date)
    entry_price: Mapped[float | None] = mapped_column(Float)
    entry_executable: Mapped[bool | None] = mapped_column(Boolean)
    exit_executable: Mapped[bool | None] = mapped_column(Boolean)
    non_executable_reason: Mapped[str | None] = mapped_column(String(128))
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


class Theme(Base):
    __tablename__ = "theme"

    theme_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    theme_type: Mapped[str] = mapped_column(String(16), nullable=False)
    exchange: Mapped[str | None] = mapped_column(String(16))
    constituent_count: Mapped[int | None] = mapped_column(Integer)
    list_date: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    first_seen_date: Mapped[date | None] = mapped_column(Date)
    last_seen_date: Mapped[date | None] = mapped_column(Date)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ThemeMemberSnapshot(Base):
    __tablename__ = "theme_member_snapshot"
    __table_args__ = (
        PrimaryKeyConstraint("snapshot_date", "theme_code", "ts_code"),
        Index("idx_theme_member_stock_snapshot", "ts_code", "snapshot_date"),
    )

    snapshot_date: Mapped[date] = mapped_column(Date)
    theme_code: Mapped[str] = mapped_column(ForeignKey("theme.theme_code"))
    ts_code: Mapped[str] = mapped_column(String(16))
    stock_name: Mapped[str | None] = mapped_column(String(64))
    is_new: Mapped[bool | None] = mapped_column(Boolean)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ThemeMemberInterval(Base):
    __tablename__ = "theme_member_interval"
    __table_args__ = (
        PrimaryKeyConstraint("theme_code", "ts_code", "valid_from"),
        Index("idx_theme_member_interval_stock_dates", "ts_code", "valid_from", "valid_to"),
    )

    theme_code: Mapped[str] = mapped_column(ForeignKey("theme.theme_code"))
    ts_code: Mapped[str] = mapped_column(String(16))
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    source_is_new: Mapped[bool | None] = mapped_column(Boolean)
    quality_flag: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ThemeDaily(Base):
    __tablename__ = "theme_daily"
    __table_args__ = (
        PrimaryKeyConstraint("trade_date", "theme_code"),
        Index("idx_theme_daily_code_date", "theme_code", "trade_date"),
    )

    trade_date: Mapped[date] = mapped_column(Date)
    theme_code: Mapped[str] = mapped_column(ForeignKey("theme.theme_code"))
    open: Mapped[float | None] = mapped_column(Float)
    high: Mapped[float | None] = mapped_column(Float)
    low: Mapped[float | None] = mapped_column(Float)
    close: Mapped[float | None] = mapped_column(Float)
    pre_close: Mapped[float | None] = mapped_column(Float)
    avg_price: Mapped[float | None] = mapped_column(Float)
    change: Mapped[float | None] = mapped_column(Float)
    pct_change: Mapped[float | None] = mapped_column(Float)
    vol: Mapped[float | None] = mapped_column(Float)
    turnover_rate: Mapped[float | None] = mapped_column(Float)
    total_mv: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ThemeMoneyflowDaily(Base):
    __tablename__ = "theme_moneyflow_daily"
    __table_args__ = (PrimaryKeyConstraint("trade_date", "theme_code"),)

    trade_date: Mapped[date] = mapped_column(Date)
    theme_code: Mapped[str] = mapped_column(ForeignKey("theme.theme_code"))
    name: Mapped[str | None] = mapped_column(String(128))
    lead_stock: Mapped[str | None] = mapped_column(String(64))
    close_price: Mapped[float | None] = mapped_column(Float)
    pct_change: Mapped[float | None] = mapped_column(Float)
    theme_index: Mapped[float | None] = mapped_column(Float)
    company_num: Mapped[float | None] = mapped_column(Float)
    lead_stock_pct_change: Mapped[float | None] = mapped_column(Float)
    net_buy_amount: Mapped[float | None] = mapped_column(Float)
    net_sell_amount: Mapped[float | None] = mapped_column(Float)
    net_amount: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ThemeLimitDaily(Base):
    __tablename__ = "theme_limit_daily"
    __table_args__ = (PrimaryKeyConstraint("trade_date", "theme_code"),)

    trade_date: Mapped[date] = mapped_column(Date)
    theme_code: Mapped[str] = mapped_column(ForeignKey("theme.theme_code"))
    name: Mapped[str | None] = mapped_column(String(128))
    days: Mapped[int | None] = mapped_column(Integer)
    up_stat: Mapped[str | None] = mapped_column(String(64))
    cons_nums: Mapped[int | None] = mapped_column(Integer)
    up_nums: Mapped[int | None] = mapped_column(Integer)
    pct_chg: Mapped[float | None] = mapped_column(Float)
    hot_rank: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ThemeFactorDaily(Base):
    __tablename__ = "theme_factor_daily"
    __table_args__ = (
        PrimaryKeyConstraint("trade_date", "theme_code"),
        Index("idx_theme_factor_date_rank", "trade_date", "heat_rank"),
    )

    trade_date: Mapped[date] = mapped_column(Date)
    theme_code: Mapped[str] = mapped_column(ForeignKey("theme.theme_code"))
    member_snapshot_date: Mapped[date | None] = mapped_column(Date)
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
    turnover_rate: Mapped[float | None] = mapped_column(Float)
    turnover_ratio20: Mapped[float | None] = mapped_column(Float)
    net_amount: Mapped[float | None] = mapped_column(Float)
    net_amount_3d: Mapped[float | None] = mapped_column(Float)
    net_amount_per_member: Mapped[float | None] = mapped_column(Float)
    moneyflow_score: Mapped[float | None] = mapped_column(Float)
    limit_up_count: Mapped[int | None] = mapped_column(Integer)
    limit_up_density: Mapped[float | None] = mapped_column(Float)
    continuous_limit_count: Mapped[int | None] = mapped_column(Integer)
    continuous_limit_density: Mapped[float | None] = mapped_column(Float)
    hot_list_days: Mapped[int | None] = mapped_column(Integer)
    hot_rank: Mapped[int | None] = mapped_column(Integer)
    limit_strength_score: Mapped[float | None] = mapped_column(Float)
    heat_score: Mapped[float | None] = mapped_column(Float)
    heat_rank: Mapped[int | None] = mapped_column(Integer)
    heat_momentum1: Mapped[float | None] = mapped_column(Float)
    heat_momentum3: Mapped[float | None] = mapped_column(Float)
    rank_change: Mapped[int | None] = mapped_column(Integer)
    lifecycle: Mapped[str | None] = mapped_column(String(32))
    source_coverage: Mapped[float | None] = mapped_column(Float)
    data_coverage: Mapped[float | None] = mapped_column(Float)
    calc_version: Mapped[str] = mapped_column(String(32), nullable=False)
    config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_strategy_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    calc_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StockOpportunityDaily(Base):
    __tablename__ = "stock_opportunity_daily"
    __table_args__ = (
        PrimaryKeyConstraint("trade_date", "ts_code", "algo_version"),
        Index(
            "idx_opportunity_date_stage_score",
            "trade_date",
            "opportunity_stage",
            "opportunity_score",
        ),
    )

    trade_date: Mapped[date] = mapped_column(Date)
    ts_code: Mapped[str] = mapped_column(String(16))
    algo_version: Mapped[str] = mapped_column(String(32))
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    previous_state: Mapped[str | None] = mapped_column(String(16))
    state_day_count: Mapped[int | None] = mapped_column(Integer)
    left_reversal_score: Mapped[float | None] = mapped_column(Float)
    left_reversal_new: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    right_side_score: Mapped[float | None] = mapped_column(Float)
    trend_score: Mapped[float | None] = mapped_column(Float)
    trend_rank_score: Mapped[float | None] = mapped_column(Float)
    position_score: Mapped[float | None] = mapped_column(Float)
    extension_risk: Mapped[str | None] = mapped_column(String(16))
    market_score: Mapped[float | None] = mapped_column(Float)
    industry_sector_id: Mapped[int | None] = mapped_column(Integer)
    industry_heat: Mapped[float | None] = mapped_column(Float)
    industry_lifecycle: Mapped[str | None] = mapped_column(String(32))
    primary_theme_code: Mapped[str | None] = mapped_column(String(32))
    primary_theme_name: Mapped[str | None] = mapped_column(String(128))
    primary_theme_heat: Mapped[float | None] = mapped_column(Float)
    primary_theme_lifecycle: Mapped[str | None] = mapped_column(String(32))
    hot_theme_count: Mapped[int | None] = mapped_column(Integer)
    context_score: Mapped[float | None] = mapped_column(Float)
    opportunity_stage: Mapped[str] = mapped_column(String(32), nullable=False)
    opportunity_score: Mapped[float | None] = mapped_column(Float)
    reason_codes: Mapped[dict | None] = mapped_column(JSONB)
    calc_version: Mapped[str] = mapped_column(String(32), nullable=False)
    config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_strategy_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    calc_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class _ResearchForwardFields:
    entry_trade_date: Mapped[date | None] = mapped_column(Date)
    entry_price: Mapped[float | None] = mapped_column(Float)
    entry_executable: Mapped[bool | None] = mapped_column(Boolean)
    entry_reason: Mapped[str | None] = mapped_column(String(32))
    evaluated_until_date: Mapped[date | None] = mapped_column(Date)
    mature5: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    mature10: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    mature20: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    mature60: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    exit_trade_date5: Mapped[date | None] = mapped_column(Date)
    exit_trade_date10: Mapped[date | None] = mapped_column(Date)
    exit_trade_date20: Mapped[date | None] = mapped_column(Date)
    exit_trade_date60: Mapped[date | None] = mapped_column(Date)
    exit_executable5: Mapped[bool | None] = mapped_column(Boolean)
    exit_executable10: Mapped[bool | None] = mapped_column(Boolean)
    exit_executable20: Mapped[bool | None] = mapped_column(Boolean)
    exit_executable60: Mapped[bool | None] = mapped_column(Boolean)
    exit_reason5: Mapped[str | None] = mapped_column(String(32))
    exit_reason10: Mapped[str | None] = mapped_column(String(32))
    exit_reason20: Mapped[str | None] = mapped_column(String(32))
    exit_reason60: Mapped[str | None] = mapped_column(String(32))
    ret5: Mapped[float | None] = mapped_column(Float)
    ret10: Mapped[float | None] = mapped_column(Float)
    ret20: Mapped[float | None] = mapped_column(Float)
    ret60: Mapped[float | None] = mapped_column(Float)
    benchmark_ret5: Mapped[float | None] = mapped_column(Float)
    benchmark_ret10: Mapped[float | None] = mapped_column(Float)
    benchmark_ret20: Mapped[float | None] = mapped_column(Float)
    benchmark_ret60: Mapped[float | None] = mapped_column(Float)
    excess_ret5: Mapped[float | None] = mapped_column(Float)
    excess_ret10: Mapped[float | None] = mapped_column(Float)
    excess_ret20: Mapped[float | None] = mapped_column(Float)
    excess_ret60: Mapped[float | None] = mapped_column(Float)
    mfe20: Mapped[float | None] = mapped_column(Float)
    mae20: Mapped[float | None] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OpportunityForwardEval(_ResearchForwardFields, Base):
    __tablename__ = "opportunity_forward_eval"
    __table_args__ = (
        UniqueConstraint(
            "trade_date",
            "ts_code",
            "algo_version",
            "strategy_config_hash",
            "opportunity_calc_version",
            "opportunity_config_hash",
            "research_version",
            "research_config_hash",
            "eval_version",
            "entry_basis",
            name="uq_opportunity_forward_eval_identity",
        ),
        Index("idx_opp_eval_date_stage", "trade_date", "opportunity_stage"),
        Index("idx_opp_eval_stage_rank", "opportunity_stage", "trend_rank_score"),
        Index("idx_opp_eval_risk_date", "extension_risk", "trade_date"),
        Index("idx_opp_eval_regime_date", "market_regime", "trade_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    ts_code: Mapped[str] = mapped_column(String(16), nullable=False)
    algo_version: Mapped[str] = mapped_column(String(32), nullable=False)
    strategy_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    opportunity_calc_version: Mapped[str] = mapped_column(String(32), nullable=False)
    opportunity_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    research_version: Mapped[str] = mapped_column(String(32), nullable=False)
    research_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    eval_version: Mapped[str] = mapped_column(String(32), nullable=False)
    entry_basis: Mapped[str] = mapped_column(String(16), nullable=False)
    benchmark_code: Mapped[str] = mapped_column(String(16), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    previous_state: Mapped[str | None] = mapped_column(String(16))
    state_day_count: Mapped[int | None] = mapped_column(Integer)
    opportunity_stage: Mapped[str] = mapped_column(String(32), nullable=False)
    left_reversal_score: Mapped[float | None] = mapped_column(Float)
    left_reversal_new: Mapped[bool | None] = mapped_column(Boolean)
    right_side_score: Mapped[float | None] = mapped_column(Float)
    trend_score: Mapped[float | None] = mapped_column(Float)
    trend_rank_score: Mapped[float | None] = mapped_column(Float)
    position_score: Mapped[float | None] = mapped_column(Float)
    extension_risk: Mapped[str | None] = mapped_column(String(16))
    opportunity_score: Mapped[float | None] = mapped_column(Float)
    context_score: Mapped[float | None] = mapped_column(Float)
    market_score: Mapped[float | None] = mapped_column(Float)
    market_regime: Mapped[str | None] = mapped_column(String(32))
    industry_sector_id: Mapped[int | None] = mapped_column(Integer)
    industry_heat: Mapped[float | None] = mapped_column(Float)
    industry_lifecycle: Mapped[str | None] = mapped_column(String(32))
    primary_theme_code: Mapped[str | None] = mapped_column(String(32))
    primary_theme_heat: Mapped[float | None] = mapped_column(Float)
    primary_theme_lifecycle: Mapped[str | None] = mapped_column(String(32))
    hot_theme_count: Mapped[int | None] = mapped_column(Integer)
    theme_context_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    theme_context_coverage: Mapped[float | None] = mapped_column(Float)


class ThemeForwardEval(_ResearchForwardFields, Base):
    __tablename__ = "theme_forward_eval"
    __table_args__ = (
        UniqueConstraint(
            "trade_date",
            "theme_code",
            "strategy_config_hash",
            "theme_calc_version",
            "opportunity_config_hash",
            "research_version",
            "research_config_hash",
            "eval_version",
            "entry_basis",
            name="uq_theme_forward_eval_identity",
        ),
        Index("idx_theme_eval_date_rank", "trade_date", "heat_rank"),
        Index("idx_theme_eval_lifecycle_date", "lifecycle", "trade_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    theme_code: Mapped[str] = mapped_column(String(32), nullable=False)
    strategy_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    theme_calc_version: Mapped[str] = mapped_column(String(32), nullable=False)
    opportunity_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    research_version: Mapped[str] = mapped_column(String(32), nullable=False)
    research_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    eval_version: Mapped[str] = mapped_column(String(32), nullable=False)
    entry_basis: Mapped[str] = mapped_column(String(16), nullable=False)
    benchmark_code: Mapped[str] = mapped_column(String(16), nullable=False)
    heat_score: Mapped[float | None] = mapped_column(Float)
    heat_rank: Mapped[int | None] = mapped_column(Integer)
    heat_momentum1: Mapped[float | None] = mapped_column(Float)
    heat_momentum3: Mapped[float | None] = mapped_column(Float)
    rank_change: Mapped[int | None] = mapped_column(Integer)
    lifecycle: Mapped[str | None] = mapped_column(String(32))
    return1: Mapped[float | None] = mapped_column(Float)
    return5: Mapped[float | None] = mapped_column(Float)
    return20: Mapped[float | None] = mapped_column(Float)
    moneyflow_score: Mapped[float | None] = mapped_column(Float)
    net_amount: Mapped[float | None] = mapped_column(Float)
    net_amount_3d: Mapped[float | None] = mapped_column(Float)
    limit_strength_score: Mapped[float | None] = mapped_column(Float)
    limit_up_count: Mapped[int | None] = mapped_column(Integer)
    continuous_limit_count: Mapped[int | None] = mapped_column(Integer)
    breadth20: Mapped[float | None] = mapped_column(Float)
    breadth60: Mapped[float | None] = mapped_column(Float)
    rps60_median: Mapped[float | None] = mapped_column(Float)
    source_coverage: Mapped[float | None] = mapped_column(Float)
    data_coverage: Mapped[float | None] = mapped_column(Float)
    theme_context_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    theme_context_coverage: Mapped[float | None] = mapped_column(Float)


class ResearchTransitionEval(Base):
    __tablename__ = "research_transition_eval"
    __table_args__ = (
        UniqueConstraint(
            "event_trade_date",
            "ts_code",
            "event_key",
            "algo_version",
            "trend_calc_version",
            "opportunity_calc_version",
            "strategy_config_hash",
            "opportunity_config_hash",
            "research_version",
            "research_config_hash",
            name="uq_research_transition_identity",
        ),
        Index("idx_transition_key_date", "event_key", "event_trade_date"),
        Index("idx_transition_type_threshold", "event_type", "threshold_value"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    ts_code: Mapped[str] = mapped_column(String(16), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    event_key: Mapped[str] = mapped_column(String(32), nullable=False)
    threshold_value: Mapped[float | None] = mapped_column(Float)
    source_state: Mapped[str] = mapped_column(String(16), nullable=False)
    source_score: Mapped[float | None] = mapped_column(Float)
    algo_version: Mapped[str] = mapped_column(String(32), nullable=False)
    trend_calc_version: Mapped[str] = mapped_column(String(32), nullable=False)
    opportunity_calc_version: Mapped[str] = mapped_column(String(32), nullable=False)
    strategy_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    opportunity_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    research_version: Mapped[str] = mapped_column(String(32), nullable=False)
    research_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    mature5: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    mature10: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    mature20: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    state5: Mapped[str | None] = mapped_column(String(16))
    state10: Mapped[str | None] = mapped_column(String(16))
    state20: Mapped[str | None] = mapped_column(String(16))
    days_to_s3: Mapped[int | None] = mapped_column(Integer)
    days_to_s4plus: Mapped[int | None] = mapped_column(Integer)
    days_to_s5: Mapped[int | None] = mapped_column(Integer)
    reached_s3_5: Mapped[bool | None] = mapped_column(Boolean)
    reached_s3_10: Mapped[bool | None] = mapped_column(Boolean)
    reached_s3_20: Mapped[bool | None] = mapped_column(Boolean)
    reached_s4plus_5: Mapped[bool | None] = mapped_column(Boolean)
    reached_s4plus_10: Mapped[bool | None] = mapped_column(Boolean)
    reached_s4plus_20: Mapped[bool | None] = mapped_column(Boolean)
    reached_s5_5: Mapped[bool | None] = mapped_column(Boolean)
    reached_s5_10: Mapped[bool | None] = mapped_column(Boolean)
    reached_s5_20: Mapped[bool | None] = mapped_column(Boolean)
    hit_s0_20: Mapped[bool | None] = mapped_column(Boolean)
    hit_s6_20: Mapped[bool | None] = mapped_column(Boolean)
    fell_below_s3_20: Mapped[bool | None] = mapped_column(Boolean)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
