from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, localcontext
from enum import StrEnum
from typing import Any

from app.domain.agent.chat import ChatCitation, StructuredClaim, StructuredFact
from app.domain.agent.report import ResearchReportSnapshot
from app.services.agent.chat.evidence_compiler import _ALLOWED_PATHS, _allowed_units
from app.services.agent.report.canonical import canonical_hash, decimal_text

# Retain the entire semantic path from the published Claim field allowlist.
ENTITY_KINDS = {
    "data.coverage": "dataset",
    "market.snapshot": "market",
    "sector.top": "sector",
    "theme.top": "theme",
    "opportunity.list": "stock",
    "backtest.summary": "backtest_run",
    "performance.summary": "backtest_run",
    "walk_forward.summary": "study",
    "walk_forward.window_lineage": "window",
}


class MetricValueKind(StrEnum):
    NUMERIC = "NUMERIC"
    DATE = "DATE"
    IDENTIFIER = "IDENTIFIER"


@dataclass(frozen=True, order=True)
class MetricDescriptor:
    metric_id: str
    entity_kind: str
    entity_id: str
    sample_role: str
    unit: str
    date_granularity: str


@dataclass(frozen=True)
class FactCandidate:
    descriptor: MetricDescriptor
    trade_date: str
    value: str
    claim_ids: tuple[str, ...]
    citation: ChatCitation

    def view(self) -> dict[str, Any]:
        return {
            "value_type": self.value_type,
            "metric_identity": asdict(self.descriptor),
            "value": self.value,
            "trade_date": self.trade_date,
            "claim_ids": list(self.claim_ids),
            "evidence_ids": [self.citation.evidence_id],
            "provenance": self.citation.model_dump(
                mode="json", exclude={"marker", "observed_at", "navigation"}
            ),
        }

    @property
    def value_type(self):
        return {"date": MetricValueKind.DATE, "identifier": MetricValueKind.IDENTIFIER}.get(
            self.descriptor.unit, MetricValueKind.NUMERIC
        )


@dataclass
class FactInventory:
    unique: dict[MetricDescriptor, FactCandidate]
    issues: list[dict[str, Any]]


def metric_semantics(fact: StructuredFact, citation: ChatCitation) -> str | None:
    patterns = _ALLOWED_PATHS.get(citation.tool_name, ())
    normalized_path = ".".join(["records", "*", *fact.path.split(".")[2:]])
    if citation.tool_name not in ENTITY_KINDS or normalized_path not in patterns:
        return None
    suffix = fact.path.split(".")[2:]
    # Nested array indices have no archived business key. Never equate by position.
    if any(part.isdigit() for part in suffix) or fact.unit not in _allowed_units(fact.path):
        return None
    if citation.tool_name == "walk_forward.window_lineage" and (
        (suffix[0] == "train_metrics" and fact.sample_role != "TRAIN")
        or (suffix[0] == "oos_metrics" and fact.sample_role != "OOS")
    ):
        return None
    return f"{citation.tool_name}:{'.'.join(suffix)}"


def collect_facts(snapshot: ResearchReportSnapshot) -> FactInventory:
    return collect_claim_facts(snapshot.claims, snapshot.citations)


def collect_claim_facts(claims: list[StructuredClaim], refs: list[ChatCitation]) -> FactInventory:
    citations: dict[str, list[ChatCitation]] = defaultdict(list)
    for citation in refs:
        citations[citation.evidence_id].append(citation)
    groups: dict[MetricDescriptor, list[FactCandidate]] = defaultdict(list)
    issues: list[dict[str, Any]] = []
    for claim in claims:
        for fact in claim.structured_facts:
            refs = [ref for eid in claim.evidence_ids for ref in citations[eid]]
            bound = [
                ref
                for ref in refs
                if ref.entity_id == fact.entity
                and ref.as_of_date == fact.trade_date
                and metric_semantics(fact, ref) is not None
            ]
            if len(bound) != 1:
                code = (
                    "UNRESOLVED_EVIDENCE_BINDING"
                    if len(bound) > 1 or not refs
                    else "LEGACY_METRIC_IDENTITY_INCOMPLETE"
                )
                issues.append(
                    {
                        "claim_id": claim.claim_id,
                        "path": fact.path,
                        "entity": fact.entity,
                        "reason_code": code,
                    }
                )
                continue
            citation = bound[0]
            metric = metric_semantics(fact, citation)
            assert metric is not None
            try:
                if fact.unit == "date":
                    value = date.fromisoformat(str(fact.value)).isoformat()
                    if value != str(fact.value):
                        raise ValueError("noncanonical date")
                elif fact.unit == "identifier":
                    value = str(fact.value)
                    if not value.strip() or len(value) > 128 or isinstance(fact.value, bool):
                        raise ValueError("invalid identifier")
                else:
                    number = Decimal(str(fact.value))
                    if (
                        not number.is_finite()
                        or len(number.as_tuple().digits) > 128
                        or abs(number.as_tuple().exponent) > 128
                    ):
                        raise ValueError("numeric resource limit")
                    with localcontext() as ctx:
                        ctx.prec = 1000
                        value = decimal_text(number)
            except (InvalidOperation, ValueError):
                issues.append(
                    {
                        "claim_id": claim.claim_id,
                        "path": fact.path,
                        "entity": fact.entity,
                        "reason_code": "INVALID_CONTEXT_FACT"
                        if fact.unit in {"date", "identifier"}
                        else "NON_NUMERIC_METRIC",
                    }
                )
                continue
            key = MetricDescriptor(
                metric,
                ENTITY_KINDS[citation.tool_name],
                fact.entity,
                fact.sample_role,
                fact.unit,
                "DAILY",
            )
            groups[key].append(
                FactCandidate(key, fact.trade_date.isoformat(), value, (claim.claim_id,), citation)
            )
    unique: dict[MetricDescriptor, FactCandidate] = {}
    for key, candidates in sorted(groups.items()):
        signatures = {canonical_hash({**item.view(), "claim_ids": []}) for item in candidates}
        if len(signatures) != 1:
            issues.append(
                {"metric_identity": asdict(key), "reason_code": "DUPLICATE_METRIC_AMBIGUOUS"}
            )
            continue
        # Every candidate is proven identical; retain all contributing Claim IDs.
        candidate = sorted(candidates, key=lambda item: item.claim_ids)[0]
        unique[key] = FactCandidate(
            key,
            candidate.trade_date,
            candidate.value,
            tuple(sorted({cid for item in candidates for cid in item.claim_ids})),
            candidate.citation,
        )
    return FactInventory(unique, sorted(issues, key=canonical_hash))


def pairing_key(key: MetricDescriptor, intent: str) -> tuple[str, ...]:
    # Run UUID is provenance, not a metric identity for an explicit cross-run intent.
    entity = "<run>" if intent == "INDEPENDENT_BACKTESTS" else key.entity_id
    return (key.metric_id, key.entity_kind, entity, key.sample_role, key.unit, key.date_granularity)
