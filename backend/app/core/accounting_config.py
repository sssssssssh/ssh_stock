from typing import Literal

from pydantic import BaseModel, ConfigDict


class StrictAccountingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TPlusOneConfig(StrictAccountingConfig):
    unlock: Literal["NEXT_TRADE_DAY_OPEN"]


class ValuationConfig(StrictAccountingConfig):
    normal_price: Literal["RAW_CLOSE"]
    suspended_policy: Literal["CARRY_FORWARD_LAST_CLOSE"]
    inactive_holding_policy: Literal["FAIL_CLOSED"]


class CorporateActionConfig(StrictAccountingConfig):
    policy: Literal["FAIL_CLOSED_ON_ADJ_FACTOR_CHANGE"]


class NavConfig(StrictAccountingConfig):
    base: Literal["INITIAL_CASH"]
    trading_cost_metric: Literal["CASH_FEE_PLUS_SLIPPAGE"]


class AccountingConfig(StrictAccountingConfig):
    version: Literal["accounting_v3"]
    cost_basis_method: Literal["MOVING_AVERAGE"]
    buy_fee_treatment: Literal["CAPITALIZE"]
    sell_fee_treatment: Literal["REALIZED_PNL"]
    t_plus_one: TPlusOneConfig
    valuation: ValuationConfig
    corporate_action: CorporateActionConfig
    nav: NavConfig
