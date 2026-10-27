# A42365 能力与 AT 对照

所有路径相对仓库根。物理资格一律 NOT_RUN_NOT_AUTHORIZED。表中 PASS 仅表示该条已注明的离线属性，不能扩大到整组 AT 的完整验收。

| 工作包 | 源码 / 方法 | 状态 | 真实测试节点与限制 |
|---|---|---|---|
| W00 | a42365_source_guard.verify；a42365_baseline.md | IMPLEMENTED_SOURCE_PASS（待同 SHA CI） | test_AT01_AT02_AT03_exact_overlay_rejects_unregistered_paths_and_preserves_nine_manifests；旧 guards 继续运行 |
| W01 | a42365_runtime_factory.build_installed_runtime；RuntimeCoordinator | PARTIAL_ENGINEERING | test_AT05_AT08_AT47_same_factory_real_sqlite_unix_scm_child_and_two_round_l1；工厂同入口，但 live server 不完整 |
| W02 | InstalledWriterBroker.dispatch/command_plan/verify_all_writers；BrokerResourceDriver | PARTIAL_ENGINEERING / ENGINEERING_BLOCKED_BY_RUNTIME_CAPABILITY | test_AT10_AT15_broker_no_global_proof_never_routes_a_command；仅证明拒绝无命令 |
| W03 | BudgetService；DurableJournal.reserve；runtime_budget_plan | PARTIAL_ENGINEERING | test_AT19_real_processes_share_budget_without_reset_or_refund；test_AT20_budget_expiration_is_sticky_across_clock_reversal；native 中介未接通 |
| W04 | ResourceLifecycle.perform/recover；BrokerResourceDriver | PARTIAL_ENGINEERING | test_AT27_AT28_AT29_AT33_restart_unknown_ack_never_replays；test_AT24_AT29_ack_lost_after_actual_file_effect_is_never_repeated；真实 PG/Podman 后端未接通 |
| W05 | ReadOnlyProvisioner.provision/accept | PARTIAL_ENGINEERING | test_AT35_AT36_ordinary_directory_fd_is_not_readonly_mount；没有只读挂载创建/跨UID安装源码闭环 |
| W06 | InstalledSupervisor；StagedPublisher.stage/finalize | PARTIAL_ENGINEERING | test_AT43_publication_keeps_marker_if_termination_or_reviewer_missing；root factory/Reviewer 尚缺 |
| W07 | AuditConnectionFactory.open | PARTIAL_ENGINEERING / CANDIDATE_ONLY | test_AT44_AT46_unapproved_owner_audit_factory_never_connects；live generation 注册尚缺 |
| W08 | controlled.assemble；同一 RuntimeCoordinator/ResourceLifecycle/DurableJournal | PARTIAL_ENGINEERING | 固定 child、真实 SCM_RIGHTS/SQLite；不证明独立 UID/mount/cgroup；CI 结果另列 |
| W09 | 三份 ADR、baseline、runbook、closeout | IMPLEMENTED_SOURCE_PASS（材料完整性） | test_AT48_budget_proposals_are_version_bound_unsigned_and_include_extra_audit；裁决均 UNSELECTED |

## AT01–AT48 的逐组真实覆盖

新测试模块均为 `tests/unit/test_a42365_runtime.py`；W00 缺实现 RED 的八个参数节点在 `test_a42365_runtime_red.py::test_W00_mandatory_runtime_implementation_exists`。存在性 GREEN 不等于完整实现 PASS。

| AT | 测试节点后缀 | 未完成验收 |
|---|---|---|
| 01/02/03 | test_AT01_AT02_AT03_exact_overlay_rejects_unregistered_paths_and_preserves_nine_manifests | 最终同 SHA 再校验 |
| 04 | test_AT04_default_installed_service_calls_fixed_factory_without_rpc_injection | 真正空服务进程安装未运行 |
| 05/08 | test_AT05_AT08_AT47_same_factory_real_sqlite_unix_scm_child_and_two_round_l1 | 全 live adapter server 不完整 |
| 06/07 | test_AT06_AT07_strict_envelope_rejects_injected_capability | kernel peer namespace/身份整链未安装 |
| 09–15 | test_AT10_AT15_broker_no_global_proof_never_routes_a_command | 全写者/ABA/mounted/API/daemon L2 NOT_RUN，源码证明缺失 |
| 16/18/19/20/21 | test_AT16_AT19_AT20_persistent_budget_concurrent_exact_limits_and_restart；test_AT18_AT21_AT45_extra_audit_slots_separate_and_active_limits_unchanged；test_AT19_real_processes_share_budget_without_reset_or_refund；test_AT20_budget_expiration_is_sticky_across_clock_reversal | 17 native transitive census 无可通过 node，NOT_IMPLEMENTED |
| 22/23/25/26 | 既有 test_a42364_owner.py 保留；本轮没有新增真实 PG 节点 | 实机 metadata/权限/system ID NOT_RUN；Owner server 缺口 |
| 24/27/28/29/30/33/34 | test_AT24_AT29_ack_lost_after_actual_file_effect_is_never_repeated[四资源CREATE/REMOVE及CONTAINER START/STOP]；test_AT27_AT28_AT29_AT33_restart_unknown_ack_never_replays；test_AT27_AT29_container_start_stop_unknown_ack_is_not_replayed | 两阶段发布/E原始后验尚未完整接线 |
| 31/32 | test_AT31_AT32_original_identity_aba_and_first_error_survive_restart | 真实 Podman 对抗 NOT_RUN |
| 35/36 | test_AT35_AT36_ordinary_directory_fd_is_not_readonly_mount | RO mount launcher 与映射未实现 |
| 37/38/39 | 受控两轮文件观察包含在 test_AT05_AT08_AT47_same_factory_real_sqlite_unix_scm_child_and_two_round_l1 | live cross-UID E server/原始独立新连接未闭环 |
| 40/41/42 | 既有 test_a42363_supervisor.py / test_a42364_manager.py 保留；本轮 fixed-child 使用 bounded_child | actual pidfd/cgroup/setsid 后代 NOT_RUN；完整工厂缺口 |
| 43 | test_AT43_publication_keeps_marker_if_termination_or_reviewer_missing | 最终独立 Reviewer server 未实现 |
| 44/45/46 | test_AT44_AT46_unapproved_owner_audit_factory_never_connects；test_AT18_AT21_AT45_extra_audit_slots_separate_and_active_limits_unchanged | target PID/start/generation 实际登记未闭环 |
| 47 | 同 SHA ordinary CI、完整 pytest、Ruff、旧冻结 guards | 待最终 Actions 证据；不能由 targeted 推断 |
| 48 | test_AT48_budget_proposals_are_version_bound_unsigned_and_include_extra_audit；三 ADR 与本表 | G1/L2 全部 NOT_RUN_NOT_AUTHORIZED |

整体验收：**AT01–48 尚未全部满足，SOURCE 工程阶段不通过**。不能把表中的复用模型节点算成缺失实机 adapter 已完成。
