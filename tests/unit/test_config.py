import pytest
from app.core.config import Settings, _validate_research_config, get_settings
from app.core.strategy_config import StrategyConfig
from pydantic import ValidationError


def test_settings_load_yaml_defaults() -> None:
    settings = get_settings()

    assert settings.app_name == "空间"
    assert settings.algo_version == "v1.1"
    assert settings.strategy["benchmark"]["primary"] == "000300.SH"
    assert settings.tushare_http_url == "https://fastapic.stockai888.top"
    assert settings.tushare_min_interval_seconds == 1.5


def test_research_thresholds_include_production_strong_score() -> None:
    settings = get_settings()
    assert settings.research_config["eval_version"] == "research_eval_v8"
    _validate_research_config(settings.research_config, settings.opportunity_config)
    changed = {**settings.research_config, "left_thresholds": [60, 65, 70, 80, 85]}
    with pytest.raises(ValueError, match="strong_score=75"):
        _validate_research_config(changed, settings.opportunity_config)


@pytest.mark.parametrize("value", (None, "5"))
def test_invalid_exit_search_days_raises_value_error_not_type_error(value) -> None:
    settings = get_settings()
    changed = dict(settings.research_config)
    changed["executable_exit_search_days"] = value
    with pytest.raises(ValueError, match="executable_exit_search_days"):
        _validate_research_config(changed, settings.opportunity_config)


@pytest.mark.parametrize(
    ("password", "secure"),
    [("123456", True), ("", True), ("long-enough-production", False)],
)
def test_production_security_rejects_unsafe_auth(password: str, secure: bool) -> None:
    with pytest.raises(ValueError, match="production"):
        Settings(
            app_env="prod",
            bootstrap_admin_password=password,
            auth_cookie_secure=secure,
        )


def test_development_allows_bootstrap_defaults() -> None:
    settings = Settings(
        app_env="dev",
        bootstrap_admin_password="123456",
        auth_cookie_secure=False,
    )
    assert settings.app_env == "dev"


def test_production_accepts_secure_non_default_password() -> None:
    settings = Settings(
        app_env="prod",
        bootstrap_admin_password="long-enough-production",
        auth_cookie_secure=True,
    )
    assert settings.auth_cookie_secure is True


def test_strategy_config_rejects_unknown_or_misspelled_fields() -> None:
    config = get_settings().strategy.copy()
    config["trend"] = {**config["trend"], "s5_min_rps6O": 90}
    with pytest.raises(ValidationError, match="s5_min_rps6O"):
        StrategyConfig.model_validate(config)
