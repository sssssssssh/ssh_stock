# A42366 Test Matrix

Node abbreviations below refer to tests/unit/test_a42366_*.py. Unit/fault models
are not true independent identities or physical tests. Every AT retains its
uncovered full taskbook criterion; a refusal PASS does not turn it into L2 PASS.

| AT | Source node / actual local evidence | Full criterion and level |
|---|---|---|
| AT01 | publication::test_AT01_AT04_each_observation_and_fresh_original_is_checked | Unit PASS; independent final review SOURCE_BLOCKED |
| AT02 | publication::test_AT01_AT02_AT03_forged_eight_observations_never_publish | Unit PASS; duplicate/order rejection, PHYSICAL_NOT_RUN |
| AT03 | publication::test_AT01_AT04_each_observation_and_fresh_original_is_checked | Unit PASS; PRESENT/UNKNOWN/time/identity, PHYSICAL_NOT_RUN |
| AT04 | publication::test_AT04_valid_semantic_model_still_cannot_impersonate_independent_reviewer | Unit refusal PASS; true Reviewer SOURCE_BLOCKED |
| AT05 | publication::test_AT05_AT06_crash_model_never_removes_marker_without_permanent_receipt | Eight before/after commit fault models PASS; real SQLite/fsync kill matrix SOURCE_BLOCKED |
| AT06 | same AT05 node; finalize requires IndependentReviewSource | Unit idempotence PASS; independently approved success SOURCE_BLOCKED |
| AT07 | services::test_AT07_AT10_actual_multi_process_unix_sqlite_receiver | Actual Linux two-frame B receiver L1 pending exact CI; not all five mutation adapters |
| AT08 | services::test_AT08_AT10_restart_does_not_consume_or_reset_budget_twice | Unit PASS; actual Unix/SQLite reopen in AT07 pending Linux |
| AT09 | services::test_AT09_peer_checked_before_frame_decode; closed request injection | Unit PASS; complete signed multi-UID installation SOURCE_BLOCKED |
| AT10 | services::test_AT08_AT10_restart_does_not_consume_or_reset_budget_twice | Unit refusal PASS; full process restart/ACK matrix SOURCE_BLOCKED |
| AT11 | reliability::test_AT11_AT15_unproven_all_writer_capability_has_zero_commands | Fourteen actual broker rejection routes PASS; EXTERNAL_PLATFORM_REQUIRED |
| AT12 | same broker node | No kernel lease provider; EXTERNAL_PLATFORM_REQUIRED, PHYSICAL_NOT_RUN |
| AT13 | same broker node | No forged UID/policy grant reaches runner; hostile UID L2 APPROVAL_REQUIRED |
| AT14 | same broker node; existing original ABA/MountCount tests retained | Unit refusal only; true store/daemon ABA PHYSICAL_NOT_RUN |
| AT15 | same broker node | create/inspect/start/stop/rm invoke zero commands; physical cleanup NOT_RUN |
| AT16 | a42365_runtime::test_AT19_real_processes_share_budget_without_reset_or_refund | Existing real SQLite/fork node retained; Linux CI pending |
| AT17 | a42365_runtime::test_AT20_budget_expiration_is_sticky_across_clock_reversal | Existing clock/refusal node retained; native census SOURCE_BLOCKED |
| AT18 | reliability::test_AT16_AT18_unproven_native_census_is_not_a_reservation_or_execution | Unit PASS; no native COMPLETE, actual exec mediation SOURCE_BLOCKED |
| AT19 | existing a42365 persistent budget/unknown-ACK nodes | Historical tests retained; native process crash census PHYSICAL_NOT_RUN |
| AT20 | reliability::test_AT18_AT20_unknown_budget_fields_or_types_are_rejected | Unit PASS; real FS/SQL mediation wiring SOURCE_BLOCKED |
| AT21 | reliability::test_AT21_AT24_target_registration_survives_reopen_and_rejects_drift | Seven metadata-drift cases PASS; actual PG handshake SOURCE_BLOCKED |
| AT22 | same registration node; registered_session_source factory | Unit PASS; actual restarted backend/SCRAM PHYSICAL_NOT_RUN |
| AT23 | same registration node; original Owner privilege tests retained | Unit PASS; live HBA/privilege validation APPROVAL_REQUIRED |
| AT24 | existing AuditConnectionFactory unauthorized and separate slot tests | Unauthorized connection refusal retained; actual PG audit NOT_RUN |
| AT25 | publication::test_AT25_AT28_no_cleanup_of_never_prepared_resources | Unit PASS; live C adapter SOURCE_BLOCKED |
| AT26 | existing a42365_runtime CREATE/REMOVE unknown-ACK nodes | Original persistent file fault nodes retained; Linux CI pending |
| AT27 | existing a42365_runtime START/STOP unknown-ACK nodes | Original persistent file fault nodes retained; live resources NOT_RUN |
| AT28 | publication::test_AT28_stop_ack_loss_does_not_prevent_owned_cleanup_or_replay_stop | Unit PASS; owned cleanup despite B failure, no STOP replay; full root factory SOURCE_BLOCKED |
| AT29 | existing a42365_runtime::test_AT31_AT32_original_identity_aba_and_first_error_survive_restart | Original first-error/ABA test retained; physical identity/census NOT_RUN |
| AT30 | existing a42365 ordinary-directory/ReadOnlyProvisioner refusal node | True RO mount launcher EXTERNAL_PLATFORM_REQUIRED |
| AT31 | publication fresh B/C and original identity validation | Unit semantic rejection PASS; same-store cross-UID E SOURCE_BLOCKED |
| AT32 | publication independent Reviewer rejection | Unit refusal PASS; reviewer server/store/credential provisioning SOURCE_BLOCKED |
| AT33 | AbsenceEndpoint fresh before/after each round; old independent collector tests | Kernel RO delegation and physical two-round observation NOT_RUN |
| AT34 | services::test_AT34_AT37_a_root_manager_shaped_object_is_not_a_kernel_installation | Unit refusal PASS; actual cgroup FD install EXTERNAL_PLATFORM_REQUIRED |
| AT35 | same root node; existing Guardian-before-release tests retained | Actual installed Guardian factory SOURCE_BLOCKED |
| AT36 | same root node; original descendant tests retained | setsid/fork/fsync/host-restart L2 APPROVAL_REQUIRED |
| AT37 | same root node; v5 root factory fails closed | Unit refusal PASS; genuine root termination PHYSICAL_NOT_RUN |

## Local raw records

W00 RED: .codex_tmp/a42366-red.xml, seven actual baseline behavioral failures,
SHA256 b5c021308799cc1df672c754d4af400d6f4c2cdd5600a6f92f1980d6513cedac.
First safety GREEN: .codex_tmp/a42366-a-green.xml, 15 passed,
SHA256 86e0facf14901684fee07549eea63ebf3dda063a459fae1b7dc09acca547ffbc.
Final portable targeted and guarded full attempt: see a42366_evidence.json.

Windows full pytest cannot collect ten existing Linux-only modules (fcntl/resource).
The bootstrap disables business dotenv loading and points only at an unavailable
loopback test endpoint. It does not alter any test or touch the business database.
The single new fork/SO_PEERCRED receiver node is explicitly deselected locally,
not skipped in source or ordinary Linux CI. Exact-SHA Linux results supersede no
local failure; both remain recorded. Ruff and diff checks are separate evidence.
