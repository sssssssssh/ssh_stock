import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import Field, StrictBool, field_validator, model_validator

from app.core.paper_config import StrictPaperModel
from app.domain.decision.contracts import DecisionAction

Code = Annotated[str, Field(pattern=r"^\d{6}\.(SH|SZ|BJ)$")]


class PaperRequest(StrictPaperModel):
    request_id: str = Field(min_length=1, max_length=128, pattern=r"^\S+$")


class CreateObservation(PaperRequest):
    signal_date: date
    account_id: uuid.UUID | None = None
    include_codes: tuple[Code, ...] = Field(default=(), max_length=100)

    @model_validator(mode="after")
    def unique_codes(self):
        if len(set(self.include_codes)) != len(self.include_codes):
            raise ValueError("duplicate include_codes")
        return self


class CreateProposal(PaperRequest):
    account_id: uuid.UUID
    observation_id: uuid.UUID
    ts_code: Code
    action: DecisionAction
    target_weight: Decimal = Field(default=Decimal("0"), ge=0, le=1, max_digits=9, decimal_places=8)
    note: str = Field(default="", max_length=1000)
    supersedes_id: uuid.UUID | None = None
    source_report_id: uuid.UUID | None = None
    source_report_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @field_validator("target_weight", mode="before")
    @classmethod
    def no_float(cls, value):
        if isinstance(value, (float, bool)):
            raise ValueError("weight must be a decimal string")
        return value

    @model_validator(mode="after")
    def consistent_action(self):
        if (
            self.action in (DecisionAction.WATCH, DecisionAction.PROPOSE_EXIT)
            and self.target_weight != 0
        ):
            raise ValueError("WATCH/EXIT require zero target weight")
        if self.action == DecisionAction.PROPOSE_BUY and self.target_weight <= 0:
            raise ValueError("BUY requires positive target weight")
        if (self.source_report_id is None) != (self.source_report_hash is None):
            raise ValueError("report requires exact id and hash")
        return self


class ApproveProposal(PaperRequest):
    target_weight: Decimal = Field(ge=0, le=1, max_digits=9, decimal_places=8)
    confirmed: StrictBool
    note: str = Field(default="", max_length=1000)

    @field_validator("target_weight", mode="before")
    @classmethod
    def no_float(cls, value):
        return CreateProposal.no_float(value)

    @model_validator(mode="after")
    def manual_confirmation(self):
        if not self.confirmed:
            raise ValueError("explicit manual confirmation required")
        return self


class RejectProposal(PaperRequest):
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("reason must not be blank")
        return value
