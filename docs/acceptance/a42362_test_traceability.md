# A42362 AT01-AT72 Traceability

Status is evidence level, NOT 72 passed. PORTABLE_PASS refers to the local46-case L0
set or baseline source regressions, not physical tests. L1/CI pending items must be read
from final same-SHA Actions artifacts; no skip/xfail qualifies as an execution. Physical
L2 remains NOT_RUN_NOT_AUTHORIZED even if ordinary application PG17 CI passes.

`source_guard`, `approval_ledger`, `owner_recovery`, `audit_supervisor` abbreviate
`tests/unit/test_a42362_<name>.py`. L1 abbreviates the exact integration_offline file.

| AT | Object | Actual Evidence Level at Commit Preparation | Test / Implementation |
|---|---|---|---|
| AT01 | HEAD/master/origin | BASELINE_VERIFIED; FINAL_CI_PENDING | source_guard.test_AT01_AT06_final_commit_has_exact_paths_and_historical_manifests_unchanged |
| AT02 | exact paths | L0_PENDING_FINAL_COMMIT | source_guard.test_AT02_no_directory_or_prefix_exemptions |
| AT03 | full HEAD FD/Chinese/NUL/index | INHERITED_LINUX_CI_PENDING | legacy test_a42361_source_entrypoints.py full-tree race/tamper cases |
| AT04 | historical overlays | L0_PENDING_FINAL_COMMIT | source_guard.test_AT04_normalization_excludes_only_the_new_self_reference_literal; legacy old pins |
| AT05 | source read/HEAD race | INHERITED_LINUX_CI_PENDING | legacy test_a42361_source_entrypoints.py |
| AT06 | same SHA evidence | CI_PENDING | source_guard final manifest plus actual Actions metadata/JUnit |
| AT07 | RFC8032 crypto | INHERITED_CI_PENDING | test_a42361_trust.py; no formal signing key |
| AT08 | independent approval | PARTIAL_SOURCE | ApprovalRegistryService; inherited crypto/approval negatives |
| AT09 | revocation/TTL | SOURCE + INHERITED_CI_PENDING | SQL epoch/locks; actual PG concurrency NOT_RUN |
| AT10 | binding source/image/limits | PARTIAL_SOURCE | ControlRepository.verify_scope; real independent root deploy NOT_RUN |
| AT11 | A peer ACL | L1_PENDING + PARTIAL_SOURCE | integration_offline kernel peer test; not five installed identities |
| AT12 | persistent A approvals | NOT_RUN_PHYSICAL | external import SQL; live A store/independent signature custody not configured |
| AT13 | B concurrent consume | MODEL_ONLY / NOT_RUN_PHYSICAL | legacy test_a42361_store.py two-consumer model; SQL lock contract |
| AT14 | commit ACK unknown | PORTABLE_PASS | approval_ledger.test_AT14_AT15_bad_commit_or_read_never_retries_or_returns_success |
| AT15 | fresh reader | PORTABLE_PASS | approval_ledger.test_AT15_AT16_actual_adapter_commits_then_uses_new_reader_connection |
| AT16 | reserve before side effects | PORTABLE_PASS | owner_recovery.test_AT16_uncommitted_reservation_prevents_first_side_effect |
| AT17 | four-kind immutable ledger | PORTABLE_PASS / PHYSICAL_NOT_RUN | approval_ledger schema/transition tests |
| AT18 | no create replay | PORTABLE_PASS | owner_recovery.test_AT18_resource_event_cannot_reopen_create_after_unknown |
| AT19 | role ACL | SOURCE_ONLY | approval_ledger.test_AT19_schema_separates_actors_and_keeps_every_table_append_only |
| AT20 | control target isolation | PARTIAL_SOURCE | ControlRepository.connect/verify; legacy Owner attestation integration still blocked |
| AT21 | raw new PG identity | PARTIAL_SOURCE / PHYSICAL_NOT_RUN | owner_recovery raw record rejection; no real metadata |
| AT22 | owner role/public/memberships | PARTIAL_SOURCE / PHYSICAL_NOT_RUN | owner_role_audit.sql review template, not actual initializer |
| AT23 | init budget | MODEL_ONLY / PHYSICAL_NOT_RUN | owner_recovery.test_AT21_AT23_owner_raw_record_budget_or_version_cannot_be_promoted |
| AT24 | pre-connect lease v2 | INHERITED_CI_PENDING | legacy test_a42361_worker_evidence.py |
| AT25 | post-connect session v2 | INHERITED_CI_PENDING / METHOD_BLOCKED | legacy identity negatives; no real session issuance |
| AT26 | target GUC proof | METHOD_BLOCKED | owner_recovery.test_AT26_AT29_no_free_same_session_guc_proof_no_credentials_or_sql |
| AT27 | credentials | DEFAULT_DENIED / PHYSICAL_NOT_RUN | no credentials issued; existing lease model only |
| AT28 | no business role/schema | PARTIAL_SOURCE / PHYSICAL_NOT_RUN | owner role template/RootFD guard, no actual PG access |
| AT29 | method stop | PORTABLE_PASS / METHOD_BLOCKED | require_session_method; no added query |
| AT30 | socket create crash | MODEL_ONLY | owner_recovery.test_AT30_AT34_each_create_ack_loss_is_journaled_without_second_create[SOCKET_DIR] |
| AT31 | volume create crash | MODEL_ONLY | same test[VOLUME]; no Podman |
| AT32 | secret create crash | MODEL_ONLY; REAL_RECOVERY_PARTIAL | same test[SECRET]; unrecorded ID/epoch reconciliation not closed |
| AT33 | container create crash | MODEL_ONLY; REAL_RECOVERY_PARTIAL | same test[CONTAINER]; no real container |
| AT34 | Owner init timeout | PARTIAL_SOURCE / NOT_RUN | no concrete initializer, method stops earlier |
| AT35 | identity drift | PORTABLE_PASS / PHYSICAL_NOT_RUN | owner_recovery.test_AT35_mutated_resource_binding_does_not_reach_remove |
| AT36 | socket FD cleanup | L1_PENDING | integration_offline.test_AT36_actual_socket_directory_rejects_replacement_and_never_recurses |
| AT37 | foreign resource | PORTABLE_PASS | owner_recovery.test_AT37_missing_ledger_never_scans_or_deletes_similar_names |
| AT38 | remove interrupted | MODEL_ONLY | owner_recovery.test_AT38_each_remove_failure_keeps_first_error_and_never_claims_cleanup |
| AT39 | cleanup timeout | PORTABLE_PASS_MODEL | owner_recovery.test_AT39_expired_cleanup_budget_never_deletes_or_claims_success |
| AT40 | E independent UID | PORTABLE_PASS_MODEL | audit_supervisor.test_AT40_AT46_untrusted_or_unobservable_negative_never_commits_absent |
| AT41 | E no copied C JSON | PORTABLE_PASS_MODEL | same test[copy_controller]; concrete E store not wired |
| AT42 | E all resource kinds | PORTABLE_PASS_MODEL | audit_supervisor.test_AT42_missing_resource_is_not_complete_absence |
| AT43 | E permission/race | PORTABLE_PASS_MODEL | same audit rejection[permission/recreated] |
| AT44 | E append-only persistent store | PARTIAL_SOURCE / NOT_RUN | schema only; concrete E store/reader still missing |
| AT45 | E ordering | MODEL_ONLY | audit_supervisor.test_AT40_AT45_independent_model_observes_all_four_resources_twice |
| AT46 | E reconstruction/namespace | PARTIAL_SOURCE / NOT_RUN | identity rejection model only, platform delegation not supplied |
| AT47 | installed worker/source | PARTIAL_SOURCE | verify_worker_fd primitive; complete launcher not implemented |
| AT48 | D launch prerequisites | DEFAULT_DENIED / PARTIAL_SOURCE | audit_supervisor.test_AT47_AT48_AT63_default_host_supervisor_and_reconciler_deny_before_side_effects |
| AT49 | real child reap | L1_PENDING | integration_offline.test_AT49_normal_controlled_child_is_reaped |
| AT50 | grandchild residual | L1_PENDING; METHOD_NOT_PROVEN | integration_offline.test_AT50_parent_exit_with_live_grandchild_is_not_scope_success |
| AT51 | PID/group reuse | SOURCE + L1_PENDING | terminate_scope validates seal/start; no signal after leader reaped |
| AT52 | blocked handler | L1_PENDING | integration_offline.test_AT52_AT55_blocking_child_is_killed_outside_handler[ipc] |
| AT53 | 16 SQL | INHERITED_CI_PENDING | legacy SqlBudget/schedule/wire tests unchanged; no actual probe |
| AT54 | 100ms/2s/8rows | INHERITED_CI_PENDING | legacy worker budget tests unchanged |
| AT55 | fsync stall | L1_PENDING; PUBLISHER_PARTIAL | same L1 blocking test[fsync]; full trusted bundle publisher missing |
| AT56 | CPU/GC | INHERITED_CI_PENDING / NOT_PROVEN | existing worker model; CPU unavailable, no physical GC/Observer |
| AT57 | create ACK loss | SOURCE + PARTIAL_INTEGRATION | ControlService sends reconcile; C server composition unavailable |
| AT58 | cleanup ACK loss | PARTIAL_SOURCE | no C/E authoritative destroy pipeline; never qualified |
| AT59 | sticky first failure | PORTABLE_PASS | audit_supervisor.test_AT59_first_error_remains_after_cleanup_errors |
| AT60 | cross-domain epoch receipts | PARTIAL_SOURCE | bound ledger receipts only; complete raw cross-domain reviewer not added |
| AT61 | offline reviewer nonqualifying | INHERITED_CI_PENDING | old trusted evidence Reviewer unchanged, no physical qualification |
| AT62 | safe output | PORTABLE_PASS | approval_ledger.test_AT62_records_contain_no_credential_field; failure sentinels |
| AT63 | startup trust | PORTABLE_PASS | default host/installation constructors reject before operations |
| AT64 | kernel peer FD/frame | L1_PENDING | integration_offline.test_AT11_AT64_AT68_kernel_peer_uid_checked_before_dispatch |
| AT65 | stop runbook | DESIGN_ONLY / PARTIAL_SOURCE | deployment review doc; no complete installed stop manager |
| AT66 | platform/userns/cgroup | PLATFORM_NOT_VERIFIED | no live Podman/OS installation |
| AT67 | old 279/238/85/308 | INHERITED_CI_PENDING | full ordinary Linux pytest, no skips/removal |
| AT68 | new process/IPC faults | L1_PENDING | all integration_offline/test_a42362_ipc_process.py cases |
| AT69 | main CI | CI_PENDING | ordinary push only, not manual dispatch |
| AT70 | physical not approved | PORTABLE_DEFAULT_DENIED | no G1/PG/Podman/cloud/.env operation; all old live entry gates retained |
| AT71 | G1/G2/G3 independent | PORTABLE_PASS | State forbids true flags, total8; actual G1/G3 not run |
| AT72 | final identity/artifacts | CI_PENDING | must collect actual final SHA/run/attempt and separately hash ZIP/contents |

## Commands

```text
python -m pytest tests/unit/test_a42362_contract.py tests/unit/test_a42362_approval_ledger.py tests/unit/test_a42362_owner_recovery.py tests/unit/test_a42362_audit_supervisor.py -q
python -m pytest tests/integration_offline/test_a42362_ipc_process.py -q
python -m pytest
python -m ruff check backend tests migrations scripts
git diff --check
```

Only the first is run locally on Windows; L1 and full pytest require Linux and are left
to the existing ordinary CI, without modifying workflow triggers or running any G1.
The full suite retains old contracts/counts and is not narrowed to make this stage green.
Concrete Owner initialization, independent E storage, trusted cgroup/worker/FD/publisher
and runtime C/E/D host wiring remain source gaps regardless of test totals.
