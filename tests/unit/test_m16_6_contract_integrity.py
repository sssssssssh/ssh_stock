import uuid
from copy import deepcopy
from types import SimpleNamespace

import pytest
from app.core.agent_frozen_contract_config import AgentFrozenContractConfig
from app.domain.agent.archive import AgentArchiveError
from app.services.agent.contracts.canonical import contract_hash, contract_storage_size
from app.services.agent.contracts.integrity import verify_contract_archive
from m16_6_fixtures import synthetic_m14


def synthetic_archive(body=None):
    body = body or synthetic_m14()
    owner, chat, turn, tool_id, row_id = (uuid.uuid4() for _ in range(5))
    parent = SimpleNamespace(
        id=uuid.uuid4(), manifest_hash="a" * 64, owner_user_id=owner, chat_id=chat, turn_id=turn
    )
    tool = SimpleNamespace(
        id=tool_id,
        tool_call_id="call",
        tool_name="performance.summary",
        payload_json={
            "identity": deepcopy(body["selected"]),
            "records": [deepcopy(body["record"])],
            "evidence": deepcopy(body["evidence"]),
        },
    )
    row = SimpleNamespace(
        id=row_id,
        owner_user_id=owner,
        chat_id=chat,
        turn_id=turn,
        tool_result_archive_id=tool_id,
        contract_kind="M14_EXACT_BUNDLE",
        subject_id=body["selected"]["run_id"],
        role="LIVE",
        schema_version="m16.6-m14-bundle-v1",
        verification_scope="FROZEN_CONTRACT_RECHECK",
        contract_json=body,
        contract_hash=contract_hash(body),
        size_bytes=contract_storage_size(body),
    )
    ref = {
        "id": str(row_id),
        "tool_call_id": "call",
        "tool_result_archive_id": str(tool_id),
        "contract_kind": row.contract_kind,
        "subject_id": row.subject_id,
        "role": row.role,
        "schema_version": row.schema_version,
        "contract_hash": row.contract_hash,
    }
    manifest = SimpleNamespace(
        id=uuid.uuid4(),
        owner_user_id=owner,
        chat_id=chat,
        turn_id=turn,
        base_manifest_id=parent.id,
        base_manifest_hash=parent.manifest_hash,
        policy_version="m16.6-contract-manifest-v1",
        contract_count=1,
        contract_ids_hash=contract_hash([ref]),
    )
    manifest.manifest_json = {
        "policy_version": manifest.policy_version,
        "base_manifest_id": str(parent.id),
        "base_manifest_hash": parent.manifest_hash,
        "owner_user_id": str(owner),
        "chat_id": str(chat),
        "turn_id": str(turn),
        "contract_count": 1,
        "contract_ids_hash": manifest.contract_ids_hash,
        "contracts": [ref],
    }
    manifest.manifest_hash = contract_hash(manifest.manifest_json)
    binding = SimpleNamespace(
        evidence_id=body["evidence"][0]["evidence_id"], tool_result_archive_id=tool_id
    )
    return manifest, [row], SimpleNamespace(manifest=parent, tools=[tool], bindings=[binding])


def test_manifest_exact_set_hash_tool_binding_and_unknown_contract_version():
    manifest, rows, base = synthetic_archive()
    checked = verify_contract_archive(manifest, rows, base, AgentFrozenContractConfig())
    assert checked.check["contract_semantics"]["status"] == "VERIFIED"
    assert checked.check["comparison_permission"]["allowed"] is False
    assert checked.check["calculation_reproduced"] is False
    rows[0].schema_version = "future-v99"
    manifest.manifest_json["contracts"][0]["schema_version"] = rows[0].schema_version
    manifest.contract_ids_hash = contract_hash(manifest.manifest_json["contracts"])
    manifest.manifest_json["contract_ids_hash"] = manifest.contract_ids_hash
    manifest.manifest_hash = contract_hash(manifest.manifest_json)
    unknown = verify_contract_archive(manifest, rows, base, AgentFrozenContractConfig())
    assert unknown.check["results"][0]["reason_codes"] == ["CONTRACT_VERSION_UNSUPPORTED"]
    assert not unknown.verified


@pytest.mark.parametrize(
    "mutation",
    [
        lambda m, rows, base: setattr(rows[0], "owner_user_id", uuid.uuid4()),
        lambda m, rows, base: setattr(m, "base_manifest_hash", "0" * 64),
        lambda m, rows, base: setattr(rows[0], "size_bytes", 1),
        lambda m, rows, base: (
            rows[0].contract_json["record"]["performance"].update(annualized_return="4")
        ),
        lambda m, rows, base: (
            base.tools[0].payload_json["evidence"][0].update(content_hash="0" * 64)
        ),
        lambda m, rows, base: (
            base.tools[0].payload_json["identity"].update(risk_id=str(uuid.uuid4()))
        ),
        lambda m, rows, base: m.manifest_json["contracts"].append(
            deepcopy(m.manifest_json["contracts"][0])
        ),
    ],
)
def test_contract_tampering_cannot_gain_permission(mutation):
    manifest, rows, base = synthetic_archive()
    mutation(manifest, rows, base)
    with pytest.raises(AgentArchiveError) as caught:
        verify_contract_archive(manifest, rows, base, AgentFrozenContractConfig())
    assert caught.value.status_code == 409
