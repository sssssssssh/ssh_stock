from bisect import bisect_left
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from math import isfinite

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.market_data import StockBasic, TradeCalendar

IPO_FIRST_5_TRADING_DAYS = "IPO_FIRST_5_TRADING_DAYS"
IPO_LISTING_DAY = "IPO_LISTING_DAY"

_EXCHANGE_ALIASES = {
    "SSE": "SSE",
    "SH": "SSE",
    "SZSE": "SZSE",
    "SZ": "SZSE",
    "BSE": "BSE",
    "BJ": "BSE",
}
_SUFFIX_EXCHANGES = {"SH": "SSE", "SZ": "SZSE", "BJ": "BSE"}


@dataclass(frozen=True)
class PriceLimitExemption:
    exempt: bool
    reason: str | None = None
    evidence: dict[str, object] | None = None


@dataclass(frozen=True)
class PriceLimitValidation:
    normal_valid_codes: frozenset[str] = frozenset()
    exempt_valid_codes: frozenset[str] = frozenset()
    invalid_codes: frozenset[str] = frozenset()
    unclassified_codes: frozenset[str] = frozenset()
    exemptions: dict[str, PriceLimitExemption] = field(default_factory=dict)

    @property
    def valid_codes(self) -> set[str]:
        return set(self.normal_valid_codes | self.exempt_valid_codes)

    def issue_codes(self) -> dict[str, object]:
        exempt_codes = sorted(self.exempt_valid_codes)
        invalid_codes = sorted(self.invalid_codes)
        diagnostics = {
            code: str(info.evidence["diagnostic"])
            for code, info in sorted(self.exemptions.items())
            if info.evidence and info.evidence.get("diagnostic")
        }
        return {
            "price_limit_exempt_count": len(exempt_codes),
            "price_limit_exempt_codes": exempt_codes[:100],
            "price_limit_exempt_reasons": {
                code: self.exemptions[code].reason
                for code in exempt_codes[:100]
                if self.exemptions[code].reason
            },
            "invalid_limit_count": len(invalid_codes),
            "invalid_limit_codes": invalid_codes[:100],
            "unclassified_limit_count": len(self.unclassified_codes),
            "unclassified_limit_codes": sorted(self.unclassified_codes)[:100],
            "price_limit_exemption_diagnostics": dict(list(diagnostics.items())[:100]),
        }


def price_limit_exemptions(
    db: Session,
    *,
    trade_date: date,
    ts_codes: set[str],
) -> dict[str, PriceLimitExemption]:
    codes = {str(code) for code in ts_codes if code}
    if not codes:
        return {}

    stock_rows = db.execute(
        select(
            StockBasic.ts_code,
            StockBasic.exchange,
            StockBasic.market,
            StockBasic.list_date,
        ).where(StockBasic.ts_code.in_(sorted(codes)))
    ).all()
    stocks = {str(row.ts_code): row for row in stock_rows}
    listed_dates = [
        row.list_date
        for row in stock_rows
        if row.list_date is not None and row.list_date <= trade_date
    ]
    calendar_status: dict[date, bool] = {}
    if listed_dates:
        calendar_rows = db.execute(
            select(TradeCalendar.cal_date, TradeCalendar.is_open)
            .where(
                TradeCalendar.cal_date >= min(listed_dates),
                TradeCalendar.cal_date <= trade_date,
            )
            .order_by(TradeCalendar.cal_date)
        ).all()
        calendar_status = {row.cal_date: bool(row.is_open) for row in calendar_rows}
    open_dates = [day for day, is_open in calendar_status.items() if is_open]

    results: dict[str, PriceLimitExemption] = {}
    for code in sorted(codes):
        stock = stocks.get(code)
        if stock is None:
            results[code] = _not_exempt("STOCK_BASIC_MISSING")
            continue
        exchange, diagnostic = _resolve_exchange(code, stock.exchange)
        if diagnostic:
            results[code] = _not_exempt(
                diagnostic,
                exchange=stock.exchange,
                suffix=code.rpartition(".")[2].upper() or None,
            )
            continue
        if stock.list_date is None:
            results[code] = _not_exempt("LIST_DATE_MISSING", exchange=exchange)
            continue
        if stock.list_date > trade_date:
            results[code] = _not_exempt(
                "TRADE_DATE_BEFORE_LISTING",
                exchange=exchange,
                list_date=stock.list_date.isoformat(),
            )
            continue

        calendar_days = (trade_date - stock.list_date).days + 1
        if any(
            stock.list_date + timedelta(days=offset) not in calendar_status
            for offset in range(calendar_days)
        ):
            results[code] = _not_exempt(
                "TRADE_CALENDAR_EVIDENCE_MISSING",
                exchange=exchange,
                list_date=stock.list_date.isoformat(),
            )
            continue

        first_index = bisect_left(open_dates, stock.list_date)
        if first_index >= len(open_dates):
            results[code] = _not_exempt(
                "TRADE_CALENDAR_EVIDENCE_MISSING",
                exchange=exchange,
                list_date=stock.list_date.isoformat(),
            )
            continue
        window_size = 1 if exchange == "BSE" else 5
        qualifying_dates = open_dates[first_index : first_index + window_size]
        reason = IPO_LISTING_DAY if exchange == "BSE" else IPO_FIRST_5_TRADING_DAYS
        evidence = {
            "exchange": exchange,
            "list_date": stock.list_date.isoformat(),
            "qualifying_trade_dates": [item.isoformat() for item in qualifying_dates],
        }
        if trade_date in qualifying_dates:
            results[code] = PriceLimitExemption(True, reason, evidence)
        else:
            results[code] = PriceLimitExemption(False, evidence=evidence)
    return results


def validate_price_limit_rows(
    db: Session,
    *,
    trade_date: date,
    rows: Iterable[Mapping[str, object]],
) -> PriceLimitValidation:
    normal_valid_codes: set[str] = set()
    candidate_rows: dict[str, Mapping[str, object]] = {}
    for row in rows:
        code = str(row.get("ts_code") or "").strip()
        if not code:
            continue
        if _normal_limit_values(row.get("up_limit"), row.get("down_limit")):
            normal_valid_codes.add(code)
        else:
            candidate_rows[code] = row

    exemptions = price_limit_exemptions(
        db,
        trade_date=trade_date,
        ts_codes=set(candidate_rows),
    )
    exempt_valid_codes: set[str] = set()
    invalid_codes: set[str] = set()
    unclassified_codes: set[str] = set()
    for code, row in candidate_rows.items():
        exemption = exemptions.get(code)
        sentinel = _no_limit_sentinel(row.get("up_limit"), row.get("down_limit"))
        if sentinel and exemption is not None and exemption.exempt:
            exempt_valid_codes.add(code)
            continue
        invalid_codes.add(code)
        if sentinel and (exemption is None or not exemption.exempt):
            unclassified_codes.add(code)

    return PriceLimitValidation(
        normal_valid_codes=frozenset(normal_valid_codes),
        exempt_valid_codes=frozenset(exempt_valid_codes),
        invalid_codes=frozenset(invalid_codes),
        unclassified_codes=frozenset(unclassified_codes),
        exemptions=exemptions,
    )


def _resolve_exchange(ts_code: str, exchange: object) -> tuple[str | None, str | None]:
    raw_exchange = str(exchange).strip().upper() if exchange else ""
    metadata_exchange = _EXCHANGE_ALIASES.get(raw_exchange) if raw_exchange else None
    suffix = ts_code.rpartition(".")[2].upper()
    suffix_exchange = _SUFFIX_EXCHANGES.get(suffix)
    if raw_exchange and metadata_exchange is None:
        return None, "EXCHANGE_METADATA_UNKNOWN"
    if metadata_exchange and suffix_exchange and metadata_exchange != suffix_exchange:
        return None, "EXCHANGE_METADATA_CONFLICT"
    resolved = metadata_exchange or suffix_exchange
    if resolved is None:
        return None, "EXCHANGE_METADATA_MISSING"
    return resolved, None


def _normal_limit_values(up_limit: object, down_limit: object) -> bool:
    return _finite_number(up_limit, positive=True) and _finite_number(
        down_limit, positive=True
    )


def _no_limit_sentinel(up_limit: object, down_limit: object) -> bool:
    return _finite_number(up_limit, positive=True) and _finite_number(
        down_limit, exact_zero=True
    )


def _finite_number(
    value: object,
    *,
    positive: bool = False,
    exact_zero: bool = False,
) -> bool:
    if value is None:
        return False
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    if not isfinite(number):
        return False
    if positive:
        return number > 0
    if exact_zero:
        return number == 0
    return True


def _not_exempt(diagnostic: str, **evidence: object) -> PriceLimitExemption:
    return PriceLimitExemption(
        False,
        evidence={"diagnostic": diagnostic, **evidence},
    )
