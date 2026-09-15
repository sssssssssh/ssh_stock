from datetime import date
from types import ModuleType, SimpleNamespace

import app.providers.tushare_provider as tushare_provider_module
import pandas as pd
import pytest
from app.providers.tushare_provider import (
    TushareProvider,
    _compact_error,
    _configure_tushare_http_url,
    _is_retryable_provider_error,
    to_tushare_date,
)


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


def test_tushare_proxy_configuration_rejects_incompatible_sdk() -> None:
    with pytest.raises(RuntimeError, match="missing private attribute"):
        _configure_tushare_http_url(SimpleNamespace(), "https://proxy.example")


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (TimeoutError("timed out"), True),
        (RuntimeError("SSL UNEXPECTED_EOF_WHILE_READING"), True),
        (RuntimeError("frequency limit exceeded"), True),
        (RuntimeError("token invalid"), False),
        (RuntimeError("permission denied"), False),
        (RuntimeError("invalid parameter: trade_date"), False),
        (RuntimeError("积分不足"), False),
    ],
)
def test_provider_retry_only_accepts_transient_errors(error, expected) -> None:
    assert _is_retryable_provider_error(error) is expected


def test_tushare_provider_waits_between_calls(monkeypatch) -> None:
    calls = []
    provider = object.__new__(TushareProvider)
    provider._min_interval_seconds = 1.5
    monkeypatch.setattr(
        tushare_provider_module,
        "wait_for_rate_limit",
        lambda *args: calls.append(args),
    )

    provider._wait_for_rate_limit("daily")

    assert calls == [("tushare", "daily", 1.5)]


def test_tushare_provider_marks_possible_truncation() -> None:
    provider = object.__new__(TushareProvider)
    provider._safe_limits = {"daily": 2}
    provider.provider_name = "tushare"
    df = pd.DataFrame([{"ts_code": "000001.SZ"}, {"ts_code": "000002.SZ"}])

    provider._mark_possible_truncation("daily", df)

    assert df.attrs["provider_warning"] == "POSSIBLE_TRUNCATION"
    assert "safe_limit=2" in df.attrs["provider_warning_message"]


def test_tushare_provider_fetches_index_daily_range(monkeypatch) -> None:
    provider = object.__new__(TushareProvider)
    calls = []

    def fake_call(api_name, **kwargs):
        calls.append((api_name, kwargs))
        return pd.DataFrame([{"ts_code": kwargs["ts_code"]}])

    monkeypatch.setattr(provider, "_call", fake_call)

    df = provider.get_index_daily_range("000300.SH", date(2026, 8, 1), date(2026, 8, 31))

    assert calls == [
        (
            "index_daily",
                {
                    "ts_code": "000300.SH",
                    "start_date": "20260801",
                    "end_date": "20260831",
                    "fields": (
                        "ts_code,trade_date,open,high,low,close,pre_close,"
                        "pct_chg,vol,amount"
                    ),
                },
        )
    ]
    assert len(df.index) == 1


def test_tushare_provider_fetches_stock_basic_statuses(monkeypatch) -> None:
    requested_shards = []
    fake_pro = SimpleNamespace(_DataApi__http_url=None)

    def stock_basic(**kwargs):
        status = kwargs["list_status"]
        requested_shards.append((status, kwargs["exchange"]))
        return pd.DataFrame(
            [
                {
                    "ts_code": f"00000{len(requested_shards)}.SZ",
                    "list_status": status,
                }
            ]
        )

    fake_pro.stock_basic = stock_basic
    fake_ts = ModuleType("tushare")
    fake_ts.set_token = lambda token: None
    fake_ts.pro_api = lambda: fake_pro
    monkeypatch.setitem(__import__("sys").modules, "tushare", fake_ts)

    provider = TushareProvider(token="test-token", min_interval_seconds=0)
    df = provider.get_stock_basic()

    assert requested_shards == [
        (status, exchange)
        for status in ("L", "D", "P")
        for exchange in ("SSE", "SZSE", "BSE")
    ]
    assert set(df["list_status"]) == {"L", "D", "P"}


def test_stock_basic_required_status_error_includes_source_error(monkeypatch) -> None:
    fake_pro = SimpleNamespace(_DataApi__http_url=None)

    def stock_basic(**kwargs):
        status = kwargs["list_status"]
        if status == "L":
            raise RuntimeError("tushare frequency limit exceeded")
        return pd.DataFrame([{"ts_code": f"00000{status}.SZ", "list_status": status}])

    fake_pro.stock_basic = stock_basic
    fake_ts = ModuleType("tushare")
    fake_ts.set_token = lambda token: None
    fake_ts.pro_api = lambda: fake_pro
    monkeypatch.setitem(__import__("sys").modules, "tushare", fake_ts)

    provider = TushareProvider(token="test-token", min_interval_seconds=0)

    with pytest.raises(RuntimeError) as exc_info:
        provider.get_stock_basic()

    message = str(exc_info.value)
    assert "stock_basic required statuses missing: ['L']" in message
    assert "L/SSE: tushare frequency limit exceeded" in message
    assert "L/SZSE: tushare frequency limit exceeded" in message
    assert "L/BSE: tushare frequency limit exceeded" in message


def test_compact_error_limits_long_source_error() -> None:
    message = _compact_error(RuntimeError("x" * 1000), max_length=12)

    assert message == "x" * 12 + "..."


def test_stock_basic_aggregates_shard_truncation_warning(monkeypatch) -> None:
    provider = object.__new__(TushareProvider)

    def fake_call(api_name, **kwargs):
        frame = pd.DataFrame(
            [
                {
                    "ts_code": f"{kwargs['list_status']}.{kwargs['exchange']}",
                    "list_status": kwargs["list_status"],
                }
            ]
        )
        if kwargs["list_status"] == "L" and kwargs["exchange"] == "SZSE":
            frame.attrs["provider_warning"] = "POSSIBLE_TRUNCATION"
        return frame

    monkeypatch.setattr(provider, "_call", fake_call)

    result = provider.get_stock_basic()

    assert result.attrs["provider_warning"] == "POSSIBLE_TRUNCATION"
    assert "L/SZSE:POSSIBLE_TRUNCATION" in result.attrs["provider_warning_message"]


def test_tushare_provider_fetches_milestone9_raw_datasets(monkeypatch) -> None:
    provider = object.__new__(TushareProvider)
    calls = []

    def fake_call(api_name, **kwargs):
        calls.append((api_name, kwargs))
        return pd.DataFrame()

    monkeypatch.setattr(provider, "_call", fake_call)
    target = date(2026, 9, 15)

    provider.get_stock_st(target)
    provider.get_suspend_daily(target)
    provider.get_stock_limit(target)

    assert [call[0] for call in calls] == ["stock_st", "suspend_d", "stk_limit"]
    assert calls[0][1]["trade_date"] == "20260915"
    assert calls[1][1]["trade_date"] == "20260915"
    assert calls[2][1]["trade_date"] == "20260915"
