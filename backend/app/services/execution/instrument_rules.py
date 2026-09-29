from app.domain.execution import InstrumentExecutionProfile, QuantityValidation

_INVALID_LOT = "INVALID_LOT"
_MAX_QUANTITY_EXCEEDED = "MAX_QUANTITY_EXCEEDED"


class AshareInstrumentRuleResolver:
    def resolve(
        self,
        *,
        ts_code: str,
        exchange: str | None,
        market: str | None,
    ) -> InstrumentExecutionProfile | None:
        normalized_exchange = (exchange or "").upper()
        normalized_market = (market or "").strip()
        if normalized_exchange == "SSE" and "科创" in normalized_market:
            return InstrumentExecutionProfile(
                ts_code=ts_code,
                exchange="SSE",
                market=normalized_market,
                min_buy_quantity=200,
                buy_step=1,
                max_buy_quantity=100_000,
                min_sell_quantity=200,
                sell_step=1,
                max_sell_quantity=100_000,
            )
        if normalized_exchange == "SZSE" and "创业" in normalized_market:
            return InstrumentExecutionProfile(
                ts_code=ts_code,
                exchange="SZSE",
                market=normalized_market,
                min_buy_quantity=100,
                buy_step=100,
                max_buy_quantity=300_000,
                min_sell_quantity=100,
                sell_step=100,
                max_sell_quantity=300_000,
            )
        if normalized_exchange == "BSE" and normalized_market in {
            "北交所",
            "北交",
        }:
            return InstrumentExecutionProfile(
                ts_code=ts_code,
                exchange="BSE",
                market=normalized_market,
                min_buy_quantity=100,
                buy_step=1,
                max_buy_quantity=1_000_000,
                min_sell_quantity=100,
                sell_step=1,
                max_sell_quantity=1_000_000,
            )
        if normalized_exchange in {"SSE", "SZSE"} and normalized_market in {
            "主板",
            "中小板",
            "沪市主板",
            "深市主板",
        }:
            return InstrumentExecutionProfile(
                ts_code=ts_code,
                exchange=normalized_exchange,
                market=normalized_market,
                min_buy_quantity=100,
                buy_step=100,
                max_buy_quantity=1_000_000,
                min_sell_quantity=100,
                sell_step=100,
                max_sell_quantity=1_000_000,
            )
        return None

    @staticmethod
    def validate_buy(
        profile: InstrumentExecutionProfile, quantity: int
    ) -> QuantityValidation:
        if quantity > profile.max_buy_quantity:
            return QuantityValidation(False, _MAX_QUANTITY_EXCEEDED)
        if quantity < profile.min_buy_quantity:
            return QuantityValidation(False, _INVALID_LOT)
        valid = (quantity - profile.min_buy_quantity) % profile.buy_step == 0
        return QuantityValidation(valid, None if valid else _INVALID_LOT)

    @staticmethod
    def validate_sell(
        profile: InstrumentExecutionProfile,
        quantity: int,
        total_quantity: int,
    ) -> QuantityValidation:
        if quantity > profile.max_sell_quantity:
            return QuantityValidation(False, _MAX_QUANTITY_EXCEEDED)
        if profile.odd_lot_sell_all_allowed and quantity == total_quantity:
            return QuantityValidation(True)
        if quantity < profile.min_sell_quantity:
            return QuantityValidation(False, _INVALID_LOT)
        valid = (quantity - profile.min_sell_quantity) % profile.sell_step == 0
        return QuantityValidation(valid, None if valid else _INVALID_LOT)
