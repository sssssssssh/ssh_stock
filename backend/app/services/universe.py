from datetime import date


def is_stock_active_on(
    list_date: date | None,
    delist_date: date | None,
    trade_date: date,
) -> bool:
    if list_date is None or list_date != list_date:
        return False
    if list_date > trade_date:
        return False
    if delist_date is None or delist_date != delist_date:
        return True
    return trade_date <= delist_date
