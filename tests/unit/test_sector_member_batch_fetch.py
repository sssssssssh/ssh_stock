import pandas as pd
import pytest
from app.providers.tushare_provider import TushareProvider


def _provider_with_fake_call(responses):
    provider = object.__new__(TushareProvider)
    provider.calls = []

    def fake_call(api_name, **kwargs):
        provider.calls.append((api_name, kwargs))
        response = responses[(api_name, kwargs.get("l1_code"), kwargs.get("is_new"))]
        if isinstance(response, Exception):
            raise response
        return response

    provider._call = fake_call
    return provider


def test_sector_member_batch_fetches_l1_current_and_history() -> None:
    classification = pd.DataFrame(
        [
            {"index_code": "801010.SI", "name": "农林牧渔", "level": "L1"},
            {"index_code": "801030.SI", "name": "基础化工", "level": "L1"},
            {"index_code": "801011.SI", "name": "种植业", "level": "L2"},
        ]
    )
    responses = {
        ("index_classify", None, None): classification,
        ("index_member_all", "801010.SI", "Y"): pd.DataFrame(
            [{"l1_code": "801010.SI", "con_code": "000001.SZ", "in_date": "20200101"}]
        ),
        ("index_member_all", "801010.SI", "N"): pd.DataFrame(
            [
                {
                    "l1_code": "801010.SI",
                    "con_code": "000001.SZ",
                    "in_date": "20200101",
                    "out_date": "20210101",
                }
            ]
        ),
        ("index_member_all", "801030.SI", "Y"): pd.DataFrame(
            [{"l1_code": "801030.SI", "con_code": "000002.SZ", "in_date": "20200201"}]
        ),
        ("index_member_all", "801030.SI", "N"): pd.DataFrame(
            [
                {
                    "l1_code": "801030.SI",
                    "con_code": "000002.SZ",
                    "in_date": "20200201",
                    "out_date": "20210201",
                }
            ]
        ),
    }
    provider = _provider_with_fake_call(responses)

    df = provider.get_sector_members()

    assert provider.calls == [
        ("index_classify", {"src": "SW2021"}),
        ("index_member_all", {"src": "SW", "l1_code": "801010.SI", "is_new": "Y"}),
        ("index_member_all", {"src": "SW", "l1_code": "801010.SI", "is_new": "N"}),
        ("index_member_all", {"src": "SW", "l1_code": "801030.SI", "is_new": "Y"}),
        ("index_member_all", {"src": "SW", "l1_code": "801030.SI", "is_new": "N"}),
    ]
    assert len(df.index) == 4
    assert set(df["out_date"].dropna()) == {"20210101", "20210201"}


def test_sector_member_batch_failure_mentions_l1_code() -> None:
    classification = pd.DataFrame([{"index_code": "801010.SI", "name": "农林牧渔", "level": "L1"}])
    responses = {
        ("index_classify", None, None): classification,
        ("index_member_all", "801010.SI", "Y"): RuntimeError("frequency limited"),
        ("index_member_all", "801010.SI", "N"): pd.DataFrame(),
    }
    provider = _provider_with_fake_call(responses)

    with pytest.raises(RuntimeError, match="801010.SI/Y"):
        provider.get_sector_members()


def test_sector_member_current_batch_empty_fails_with_l1_code() -> None:
    classification = pd.DataFrame([{"index_code": "801010.SI", "name": "农林牧渔", "level": "L1"}])
    responses = {
        ("index_classify", None, None): classification,
        ("index_member_all", "801010.SI", "Y"): pd.DataFrame(),
        ("index_member_all", "801010.SI", "N"): pd.DataFrame(),
    }
    provider = _provider_with_fake_call(responses)

    with pytest.raises(RuntimeError) as exc_info:
        provider.get_sector_members()

    message = str(exc_info.value)
    assert "sector_member current batch empty" in message
    assert "l1_code=801010.SI" in message


def test_sector_member_history_batch_empty_is_allowed() -> None:
    classification = pd.DataFrame([{"index_code": "801010.SI", "name": "农林牧渔", "level": "L1"}])
    responses = {
        ("index_classify", None, None): classification,
        ("index_member_all", "801010.SI", "Y"): pd.DataFrame(
            [{"l1_code": "801010.SI", "con_code": "000001.SZ", "in_date": "20200101"}]
        ),
        ("index_member_all", "801010.SI", "N"): pd.DataFrame(),
    }
    provider = _provider_with_fake_call(responses)

    df = provider.get_sector_members()

    assert len(df.index) == 1
    assert df.iloc[0]["con_code"] == "000001.SZ"
