from datetime import date

from app.services.universe import is_stock_active_on


def test_stock_active_on_point_in_time_boundaries() -> None:
    list_date = date(2020, 1, 10)
    delist_date = date(2022, 6, 30)

    assert is_stock_active_on(list_date, delist_date, date(2020, 1, 9)) is False
    assert is_stock_active_on(list_date, delist_date, date(2020, 1, 10)) is True
    assert is_stock_active_on(list_date, delist_date, date(2021, 5, 20)) is True
    assert is_stock_active_on(list_date, delist_date, date(2022, 6, 30)) is True
    assert is_stock_active_on(list_date, delist_date, date(2022, 7, 1)) is False


def test_stock_without_list_date_is_not_active_for_research() -> None:
    assert is_stock_active_on(None, None, date(2026, 8, 31)) is False
