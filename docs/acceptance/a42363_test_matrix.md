# A42363 AT01–AT88 traceability

Each row preserves the exact taskbook obligation. A cited test proves only its stated
L0/L1 scenario; it does not certify the entire physical obligation. DB models are
DB_MODEL_ONLY. Portable targeted run:149 passed in4.33s; initial RED10 failures retained.
Linux-only pidfd/setsid is NOT_RUN locally on macOS and must be read from CI JUnit
property linux_setsid_pidfd_executed. L2 is NOT_RUN_NOT_AUTHORIZED for every row.
Final full-unit/CI results and downloaded artifact identities are reported in the
external delivery evidence; this frozen file never predicts a Run ID or future SHA.

| AT | Exact obligation | Reproducible test node / related source | Result boundary |
|---|---|---|---|
| AT01 | 完整 HEAD/master/origin 以及实际 diff 基线一致，历史 SHA 可审计。 | `tests/unit/test_a42363_source_guard.py::test_AT01_AT03_committed_manifest_full_guard_and_four_history_layers` | L0 targeted; inherited freeze regressions required |
| AT02 | 旧 A42351/A4236/A42361/A42362 manifest 的文件内容、摘要和冻结原语保持不变。 | `tests/unit/test_a42363_source_guard.py::test_AT01_AT03_committed_manifest_full_guard_and_four_history_layers` | L0 targeted; inherited freeze regressions required |
| AT03 | 新阶段仅精确允许文件变更，目录级通配写保护拒绝。 | `tests/unit/test_a42363_source_guard.py::test_AT02_exact_paths_no_directory_exemptions` | L0 targeted; inherited freeze regressions required |
| AT04 | Git `core.quotePath`、中文路径、NUL 分隔路径按真实 bytes 校验。 | `tests/unit/test_a42361_source_entrypoints.py::test_AT03_full_tree_positive_preserves_nul_unicode_and_legacy_layer` | L0 targeted; inherited freeze regressions required |
| AT05 | 隐藏 index flags（assume-unchanged/skip-worktree）下篡改真实 HEAD tracked bytes 必拒绝。 | `tests/unit/test_a42361_source_entrypoints.py::test_RED_AT03_hidden_index_root_content_must_not_be_trusted` | L0 targeted; inherited freeze regressions required |
| AT06 | HEAD race、symlink、硬链接、路径逃逸、模式与 inode 置换拒绝。 | `tests/unit/test_a42361_source_entrypoints.py::test_AT03_full_tree_read_race_rejected_with_held_descriptor` | L0 targeted; inherited freeze regressions required |
| AT07 | 老 Reviewer 假 joined/fake cleanup 负例仍拒绝；合法失败仍保持 INCOMPLETE。 | `tests/unit/test_a42361_source_entrypoints.py::test_AT40_old_live_and_fake_stay_incapable` | L0 targeted; inherited freeze regressions required |
| AT08 | `--execute`、`.env`、伪 token、测试钥、Git push、CI 都无法启用 live 入口。 | `tests/unit/test_a42363_contracts.py::test_AT08_AT37_default_host_and_composition_no_side_effects` | L0 targeted; inherited freeze regressions required |
| AT09 | 修改业务后端/生产 SQL/工作流/旧协议及旧 manifest 被 source guard 明确拒绝。 | `tests/unit/test_a42363_source_guard.py::test_AT09_production_and_frozen_protocols_untouched` | L0 targeted; inherited freeze regressions required |
| AT10 | 当前阶段所有状态报告不得自动写 G1 physical PASS、SQL>0 或 G2/G3 approved。 | `tests/unit/test_a42363_contracts.py::test_AT87_safety_state_cannot_accept_real_success` | L0 targeted; inherited freeze regressions required |
| AT11 | Ed25519 RFC8032 真实测试向量验签正确；任一 payload 原字节改动均拒绝。 | `tests/unit/test_a42361_trust.py::test_AT05_real_RFC8032_test2_nonempty_vector` | L0/DB_MODEL_ONLY; PG17 privileges NOT_RUN |
| AT12 | 双审批主体不同、issuer 不可自审；测试公钥、撤销、未知 key、过期拒绝。 | `tests/unit/test_a42361_trust.py::test_AT08_signature_alone_cannot_approve` | L0/DB_MODEL_ONLY; PG17 privileges NOT_RUN |
| AT13 | A registry/approval/import/revoke/receipt RPC 与 LocalService 方法表完全一致。 | `tests/unit/test_a42363_contracts.py::test_AT12_AT25_AT39_AT64_client_server_method_matrix_exact` | L0/DB_MODEL_ONLY; PG17 privileges NOT_RUN |
| AT14 | A import 仅受信 operator UID 可调用，其他域调用拒绝且无 DB write。 | `tests/unit/test_a42363_contracts.py::test_AT14_reader_cannot_import_before_repository_or_crypto` | L0 direct-host rejection before repository/crypto; PG roles NOT_RUN |
| AT15 | A 记录采用严格 version/epoch、撤销与原始 payload digest；改变后旧授权不可消费。 | `tests/unit/test_a42361_trust.py::test_AT07_revocation_rotation_clock_fail_closed` | L0/DB_MODEL_ONLY; PG17 privileges NOT_RUN |
| AT16 | A 导入 COMMIT/ACK 丢失不自动重复导入、不返回虚假 committed。 | `tests/unit/test_a42362_approval_ledger.py::test_AT14_AT15_bad_commit_or_read_never_retries_or_returns_success` | L0/DB_MODEL_ONLY; PG17 privileges NOT_RUN |
| AT17 | B consume 请求完整 binding/allowlist/image/预算校验，错误输入在 SQL 前拒绝。 | `tests/unit/test_a42361_store.py::test_consumer_receiver_rejects_drift_or_signature_without_consumption` | L0/DB_MODEL_ONLY; PG17 privileges NOT_RUN |
| AT18 | B 两个并发同 token：最多一个 commit；同 nonce/fixture 重放被 DB UNIQUE 拒绝。 | `tests/unit/test_a42361_store.py::test_AT11_model_two_consumers_one_commit` | L0/DB_MODEL_ONLY; PG17 privileges NOT_RUN |
| AT19 | B CONSUMED 和完整 payload 在同一消费事务持久落盘；没有分叉可授权状态。 | `tests/unit/test_a42361_store.py::test_AT12_schema_and_CAS_are_atomic_not_select_then_insert` | L0/DB_MODEL_ONLY; PG17 privileges NOT_RUN |
| AT20 | B 资源 ledger 的 `RESERVED/CREATE_ATTEMPTED/OBSERVED_CREATED/UNKNOWN/REMOVE_*` 状态转换严格。 | `tests/unit/test_a42363_contracts.py::test_AT23_AT24_ddl_enforces_transitions_fixed_owner_public_revocation` | L0/DB_MODEL_ONLY; PG17 privileges NOT_RUN |
| AT21 | B 账本写入 commit 后再用另一连接读 committed receipt，拒绝原连接内自证。 | `tests/unit/test_a42363_contracts.py::test_AT21_AT63_independent_reader_after_commit` | L0/DB_MODEL_ONLY; PG17 privileges NOT_RUN |
| AT22 | B 丢 ACK、锁争用、连接关闭失败、未知提交不得重试或退款消费。 | `tests/unit/test_a42363_contracts.py::test_AT22_controller_scope_lock_uses_distinct_session_and_closes` | L0/DB_MODEL_ONLY; PG17 privileges NOT_RUN |
| AT23 | 资源事件同资源不同 token/fixture/epoch/name 不能互相接管或授权删除。 | `tests/unit/test_a42363_contracts.py::test_AT23_AT24_ddl_enforces_transitions_fixed_owner_public_revocation` | L0/DB_MODEL_ONLY; PG17 privileges NOT_RUN |
| AT24 | B 消费/事件/审计表的实际 DDL 具唯一性、只追加、固定 owner/search_path/最小权限，无跨业务库。 | `tests/unit/test_a42363_contracts.py::test_AT23_AT24_ddl_enforces_transitions_fixed_owner_public_revocation` | L0/DB_MODEL_ONLY; PG17 privileges NOT_RUN |
| AT25 | B 通用 receiver 权限：C 只可资源事件；D 仅消费；E 只读许可边界；陌生 UID/方法拒绝。 | `tests/unit/test_a42363_contracts.py::test_AT25_domain_repository_pins_writer_and_separate_reader_without_connect` | L0/DB_MODEL_ONLY; PG17 privileges NOT_RUN |
| AT26 | Owner 使用独立受信 source 获取 system identifier、PG17 major、镜像/卷/container/namespace 实体身份。 | `tests/unit/test_a42363_contracts.py::test_AT26_AT27_owner_raw_audit_fixed_eight_sqls_and_budget` | L0 denial/raw model; METHOD_BLOCKED |
| AT27 | Owner 启动预算 ≤8 init SQL/12 commands/2s 草案不被程序擅自扩大。 | `tests/unit/test_a42363_contracts.py::test_AT26_AT27_owner_raw_audit_fixed_eight_sqls_and_budget` | L0 denial/raw model; METHOD_BLOCKED |
| AT28 | Owner 身份核验实际 probe 角色不含 superuser/createdb/createrole/bypassrls/replication/maintain/DDL/DML/business 读取。 | `tests/unit/test_a42363_contracts.py::test_AT26_AT27_owner_raw_audit_fixed_eight_sqls_and_budget` | L0 denial/raw model; METHOD_BLOCKED |
| AT29 | Owner 仅能签发绑定 token/worker PID/fixture 的短期 lease，凭据不入 argv/env/artifact。 | `tests/unit/test_a42363_contracts.py::test_AT33_AT68_worker_gate_precedes_fd_credentials_connection_and_sql` | source/ADR + denial contract; target-session method NOT_APPROVED |
| AT30 | lease v2 不包含尚未存在 backend 的 start；session v2 必须在连接后绑定真实 backend PID/start/role/namespace。 | `tests/unit/test_a42363_contracts.py::test_AT30_AT35_unapproved_session_method_stops_first_probe` | source/ADR + denial contract; target-session method NOT_APPROVED |
| AT31 | 其他 backend 的 `pg_settings/SHOW` 不能被接受为目标 probe 真实 GUC。 | `tests/unit/test_a42363_contracts.py::test_AT30_AT35_unapproved_session_method_stops_first_probe` | L0 denial/raw model; METHOD_BLOCKED |
| AT32 | 只有角色默认值或连接 options 无法自动变 `SESSION_GUC_VERIFIED`。 | `tests/unit/test_a42363_contracts.py::test_AT30_AT35_unapproved_session_method_stops_first_probe` | L0 denial/raw model; METHOD_BLOCKED |
| AT33 | 在无获批同会话证据方法时，Owner 不发可执行凭据/Worker 不发送第一条 probe SQL。 | `tests/unit/test_a42363_contracts.py::test_AT33_AT68_worker_gate_precedes_fd_credentials_connection_and_sql` | L0 denial/raw model; METHOD_BLOCKED |
| AT34 | 所有可选同会话方法带具体 SQL 次数/模板 bytes/permission/budget 影响文档；方案 A 未批准不启用。 | `tests/unit/test_a42363_contracts.py::test_AT30_AT35_unapproved_session_method_stops_first_probe` | source/ADR + denial contract; target-session method NOT_APPROVED |
| AT35 | 任何 projection 修改需独立协议审批及 allowlist 迁移，不可继承旧证明。 | `tests/unit/test_a42363_contracts.py::test_AT30_AT35_unapproved_session_method_stops_first_probe` | source/ADR + denial contract; target-session method NOT_APPROVED |
| AT36 | Owner 连接角色隔离，未知 socket/source/expiry/UID/restart/connection generation 全拒绝。 | `tests/unit/test_a42361_worker_evidence.py::test_post_connect_session_drift_cannot_send_first_probe_sql` | L0 denial/raw model; METHOD_BLOCKED |
| AT37 | Owner 实际 backend 未配置时必须 fail-closed，不允许测试驱动假装已部署。 | `tests/unit/test_a42363_contracts.py::test_AT08_AT37_default_host_and_composition_no_side_effects` | L0 denial/raw model; METHOD_BLOCKED |
| AT38 | ADR 记录 A/B/C 裁决、批准状态、后续准确动作，不能把 `METHOD_BLOCKED` 当全部任务实现完成。 | `tests/unit/test_a42363_contracts.py::test_AT30_AT35_unapproved_session_method_stops_first_probe` | source/ADR + denial contract; target-session method NOT_APPROVED |
| AT39 | C RPC create/destroy/reconcile/receipt 与上游方法表一致，未安装就无副作用。 | `tests/unit/test_a42363_contracts.py::test_AT39_AT64_AT67_real_host_composes_c_e_d_and_enforces_peer_acl` | L0 + file L1; Podman NOT_RUN |
| AT40 | 四资源名称只能由固定 token/fixture 派生，任意 path/name/Podman argv 被拒绝。 | `tests/unit/test_a42363_contracts.py::test_AT40_fixed_creation_commands_reject_scope_name_and_never_contain_credentials` | L0 + file L1; Podman NOT_RUN |
| AT41 | 各资源必须先有 B 新连接核验的 RESERVED、CREATE_ATTEMPTED 再首次执行 create。 | `tests/unit/test_a42363_contracts.py::test_AT41_AT50_partial_creation_ack_loss_never_recreates` | L0 + file L1; Podman NOT_RUN |
| AT42 | Socket 创建/owner/inode/marker/模式实际 L1 验证，陌生文件不得强制清理。 | `tests/unit/test_a42361_controller_watchdog.py::test_AT12_reservation_must_be_committed_before_mkdir` | L0 + file L1; Podman NOT_RUN |
| AT43 | Volume 完整 ID/label/namespace/binding 才可被归属认证。 | `tests/unit/test_a42363_contracts.py::test_AT43_volume_name_or_mountpoint_cannot_authorize_removal` | PASS rejection; immutable-ID volume removal capability BLOCKED |
| AT44 | Secret exact ID/epoch 与 owner，无法证明新建 epoch 时只能隔离，不能按名字删除。 | `tests/unit/test_a42363_contracts.py::test_AT43_AT44_raw_resource_epoch_labels_cannot_be_echoed` | L0 + file L1; Podman NOT_RUN |
| AT45 | Container image/ID/name/labels/用户/网络/卷/资源/只读隔离都必须核验。 | `tests/unit/test_a42361_controller_watchdog.py::test_AT17_AT18_inspection_rejects_escalation` | L0 + file L1; Podman NOT_RUN |
| AT46 | Socket 已创建但 ACK 丢失：下一次仅 reconcile，禁止二次 mkdir/清除外国 socket。 | `tests/unit/test_a42363_contracts.py::test_AT41_AT50_partial_creation_ack_loss_never_recreates` | L0 + file L1; Podman NOT_RUN |
| AT47 | Volume 创建后响应丢失：不得再次 volume create；要以账本+独立 inspect 对账。 | `tests/unit/test_a42363_contracts.py::test_AT41_AT50_partial_creation_ack_loss_never_recreates` | L0 + file L1; Podman NOT_RUN |
| AT48 | Secret 创建成功、ID 未入账：不得按相似 secret 名清理。 | `tests/unit/test_a42363_contracts.py::test_AT41_AT50_partial_creation_ack_loss_never_recreates` | L0 + file L1; Podman NOT_RUN |
| AT49 | Container 创建中断、运行时失败：仅在 exact ID/epoch 确认后可精准删除。 | `tests/unit/test_a42363_contracts.py::test_AT41_AT50_partial_creation_ack_loss_never_recreates` | L0 + file L1; Podman NOT_RUN |
| AT50 | B event append ACK 丢失或事件缺失不能重置消费/第二次创建。 | `tests/unit/test_a42363_contracts.py::test_AT41_AT50_partial_creation_ack_loss_never_recreates` | L0 + file L1; Podman NOT_RUN |
| AT51 | 资源创建后被置换、标签变化、namespace 漂移只能 `OWNERSHIP_UNKNOWN_QUARANTINE`。 | `tests/unit/test_a42363_contracts.py::test_AT51_unknown_suffix_keeps_original_identity_and_never_removes_replacement` | L0 + file L1; Podman NOT_RUN |
| AT52 | C recover 严格按账本、倒序目标资源，只处理本 token，不枚举相似资源。 | `tests/unit/test_a42363_contracts.py::test_AT51_unknown_suffix_keeps_original_identity_and_never_removes_replacement` | L0 + file L1; Podman NOT_RUN |
| AT53 | remove 已发送但回执丢失：必须独立查证后续事实，不能默认为 ABSENT。 | `tests/unit/test_a42363_contracts.py::test_AT53_remove_ack_loss_uses_independent_absence_without_second_remove` | L0 + file L1; Podman NOT_RUN |
| AT54 | Socket rmdir 仅在已保存 held dir FD/inode/device/marker/owner 仍匹配时执行。 | `tests/unit/test_a42361_controller_watchdog.py::test_AT19_AT20_dual_identity_or_mount_drift` | L0 + file L1; Podman NOT_RUN |
| AT55 | cleanup 预算耗尽时 first failure sticky、cleanup 单列，不宣称 COMPLETE。 | `tests/unit/test_a42362_owner_recovery.py::test_AT39_expired_cleanup_budget_never_deletes_or_claims_success` | L0 + file L1; Podman NOT_RUN |
| AT56 | Rootless/无公网/资源限额/命令次数/初始化限额不可由测试参数或运行配置放宽。 | `tests/unit/test_a42363_contracts.py::test_AT56_readonly_and_cleanup_accounting_cannot_refund_initialization` | L0 + file L1; Podman NOT_RUN |
| AT57 | E observer UID 与 Controller UID 不同，且具独立真实可见性证明；否则拒绝。 | `tests/unit/test_a42363_contracts.py::test_AT57_AT66_e_never_accepts_unknown_visibility_or_recreation` | L0/file L1; independent multi-UID delegation NOT_PROVEN |
| AT58 | E 不能仅根据 C 发来的 `absent=true` 或同源复制 JSON 发证书。 | `tests/unit/test_a42363_contracts.py::test_AT57_AT66_e_never_accepts_unknown_visibility_or_recreation` | L0/file L1; independent multi-UID delegation NOT_PROVEN |
| AT59 | E 能确认四类型资源完整集合，不可漏看 Secret 或 Socket。 | `tests/unit/test_a42362_audit_supervisor.py::test_AT40_AT45_independent_model_observes_all_four_resources_twice` | L0/file L1; independent multi-UID delegation NOT_PROVEN |
| AT60 | E 对 4 种资源做前后两轮有序独立 raw 观察，记录 exact epoch/namespace/IDs。 | `tests/unit/test_a42362_audit_supervisor.py::test_AT40_AT45_independent_model_observes_all_four_resources_twice` | L0/file L1; independent multi-UID delegation NOT_PROVEN |
| AT61 | 任何 permission denied、unknown Podman namespace、collector 摘要不符→`ABSENCE_UNKNOWN`。 | `tests/unit/test_a42363_contracts.py::test_AT57_AT66_e_never_accepts_unknown_visibility_or_recreation` | L0/file L1; independent multi-UID delegation NOT_PROVEN |
| AT62 | E 发现资源重新创建/ID 更新、插入竞态→不产生 ABSENT。 | `tests/unit/test_a42363_contracts.py::test_AT57_AT66_e_never_accepts_unknown_visibility_or_recreation` | L0/file L1; independent multi-UID delegation NOT_PROVEN |
| AT63 | E 必须独立持久写入审计记录并用新连接读取 ack 后才可能提交认可。 | `tests/unit/test_a42363_contracts.py::test_AT21_AT63_independent_reader_after_commit` | L0/file L1; independent multi-UID delegation NOT_PROVEN |
| AT64 | E 的 `journal/absent/receipt` 具固定 UID/method ACL，没有独立 store 不启动。 | `tests/unit/test_a42363_contracts.py::test_AT39_AT64_AT67_real_host_composes_c_e_d_and_enforces_peer_acl` | L0/file L1; independent multi-UID delegation NOT_PROVEN |
| AT65 | 不同 UID 的 rootless 资源不可见时不能把空结果当不存在。 | `tests/unit/test_a42363_contracts.py::test_AT57_AT66_e_never_accepts_unknown_visibility_or_recreation` | L0/file L1; independent multi-UID delegation NOT_PROVEN |
| AT66 | 任何 E 审计缺口都阻断最终物理销毁/成功资格，保留 C 自身动作证据供人工复核。 | `tests/unit/test_a42363_contracts.py::test_AT57_AT66_e_never_accepts_unknown_visibility_or_recreation` | L0/file L1; independent multi-UID delegation NOT_PROVEN |
| AT67 | Supervisor/Worker 身份区分，未经受信 FD 安装不能启动 worker。 | `tests/unit/test_a42363_contracts.py::test_AT67_v2_uid_partition_preserves_v1_and_does_not_mint_test_authority` | local L1 + L0; kernel cgroup L2 NOT_RUN |
| AT68 | Worker source hash、binary/arg、scope/token/epoch 固定，任意 argv/DSN/PID 请求均拒绝。 | `tests/unit/test_a42363_contracts.py::test_AT68_AT71_root_manager_never_accepts_a_network_pid` | local L1 + L0; kernel cgroup L2 NOT_RUN |
| AT69 | Linux L1：leader 退出但 grandchild 活动，不得宣称完整 scope 已终止。 | `tests/integration_offline/test_a42363_process.py::test_AT70_platform_or_real_setsid_escape_never_becomes_scope_certificate` | macOS NOT_RUN Linux scenario; actual CI property required |
| AT70 | Linux L1：grandchild `setsid` 脱离组后，也不得因为 PGID 空而获得 `TERMINATED`。 | `tests/integration_offline/test_a42363_process.py::test_AT70_platform_or_real_setsid_escape_never_becomes_scope_certificate` | macOS NOT_RUN Linux scenario; actual CI property required |
| AT71 | 在 leader 可复用 PID/PGID 风险下绝不对外部 PID 发送信号。 | `tests/unit/test_a42363_contracts.py::test_AT68_AT71_root_manager_never_accepts_a_network_pid` | local L1 + L0; kernel cgroup L2 NOT_RUN |
| AT72 | IPC handler 阻塞、stdout 无限、fsync 卡住均由外层时间监督中止并保留失败收据。 | `tests/integration_offline/test_a42363_process.py::test_AT72_independent_fd_guardian_fires_while_handler_is_blocked` | local L1 + L0; kernel cgroup L2 NOT_RUN |
| AT73 | 子进程终止后只有明确 owner/cgroup/namespace 事实的独立回执才能提升 execution-scope 状态。 | `tests/integration_offline/test_a42363_process.py::test_AT83_missing_scope_termination_blocks_even_after_rehash` | local L1 + L0; kernel cgroup L2 NOT_RUN |
| AT74 | 固定 SQL 序列=16，失败/投影计数不退款；100ms/2s/8行负例仍保持。 | `tests/unit/test_a42361_worker_evidence.py::test_AT24_projections_count_and_seventeenth_denied` | local L1 + L0; kernel cgroup L2 NOT_RUN |
| AT75 | pre-connect lease、post-connect session/driver drift 任何失败均阻断第一条 SQL。 | `tests/unit/test_a42363_contracts.py::test_AT33_AT68_worker_gate_precedes_fd_credentials_connection_and_sql` | local L1 + L0; kernel cgroup L2 NOT_RUN |
| AT76 | artifact 写入失败留下 `.incomplete`；manifest 不能掩盖未完成或证据篡改。 | `tests/integration_offline/test_a42363_process.py::test_AT76_artifact_fsync_stall_keeps_incomplete` | local L1 + L0; kernel cgroup L2 NOT_RUN |
| AT77 | 首错先于 cleanup 错，GC 不禁用、CPU/elapsed/RSS/Observer 未证明时不填零。 | `tests/unit/test_a42361_worker_evidence.py::test_AT21_AT36_first_error_sticky_cleanup_bounded_and_distinct` | local L1 + L0; kernel cgroup L2 NOT_RUN |
| AT78 | D worker 本阶段 L1 回执只具 `UNATTESTED/NONQUALIFYING`，不产生 G1 物理成功。 | `tests/integration_offline/test_a42363_process.py::test_AT67_AT70_untrusted_scope_is_never_kernel_proof` | local L1 + L0; kernel cgroup L2 NOT_RUN |
| AT79 | A→B→C/O→D→C/E→Reviewer 一条 L1 正例必须能跨真实 Unix FD/内存模拟 backend 路由跑通。 | `tests/integration_offline/test_a42363_process.py::test_AT79_AT81_real_file_model_cross_domain_receivers_and_faults` | local cross-process L1; NONQUALIFYING |
| AT80 | 中间任意跨域 ACK 丢失，消费与资源 ledger 均不可重置/重试。 | `tests/unit/test_a42363_contracts.py::test_AT80_durable_run_attempt_survives_ack_loss_and_new_receiver` | local cross-process L1; NONQUALIFYING |
| AT81 | C `reconcile` RPC 在服务端真有接收器和精确回执，不再直接 NOT_CONFIGURED。 | `tests/integration_offline/test_a42363_process.py::test_AT79_AT81_real_file_model_cross_domain_receivers_and_faults` | local cross-process L1; NONQUALIFYING |
| AT82 | six-domain receipt 的 scope/epoch/time/hash 串联不可用重 hash bundle 伪造。 | `tests/integration_offline/test_a42363_process.py::test_AT79_AT82_six_process_fd_transport_and_forgery_rejection` | local cross-process L1; NONQUALIFYING |
| AT83 | 未独立检验 E ABSENT 或 D EXECUTION_SCOPE_TERMINATED 时 Reviewer 拒绝物理完成。 | `tests/integration_offline/test_a42363_process.py::test_AT83_missing_scope_termination_blocks_even_after_rehash` | local cross-process L1; NONQUALIFYING |
| AT84 | 全部旧单测/源冻结/Reviewer/原项目全量回归通过，没有删除/skip/xfail 来使结果变绿。 | `tests/unit/test_a42363_source_guard.py::test_AT01_AT03_committed_manifest_full_guard_and_four_history_layers` | pending actual final-SHA full regression/CI audit; source test alone insufficient |
| AT85 | 原有 GitHub Actions 同 SHA 实际日志/JUnit/coverage/artifact 对应 HEAD/attempt，无捏造统计。 | `tests/unit/test_a42363_source_guard.py::test_AT01_AT03_committed_manifest_full_guard_and_four_history_layers` | pending actual final-SHA full regression/CI audit; source test alone insufficient |
| AT86 | Linux L1 与 Linux 物理 L2 明确区分，未授权 L2 必须 `NOT_RUN_NOT_AUTHORIZED`。 | `tests/integration_offline/test_a42363_process.py::test_AT70_platform_or_real_setsid_escape_never_becomes_scope_certificate` | local cross-process L1; NONQUALIFYING |
| AT87 | G2 effective warmups=8、G3=NOT_AUTHORIZED、生产读/容量/因果资格=false 不变。 | `tests/unit/test_a42363_contracts.py::test_AT87_safety_state_cannot_accept_real_success` | local cross-process L1; NONQUALIFYING |
| AT88 | 最终 W00–W13 逐项真实结果、阻断责任和准确剩余行动记录到审阅交付包。 | `tests/unit/test_a42363_contracts.py::test_AT87_safety_state_cannot_accept_real_success` | PARTIAL_SOURCE_BLOCKED; see closeout W00–W13 and remaining actions |

The initial ten inventory tests cannot establish behavior. New cross-domain tests run
actual C/O/D/E receiver algorithms in child processes using independently persisted
file-backed DB models and private ordinary resources; no model can issue G1 proof.
Inherited A42361/A42362 crypto, one-shot, socket, frozen worker and source guards remain
mandatory. Missing an exact scenario is an acceptance gap, never an implicit PASS.

