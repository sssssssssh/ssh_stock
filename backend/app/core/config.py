from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.strategy_config import StrategyConfig

ROOT_DIR = Path(__file__).resolve().parents[3]


def load_yaml_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML config must be a mapping: {path}")
    return data


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "dev"
    app_timezone: str = "Asia/Shanghai"
    database_url: str = "postgresql+psycopg://stock:stock@127.0.0.1:5432/stock_db"
    tushare_token: str | None = Field(default=None, repr=False)
    tushare_http_url: str | None = "https://fastapic.stockai888.top"
    tushare_min_interval_seconds: float = 1.5
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    log_level: str = "INFO"
    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: str = Field(default="123456", repr=False)
    auth_session_hours: int = 168
    auth_cookie_secure: bool = False
    auth_last_seen_update_minutes: int = 10
    auth_login_failure_window_seconds: int = 300
    auth_login_max_failures: int = 5
    auth_login_lockout_seconds: int = 60
    realtime_kline_cache_seconds: int = 120
    realtime_kline_negative_cache_seconds: int = 1800

    app_name: str = "空间"
    algo_version: str = "v1.0"
    strategy: dict[str, Any] = Field(default_factory=dict)
    opportunity_config: dict[str, Any] = Field(default_factory=dict)
    research_config: dict[str, Any] = Field(default_factory=dict)
    app_config: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_runtime_security(self) -> "Settings":
        if self.auth_last_seen_update_minutes <= 0:
            raise ValueError("AUTH_LAST_SEEN_UPDATE_MINUTES must be positive")
        for field_name in (
            "auth_login_failure_window_seconds",
            "auth_login_max_failures",
            "auth_login_lockout_seconds",
        ):
            if getattr(self, field_name) <= 0:
                raise ValueError(f"{field_name.upper()} must be positive")
        if self.realtime_kline_cache_seconds < 0:
            raise ValueError("REALTIME_KLINE_CACHE_SECONDS must be nonnegative")
        if self.realtime_kline_negative_cache_seconds < 0:
            raise ValueError("REALTIME_KLINE_NEGATIVE_CACHE_SECONDS must be nonnegative")
        if self.app_env.lower() == "prod":
            if (
                not self.bootstrap_admin_password
                or self.bootstrap_admin_password == "123456"
                or len(self.bootstrap_admin_password) < 12
            ):
                raise ValueError(
                    "production BOOTSTRAP_ADMIN_PASSWORD must be configured, non-default, "
                    "and at least 12 characters"
                )
            if not self.auth_cookie_secure:
                raise ValueError("production AUTH_COOKIE_SECURE must be true")
        return self

    @classmethod
    def build(cls) -> "Settings":
        settings = cls()
        app_config = load_yaml_config(ROOT_DIR / "config" / "app.yaml")
        strategy_raw = load_yaml_config(ROOT_DIR / "config" / "strategy.yaml")
        strategy = StrategyConfig.model_validate(strategy_raw).model_dump(mode="python")
        opportunity_config = load_yaml_config(ROOT_DIR / "config" / "opportunity.yaml")
        research_config = load_yaml_config(ROOT_DIR / "config" / "research.yaml").get(
            "research", {}
        )
        _validate_opportunity_weights(opportunity_config)
        _validate_research_config(research_config, opportunity_config)
        app_section = app_config.get("app", {})
        if isinstance(app_section, dict):
            settings.app_name = app_section.get("name", settings.app_name)
            settings.algo_version = app_section.get("algo_version", settings.algo_version)
            settings.app_timezone = app_section.get("timezone", settings.app_timezone)
        settings.app_config = app_config
        settings.strategy = strategy
        settings.opportunity_config = opportunity_config
        settings.research_config = research_config
        return settings


def _validate_research_config(
    config: dict[str, Any], opportunity_config: dict[str, Any] | None = None
) -> None:
    if not isinstance(config, dict):
        raise ValueError("research config must be a mapping")
    for key in ("version", "eval_version", "benchmark_code"):
        if not isinstance(config.get(key), str) or not config[key].strip():
            raise ValueError(f"research.{key} must be nonempty")
    if config["version"] != "research_v1" or config["eval_version"] != "research_eval_v8":
        raise ValueError("research schema requires research_v1/research_eval_v8")
    for key, upper in (
        ("horizons", 250),
        ("transition_horizons", 250),
        ("left_thresholds", 100),
        ("trend_topn", None),
        ("theme_topn", None),
    ):
        values = config.get(key)
        if (
            not isinstance(values, list)
            or not values
            or any(type(value) is not int for value in values)
            or any(
                (value < 0 if key == "left_thresholds" else value <= 0)
                or (upper is not None and value > upper)
                for value in values
            )
            or values != sorted(set(values))
        ):
            raise ValueError(f"research.{key} must be strictly increasing valid integers")
    if config["horizons"] != [5, 10, 20, 60] or config["transition_horizons"] != [5, 10, 20]:
        raise ValueError("research v1 schema supports fixed 5/10/20/60 and 5/10/20 horizons")
    if opportunity_config is not None:
        strong_score = opportunity_config.get("left_reversal", {}).get("strong_score")
        if strong_score not in config["left_thresholds"]:
            raise ValueError(
                "research.left_thresholds must contain production "
                f"left_reversal.strong_score={strong_score}"
            )
    if config.get("stock", {}).get("entry_basis") != "NEXT_OPEN":
        raise ValueError("research.stock.entry_basis must be NEXT_OPEN")
    theme = config.get("theme", {})
    if theme.get("entry_basis") != "NEXT_CLOSE":
        raise ValueError("research.theme.entry_basis must be NEXT_CLOSE")
    coverage = theme.get("min_data_coverage")
    if not isinstance(coverage, (int, float)) or not 0 <= coverage <= 1:
        raise ValueError("research.theme.min_data_coverage must be in 0..1")
    size = config.get("score_bucket_size")
    if type(size) is not int or not 1 <= size <= 50:
        raise ValueError("research.score_bucket_size must be in 1..50")
    search_days = config.get("executable_exit_search_days")
    if type(search_days) is not int or not 0 <= search_days <= 20:
        raise ValueError("research.executable_exit_search_days must be in 0..20")
    min_refresh_lookback = max(config["horizons"]) + 1 + search_days
    if config.get("refresh_lookback_trade_days", 0) < min_refresh_lookback:
        raise ValueError("research.refresh_lookback_trade_days is too short")
    for key in ("batch_trade_days", "min_sample_warning"):
        if type(config.get(key)) is not int or config[key] <= 0:
            raise ValueError(f"research.{key} must be positive")
    costs = config.get("trading_cost")
    if not isinstance(costs, dict):
        raise ValueError("research.trading_cost must be a mapping")
    required_costs = {
        "enabled",
        "commission_rate",
        "minimum_commission_cny",
        "stamp_tax_sell_rate",
        "slippage_bps",
    }
    if set(costs) != required_costs or type(costs["enabled"]) is not bool:
        raise ValueError("research.trading_cost has invalid fields")
    for key in required_costs - {"enabled"}:
        if not isinstance(costs[key], (int, float)) or costs[key] < 0:
            raise ValueError(f"research.trading_cost.{key} must be nonnegative")


def _validate_opportunity_weights(config: dict[str, Any]) -> None:
    paths = [
        ("theme", "heat_weights"),
        ("left_reversal", "weights"),
        ("trend_pool", "weights"),
    ]
    for section, key in paths:
        weights = config.get(section, {}).get(key, {})
        if not isinstance(weights, dict) or not weights:
            raise ValueError(f"opportunity config missing weights: {section}.{key}")
        total = sum(float(value) for value in weights.values())
        if abs(total - 1.0) > 1e-6 or any(float(value) < 0 for value in weights.values()):
            raise ValueError(f"opportunity weights are invalid: {section}.{key}={total}")

    paired_weights = [
        (
            "opportunity.left",
            config.get("opportunity", {}),
            ("left_structure_weight", "left_context_weight"),
        ),
        (
            "opportunity.trend",
            config.get("opportunity", {}),
            ("trend_quality_weight", "trend_position_weight"),
        ),
        (
            "right_side",
            config.get("right_side", {}),
            ("right_score_weight", "context_weight", "market_weight"),
        ),
    ]
    for name, section, keys in paired_weights:
        total = sum(float(section.get(key, 0)) for key in keys)
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"opportunity weights are invalid: {name}={total}")


@lru_cache
def get_settings() -> Settings:
    return Settings.build()
