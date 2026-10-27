# A42364 AT01-AT40 Acceptance Matrix

Portable tests: 121 passed,0failed,0skipped in7.18s (before final overlay tests).
Repository Ruff: PASS. Final committed overlay / Linux L1 / full-suite CI: PENDING.
Rows are mapped scenarios, NOT40 independent physical PASS certificates.
Unit nodes live under tests/unit; Linux nodes under tests/integration_offline.
Parametrized nodes retain every parameter; inherited tests retain original bytes
except the explicit AT59 infra-contract adaptation.

| AT | Actual node / check | Level and limitation |
|---|---|---|
| 01 | `test_a42364_source_guard.py::test_AT01_exact_paths_do_not_grant_prefix_permissions` | L0 exact whitelist |
| 02 | `test_a42364_source_guard.py::test_AT02_history_and_all_committed_pins_match_final_stage` | L0 committed Git blobs; after commit |
| 03 | `test_a42364_source_guard.py::test_AT03_only_explicitly_reviewed_function_can_change` | L0 AST + byte freeze |
| 04 | `test_a42364_source_guard.py::test_AT04_production_and_frozen_sql_never_enter_this_stage` | L0 protected paths; inherited full FD/NUL checks unchanged |
| 05 | `test_a42364_process.py::test_AT05_AT08_native_bootstrap_compiles_and_unprivileged_entry_cannot_initialize` | Linux L1 compile/refusal, no initdb |
| 06 | `test_a42364_bootstrap.py::test_AT06_AT08_image_policy_mutations_rejected` | L0 actual source/HBA/build-command mutation contract |
| 07 | `test_a42364_installation.py::test_AT07_keepid_mapping_and_socket_must_match` | L0 map/ownership vectors, not actual maps |
| 08 | `test_a42364_process.py::test_AT05_shellcheck_all_fixed_entry_scripts_without_execution` | Linux static lint; supply/deployment not run |
| 09 | `test_a42364_owner.py::test_AT09_AT12_fixed_owner_adapter_runs_all_twelve_steps_in_offline_model` | L0 positive fixed adapter model, not PG |
| 10 | `test_a42364_owner.py::test_AT10_create_ack_unknown_cannot_connect_again` | L0 attempt/ACK no retry |
| 11 | `test_a42364_owner.py::test_AT11_AT12_empty_foreign_or_privileged_metadata_rejected` | L0 raw metadata/privileges |
| 12 | `test_a42364_owner.py::test_AT12_empty_metadata_is_not_ready` | L0 no empty READY |
| 13 | `test_a42364_protocol.py::test_AT13_active_limits_remain_blocked_despite_candidate` | L0 old budget/method remain DENY |
| 14 | `test_a42364_protocol.py::test_AT14_shared_named_budget_cannot_reset_by_restarting_owner` | L0 persistent model; global bridge incomplete |
| 15 | `test_a42364_protocol.py::test_AT15_formally_shaped_record_is_not_an_approval` | L0 no installed authority |
| 16 | `test_a42364_protocol.py::test_AT14_AT16_every_cost_has_hash_and_prebuilt_is_not_free` | L0 plans, not measured feasibility |
| 17 | `test_a42364_process.py::test_AT17_AT20_real_candidate_parser_stays_nonqualifying_for_model_rows` | Linux parser model, not GUC observation |
| 18 | `test_a42364_process.py::test_AT18_bad_target_projection_metadata_rejected` | Linux metadata/timeout/empty negatives |
| 19 | `test_a42364_session.py` | Exact schedule/hash/default denial unit module; real backend drift NOT_RUN |
| 20 | `test_a42363_complete.py::test_CF_AT20_postconnect_target_drift_stops_before_method_or_sql` | Inherited L0 drift guard; physical backend NOT_RUN |
| 21 | `test_a42364_volume.py` | ABA/epoch/mount/global-broker negatives; actual hostile writer NOT_RUN |
| 22 | `test_a42364_volume.py` | All-writer broker missing, SAFE_DELETE_UNPROVEN asserted; no claim of kernel exclusion |
| 23 | `test_a42364_red.py::test_RED_AT21_volume_target_is_name_only_under_separate_exclusion_contract` | L0 no StorageID deletion |
| 24 | `test_a42364_volume.py` | Mounted volume/different original negative models |
| 25 | `test_a42364_chain.py::test_AT25_AT29_private_persistence_blocks_second_remove_after_process_restart` | Linux L1 SQLite unique attempt |
| 26 | `test_a42363_review.py::test_RF_AT08_resource_damage_never_reaches_delete` | Inherited L0 damaged identity/labels |
| 27 | `test_a42363_review.py::test_RF_AT34_aba_new_object_is_not_the_original` | Inherited L0 replacement identity |
| 28 | `test_a42363_review.py::test_RF_AT31_AT33_persistent_creation_cut_never_retries` | Inherited L0 per-resource ACK cuts |
| 29 | `test_a42364_chain.py::test_AT25_AT29_private_persistence_blocks_second_remove_after_process_restart` | Linux L1 all4 kinds; first-error tests retained |
| 30 | `test_a42364_evidence.py::test_AT30_AT32_collector_permissions_never_become_absent` | L0 125/126/127/-9/bool => unknown |
| 31 | `test_a42364_evidence.py::test_AT31_collector_rechecks_delegation_after_observation` | L0 delegation replacement denied |
| 32 | `test_a42363_contracts.py::test_AT57_AT66_e_never_accepts_unknown_visibility_or_recreation` | Inherited L0 same-store/permission/recreation; actual RO mounts NOT_RUN |
| 33 | `test_a42364_installation.py::test_AT33_installer_plan_neither_starts_units_nor_accepts_arbitrary_files` | L0 installation plan only |
| 34 | `test_a42363_review.py::test_RF_AT49_guardian_parent_death_fires_without_cancel` | Inherited Linux L1 held-FD Guardian; not actual cgroup |
| 35 | `test_a42364_process.py::test_AT33_AT35_private_child_fault_is_bounded_without_claiming_kernel_scope` | Linux L1 fsync/pipe/exec; setsid/PID/cgroup physical NOT_RUN |
| 36 | `test_a42363_contracts.py::test_AT80_durable_run_attempt_survives_ack_loss_and_new_receiver` | Inherited durable attempt model; concurrent real control PG NOT_RUN |
| 37 | `test_a42364_evidence.py::test_AT37_reader_changed_after_reference_is_not_self_attested` | L0 independent read mismatch |
| 38 | `test_a42364_chain.py::test_AT36_AT38_six_process_fd_handoff_and_independent_persistent_receipts` | Linux L1 real Unix FD/process/SQLite, MODEL_ONLY |
| 39 | `Repository Ruff + existing ordinary safety-plugin full pytest` | PENDING same-SHA CI; no skips to hide failures |
| 40 | `Final delivery audit of exact SHA/run/attempt/JUnit/ZIP and inner hashes` | PENDING artifact generation; never infer from baseline |

## Historical Protection

New source guard retains full HEAD/NUL/Chinese-path/index-flag/FD-race/error-precedence
checks by delegating the inherited source guard, not replacing it with a prefix
allowlist. All seven historical manifests remain byte-identical with their original
closing SHA pins. Current66 exact paths have new pins and normalized self-reference.
Only AT59 changes in the old review-test file. User allowed a linked AT57 exception
if needed, but investigation showed AT57's baseline predates that test file:
AT57 is unchanged. New AST/raw comparison permits only AT59 body to differ.

## RED to GREEN

Five W00 tests actually failed with missing modules before source creation
(5failed,0skipped,2.23s). The same five then passed; the expanded120-case portable
set also passed (121 after adding build-command mutation). This is SOURCE evidence,
not live approval. See baseline_and_red.
Linux static checks require cc/sh/shellcheck on the existing CI runner. A missing
tool is a real failure, not a skip. Windows does not have these Linux capabilities.
The later CI audit must report actual counts/coverage/warnings/JUnit and ZIP hashes;
baseline4725/89.28% are not current-SHA evidence.
