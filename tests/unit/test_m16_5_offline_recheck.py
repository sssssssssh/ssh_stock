import json
import uuid
from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from app.core.agent_archive_config import AgentArchiveConfig
from app.domain.agent.archive import ARCHIVE_VERSION, AgentArchiveError, ArchiveVerifyView
from app.repositories.agent_archive import compiled_message_digest
from app.services.agent.archive.canonical import archive_hash
from app.services.agent.archive.capture import assemble_archive
from app.services.agent.archive.integrity import ArchiveBundle
from app.services.agent.archive.recheck import recheck_archive
from app.services.agent.chat.evidence_compiler import EvidenceCompiler
from test_m16_5_archive_capture import claims_for, market_context


def bundle(*, with_inference=False):
    context = market_context()
    claims, _ = claims_for(context)
    if with_inference:
        claims.append(
            {
                "claim_id": "inference-market",
                "claim_type": "INFERENCE",
                "text": "untrusted inference",
                "evidence_ids": list(claims[0].evidence_ids),
                "structured_facts": [],
                "inference": {
                    "hypothesis": "POSSIBLE_REGIME_SENSITIVITY",
                    "supporting_claim_ids": [claims[0].claim_id],
                    "uncertainties": ["CAUSALITY_NOT_ESTABLISHED"],
                    "limitations": ["HISTORICAL_EVIDENCE_ONLY"],
                },
            }
        )
    compiled = EvidenceCompiler(max_answer_chars=8000).compile(
        final_text=json.dumps(
            {
                "answer": "verified",
                "claims": [
                    item.model_dump(mode="json") if hasattr(item, "model_dump") else item
                    for item in claims
                ],
                "evidence_ids": [],
                "warnings": [],
                "needs_clarification": False,
            }
        ),
        tool_results=[context],
        inherited_warnings=[],
    )
    draft = assemble_archive(
        tool_results=[context],
        claims=compiled.claims,
        citations=compiled.citations,
        config=AgentArchiveConfig(),
    )
    owner, chat, turn_id, message_id = (uuid.uuid4() for _ in range(4))
    shared = dict(owner_user_id=owner, chat_id=chat, turn_id=turn_id, created_at=datetime.now(UTC))
    tools = [
        SimpleNamespace(id=uuid.uuid4(), **shared, **item.model_dump(mode="python"))
        for item in draft.tools
    ]
    bindings = [
        SimpleNamespace(
            id=uuid.uuid4(),
            **shared,
            tool_result_archive_id=tools[0].id,
            **item.model_dump(mode="python", exclude={"tool_call_id"}),
        )
        for item in draft.bindings
    ]
    metadata = {
        "verified_claims": [item.model_dump(mode="json") for item in compiled.claims],
        "citations": [item.model_dump(mode="json") for item in compiled.citations],
    }
    message = SimpleNamespace(
        id=message_id,
        session_id=chat,
        role="ASSISTANT",
        status="COMPLETED",
        metadata_json=metadata,
        content=compiled.answer,
    )
    digest = compiled_message_digest(message.content, metadata)
    body = {
        "manifest_version": ARCHIVE_VERSION,
        "owner_user_id": str(owner),
        "chat_id": str(chat),
        "turn_id": str(turn_id),
        "assistant_message_id": str(message_id),
        "archive_status": "COMPLETE",
        "required_evidence_ids": draft.required_evidence_ids,
        "claim_digest": draft.claim_digest,
        "compiled_message_digest": digest,
        "tools": [
            item.model_dump(
                mode="json", exclude={"payload_json", "arguments_json", "input_schema_json"}
            )
            for item in draft.tools
        ],
        "bindings": [
            item.model_dump(mode="json", exclude={"ref_json", "source_projection_json"})
            for item in draft.bindings
        ],
    }
    manifest = SimpleNamespace(
        id=uuid.uuid4(),
        **shared,
        assistant_message_id=message_id,
        manifest_version=ARCHIVE_VERSION,
        archive_status="COMPLETE",
        manifest_json=body,
        manifest_hash=archive_hash(body),
        claim_digest=draft.claim_digest,
        compiled_message_digest=digest,
    )
    turn = SimpleNamespace(
        id=turn_id, session_id=chat, status="COMPLETED", assistant_message_id=message_id
    )
    audits = [
        SimpleNamespace(
            tool_call_id=context.tool_call_id,
            tool_name=context.tool_name,
            args_hash=draft.tools[0].arguments_hash,
            status="READY",
            cache_reused=False,
            evidence_ids_json=draft.required_evidence_ids,
        )
    ]
    return ArchiveBundle(manifest, tools, bindings, audits, turn, message, owner)


def recheck(value, **kwargs):
    return recheck_archive(value, config=AgentArchiveConfig(), **kwargs)


def test_pure_recheck_reuses_frozen_facts_without_any_database_or_llm_dependency():
    value = bundle()
    before = deepcopy(value.tools[0].payload_json)
    result = recheck(value)
    assert result["integrity"]["status"] == "VERIFIED"
    assert result["fact_recheck"]["status"] == "VERIFIED"
    assert result["verification_level"] == "FACT_REVERIFIED"
    assert result["calculation_reproduced"] is False
    assert value.tools[0].payload_json == before


def test_inference_rechecks_support_without_claiming_direct_facts_or_causality():
    result = recheck(bundle(with_inference=True))
    rows = {row["claim_id"]: row for row in result["fact_recheck"]["results"]}
    inference = rows["inference-market"]
    assert result["integrity"]["status"] == "VERIFIED"
    assert inference["check_kind"] == "INFERENCE_SUPPORT"
    assert inference["facts_applicable"] is False
    assert inference["support_status"] == "VERIFIED"
    assert inference["status"] == "VERIFIED"
    assert "INFERENCE_NOT_CAUSAL_PROOF" in inference["reason_codes"]
    assert result["claim_recheck_summary"]["status"] == "VERIFIED"
    validated = ArchiveVerifyView.model_validate(result)
    assert validated.fact_recheck.results[-1].support_status == "VERIFIED"


@pytest.mark.parametrize(
    "fault, expected_status, reason",
    [
        ("missing", "UNVERIFIABLE", "INFERENCE_SUPPORT_UNVERIFIABLE"),
        ("duplicate", "MISMATCH", "INFERENCE_SUPPORT_INVALID"),
        ("extra_ref", "MISMATCH", "INFERENCE_FIELD_REFS_INVALID"),
        ("extra_evidence", "MISMATCH", "ARCHIVE_INTEGRITY_MISMATCH"),
    ],
)
def test_resealed_inference_support_faults_do_not_verify(fault, expected_status, reason):
    value = bundle(with_inference=True)
    claim = next(
        item
        for item in value.assistant.metadata_json["verified_claims"]
        if item["claim_type"] == "INFERENCE"
    )
    if fault == "missing":
        claim["inference"]["supporting_claim_ids"] = ["missing"]
    elif fault == "duplicate":
        claim["inference"]["supporting_claim_ids"] *= 2
    elif fault == "extra_ref":
        claim["verified_fact_refs"].append("forged:records.0.market_score")
    else:
        claim["evidence_ids"].append("forged-evidence")
    reseal_message(value)
    if fault == "extra_evidence":
        with pytest.raises(AgentArchiveError) as error:
            recheck(value)
        assert error.value.code == reason
        return
    result = recheck(value)
    inference = next(
        item
        for item in result["fact_recheck"]["results"]
        if item["claim_id"] == "inference-market"
    )
    assert inference["status"] == expected_status
    assert inference["support_status"] == expected_status
    assert reason in inference["reason_codes"]
    assert result["claim_recheck_summary"]["status"] == expected_status


@pytest.mark.parametrize(
    "fault",
    [
        "payload",
        "arguments",
        "schema",
        "ref",
        "projection",
        "manifest",
        "owner",
        "audit",
        "assistant",
        "turn",
    ],
)
def test_each_frozen_integrity_surface_is_checked(fault):
    value = bundle()
    if fault == "payload":
        value.tools[0].payload_json["records"][0]["market_score"] = "999"
    elif fault == "arguments":
        value.tools[0].arguments_json["trade_date"] = "2026-01-03"
    elif fault == "schema":
        value.tools[0].input_schema_json["title"] = "tampered"
    elif fault == "ref":
        value.bindings[0].ref_json["entity_id"] = "other"
    elif fault == "projection":
        value.bindings[0].source_projection_json["market_score"] = "999"
    elif fault == "manifest":
        value.manifest.manifest_json["required_evidence_ids"] = []
    elif fault == "owner":
        value.owner_id = uuid.uuid4()
    elif fault == "audit":
        value.audits[0].args_hash = "e" * 64
    elif fault == "assistant":
        value.assistant.content = "tampered"
    else:
        value.turn.status = "FAILED"
    with pytest.raises(AgentArchiveError):
        recheck(value)


def reseal_message(value):
    # Deliberately emulate fully consistent SHA metadata to prove SHA alone does not verify a Claim.
    value.manifest.claim_digest = archive_hash(value.assistant.metadata_json["verified_claims"])
    value.manifest.compiled_message_digest = compiled_message_digest(
        value.assistant.content, value.assistant.metadata_json
    )
    value.manifest.manifest_json.update(
        claim_digest=value.manifest.claim_digest,
        compiled_message_digest=value.manifest.compiled_message_digest,
    )
    value.manifest.manifest_hash = archive_hash(value.manifest.manifest_json)


@pytest.mark.parametrize(
    "field, bad",
    [
        ("value", "999"),
        ("unit", "currency"),
        ("entity", "other"),
        ("trade_date", "2026-01-03"),
        ("path", "records.0.hidden.market_score"),
    ],
)
def test_consistent_hashes_still_cannot_promote_a_wrong_fact(field, bad):
    value = bundle()
    claim = value.assistant.metadata_json["verified_claims"][0]
    claim["structured_facts"][0][field] = bad
    if field == "path":
        claim["verified_fact_refs"] = [f"{claim['evidence_ids'][0]}:{bad}"]
    reseal_message(value)
    result = recheck(value)
    assert result["integrity"]["status"] == "VERIFIED"
    assert result["fact_recheck"]["status"] == "MISMATCH"
    assert result["fact_recheck"]["results"][0]["failed_fields"]
    assert "999" not in str(result)  # never return the unsafe claimed number


def test_unknown_projector_is_unverifiable_not_reinterpreted_using_current_version():
    value = bundle()
    value.tools[0].projector_version = "unknown-projector"
    value.manifest.manifest_json["tools"][0]["projector_version"] = "unknown-projector"
    value.manifest.manifest_hash = archive_hash(value.manifest.manifest_json)
    result = recheck(value)
    assert result["integrity"]["status"] == "UNVERIFIABLE"
    assert "UNSUPPORTED_PROJECTOR_VERSION" in result["warnings"]


@pytest.mark.parametrize("version", ["evidence", "tool", "manifest"])
def test_unknown_frozen_versions_keep_hash_checks_but_never_use_current_parser(version):
    value = bundle()
    if version == "evidence":
        value.bindings[0].ref_json["evidence_version"] = "v3"
        value.tools[0].payload_json["evidence"][0]["evidence_version"] = "v3"
        value.assistant.metadata_json["citations"][0]["evidence_version"] = "v3"
        value.bindings[0].ref_hash = archive_hash(value.bindings[0].ref_json)
        value.manifest.manifest_json["bindings"][0]["ref_hash"] = value.bindings[0].ref_hash
    elif version == "tool":
        value.tools[0].tool_version = value.tools[0].payload_json["tool_version"] = "2.0"
        value.manifest.manifest_json["tools"][0]["tool_version"] = "2.0"
    else:
        value.manifest.manifest_version = value.manifest.manifest_json["manifest_version"] = (
            "future"
        )
    value.tools[0].payload_hash = archive_hash(value.tools[0].payload_json)
    value.manifest.manifest_json["tools"][0]["payload_hash"] = value.tools[0].payload_hash
    reseal_message(value)
    result = recheck(value)
    assert result["verification_level"] == "UNVERIFIABLE"
    assert any(item.startswith("UNSUPPORTED_") for item in result["warnings"])


def test_verify_timeout_and_resource_option_are_enforced():
    ticks = iter([0, 10])
    with pytest.raises(AgentArchiveError) as error:
        recheck(bundle(), monotonic=lambda: next(ticks))
    assert error.value.code == "ARCHIVE_VERIFY_TIMEOUT"


@pytest.mark.parametrize(
    "kind, gap",
    [
        ("INDEPENDENT_BACKTESTS", "EXACT_M14_BUNDLE_NOT_ARCHIVED"),
        ("TRAIN_VS_OOS", "FROZEN_M15_WINDOW_LINEAGE_REQUIRED"),
    ],
)
def test_frozen_summary_does_not_regrant_database_verified_comparison_permission(kind, gap):
    value = bundle()
    claim = value.assistant.metadata_json["verified_claims"][0]
    claim.update(claim_type="COMPARISON", comparison_type=kind, comparison_state="COMPARABLE")
    reseal_message(value)
    result = recheck(value)
    row = result["fact_recheck"]["results"][0]
    assert row["facts_status"] == "VERIFIED" and row["status"] == "UNVERIFIABLE"
    assert row["comparison_state"] == "INCOMPATIBLE" and gap in row["reason_codes"]
    assert result["fact_recheck"]["status"] == "VERIFIED"
    assert result["claim_recheck_summary"]["status"] == "UNVERIFIABLE"
    assert "delta" not in str(result) and result["calculation_reproduced"] is False
