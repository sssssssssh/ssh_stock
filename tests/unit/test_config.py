import pytest
from app.core.config import _validate_research_config, get_settings


def test_settings_load_yaml_defaults() -> None:
    settings = get_settings()

    assert settings.app_name == "空间"
    assert settings.algo_version == "v1.1"
    assert settings.strategy["benchmark"]["primary"] == "000300.SH"
    assert settings.tushare_http_url == "https://fastapic.stockai888.top"
    assert settings.tushare_min_interval_seconds == 1.5


def test_research_thresholds_include_production_strong_score() -> None:
    settings = get_settings()
    _validate_research_config(settings.research_config, settings.opportunity_config)
    changed = {**settings.research_config, "left_thresholds": [60, 65, 70, 80, 85]}
    with pytest.raises(ValueError, match="strong_score=75"):
        _validate_research_config(changed, settings.opportunity_config)
