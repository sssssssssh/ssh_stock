from pydantic import BaseModel, ConfigDict, Field


class StrictConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UniverseConfig(StrictConfig):
    exclude_st: bool
    min_listed_trading_days: int = Field(gt=0)
    min_avg_amount_20_cny: float = Field(ge=0)
    min_close: float = Field(ge=0)


class BenchmarkConfig(StrictConfig):
    primary: str
    market_indices: list[str]


class FactorConfig(StrictConfig):
    ma_windows: list[int]
    return_windows: list[int]
    rps_windows: list[int]
    atr_window: int = Field(gt=0)


class RightSideConfig(StrictConfig):
    min_score: float
    min_rps20: float
    volume_ratio_confirm: float
    base_ma60_distance_pct: float
    s3_max_days: int = Field(gt=0)


class TrendConfig(StrictConfig):
    s4_min_score: float
    s4_min_rps60: float
    s5_min_score: float
    s5_min_rps60: float
    s5_min_rps120: float


class MarketConfig(StrictConfig):
    risk_on_score: float
    risk_off_score: float


class SectorConfig(StrictConfig):
    heat_main_up: float
    heat_climax: float
    heat_watch: float


class CoverageThreshold(StrictConfig):
    warning_coverage_rate: float = Field(ge=0, le=1)
    error_coverage_rate: float = Field(ge=0, le=1)


class CrossTableConfig(StrictConfig):
    adj_vs_daily: CoverageThreshold
    basic_vs_daily: CoverageThreshold
    factor_vs_daily: CoverageThreshold
    state_vs_factor: CoverageThreshold


class DataQualityConfig(StrictConfig):
    daily: CoverageThreshold
    cross_table: CrossTableConfig


class RawQualityConfig(StrictConfig):
    adj_factor: CoverageThreshold
    daily_basic: CoverageThreshold
    stk_limit: CoverageThreshold


class SafeLimitsConfig(StrictConfig):
    stock_basic: int = Field(gt=0)
    daily: int = Field(gt=0)
    daily_basic: int = Field(gt=0)
    stock_st: int = Field(gt=0)
    stk_limit: int = Field(gt=0)
    index_member_all: int = Field(gt=0)


class TushareStrategyConfig(StrictConfig):
    safe_limits: SafeLimitsConfig


class ProviderStrategyConfig(StrictConfig):
    tushare: TushareStrategyConfig


class StrategyConfig(StrictConfig):
    universe: UniverseConfig
    benchmark: BenchmarkConfig
    factor: FactorConfig
    right_side: RightSideConfig
    trend: TrendConfig
    market: MarketConfig
    sector: SectorConfig
    data_quality: DataQualityConfig
    raw_quality: RawQualityConfig
    provider: ProviderStrategyConfig
