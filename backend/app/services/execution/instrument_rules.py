from app.domain.execution import InstrumentExecutionProfile


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
                ts_code, "SSE", normalized_market, 200, 1, 200, 1
            )
        if normalized_exchange == "SZSE" and "创业" in normalized_market:
            return InstrumentExecutionProfile(
                ts_code, "SZSE", normalized_market, 100, 100, 100, 100
            )
        if normalized_exchange == "BSE" and normalized_market in {
            "北交所",
            "北交",
        }:
            return InstrumentExecutionProfile(
                ts_code, "BSE", normalized_market, 100, 1, 100, 1
            )
        if normalized_exchange in {"SSE", "SZSE"} and normalized_market in {
            "主板",
            "中小板",
            "沪市主板",
            "深市主板",
        }:
            return InstrumentExecutionProfile(
                ts_code,
                normalized_exchange,
                normalized_market,
                100,
                100,
                100,
                100,
            )
        return None

    @staticmethod
    def valid_buy(profile: InstrumentExecutionProfile, quantity: int) -> bool:
        if quantity < profile.min_buy_quantity:
            return False
        return (quantity - profile.min_buy_quantity) % profile.buy_step == 0

    @staticmethod
    def valid_sell(
        profile: InstrumentExecutionProfile,
        quantity: int,
        total_quantity: int,
    ) -> bool:
        if profile.odd_lot_sell_all_allowed and quantity == total_quantity:
            return True
        if quantity < profile.min_sell_quantity:
            return False
        return (quantity - profile.min_sell_quantity) % profile.sell_step == 0
