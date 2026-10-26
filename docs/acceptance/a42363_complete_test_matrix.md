# AT01–AT60 actual obligations and evidence levels

These are node mappings, not60predeclared PASS certificates. Final JUnit results are
joined to these nodes in the delivery receipt. All physical counterparts remain
L2_NOT_RUN_NOT_AUTHORIZED. A passing denial case proves denial, not successful PG setup.

Node aliases (full pytest file paths):

- C = `tests/unit/test_a42363_complete.py`
- G = `tests/unit/test_a42363_complete_guard.py`
- L = `tests/integration_offline/test_a42363_complete_process.py`
- U = `tests/unit/test_a42363_contracts.py`
- I = `tests/integration_offline/test_a42363_process.py`
- B = `tests/unit/test_a42361_store.py`
- F = `tests/unit/test_a42361_source_entrypoints.py`
- R = `tests/unit/test_a42362_owner_recovery.py`

Each name below is an actual node function; parametrized variants remain in JUnit.
Raw local JUnit names are in complete_baseline; complete-fix/old groups are not added
across runs. New tests use no skip/xfail. Linux-only inherited tests are attempted and
reported as failed if unavailable locally, then actually run under ordinary Linux CI.

| AT | Node(s) | Level / what the result establishes |
|---|---|---|
|01|G::test_CF_AT01_AT02_all_five_manifests_and_full_current_identity; actual Git HEAD/origin/status|L0 final commit and remote evidence|
|02|G::test_CF_AT02_exact_registered_paths_not_prefixes; G::test_CF_AT01_AT02_all_five_manifests_and_full_current_identity|L0 exact five historical manifests and sixth delta|
|03|F::test_AT03_full_tree_positive_preserves_nul_unicode_and_legacy_layer; F::test_RED_AT03_hidden_index_root_content_must_not_be_trusted; F::test_AT03_full_tree_read_race_rejected_with_held_descriptor|L0 actual temporary Git/FD scenarios; old codes preserved|
|04|original A42351/A4236 Reviewer false-joined tests in full suite|L0 inherited regression, not new implementation|
|05|U::test_AT08_AT37_default_host_and_composition_no_side_effects; G::test_CF_AT05_AT21_production_templates_and_old_authorizations_are_unchanged|L0 live deny and protected bytes|
|06|C::test_CF_AT06_AT07_one_fixture_target_is_derived_from_consumed_scope; C::test_CF_AT06_all_derived_fields_are_revalidated|L0 all derived fields|
|07|C::test_CF_AT07_changed_identity_rejected_before_capabilities|L0 dynamic target drift rejection|
|08|C::test_CF_AT09_AT10_every_method_has_peer_and_closed_body_contract; U::test_AT39_AT81_controller_receiver_rejects_arbitrary_argv_and_default_create|L0 closed body/no arbitrary capabilities|
|09|C::test_CF_AT09_AT10_closed_method_schema_matrix; C::test_CF_AT09_AT10_every_method_has_peer_and_closed_body_contract|L0 methods+schemas,26negative cases; positive physical paths unverified|
|10|C::test_CF_AT09_AT10_every_method_has_peer_and_closed_body_contract|L0 peer-before-backend reject|
|11|C::test_CF_AT11_create_does_not_mean_running_or_pg_ready|L0 no CREATED=>READY upgrade|
|12|C::test_CF_AT12_socket_mount_and_uid_mapping_are_not_optional|L0 four mount/map faults; no real socket permissions claim|
|13|C::test_CF_AT13_AT14_start_failure_is_sticky_and_cannot_be_retried; L::test_CF_AT54_AT55_actual_hosts_A_B_O_C_D_E_and_independent_review[pg_not_ready]|DB_MODEL_ONLY start/ready rejection|
|14|C::test_CF_AT13_AT14_start_failure_is_sticky_and_cannot_be_retried[replacement]; U::test_AT51_unknown_suffix_keeps_original_identity_and_never_removes_replacement|DB_MODEL_ONLY original identity preservation|
|15|C::test_CF_AT15_AT18_owner_raw_version_and_each_privilege_are_audited; U::test_AT26_AT27_owner_raw_audit_fixed_eight_sqls_and_budget|DB_MODEL_ONLY raw-row audit; actual server/systemID NOT_RUN|
|16|C::test_CF_AT16_owner_budget_fails_before_opening_any_connection; C::test_CF_AT16_initialization_plan_cannot_accept_a_budget_override; U::test_AT56_readonly_and_cleanup_accounting_cannot_refund_initialization|L0 budget denial; initialization ENGINEERING_BLOCKED|
|17|C::test_CF_AT16_AT17_database_bootstrap_never_hides_extra_sql; C::test_CF_AT17_harness_preflight_before_first_side_effect|L0 counts9>8, no free bootstrap|
|18|C::test_CF_AT15_AT18_owner_raw_version_and_each_privilege_are_audited|DB_MODEL_ONLY each privilege/membership denial; physical ACL NOT_RUN|
|19|C::test_CF_AT19_preconnect_lease_never_contains_backend_start|L0 guessed backend_start rejected|
|20|C::test_CF_AT20_postconnect_target_drift_stops_before_method_or_sql|L0 PID/role/namespace/generation drift rejection|
|21|C::test_CF_AT21_candidate_projection_bytes_and_hash_are_doc_only; G::test_CF_AT05_AT21_production_templates_and_old_authorizations_are_unchanged|L0 exact candidate hashes/old16unchanged|
|22|U::test_AT30_AT35_unapproved_session_method_stops_first_probe|L0 METHOD_BLOCKED, no actual target-session observation|
|23|B::test_AT11_model_two_consumers_one_commit|DB_MODEL_ONLY concurrent one-shot; control PG L2 NOT_RUN|
|24|B::test_AT12_schema_and_CAS_are_atomic_not_select_then_insert; L::test_CF_AT54_AT55_actual_hosts_A_B_O_C_D_E_and_independent_review[consumer_ack]|L0/source+L1 single-file full-payload commit; physical DB NOT_RUN|
|25|C::test_CF_AT25_signed_revocation_requires_full_schema_and_commit; original A42361 trust and A42362 approval tests|L0 model/signature separately inherited; no new real issuer|
|26|B::test_receiver_foreign_uid_denied_before_reading_even_a_valid_frame; L::test_CF_AT54_AT55_actual_hosts_A_B_O_C_D_E_and_independent_review[wrong_peer]|inherited IPC model + new Linux SO_PEERCRED branch; independent UID L2 NOT_RUN|
|27|U::test_AT41_AT50_partial_creation_ack_loss_never_recreates; L::test_CF_AT54_AT55_actual_hosts_A_B_O_C_D_E_and_independent_review[consumer_ack]|DB_MODEL_ONLY/L1 consumed stays committed|
|28|U::test_AT41_AT50_partial_creation_ack_loss_never_recreates[SOCKET_DIR-*]|DB_MODEL_ONLY exact historical identity; actual root-owned socket L2 NOT_RUN|
|29|U::test_AT41_AT50_partial_creation_ack_loss_never_recreates[VOLUME-*]|DB_MODEL_ONLY unknown quarantines; physical volume NOT_RUN|
|30|U::test_AT41_AT50_partial_creation_ack_loss_never_recreates[SECRET-*]|DB_MODEL_ONLY no ID/no name-delete|
|31|C::test_CF_AT31_nonzero_command_still_cannot_be_washed_by_inspect; U::test_AT49_failed_create_command_never_certifies_an_inspected_existing_object|L0 original safety patch retained|
|32|U::test_AT41_AT50_partial_creation_ack_loss_never_recreates[CONTAINER-*]; L::test_CF_AT54_AT55_actual_hosts_A_B_O_C_D_E_and_independent_review[create_ack]|DB_MODEL_ONLY/L1 no recreate|
|33|U::test_AT51_unknown_suffix_keeps_original_identity_and_never_removes_replacement; L::test_CF_AT54_AT55_actual_hosts_A_B_O_C_D_E_and_independent_review[replaced_resource]|DB_MODEL_ONLY/L1 foreign object preserved|
|34|C::test_CF_AT34_volume_id_field_alone_cannot_authorize_name_only_api; U::test_AT43_volume_name_or_mountpoint_cannot_authorize_removal|L0 SAFE_DELETE_UNPROVEN/REMOVE_ID_REQUIRED; engineering block|
|35|C::test_CF_AT35_remove_attempt_is_never_reissued_if_e_cannot_prove_absence; U::test_AT53_remove_ack_loss_uses_independent_absence_without_second_remove|DB_MODEL_ONLY no repeated remove|
|36|original R exact socket content/marker/inode tests; G full FD walk|L0 tempdir; new shared PG directory actual mapping/cleanup remains unverified|
|37|U::test_AT23_AT24_ddl_enforces_transitions_fixed_owner_public_revocation; inherited A42362 ledger replay/ordering tests|L0 SQL/source+model, DDL003 unchanged and not physically executed|
|38|U::test_AT56_readonly_and_cleanup_accounting_cannot_refund_initialization; inherited A42362 first_error tests|L0 sticky first failure/separate cleanup budgets|
|39|U::test_AT57_AT66_e_never_accepts_unknown_visibility_or_recreation|DB_MODEL_ONLY observer/store failure; physical delegation NOT_RUN|
|40|U::test_AT57_AT66_e_never_accepts_unknown_visibility_or_recreation|DB_MODEL_ONLY namespace drift refusal|
|41|C::test_CF_AT41_missing_delegated_collector_fd_fails_before_runtime_info|L0 no installed readonly FD=>no runtime call|
|42|I::test_AT79_AT81_real_file_model_cross_domain_receivers_and_faults; inherited A42362 independent4×2audits|L1 file8observations, not physical absence|
|43|C::test_CF_AT43_recreation_between_rounds_invalidates_absence|L0 B ledger changed between rounds=>no E commit|
|44|I::test_AT79_AT81_real_file_model_cross_domain_receivers_and_faults[permission]; U::test_AT57_AT66_e_never_accepts_unknown_visibility_or_recreation|DB_MODEL_ONLY/L1 denied never absent|
|45|U::test_AT22_unknown_commit_never_returns_receipt_or_retries[commit]; U::test_AT21_AT63_independent_reader_after_commit[absence_auditor]|DB_MODEL_ONLY E fresh read/commit uncertainty|
|46|U::test_AT68_AT71_root_manager_never_accepts_a_network_pid; U::test_AT67_v2_uid_partition_preserves_v1_and_does_not_mint_test_authority|L0 root/UID/scope rejection; installed physical root manager NOT_RUN|
|47|I::test_AT67_AT70_untrusted_scope_is_never_kernel_proof|L1 ordinary file rejected by kernel scope constructor|
|48|I::test_AT70_platform_or_real_setsid_escape_never_becomes_scope_certificate|Linux CI exact pidfd scenario; macOS explicitly portable only; no cgroup proof|
|49|inherited A42361 no-foreign-PID tests; I::test_AT70_platform_or_real_setsid_escape_never_becomes_scope_certificate|L0+Linux pidfd L1; physical PID reuse/cgroup binding NOT_RUN|
|50|C::test_CF_AT50_guardian_armed_before_worker_launch; I::test_AT72_independent_fd_guardian_fires_while_handler_is_blocked|L0 ordering+L1 private-file deadline; kernel L2 NOT_RUN|
|51|U::test_AT33_AT68_worker_gate_precedes_fd_credentials_connection_and_sql; inherited worker FD/driver tamper contracts|L0 first gate, no physical installed worker proof|
|52|C::test_CF_AT52_failed_publication_cannot_leave_final_terminated_receipt; I::test_AT76_artifact_fsync_stall_keeps_incomplete|L0 final D ordering+L1 bounded fsync/marker|
|53|C::test_CF_AT53_runtime_commands_require_descendant_scope_before_spawn; I::test_AT70_platform_or_real_setsid_escape_never_becomes_scope_certificate|L0 no kernel scope=>no spawn; existing Linux escape not scope success|
|54|L::test_CF_AT54_AT55_actual_hosts_A_B_O_C_D_E_and_independent_review[None]|L1/DB_MODEL_ONLY actual A/B/C/D/E receivers, O raw model; not full physical/installed closure|
|55|L::test_CF_AT54_AT55_actual_hosts_A_B_O_C_D_E_and_independent_review|L1 explicit lost-reply/model-fault branches; approval/Owner/E reply loss is simulated by caller stop, not a killed signed PG server|
|56|C::test_CF_AT56_reviewer_rejects_owner_receipt_with_wrong_event; I::test_AT79_AT82_six_process_fd_transport_and_forgery_rejection|L0+L1 six sources/self-rehash rejection|
|57|I::test_AT83_missing_scope_termination_blocks_even_after_rehash; L::test_CF_AT54_AT55_actual_hosts_A_B_O_C_D_E_and_independent_review[missing_e]|L0+L1 missing D/E/Owner evidence blocks|
|58|all old A42341/A4235/A42351/A4236/A42361/A42362/A42363 tests|final actual full regression counts in delivery; zero old case removals|
|59|actual final ordinary CI run/attempt/jobs/JUnit/coverage and downloaded bytes|post-push external receipt only; not fabricated repository values|
|60|U::test_AT87_safety_state_cannot_accept_real_success; protected production/template bytes; G1 no-run audit|L0 immutable qualification flags; G1/L2 SQL0, G2 pending8/G3 unauthorized|

Open limitations are engineering obligations, not successful test claims. In particular,
AT11–18 cannot be called an authenticated PG startup PASS, AT34 cannot be called safe
physical volume destruction, AT46–53 cannot be called installed kernel proof, and AT54
cannot be called a full signed+PG+multi-UID end-to-end run. See complete_closeout.
