from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

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

    app_name: str = "空间"
    algo_version: str = "v1.0"
    strategy: dict[str, Any] = Field(default_factory=dict)
    opportunity_config: dict[str, Any] = Field(default_factory=dict)
    app_config: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def build(cls) -> "Settings":
        settings = cls()
        app_config = load_yaml_config(ROOT_DIR / "config" / "app.yaml")
        strategy = load_yaml_config(ROOT_DIR / "config" / "strategy.yaml")
        opportunity_config = load_yaml_config(ROOT_DIR / "config" / "opportunity.yaml")
        _validate_opportunity_weights(opportunity_config)
        app_section = app_config.get("app", {})
        if isinstance(app_section, dict):
            settings.app_name = app_section.get("name", settings.app_name)
            settings.algo_version = app_section.get("algo_version", settings.algo_version)
            settings.app_timezone = app_section.get("timezone", settings.app_timezone)
        settings.app_config = app_config
        settings.strategy = strategy
        settings.opportunity_config = opportunity_config
        return settings


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
