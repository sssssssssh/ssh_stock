from app.core.config import get_settings


def test_settings_load_yaml_defaults() -> None:
    settings = get_settings()

    assert settings.app_name == "空间"
    assert settings.algo_version == "v1.1"
    assert settings.strategy["benchmark"]["primary"] == "000300.SH"
    assert settings.tushare_http_url == "https://fastapic.stockai888.top"
    assert settings.tushare_min_interval_seconds == 1.5
