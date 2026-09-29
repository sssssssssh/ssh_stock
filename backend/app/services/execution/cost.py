from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.core.execution_config import TradingCostConfig

_MONEY_QUANT = Decimal("0.0001")


class UnsupportedCostDateError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExecutionCost:
    commission: Decimal
    stamp_tax: Decimal
    transfer_fee: Decimal
    cash_fee_total: Decimal


class ExecutionCostCalculator:
    def calculate(
        self,
        *,
        side: str,
        trade_date: date,
        exchange: str,
        gross_amount: Decimal,
        config: TradingCostConfig,
    ) -> ExecutionCost:
        commission = _money(
            max(
                gross_amount * config.commission_rate,
                config.minimum_commission_cny,
            )
        )
        stamp_tax = Decimal("0")
        if side == "SELL":
            stamp_rate = self._stamp_tax_rate(trade_date, config)
            stamp_tax = _money(gross_amount * stamp_rate)
        transfer_fee = Decimal("0")
        if config.transfer_fee.enabled:
            transfer_rate = self._transfer_fee_rate(
                trade_date, exchange, config
            )
            transfer_fee = _money(gross_amount * transfer_rate)
        cash_fee_total = _money(commission + stamp_tax + transfer_fee)
        return ExecutionCost(
            commission=commission,
            stamp_tax=stamp_tax,
            transfer_fee=transfer_fee,
            cash_fee_total=cash_fee_total,
        )

    @staticmethod
    def _stamp_tax_rate(trade_date: date, config: TradingCostConfig) -> Decimal:
        matches = [
            item
            for item in config.stamp_tax_sell_schedule
            if item.effective_from <= trade_date
        ]
        if not matches:
            raise UnsupportedCostDateError(
                f"no stamp tax schedule for trade date {trade_date.isoformat()}"
            )
        return max(matches, key=lambda item: item.effective_from).rate

    @staticmethod
    def _transfer_fee_rate(
        trade_date: date,
        exchange: str,
        config: TradingCostConfig,
    ) -> Decimal:
        matches = [
            item
            for item in config.transfer_fee.schedules
            if exchange in item.exchanges
            and item.effective_from <= trade_date
            and (item.effective_to is None or trade_date <= item.effective_to)
        ]
        if len(matches) != 1:
            raise UnsupportedCostDateError(
                "expected exactly one transfer fee schedule for "
                f"{exchange} on {trade_date.isoformat()}, found {len(matches)}"
            )
        return matches[0].rate


def money(value: Decimal) -> Decimal:
    return _money(value)


def _money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP)
