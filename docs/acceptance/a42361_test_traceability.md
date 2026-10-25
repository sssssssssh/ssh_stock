# A42361 AT01–40 证据映射（不是40项物理PASS）

类别：PURE_UNIT / CRYPTO_VECTOR / FAULT_INJECTION_OFFLINE；真实集成一律 TRUSTED_INTEGRATION_NOT_RUN。
测试名字含编号是索引，不以测试数量代替工程完成；BLOCKED行保留明确缺口。

| AT | 实际断言/文件（tests/unit/） | 判定边界 |
|---|---|---|
|01|test_a42361_source_entrypoints actual_source_freeze；旧source_guard identity|PURE_UNIT，clean/完整SHA/历史树；最终远端另核|
|02|actual_source_freeze；旧308原函数AST/14blob/manifests|PURE_UNIT，不回填旧记录|
|03|new_layer_content、no_prefix、symlink；旧manifest/HEAD/index竞态8负例；追加root/full_tree21项|PURE_UNIT，精确39路径+全部HEAD tracked真实bytes、mode及FD竞态|
|04|actual_source_freeze git diff业务/工作流/依赖为空|PURE_UNIT|
|05|test_a42361_trust real_RFC8032_test2_nonempty_vector|CRYPTO_VECTOR，本机OpenSSL真实验签|
|06|real_crypto_tamper、strict_encoding、closed_schema|CRYPTO_VECTOR+PURE_UNIT，无回退|
|07|default_has_no_key、revocation_rotation_clock|FAULT_INJECTION_OFFLINE，现实撤销服务NOT_RUN|
|08|signature_alone_cannot_approve，双审批/issuer分离|FAULT_INJECTION_OFFLINE；审批现实NOT_RUN|
|09|binding_drift_before_crypto；旧harness_grant身份漂移|PURE_UNIT，不允许创建|
|10|test_keys_rejected_even_if_mislabeled|PURE_UNIT，托管注册表现实NOT_RUN|
|11|test_a42361_store model_two_consumers_one_commit|模型仅一提交；真实并发NOT_RUN|
|12|schema_and_CAS、resource_creation_reservation|真实SQL源码+协议模型；PG唯一约束未运行|
|13|fault_no_retry、lost_independent_ack、commit_precedes|FAULT_INJECTION_OFFLINE，不退款/不重试|
|14|fault_no_retry disconnect/permission/identity|模型；真实切换/掉电NOT_RUN|
|15|unconfigured_or_business_database_no_connect|PURE_UNIT，connect调用为0|
|16|test_a42361_controller_watchdog isolation_config、forbidden_runtime|PURE_UNIT；真实新建NOT_RUN|
|17|inspection_rejects_escalation、mount_drift|PURE_UNIT；实际runtime网络NOT_RUN|
|18|forbidden_runtime、inspection user/cap/privilege；旧角色合同|BLOCKED：完整owner/角色初始化服务端未齐|
|19|dual_identity_or_mount_drift、OCI_labels|模型拒绝；双域实证NOT_RUN，owner服务端BLOCKED|
|20|dual_identity、no_foreign_PID；销毁源码二次归属检查|模型/源码，部分创建reconcile BLOCKED|
|21|first_error_sticky；旧harness_grant cleanup缺序负例|BLOCKED：独立absent服务端未齐，不能称销毁实证|
|22|default_denies_before_resource_or_command|PURE_UNIT，mkdir/Popen/SQL=0|
|23|test_a42361_worker_evidence real_locked_driver_conversion、mismatch_denies|真实锁定驱动离线转换，无SQL|
|24|projections_count_and_seventeenth_denied、driver故障前缀|模型，第17条发送前拒绝，失败不退款|
|25|first_budget_fault、reserve_clock_backwards|模型100ms/2s/8行，不等于物理期限保证|
|26|model_TERM_KILL_reap、nonterminable、no_foreign_PID|FAULT_INJECTION_OFFLINE；实际kill NOT_RUN；launcher BLOCKED|
|27|worker_default、all_default_entries|PURE_UNIT，真实SQL/Popen/socket=0|
|28|all_default_entries/CLI/env/workflow_dispatch；旧cli默认拒绝|PURE_UNIT，普通push不授予G1|
|29|same_session_driver_model、real_locked_driver_conversion|真实离线wire+模型缓存/同连接，物理NOT_RUN|
|30|server_missing_mode_drift_counter_loss、driver_model reconnect|模型拒绝/有限前缀NOT_PROVEN|
|31|driver_model cached_plan_structure固定未验证|PURE_UNIT，不以模板推导cached计划|
|32|driver_model backendCPU=null；旧resources_observer映射负例|PURE_UNIT/模型，无/proc采集|
|33|driver_model GC不禁用/不扣除、Observer未join值null；旧资源合同|PURE_UNIT/模型，RSS原生单位非bytes|
|34|driver_model BRACKET_UNCOVERED；旧observer_feasibility负例|模型，不补sleep/tick/SQL|
|35|driver_model maintenance UNKNOWN/统计MVCC NOT_PROVEN；旧environment合同|PURE_UNIT/模型，不把相等推导无维护|
|36|offline_bundle、rehashed_bundle、first_error_sticky|PURE_UNIT，自报bundle无资格；外部收据实际NOT_RUN|
|37|bundle_tampering、exclusive_output、fsync_failure、parent_symlink|PURE_UNIT，真实本地安全文件IO；外层fsync终止BLOCKED|
|38|本地全unit/ruff/diff；最终既有CI|具体计数见closeout及最终交付回执，未跑项不预填|
|39|source精确路径；推送后API/日志/工件下载逐级核对|提交时PENDING，最终回执补充，绝不借旧SHA绿灯|
|40|capability_unknowns、old_live_and_fake、default_entries|PURE_UNIT，G1未运行/G2总8/G3未授权/资格false|

原始RED：四实现方法缺失4 failed/0.06s。后续真实修复过程曾发现 synthetic run_id不合法、wire JSON tuple
严格转换、配置正例误用TEST_ONLY、driver模型上下文等测试失败；据实际根因改码/夹具，不降低断言。
受信存储/PG17/OS物理集成不是pytest skip/xfail，明确不属于此次运行集合，统一NOT_RUN待独立授权。

追加AT03在首次推送后获明确授权。12项负例先12 failed、正常正例1 passed；不更改真实用户index flags，
以临时目录真实文件和独立Git协议夹具保持diff/status干净。修复后21 passed/0.36s；后续全unit/新SHA CI另核。
首次CI4151/0skip仅绑定6b29f5d；新测试总数由新JUnit计数，不以旧绿灯填补新SHA。
