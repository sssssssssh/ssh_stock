# CI-OPT-02 实测耗时 Top 30

来自57edac41的原始安全JUnit；时间包含setup/call/teardown，不能当纯CPU。参数通过现有脱敏函数逐字映射，不能跨SHA冒充验收。

| 秒 | 当前同名节点 |
|---:|---|
| 140.813 | tests/integration/test_m17_paper_capacity.py::test_real_daily_queue_claim_source_and_settlement_are_bounded[True-250] |
| 101.341 | tests/integration/test_business_quality_continuity.py::test_ten_different_real_roots_are_fifo_idempotent_and_published |
| 66.428 | tests/integration/test_m17_paper_capacity.py::test_real_daily_queue_claim_source_and_settlement_are_bounded[False-250] |
| 52.803 | tests/integration/test_worker02_r5_ledger_parity.py::test_original_off_on_lifecycle_also_preserves_ledger_business_fields[catchup] |
| 49.502 | tests/integration/test_worker02_r2_lifecycle.py::test_claimed_roots_off_on_complete_publication_and_record_cost[catchup] |
| 38.021 | tests/integration_offline/test_source_contract_history.py::test_all_original_historical_source_contract_positives_and_negatives |
| 31.145 | tests/integration/test_ab_profile_cursor_v14_a4.py::test_profile_real_cursor_complete_golden_and_driver_restoration |
| 29.240 | tests/integration/test_perf03_root_diagnostics.py::test_real_root_parity_and_local_reports[success-0] |
| 27.802 | tests/integration/test_ab_merge_read_v14.py::test_real_engine_and_atomic_publication_equal_legacy_full_path |
| 27.308 | tests/integration/test_worker02_r5_ledger_parity.py::test_original_off_on_lifecycle_also_preserves_ledger_business_fields[recalculate] |
| 27.126 | tests/integration/test_worker02_r2_lifecycle.py::test_claimed_roots_off_on_complete_publication_and_record_cost[recalculate] |
| 27.009 | tests/integration/test_ab_read_experiment_v14_a4_2.py::test_experiment_sql_preserves_real_engine_ten_table_publication_golden[S5] |
| 26.851 | tests/integration/test_ab_read_experiment_v14_a4_2.py::test_experiment_sql_preserves_real_engine_ten_table_publication_golden[S3_KEYS] |
| 26.270 | tests/integration/test_ab_read_experiment_v14_a4_2.py::test_experiment_sql_preserves_real_engine_ten_table_publication_golden[S4] |
| 25.835 | tests/integration/test_perf03_root_diagnostics.py::test_real_root_parity_and_local_reports[success-1] |
| 25.659 | tests/integration/test_perf03_root_diagnostics.py::test_real_root_parity_and_local_reports[success-2] |
| 25.589 | tests/integration/test_publication_lookup_v13.py::test_real_worker_chain_published_business_output_matches_frozen_baseline |
| 22.623 | tests/integration/test_worker02_revision.py::test_real_worker_on_off_financial_frames_dtypes_and_hashes_are_identical |
| 21.430 | tests/integration/test_a42_ci_scope_pg17.py::test_real_scoped_fetch_windows_month_root_and_actual_plan |
| 20.450 | tests/integration/test_business_policy_worker_pg17.py::test_daily_catchup_real_calculators_keep_root_identity_and_git_audit[catchup] |
| 16.838 | tests/integration/test_capacity_level_isolation.py::test_medium_diagnostic_retains_real_upserts_commits_readers_and_rollback_probes |
| 16.297 | tests/integration/test_business_policy_worker_pg17.py::test_resident_worker_git_only_continues_but_real_drift_aborts_a_unchanged[head] |
| 15.479 | tests/integration/test_business_policy_worker_pg17.py::test_resident_worker_git_only_continues_but_real_drift_aborts_a_unchanged[dirty] |
| 14.974 | tests/integration/test_m17_1_1_retention_capacity.py::test_million_row_provenance_explain_and_actual_cleanup_are_bounded |
| 14.864 | tests/integration/test_perf03_root_diagnostics.py::test_real_root_parity_and_local_reports[cancel-0] |
| 14.147 | tests/integration/test_m16_6_window_end_to_end.py::test_real_minimum_and_maximum_windows_capture_has_bounded_selects_and_fails_closed |
| 13.942 | tests/integration/test_tail_stability_pg17_a4232.py::test_actual_pg17_catalog_digests_and_fresh_cached_plans_are_stable |
| 13.736 | tests/integration/test_tail_stability_pg17_a4232.py::test_conditional_table_control_is_limited_to_new_synthetic_relations |
| 13.493 | tests/integration/test_m17_contract_capture_entry_pg.py::test_real_chat_36_windows_refuses_before_bulk_contract_collection_and_archive_write |
| 12.848 | tests/unit/test_a4236_source_guard.py::test_AT35_legacy_observer_false_join_exact_error_and_valid_failures_preserved |
