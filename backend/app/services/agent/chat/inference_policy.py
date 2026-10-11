from __future__ import annotations

from dataclasses import dataclass

from app.domain.agent.chat import StructuredClaim, StructuredInference

INFERENCE_POLICY_VERSION = "m16.2.2-inference-v1"

_HYPOTHESIS_TEXT = {
    "POSSIBLE_ASSOCIATION": "这些已验证事实可能存在关联",
    "POSSIBLE_REGIME_SENSITIVITY": "结果可能对市场阶段敏感",
    "POSSIBLE_COST_SENSITIVITY": "结果可能对交易成本假设敏感",
    "POSSIBLE_STABILITY_CONCERN": "这些事实可能提示稳定性仍需进一步验证",
}

_UNCERTAINTY_TEXT = {
    "CAUSALITY_NOT_ESTABLISHED": "现有证据不能确定因果关系",
    "SAMPLE_SCOPE_LIMITED": "当前样本范围有限",
    "MARKET_REGIME_MAY_DIFFER": "其他市场阶段可能出现不同结果",
    "UNOBSERVED_FACTORS_REMAIN": "仍可能存在未观测因素",
}

_LIMITATION_TEXT = {
    "HISTORICAL_EVIDENCE_ONLY": "仅基于历史研究证据",
    "NOT_A_RETURN_GUARANTEE": "不构成收益保证",
    "NOT_A_TRADING_RECOMMENDATION": "不构成交易建议",
    "COMPARISON_CONTEXT_REQUIRED": "比较仍需结合明确口径背景",
}


class InferencePolicyError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class InferenceDecision:
    text: str
    inference: StructuredInference | None
    reason_codes: tuple[str, ...]
    verified_fact_refs: tuple[str, ...] = ()
    policy_version: str = INFERENCE_POLICY_VERSION


class InferencePolicy:
    """Render only controlled qualitative language; never echo provider prose."""

    def evaluate(
        self,
        claim: StructuredClaim,
        verified_claims: dict[str, StructuredClaim],
    ) -> InferenceDecision:
        if not claim.evidence_ids:
            raise InferencePolicyError("INFERENCE_EVIDENCE_REQUIRED")
        if claim.inference is None:
            return InferenceDecision(
                text=(
                    "该结论只能视为基于所列证据的有限推断，尚不能确定因果关系，"
                    "也不构成收益保证或交易建议。"
                ),
                inference=None,
                reason_codes=("LEGACY_BOUNDED_INFERENCE",),
            )
        support_ids = list(dict.fromkeys(claim.inference.supporting_claim_ids))
        if len(support_ids) != len(claim.inference.supporting_claim_ids):
            raise InferencePolicyError("DUPLICATE_SUPPORTING_CLAIM_ID")
        supports: list[StructuredClaim] = []
        for claim_id in support_ids:
            support = verified_claims.get(claim_id)
            if support is None or support.claim_type == "INFERENCE":
                raise InferencePolicyError("UNKNOWN_SUPPORTING_CLAIM_ID")
            supports.append(support)
        supported_evidence = {
            evidence_id for support in supports for evidence_id in support.evidence_ids
        }
        if not set(claim.evidence_ids).issubset(supported_evidence):
            raise InferencePolicyError("INFERENCE_EVIDENCE_NOT_SUPPORTED")
        uncertainty = "；".join(
            _UNCERTAINTY_TEXT[item] for item in claim.inference.uncertainties
        )
        limitations = "；".join(
            _LIMITATION_TEXT[item] for item in claim.inference.limitations
        )
        text = (
            f"有限推断：{_HYPOTHESIS_TEXT[claim.inference.hypothesis]}。"
            f"不确定性：{uncertainty}。限制：{limitations}。"
        )
        verified_fact_refs = tuple(
            dict.fromkeys(
                reference for support in supports for reference in support.verified_fact_refs
            )
        )
        return InferenceDecision(
            text=text,
            inference=claim.inference,
            reason_codes=("BOUNDED_QUALITATIVE_INFERENCE",),
            verified_fact_refs=verified_fact_refs,
        )
