from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictExecutionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StampTaxSchedule(StrictExecutionConfig):
    effective_from: date
    rate: Decimal = Field(ge=0)


class TransferFeeSchedule(StrictExecutionConfig):
    effective_from: date
    effective_to: date | None = None
    exchanges: tuple[Literal["SSE", "SZSE", "BSE"], ...] = Field(min_length=1)
    rate: Decimal = Field(ge=0)

    @model_validator(mode="after")
    def validate_interval(self) -> "TransferFeeSchedule":
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("transfer fee effective_to must be on or after effective_from")
        if len(set(self.exchanges)) != len(self.exchanges):
            raise ValueError("transfer fee exchanges must be unique")
        return self


class TransferFeeConfig(StrictExecutionConfig):
    enabled: bool
    schedules: tuple[TransferFeeSchedule, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_non_overlapping_schedules(self) -> "TransferFeeConfig":
        for exchange in ("SSE", "SZSE", "BSE"):
            matching = sorted(
                (item for item in self.schedules if exchange in item.exchanges),
                key=lambda item: item.effective_from,
            )
            for previous, current in zip(matching, matching[1:], strict=False):
                if previous.effective_to is None or current.effective_from <= previous.effective_to:
                    raise ValueError(
                        f"transfer fee schedules overlap for exchange {exchange}"
                    )
        return self


class FillModelConfig(StrictExecutionConfig):
    partial_fill: Literal[False]
    insufficient_cash_policy: Literal["REJECT"]
    temporary_block_policy: Literal["RETRY"]


class TradingCostConfig(StrictExecutionConfig):
    commission_rate: Decimal = Field(ge=0)
    minimum_commission_cny: Decimal = Field(ge=0)
    stamp_tax_sell_schedule: tuple[StampTaxSchedule, ...] = Field(min_length=1)
    transfer_fee: TransferFeeConfig
    slippage_bps: Decimal = Field(ge=0)

    @model_validator(mode="after")
    def validate_stamp_tax_schedule(self) -> "TradingCostConfig":
        starts = [item.effective_from for item in self.stamp_tax_sell_schedule]
        if starts != sorted(set(starts)):
            raise ValueError("stamp tax schedule must have unique ascending effective dates")
        return self


class ExecutionConfig(StrictExecutionConfig):
    version: Literal["execution_v3"]
    mode: Literal["SIMULATED"]
    ruleset_version: Literal["cn_a_share_2026_v2"]
    simulated_order_style: Literal["LIMIT_AT_OPEN"]
    signal_time: Literal["CLOSE"]
    entry_basis: Literal["NEXT_OPEN"]
    exit_basis: Literal["NEXT_OPEN"]
    t_plus_one: Literal[True]
    pending_order_max_trade_days: int = Field(gt=0)
    price_tick_cny: Decimal = Field(gt=0)
    fill_model: FillModelConfig
    trading_cost: TradingCostConfig
