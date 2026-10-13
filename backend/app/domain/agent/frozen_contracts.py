from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

M14_CONTRACT_VERSION = "m16.6-m14-bundle-v1"
M15_WINDOW_CONTRACT_VERSION = "m16.6-m15-window-v1"
M15_AGGREGATE_CONTRACT_VERSION = "m16.6-m15-aggregate-v1"
CONTRACT_MANIFEST_VERSION = "m16.6-contract-manifest-v1"


class FrozenContractDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_call_id: str = Field(min_length=1, max_length=128)
    contract_kind: Literal["M14_EXACT_BUNDLE", "M15_WINDOW_LINEAGE", "M15_STUDY_AGGREGATE"]
    subject_id: str = Field(min_length=1, max_length=160)
    role: Literal["LIVE", "TRAIN", "OOS", "STUDY"]
    schema_version: str
    verification_scope: Literal["FROZEN_CONTRACT_RECHECK", "STUDY_AGGREGATE_ONLY"]
    contract_json: dict[str, Any]

    @model_validator(mode="after")
    def check_kind_and_version(self):
        versions = {
            "M14_EXACT_BUNDLE": M14_CONTRACT_VERSION,
            "M15_WINDOW_LINEAGE": M15_WINDOW_CONTRACT_VERSION,
            "M15_STUDY_AGGREGATE": M15_AGGREGATE_CONTRACT_VERSION,
        }
        if self.schema_version != versions[self.contract_kind]:
            raise ValueError("frozen contract version does not match kind")
        if self.contract_kind == "M15_STUDY_AGGREGATE":
            if self.role != "STUDY" or self.verification_scope != "STUDY_AGGREGATE_ONLY":
                raise ValueError("study aggregate cannot claim window verification")
        elif self.verification_scope != "FROZEN_CONTRACT_RECHECK":
            raise ValueError("source contract requires frozen recheck scope")
        return self
