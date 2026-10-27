"""Unsigned v4 proposals. Hashes include extra audit costs, never implicit approval."""

from scripts.a42361_contract import canonical, sha
from scripts.a42364_costs import ACTIVE, CANDIDATE, cost_plan
from scripts.a42364_session import candidate_specification


def runtime_budget_plan(identity):
    return dict(
        version="a42365.budget.v4",
        bootstrap=cost_plan(identity),
        active=dict(ACTIVE),
        candidate=dict(CANDIDATE),
        extra_target_audit=dict(sql=2, authentications=2),
        probe=dict(sql=16, effective_warmups_total=8, window_ms=2000),
        prebuilt="NOT_IMPLEMENTED",
        native_transitive_census="NOT_IMPLEMENTED",
        measured=False,
        approved=False,
        qualifies=False,
    )


def proposal_hashes(identity, installation_sha256):
    common = dict(
        scope=identity.scope.model_dump(),
        installation_sha256=installation_sha256,
        version="a42365.proposal.v4",
        approved=False,
        qualifies=False,
    )
    proposals = dict(
        BOOTSTRAP_AND_BUDGET=dict(common, plan=runtime_budget_plan(identity)),
        SAFE_VOLUME_DISPOSAL=dict(
            common,
            choice="EXCLUSIVE_STORE",
            kernel_proof="NOT_IMPLEMENTED",
            deletion="EXACT_NAME_ONLY",
            owner_directory_v4="SEPARATE_UNACTIVATED_ADR",
        ),
        TARGET_SESSION_GUC=dict(
            common,
            specification=candidate_specification(),
            extra_audit_sql=2,
            extra_audit_auth=2,
            downgrade="DENY",
        ),
        G1_L2_EXECUTION=dict(common, operation="EXECUTION_ONCE", source="FIXTURE_SCOPE_PAYLOAD"),
    )
    return {kind: sha(canonical(body)) for kind, body in proposals.items()}
