from datetime import date
from types import ModuleType, SimpleNamespace

import app.providers.tushare_provider as tushare_provider_module
import pandas as pd
from app.providers.tushare_provider import TushareProvider, to_tushare_date


def test_to_tushare_date() -> None:
    assert to_tushare_date(date(2026, 8, 25)) == "20260825"


def test_tushare_provider_uses_proxy_initialization(monkeypatch) -> None:
    calls = []
    fake_pro = SimpleNamespace(_DataApi__http_url=None)
    fake_ts = ModuleType("tushare")

    def set_token(token: str) -> None:
        calls.append(("set_token", token))

    def pro_api():
        calls.append(("pro_api", None))
        return fake_pro

    fake_ts.set_token = set_token
    fake_ts.pro_api = pro_api
    monkeypatch.setitem(__import__("sys").modules, "tushare", fake_ts)

    provider = TushareProvider(
        token="test-token",
        http_url="https://fastapic.stockai888.top",
        min_interval_seconds=2.5,
    )

    assert provider._pro is fake_pro
    assert calls == [("set_token", "test-token"), ("pro_api", None)]
    assert fake_pro._DataApi__http_url == "https://fastapic.stockai888.top"
    assert provider._min_interval_seconds == 2.5


def test_tushare_provider_waits_between_calls(monkeypatch) -> None:
    fake_pro = SimpleNamespace(_DataApi__http_url=None)
    fake_pro.trade_cal = lambda **_: pd.DataFrame([{"cal_date": "20260825"}])
    fake_ts = ModuleType("tushare")
    fake_ts.set_token = lambda token: None
    fake_ts.pro_api = lambda: fake_pro
    monkeypatch.setitem(__import__("sys").modules, "tushare", fake_ts)

    sleeps = []
    ticks = iter([10.5, 12.0, 12.0, 12.2])
    monkeypatch.setattr(tushare_provider_module, "perf_counter", lambda: next(ticks))
    monkeypatch.setattr(tushare_provider_module, "sleep", lambda seconds: sleeps.append(seconds))

    provider = TushareProvider(token="test-token", min_interval_seconds=1.5)
    provider._last_call_started_at = 10.0

    df = provider.get_trade_calendar(date(2026, 8, 25), date(2026, 8, 25))

    assert len(df.index) == 1
    assert sleeps == [1.0]
