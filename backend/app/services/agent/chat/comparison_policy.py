from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.domain.agent.chat import StructuredClaim


class ComparisonPolicyError(ValueError):
    pass


@dataclass(frozen=True)
class ComparisonFactContext:
    tool_name: str
    entity: str
    trade_date: str
    path: str
    unit: str
    sample_role: str
    evidence: dict[str, Any]
    identity: dict[str, Any]


class EvidenceComparisonPolicy:
    """Deterministic compatibility gate; provider prose cannot override it."""

    def evaluate(
        self,
        claim: StructuredClaim,
        facts: list[ComparisonFactContext],
    ) -> list[str]:
        if claim.claim_type != "COMPARISON":
            return []
        if len(facts) < 2:
            raise ComparisonPolicyError("comparison requires at least two verified facts")
        method = getattr(self, f"_validate_{claim.comparison_type.lower()}")
        return method(facts)

    @staticmethod
    def _validate_same_date_ranking(
        facts: list[ComparisonFactContext],
    ) -> list[str]:
        if len({fact.trade_date for fact in facts}) != 1:
            raise ComparisonPolicyError("same-date ranking mixes trade dates")
        if len({fact.entity for fact in facts}) < 2:
            raise ComparisonPolicyError("same-date ranking requires distinct entities")
        if len({fact.tool_name for fact in facts}) != 1:
            raise ComparisonPolicyError("same-date ranking mixes tool contracts")
        _require_same_units_and_leaf_path(facts)
        _require_same_identity(facts, include_source_hash=True)
        return []

    @staticmethod
    def _validate_entity_over_time(
        facts: list[ComparisonFactContext],
    ) -> list[str]:
        if len({fact.entity for fact in facts}) != 1:
            raise ComparisonPolicyError("time-series comparison mixes entities")
        if len({fact.trade_date for fact in facts}) < 2:
            raise ComparisonPolicyError("time-series comparison requires distinct dates")
        if len({fact.tool_name for fact in facts}) != 1:
            raise ComparisonPolicyError("time-series comparison mixes tool contracts")
        _require_same_units_and_leaf_path(facts)
        _require_same_identity(facts, include_source_hash=False)
        return ["COMPARISON_REQUIRES_CONTEXT:ENTITY_OVER_TIME"]

    @staticmethod
    def _validate_independent_backtests(
        facts: list[ComparisonFactContext],
    ) -> list[str]:
        allowed = {"backtest.summary", "performance.summary"}
        if any(fact.tool_name not in allowed for fact in facts):
            raise ComparisonPolicyError(
                "independent backtest comparison uses non-backtest evidence"
            )
        if len({fact.entity for fact in facts}) < 2:
            raise ComparisonPolicyError("independent backtest comparison requires distinct runs")
        _require_same_units_and_leaf_path(facts)
        for fact in facts:
            evidence = fact.evidence
            if not evidence.get("calc_run_id") or not evidence.get("config_hash"):
                raise ComparisonPolicyError("backtest evidence lacks run or configuration identity")
        _require_analytics_contract(facts)
        return ["COMPARISON_REQUIRES_CONTEXT:INDEPENDENT_BACKTESTS"]

    @staticmethod
    def _validate_train_vs_oos(
        facts: list[ComparisonFactContext],
    ) -> list[str]:
        roles = {fact.sample_role for fact in facts}
        if roles != {"TRAIN", "OOS"}:
            raise ComparisonPolicyError(
                "TRAIN/OOS comparison requires explicit TRAIN and OOS facts"
            )
        oos = [fact for fact in facts if fact.sample_role == "OOS"]
        train = [fact for fact in facts if fact.sample_role == "TRAIN"]
        if any(fact.tool_name != "walk_forward.summary" for fact in oos):
            raise ComparisonPolicyError("OOS fact is not backed by walk-forward evidence")
        if any(
            fact.tool_name not in {"backtest.summary", "performance.summary"}
            for fact in train
        ):
            raise ComparisonPolicyError("TRAIN fact is not backed by backtest evidence")
        if len({fact.unit for fact in facts}) != 1:
            raise ComparisonPolicyError("TRAIN/OOS comparison mixes units")
        for fact in oos:
            if not fact.evidence.get("report_id") or not fact.evidence.get("source_hash"):
                raise ComparisonPolicyError("OOS evidence lacks report source identity")
        for fact in train:
            if not fact.evidence.get("calc_run_id"):
                raise ComparisonPolicyError("TRAIN evidence lacks run identity")
        return ["COMPARISON_REQUIRES_CONTEXT:TRAIN_VS_OOS"]


def _require_same_units_and_leaf_path(facts: list[ComparisonFactContext]) -> None:
    if len({fact.unit for fact in facts}) != 1:
        raise ComparisonPolicyError("comparison mixes units")
    if len({fact.path.split(".")[-1] for fact in facts}) != 1:
        raise ComparisonPolicyError("comparison mixes metric fields")


def _require_same_identity(
    facts: list[ComparisonFactContext],
    *,
    include_source_hash: bool,
) -> None:
    required_keys = ("calc_version", "config_hash")
    optional_keys = ("algo_version",)
    signatures = {
        tuple(
            fact.evidence.get(key) or fact.identity.get(key)
            for key in (*required_keys, *optional_keys)
        )
        for fact in facts
    }
    signature = next(iter(signatures))
    if len(signatures) != 1 or any(
        signature[index] is None for index in range(len(required_keys))
    ):
        raise ComparisonPolicyError("comparison calculation identity is missing or inconsistent")
    if include_source_hash:
        source_hashes = {
            fact.evidence.get("source_hash") or fact.identity.get("source_hash")
            for fact in facts
        }
        source_hashes.discard(None)
        if len(source_hashes) > 1:
            raise ComparisonPolicyError("same-date ranking mixes source identities")


def _require_analytics_contract(facts: list[ComparisonFactContext]) -> None:
    versions = set()
    configs = set()
    for fact in facts:
        identity = fact.identity
        if fact.tool_name == "performance.summary":
            versions.add(identity.get("performance_version"))
            configs.add(identity.get("performance_config_hash"))
        else:
            source = identity.get("source_identity") or identity
            versions.add(
                tuple(
                    source.get(key)
                    for key in (
                        "portfolio_version",
                        "execution_version",
                        "accounting_version",
                    )
                )
            )
            configs.add(source.get("portfolio_config_hash"))
    if None in versions or None in configs or len(versions) != 1 or len(configs) != 1:
        raise ComparisonPolicyError("backtest statistical or accounting contract is incompatible")
