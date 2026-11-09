# P0_LNX_REAL_INTEGRATION_02_DELIVERY_REPORT

核查日期：2026-11-09T17:05:53+08:00（Asia/Shanghai）；master；本地待独立代码审阅。

**本轮实现状态：INTEGRATION_CODE_READY_FOR_REVIEW；上游工程状态：UPSTREAM_CI_FAILURE。**
**R1 / 历史 AC-05 继续 PARTIAL，真实实验 NO_GO。没有自动提交、推送、dispatch 或重跑。**

## 1. W00 基线、授权及文件保护

- 开始、结束 HEAD 与 origin/master：`8443b7cd524a6964b24cecd60df5be5b6c46783b`；开始时只读 ls-remote 核实 GitHub master 同 SHA。
- 开始工作区 CLEAN，分支 master；未拉取、切换、创建分支、清理、重置或改写历史。
- 五份治理文档按 AGENTS 指定顺序读取；按 PRD → 系统设计 → PROJECT_RULES → README 核对相关业务边界，再核对外部任务书、W03/W04/W04-A、REAL-ADAPTER-01 报告及源码。
- PROJECT_STATUS 顶部 G0 和更早 CI-OPT 指针为历史快照。当前唯一授权任务来自负责人本次明确批准的 REAL-INTEGRATION-02；本轮不改治理文件、不重新规划项目。
- 工具基线 8443b7cd 与原 fixture/业务源 b6ffb7bf 分字段登记。新增工具摘要由 source_identity() 给出，旧协议/Schema/source hash 不改写，不把 Git SHA 或摘要当许可。
- 全部 1,530 个既有跟踪文件逐字节 SHA256 保持不变；其中上轮 18 文件逐项 before=after，见附录及外部 original-18-protection.json。仅新增白名单 15 文件。

## 2. 已实现能力、接口与实机缺口

| 工作包 | 新代码与复用 | 离线可证明范围 | 仍未证明 |
| --- | --- | --- | --- |
| W01 | Pg17ResourceGuard.inspect/check_connection/require_ready；显式 DB-API connector + 外部审查 verifier | BEGIN REPEATABLE READ READ ONLY；版本、物理号、marker、OID、postmaster_start、库、用户、角色能力、成员、环境和只读权限匹配；重连重新检查；失败关闭/回滚/关闭 | 无真实 connector、外部审核服务或物理隔离实证；专用实例的查询权限仍须独立验收 |
| W02 | generate_original_input；FrozenSeed.capture_once/prepare_manifest/plan_load/verify_loaded_snapshot/compare_loaded | 18 输入表、4024 行、420 日、两证券、固定请求、五默认时间列、序列、全列/类型/空值、自然键排序、ORM 索引/检查约束/枚举目录和 fixture/source 摘要；不同 loader/resource 标签；重新消费 reader 的实体值 | reader 和资源标签目前为 fake 合同，未绑定真实 PG 物理收据；G05 不关闭 |
| W03 | PgTypedExporter.export；decode_native/decode_row；复用旧 Schema/compare_snapshots | 37 表520列显式 SELECT；PG Catalog 列名/SQL型/nullable/PK/FK 全量匹配；单一只读 RR 快照；按自然键排序；日期/UTC/UUID/JSONB candidate row_key tuple 与 row_data/base_row 还原；引用闭包及独立 ACK 绑定 | 无真实导出/驱动/运行时 JSON 兼容实证；真实比较桥明确拒绝，见下文 |
| W04 | DurableOwner；LinuxProcessDomain；独立固定 supervisor/child 进程实现 | 自有文件 O_EXCL、文件 fsync、目录 fsync、hash-chain、同实例确权/期限/意图/句柄绑定/挂起/fence/cleanup ACK；固定解释器和模块摘要、shell=False、最小 env、独立 SID/PGID、pidfd 单进程信号、PID/start 重核、限流输出、期限和 TERM/KILL | Windows 目录 fsync 单测注入替身，不能证明 POSIX 落盘；实际 Linux OS 场景 NOT_RUN；外部强 fencing NOT_PROVEN |
| W05 | run_injected；OfflineIntegrationComponents；旧 execute_one_r1_root + OfflineContext | 组件有实际接线：Guard→Owner→Seed reader→fake domain→旧 create/claim/execute fake Facade→typed export/旧严格比较→清理；首错停止，仅 OFF 合同一次，无自动 ON/重试 | 无生产 Facade/真人授权 verifier 或真实 Worker 启动路径；公共 Controller CLI 无条件退出2 |
| W06 | 44 新单测 + 38 AC + 520 列子断言；原62回归 | 测试统计、失败前缀、Ruff、compile 及原件保护 | 全仓真实 PG/Worker 集成和新源码 CI 未运行 |
| W07 | 本报告、外部命令/日志/摘要/逐列证据 | 可交独立源码审阅 | 不自行 DONE/关闭门禁或进入实机阶段 |

### 2.1 Seed 与输入实体边界

默认实现候选 BASELINE_SNAPSHOT_ONCE_THEN_LOAD_TWICE，负责人选择仍 NOT_SELECTED。capture_once 只调用注入捕获器一次；后续校验重算确定性参考数据，但不再次调用原 seed 或捕获器。原 seed 文件没有修改。候选冻结时间为 UTC 2025-01-01 00:00:00.000001，仅用于未获选择的离线配方。

12 个原输入表（含 ST/停牌空边界）与6个主题空表、250交易日预热、430自然日回看、2026-02-23～02-24 请求均保留。Sector 显式101不等于序列推进至101；Sector 序列1/is_called=false、member1/true、quality600/true。字节身份包含 timestamp 微秒和全部序列状态，不以 non_timestamp_sha256 代替。

canonical 实体摘要在稳定表/自然键/PK排序下生成，不以物理写入顺序作为业务值。同源计划不等于两库实体相等；fake_entity_bytes_equal 仅描述 fake reader 返回值，real_input_equal 恒 false。真实装载 load_real() 即便 authorized=true 也无条件拒绝。原源实体、列型、catalog、序列、部分/重复/丢失数据和非空主题的负例均拒绝。

### 2.2 类型化导出、真实比较桥和预算

新导出器能接收显式 DB-API connector，源码中有实际固定 SQL 和命名游标读取实现；本轮仅 FakeConnection/FakeCursor。事务中设置 statement_timeout、获取 pg_current_snapshot()，导出前后重查物理身份；异常回滚并关闭游标及连接。DB/native 标量严格型，JSONB 中只对已声明的日期、UTC timestamp、UUID 子列恢复类型；不做 default=str、float/Decimal 混同或宽泛文本化。520列目前没有 Numeric；另有 Decimal scale/precision 辅助负例，不改变业务 Float 合同。

限制：总行数≤10000（本小型R1安全上限）、逻辑编码总量≤64MiB、单行≤262144 bytes、单值沿用65536 bytes、每次导出≤30秒；命名游标批64、Catalog批128且恰好520。引用目标与引用值索引各显式限制20000项，超过上限拒绝并保持INCOMPLETE；唯一自然键重复拒绝，scope多重集规则保留；无外部磁盘输出或 spill，默认只在内存中。Python对象/驱动分配的实际RSS、阻塞connect/内核syscall不能由这些逻辑额度硬限制，未来须有独立进程/主机资源限制。禁止据此进行百万行验收或调大门槛。

旧比较器硬性要求 SYNTHETIC_ONLY 和旧业务 baseline。本轮保留此限制：compare_fake_exports 仅桥接明确 FAKE 包，PG_TYPED_UNVERIFIED 包返回 REAL_COMPARATOR_BRIDGE_NOT_AUTHORIZED；绝不将真实导出重标 synthetic。真实结果比较的版本化授权/证据桥未交付，须另批最小增量；这也是 G09 不能关闭的明确阻断。

独立证据绑定 root UUID、worker、token、commit ACK、租约、Worker连接关闭、OS exit、cleanup ACK 与 export snapshot/source digest；unknown ACK 或未完成清理只产生 INCOMPLETE。当前 verifier/ACK 均为注入fake，不能等价于持久权威实证。安全摘要只含摘要、行数和状态，不导出 Raw 行值、证券价格、DSN、凭据、参数或完整 SQL。

### 2.3 Owner、Linux 与停止能力

DurableOwner 的 reservation 独占创建、记录逐项落盘并链式关联；重启后的新对象不能接管旧 reservation，不自动偷锁、恢复、续期或重试。租约总外限390秒，确认过期拒绝；cleanup ACK 不恢复已失效/已fence资格。Windows单测只验证实际文件操作和失败闭合，目录fsync为明确注入替身。共享文件系统、跨机信任、同UID恶意写入、外部主机租约和强fencing仍 NOT_PROVEN。

Linux实现由父控制器先记持久 intent，再启动独立supervisor；监督器收到绑定握手前不spawn固定child，child再次等待所有权握手。只支持5个无网络/无DB固定合成场景。解释器必须绝对真实路径、固定摘要，模块固定摘要及安全所有权/权限；环境仅LC_ALL/LANG/PYTHONHASHSEED。只读新建自有子进程的/proc stat，PID/PGID/SID/start核验及pidfd定向信号；不扫描无关进程、不用过期killpg。输出总量65536字节，仅保存摘要。

setup180、root180、cleanup30、outer390；root和cleanup均是绝对截止且重复进入不续期。合成lab可预设≤10秒的更早停止，绝不延长冻结预算。TERM最多等待5秒，再在清理期限内KILL。watchdog失败、首次确认失败、PID重用、未知回收、D状态或远端失联，保留reservation并记不确定/fence，禁止自动ON。D状态、Popen/内核阻塞和watchdog不可抢占不能靠Python保证硬终止；必须由外部主机/资源owner处置。本轮未证明这项能力。

公共controller CLI对默认、JSON布尔、环境/任意token参数均拒绝，exit2。DevelopmentPermit只用于进程内fake测试；require_human_authorization无条件拒绝，本轮没有预置真实token/密钥。Linux模块内部两个固定合成模式仅服务无DB/无网络child协议，不能选择任意argv/模块或股票Worker；合格lab入口还必须由独立operator注入LabPermit/verifier，不从环境自动放行。

## 3. W06 实际测试与失败证据

| 验证 | 结果 | 退出码/用时 |
| --- | --- | --- |
| 定向pytest（新44 + 原62） | **106 passed，1803 subtests passed，0 failed/errors/skipped** | 0 / pytest229.33s；外部runner230.64s |
| 新增unittest | **44 tests OK**；unittest子断言不另作顶层节点计数 | 0 / runner123.29s |
| 原W04-A unittest | **20 tests OK** | 0 / runner2.59s |
| Linux测试模块 standalone unittest | 2节点：默认拒绝1 PASS，实际Linux场景1 skipped=NOT_RUN/ENV_BLOCKED | 0；不是Linux OS通过 |
| Ruff backend tests migrations scripts --no-cache | All checks passed | 0 |
| py_compile 14个新Python文件 | 全部编译到仓库外证据目录 | 0 |
| git diff --check + 新文件 no-index whitespace检查 | 见最终 static-checks.json | 完成交付前复核 |

原62已经包含W04-A20，因此不是82个不同旧用例；另外单独复核W04-A20不重复计入106。1803子断言=原1249+新554；520列native/alien类型逐列覆盖包含在新子断言中，不冒充106个顶层测试。38个AC编号全可追踪；AC37的PASS仅证明无permit拒绝，不代表实际OS场景通过。

定向pytest保留pyproject默认 scripts.source_contract_pytest 和正常自动插件；只禁用缓存provider防止仓库缓存产物，没有禁用安全插件或改收集/断言。没有安装依赖或改环境锁。完整全仓pytest/PG17/真实Worker测试未运行，因本轮明确禁止连接数据库；不把上述定向统计当完整工程CI。

首次将新增Linux测试放进pytest合跑时，既有tests/integration/conftest.py在收集前导入app.main，离线venv缺FastAPI而exit4；未连接数据库，也未为此导入业务配置/安装依赖/改旧conftest。后来以标准unittest单独验证自包含Linux测试模块，并明确记录平台skip；未用--noconftest规避原安全收集。

RED原件全部保留：red-initial为2模块缺失收集错误exit2；首实现4failed/33passed为合法含数字列名被拒；export-focus另发现synthetic_equal封装缺口；red-composition、red-seed-capture分别证明接线/capture接口未实现；交付前另有red-identity-budget证明索引预算接口缺失，随后补齐20000上限及自然键重复拒绝，9个导出测试通过后重跑全套。随后只修改本轮新增文件。linux-unit-faults第一次1failed/5passed，原因是新测试替身全局屏蔽os.close造成文件句柄未关闭；已将替身限定到假pidfd，保留原断言。runner曾在GBK打印失败日志时再次报编码错，原日志/测试退出码JSON先已落盘；不把runner输出错误隐瞒为成功。

### 3.1 可复核命令和环境

实际绝对解释器、argv/cwd、退出码、耗时和完整stdout/stderr在仓库外 evidence 的同名 .json/.log 中，不在仓库文档写入本机路径。关键命令（python均指同一离线venv解释器）：

```text
python -m pytest <six new unit files> <five original R1 unit files> tests/unit/test_perf03_lnx_w04a_offline_contract.py -q -p no:cacheprovider --junitxml=<EVIDENCE_DIR>/sealed-unit-regression.xml
python -m unittest discover -s tests/unit -p test_r1_integration_*.py -v
python -m unittest discover -s tests/unit -p test_perf03_lnx_w04a_offline_contract.py -v
python -m unittest tests.integration.test_r1_integration_linux_mock_domain -v
python -m ruff check backend tests migrations scripts --no-cache
py_compile.compile(each_new_file, cfile=<external compiled file>, doraise=True)
git diff --check
```

执行环境：Windows10 AMD64、CPython3.12.0、pytest9.1.1、pluggy1.7.0、pytest-cov7.1.0、Ruff0.16.4；复用上次仓库外隔离venv，不代表目标Linux3.12.14已安装。无已独立审核的无网络Linux lab/permit，未自动创建VM、容器、WSL或借用CI跑进程专项。

## 4. 上游CI实际结果（精确SHA，仅只读查询）

| 工作流 | Run / attempt / event | 状态 |
| --- | --- | --- |
| A4-1 read baseline diagnosis | [42578748633](https://github.com/sssssssssh/ssh_stock/actions/runs/42578748633) / 1 / push | completed / success |
| Publication V1.3 | [42578748566](https://github.com/sssssssssh/ssh_stock/actions/runs/42578748566) / 1 / push | completed / success |
| A4-2 isolated read experiments | [42578748531](https://github.com/sssssssssh/ssh_stock/actions/runs/42578748531) / 1 / push | completed / success |
| CI | [42578748521](https://github.com/sssssssssh/ssh_stock/actions/runs/42578748521) / 1 / push | completed / failure |

以上全部绑定8443b7cd；Main开始采样in_progress，后续实际completed/failure，不能倒写为通过。Main test Job129032263125 Step24完整pytest **6392 passed / 1 failed / 816 warnings / 3285.78s / coverage90.02%**。失败节点为 tests/integration/test_perf03_root_diagnostics.py::test_real_root_parity_and_local_reports[error-0]。安全插件/--tb=no隐藏具体断言，因此根因UNKNOWN；同时pytest_unconfigure及后续证据收集报A42331_JUNIT_SANITIZATION_FAILED，必需结果汇总也失败。未归因于本轮代码或擅改旧测试/业务/Workflow。

未抓取或归档整份含环境/SQL的原始Job日志，只保存安全的Run/Job/Step元数据、节点、统计及固定错误码。其余三条工作流success不能替代Main失败，也不能将skipped专项作性能通过。本轮没有新提交，故新增15文件同SHA CI=NOT_RUN。停止推送和准入升级；最小后续建议是另立授权只审查该旧失败节点和脱敏失败，不在本轮修改旧模块或重跑。

## 5. 38项AC追踪表

每行PASS只指对应离线测试，所有实机资格仍按第6节。详尽新增节点与520列映射保存在外部ac-node-map.json、column-coverage.json。

| AC | 函数节点 | 实际结果 |
| --- | --- | --- |
| AC01 | `tests/unit/test_r1_integration_pg_guard.py::GuardTests::test_AC01_preconnect_unknown_configuration` | PASS（离线） |
| AC02 | `tests/unit/test_r1_integration_pg_guard.py::GuardTests::test_AC02_external_review_precedes_connect` | PASS（离线） |
| AC03 | `tests/unit/test_r1_integration_pg_guard.py::GuardTests::test_AC03_physical_identity_and_readonly_sql` | PASS（离线） |
| AC04 | `tests/unit/test_r1_integration_pg_guard.py::GuardTests::test_AC04_physical_version_database_marker_replay` | PASS（离线） |
| AC05 | `tests/unit/test_r1_integration_pg_guard.py::GuardTests::test_AC05_role_privileges_and_unknown` | PASS（离线） |
| AC06 | `tests/unit/test_r1_integration_pg_guard.py::GuardTests::test_AC06_reconnect_restart_permissions_and_safe_errors` | PASS（离线） |
| AC07 | `tests/unit/test_r1_integration_seed_loader.py::SeedLoaderTests::test_AC07_generate_once_complete_original` | PASS（离线） |
| AC08 | `tests/unit/test_r1_integration_seed_loader.py::SeedLoaderTests::test_AC08_default_timestamps_frozen` | PASS（离线） |
| AC09 | `tests/unit/test_r1_integration_seed_loader.py::SeedLoaderTests::test_AC09_sequences_and_catalog_exact` | PASS（离线） |
| AC10 | `tests/unit/test_r1_integration_seed_loader.py::SeedLoaderTests::test_AC10_independent_dual_loads_and_entity_values` | PASS（离线） |
| AC11 | `tests/unit/test_r1_integration_seed_loader.py::SeedLoaderTests::test_AC11_source_tampering_partial_duplicate_theme_type` | PASS（离线） |
| AC12 | `tests/unit/test_r1_integration_seed_loader.py::SeedLoaderTests::test_AC12_no_plan_only_proof_or_live_loading` | PASS（离线） |
| AC13 | `tests/unit/test_r1_integration_pg_export.py::ExportTests::test_AC13_all_37_520_catalog_native_and_negative` | PASS（离线） |
| AC14 | `tests/unit/test_r1_integration_pg_export.py::ExportTests::test_AC14_readonly_repeatable_catalog_drift` | PASS（离线） |
| AC15 | `tests/unit/test_r1_integration_pg_export.py::ExportTests::test_AC15_types_jsonb_candidates_and_tuple` | PASS（离线） |
| AC16 | `tests/unit/test_r1_integration_pg_export.py::ExportTests::test_AC16_duplicate_missing_fk_and_key_closure` | PASS（离线） |
| AC17 | `tests/unit/test_r1_integration_pg_export.py::ExportTests::test_AC17_nonfinite_timezone_scale_unmapped_json` | PASS（离线） |
| AC18 | `tests/unit/test_r1_integration_pg_export.py::ExportTests::test_AC18_budget_timeout_and_connection_failure` | PASS（离线） |
| AC19 | `tests/unit/test_r1_integration_pg_export.py::ExportTests::test_AC19_real_evidence_never_relabelled_synthetic` | PASS（离线） |
| AC20 | `tests/unit/test_r1_integration_durable_owner.py::OwnerTests::test_AC20_atomic_reserve_and_no_restart_reuse` | PASS（离线） |
| AC21 | `tests/unit/test_r1_integration_durable_owner.py::OwnerTests::test_AC21_intent_is_durable_before_handle` | PASS（离线） |
| AC22 | `tests/unit/test_r1_integration_durable_owner.py::OwnerTests::test_AC22_lease_expiry_suspend_fence` | PASS（离线） |
| AC23 | `tests/unit/test_r1_integration_durable_owner.py::OwnerTests::test_AC23_crash_truncated_tampered_and_cleanup_ack` | PASS（离线） |
| AC24 | `tests/unit/test_r1_integration_durable_owner.py::OwnerTests::test_AC24_failed_fsync_no_ack_and_no_unsafe_paths` | PASS（离线） |
| AC25 | `tests/unit/test_r1_integration_linux_domain.py::DomainTests::test_AC25_proc_identity_pid_reuse_and_foreign_domain` | PASS（离线） |
| AC26 | `tests/unit/test_r1_integration_linux_domain.py::DomainTests::test_AC26_fixed_command_environment_and_public_deny` | PASS（离线） |
| AC27 | `tests/unit/test_r1_integration_linux_domain.py::DomainTests::test_AC27_deadlines_watchdog_unknown_and_sticky_failure` | PASS（离线） |
| AC28 | `tests/unit/test_r1_integration_controller.py::ControllerTests::test_AC28_order_cleanup_and_source_dual_identity` | PASS（离线） |
| AC29 | `tests/unit/test_r1_integration_controller.py::ControllerTests::test_AC29_failure_stops_no_on_retry_and_cleanup_always` | PASS（离线） |
| AC30 | `tests/unit/test_r1_integration_controller.py::ControllerTests::test_AC30_diagnostics_and_business_flags_separate` | PASS（离线） |
| AC31 | `tests/unit/test_r1_integration_controller.py::ControllerTests::test_AC31_cli_no_json_environment_authorization` | PASS（离线） |
| AC32 | `tests/unit/test_r1_integration_controller.py::ControllerTests::test_AC32_immutable_original_bridge_and_two_levels` | PASS（离线） |
| AC33 | `tests/unit/test_r1_integration_controller.py::ControllerTests::test_AC33_metrics_unmeasured_and_bad_comparison` | PASS（离线） |
| AC34 | `tests/unit/test_r1_integration_controller.py::ControllerTests::test_AC34_old_62_nodes_and_additional_20_not_double_counted` | PASS（离线） |
| AC35 | `tests/unit/test_r1_integration_controller.py::ControllerTests::test_AC35_source_module_count_no_business_imports` | PASS（离线） |
| AC36 | `tests/unit/test_r1_integration_controller.py::ControllerTests::test_AC36_source_tamper_and_compileable` | PASS（离线） |
| AC37 | `tests/integration/test_r1_integration_linux_mock_domain.py::LinuxLabTests::test_AC37_environment_not_self_authorized` | PASS（无permit拒绝）；Linux OS NOT_RUN |
| AC38 | `tests/unit/test_r1_integration_controller.py::ControllerTests::test_AC38_upstream_ci_is_evidence_not_runtime_permission` | PASS（离线） |

新增额外负例节点（同样已执行，OS节点除外）：

- `tests/integration/test_r1_integration_linux_mock_domain.py::LinuxLabTests::test_linux_success_term_kill_owned_child`：NOT_RUN/ENV_BLOCKED
- `tests/unit/test_r1_integration_controller.py::ControllerTests::test_composed_real_adapters_fake_io_not_just_callback_labels`：PASS
- `tests/unit/test_r1_integration_linux_domain.py::DomainTests::test_spawn_intent_failure_and_pid_reuse_never_signals`：PASS
- `tests/unit/test_r1_integration_linux_domain.py::DomainTests::test_watchdog_failure_and_foreign_handle_cannot_be_success`：PASS
- `tests/unit/test_r1_integration_linux_domain.py::DomainTests::test_signal_pidfd_rechecks_identity_and_never_uses_killpg`：PASS
- `tests/unit/test_r1_integration_pg_export.py::ExportTests::test_independent_ack_cleanup_failure_and_fetch_exception`：PASS
- `tests/unit/test_r1_integration_pg_export.py::ExportTests::test_identity_budget_and_duplicate_natural_key`：PASS
- `tests/unit/test_r1_integration_seed_loader.py::SeedLoaderTests::test_capture_callback_once_row_order_and_catalog_index_tamper`：PASS

## 6. G01～G12及负责人裁决

| 门禁 | 本轮后状态 | 未解决条件 |
| --- | --- | --- |
| G01 | NOT_AUTHORIZED | 单次真实实验人工批准；本轮仅开发 |
| G02 | MISSING | 独占Linux主机、环境和外部owner/lease实证 |
| G03 | PARTIAL | 目标Linux依赖/ABI安装验收，本机venv不替代 |
| G04 | MISSING | 真实PG17物理身份、角色权限、环境独占和回收实证 |
| G05 | MISSING | 负责人选择冻结方案、两臂真实全列实体读取与独立物理资源绑定 |
| G06 | PARTIAL | 离线编排复用已验证；生产Facade/真实授权桥仍关闭 |
| G07 | NOT_PROVEN | Linux实机首次spawn/回收、watchdog阻塞、D状态和主机fencing |
| G08 | PARTIAL | OFF/ON实体输入及资源身份未在真机比较 |
| G09 | PARTIAL | 520列fake通过；真实导出、运行时JSON、真实比较桥/结果仍未验 |
| G10 | NOT_PROVEN | 本地journal不是独立强一致跨机owner；实际持久ACK/强fencing缺证 |
| G11 | BLOCKED / UPSTREAM_CI_FAILURE | 基线Main失败；本轮未提交/新CI未执行 |
| G12 | PARTIAL；真实停止NOT_PROVEN | 真Linux及资源回收/租约异常收尾仍需实证 |

负责人需裁决两项：

1. **Seed**：是否选定“一次原seed冻结快照供两臂独立加载”，并审定五列冻结时间、序列及schema/catalog版本；或另批事件映射配方。推荐前者便于证明字节输入一致，但本轮仍NOT_SELECTED。真正装载前要有两个物理PG实例的Guard收据、reader资源绑定及全列真实读取，不能仅信任loader/resource标签。
2. **Owner**：选定独立operator/持久权威与主机/资源lease、强fencing实现及D状态处置责任；本地fsync journal可作审计/单机一次性锁，但不作为跨机强fencing。未提供可信服务/权限及实机证据时，保留NOT_PROVEN并停止试验。

下一步先独立代码审阅并处理上游CI债务；经负责人另外授权后，才可在专用Linux/PG17做实际身份、Seed装载/typed export/清理验收，届时还须审阅真实比较桥的独立版本化增量。该验收完成后再单独申请OFF1→ON1。三对≤3%与百万行≥30%均未执行；不启动下一阶段或扩展Mock平台。

## 7. 固定回执

```text
P0_LNX_REAL_INTEGRATION_02_DELIVERY_REPORT
baseline_at_start: 8443b7cd524a6964b24cecd60df5be5b6c46783b
head_at_end: 8443b7cd524a6964b24cecd60df5be5b6c46783b
remote_master_at_start: 8443b7cd524a6964b24cecd60df5be5b6c46783b
changed_files: 15 NEW files, whitelist only; no existing modifications
existing_file_hashes_unchanged: TRUE (1530 tracked; original18 before=after)
upstream_ci_8443b7: Main FAILURE; A4-1/A4-2/Publication SUCCESS; attempt1 push
work_packages: W00-W07 local implementation/evidence delivered; real validation NOT_RUN
actual_commits: NONE
new_test_acs: AC01-AC38, node map in section5
pytest: 106 passed; 1803 subtests; 0 failed/errors/skipped; exit0
unittest: new44 OK; originalW04A20 OK; platform 1 PASS + 1 NOT_RUN(skip)
ruff_pycompile: PASS (full repository Ruff + 14 new files compile)
linux_os_mock: NOT_RUN / ENV_BLOCKED; no qualified Linux lab; no real Worker
pg17_connections: 0
real_worker_roots: 0
off_on_pairs: 0
capacity_runs: 0
vm_created: 0
cloud_access: 0
manual_actions_dispatches: 0
seed_recipe_selected_by_owner: NOT_SELECTED
real_input_equal: NOT_VERIFIED
real_pg_export_verified: NOT_VERIFIED
durable_owner_external_fencing: NOT_PROVEN
root_os_cleanup_real_worker: NOT_PROVEN
real_execution_bridge_original: STILL_HARD_DENY
R1: PARTIAL; AC05: PARTIAL; experiment: NO_GO
commit: NOT_COMMITTED; push: NOT_PUSHED
```

上述0只统计本轮本机动作；只读查询历史CI不表示本轮执行其数据库/Worker工作。没有创建/迁移/读写真实数据库、股票Worker、TuShare、OFF/ON、容量、部署、云资源或手工Actions。

## 附录A：原18文件保护

| 路径 | before = after SHA256 |
| --- | --- |
| `docs/acceptance/BIZ_PERF_03_A_R1_LNX_REAL_ADAPTER_01.md` | `06cf9db836ac9c820836d82f404cc429afbaaa3a9d182cc51f388d8db437fc02` |
| `docs/acceptance/BIZ_PERF_03_A_R1_LNX_W03_PREFLIGHT.md` | `21e9f0acc048d1724be985b13667a2cd71572992096abea9d8fbd57699455c9d` |
| `docs/acceptance/BIZ_PERF_03_A_R1_LNX_W04A.md` | `25bffe509c2f78473221bbb39c61bac95eec6db5e0930828205072ea46e66b20` |
| `docs/acceptance/BIZ_PERF_03_A_R1_LNX_W04_READINESS.md` | `09ac6d54828cdc085e134c5a54f91e3a1efa8933d42dea1e9bc7ae3967370f0d` |
| `docs/acceptance/biz_perf_03_a_r1_lnx_w04a_contract.json` | `0f464a6acc4efc651fdea798fac1b0b4b3b61069147515115afa5b9f2d91d2f8` |
| `docs/acceptance/r1_business_compare_schema_v1.json` | `f6be0a5de1ce46e30758039a3ab345a308ff96cb36f6ee86ec3ccdc39759f297` |
| `scripts/perf03_lnx_w04a_offline_contract.py` | `b11a4a2b8e6da6224ab8c503130073bef5ace9ec701dbf43649e116c0be6c5a0` |
| `scripts/r1_business_snapshot_contract.py` | `7219c0ffb405f01c3f9af973bf8b38665f1a02afd32361aab30cf67ab132d74a` |
| `scripts/r1_real_root_adapter.py` | `cf2de69c6e5acb2e39334e80eb6c5de3971794fd5d6c86510c406fcf4d3752e3` |
| `scripts/r1_real_root_protocol.py` | `7e3f40d4452a9dc4a7b373b089c5f11ae9b213b163ac0c00fb2b3312cf0d997e` |
| `scripts/r1_real_root_supervisor.py` | `812a5c980f7fdc91c2dbde211d1b30e6d403f719061bc3baa787e57e7cb98892` |
| `scripts/r1_seed_snapshot_recipe.py` | `06d7a34b2a99139e1f7e66a593ccd03c9195098cd1252defb057242058a02f4c` |
| `tests/unit/test_perf03_lnx_w04a_offline_contract.py` | `f3232a88f0be68ca710ffba337e8dcfae9fa096d54a681ee8dc2eb760efce2ef` |
| `tests/unit/test_r1_business_snapshot_contract.py` | `5f9f0e6d19b2c2db8fda50d17fa0fd8f20ab0a8504ff8e89653cdf9a7548ac1e` |
| `tests/unit/test_r1_real_root_adapter.py` | `06d011d40f68299c926d02a70c763dfb17655a287c03a50447f59bb6970ae6a2` |
| `tests/unit/test_r1_real_root_protocol.py` | `eca291b0f915706ef7fb3245cf119d5b277554e373ea880b214c5e66b109ab18` |
| `tests/unit/test_r1_real_root_supervisor.py` | `bf7116510b80f6560a2eb0cd4d44bdd2fc749956e868bf486dc4d401edf9a3df` |
| `tests/unit/test_r1_seed_snapshot_recipe.py` | `3d6770f615a1a4a23460c42768792f476dad78838c5f3af699cd3aecb9300662` |

## 附录B：新增文件摘要

| 路径 | SHA256 |
| --- | --- |
| `scripts/r1_integration_controller.py` | `58c1f40cdec4b02a048ade4ba7ca88fb8b2f484079132319f1717a7cb6081685` |
| `scripts/r1_integration_durable_owner.py` | `066f32ff84339663a07542b68bcc7393f975a3a078c54ed85534ddf60e1b9713` |
| `scripts/r1_integration_evidence.py` | `6e6741e31e318eb6c6e3ec7bf3468c5bfb902aaebadd9e195bba28df779ecfa1` |
| `scripts/r1_integration_linux_domain.py` | `2efa0f15e03087e8fe9b8f7baa3a0e9d990c0b5b72c6abb1bcf4c68ef0330ed6` |
| `scripts/r1_integration_pg_export.py` | `775f7ac5d91a0ebd66d0d536d7676c6152e1b77acd7f72fb9109b9103ae196a9` |
| `scripts/r1_integration_pg_guard.py` | `ed6be3dc0f03d1d445e3e11ffcf61e96b2b76b357e087b98c6ebf4e5d962590d` |
| `scripts/r1_integration_seed_loader.py` | `4aed7c07afccfbb5d1a3701c3392a5f07dcfdf01e33e28968934c28f408f47b5` |
| `tests/integration/test_r1_integration_linux_mock_domain.py` | `455e00a44983597f089ce16b3dd93ab61f3c309a3fb6862e411cda1d1a036654` |
| `tests/unit/test_r1_integration_controller.py` | `5f92ad30b12ab5b784096616c52a1a9dfb37724a196c71ba88eae9e1304884ce` |
| `tests/unit/test_r1_integration_durable_owner.py` | `57a7de240eeefa61852860071f3383684078cd3389eadf3b8ac3d000cdc4e9a1` |
| `tests/unit/test_r1_integration_linux_domain.py` | `9e117f51492a905e79b0eb52834903cdf33aa13f89a7d398194e25399b790eeb` |
| `tests/unit/test_r1_integration_pg_export.py` | `506e4c34e835be9d44216e5591332fd42c070bc18dff9c70bc6fd6dcba9f82ce` |
| `tests/unit/test_r1_integration_pg_guard.py` | `ef4866161ecff927829dcbc24152a507aa8796a57affd6d56a71b687f27222f2` |
| `tests/unit/test_r1_integration_seed_loader.py` | `6599f3001b24bb404271c6f374473d62e6880877b252cf46b6f9c80d54e87b48` |
| `docs/acceptance/BIZ_PERF_03_A_R1_LNX_REAL_INTEGRATION_02.md` | 文档自身最终摘要见仓库外 delivery-sha256.json，避免自引用 |

## 附录C：37表列覆盖

| 表 | 列数 | 新增导出校验 |
| --- | --- | --- |
| stock_basic | 11 | PASS_FAKE；每列native及alien类型负例；Catalog全量校验 |
| trade_calendar | 4 | PASS_FAKE；每列native及alien类型负例；Catalog全量校验 |
| stock_daily | 12 | PASS_FAKE；每列native及alien类型负例；Catalog全量校验 |
| stock_adj_factor | 3 | PASS_FAKE；每列native及alien类型负例；Catalog全量校验 |
| stock_daily_basic | 16 | PASS_FAKE；每列native及alien类型负例；Catalog全量校验 |
| index_daily | 10 | PASS_FAKE；每列native及alien类型负例；Catalog全量校验 |
| stock_st_daily | 7 | PASS_FAKE；每列native及alien类型负例；Catalog全量校验 |
| stock_suspend_daily | 6 | PASS_FAKE；每列native及alien类型负例；Catalog全量校验 |
| stock_limit_daily | 9 | PASS_FAKE；每列native及alien类型负例；Catalog全量校验 |
| stock_factor_daily | 54 | PASS_FAKE；每列native及alien类型负例；Catalog全量校验 |
| market_daily | 24 | PASS_FAKE；每列native及alien类型负例；Catalog全量校验 |
| sector | 7 | PASS_FAKE；每列native及alien类型负例；Catalog全量校验 |
| sector_member | 6 | PASS_FAKE；每列native及alien类型负例；Catalog全量校验 |
| sector_factor_daily | 30 | PASS_FAKE；每列native及alien类型负例；Catalog全量校验 |
| data_quality_daily | 15 | PASS_FAKE；每列native及alien类型负例；Catalog全量校验 |
| data_dirty_range | 13 | PASS_FAKE；每列native及alien类型负例；Catalog全量校验 |
| stock_trade_status_daily | 17 | PASS_FAKE；每列native及alien类型负例；Catalog全量校验 |
| stock_state_daily | 19 | PASS_FAKE；每列native及alien类型负例；Catalog全量校验 |
| strategy_signal | 14 | PASS_FAKE；每列native及alien类型负例；Catalog全量校验 |
| signal_forward_eval | 22 | PASS_FAKE；每列native及alien类型负例；Catalog全量校验 |
| theme | 11 | PASS_FAKE；每列native及alien类型负例；Catalog全量校验 |
| theme_member_snapshot | 7 | PASS_FAKE；每列native及alien类型负例；Catalog全量校验 |
| theme_member_interval | 9 | PASS_FAKE；每列native及alien类型负例；Catalog全量校验 |
| theme_daily | 15 | PASS_FAKE；每列native及alien类型负例；Catalog全量校验 |
| theme_moneyflow_daily | 14 | PASS_FAKE；每列native及alien类型负例；Catalog全量校验 |
| theme_limit_daily | 11 | PASS_FAKE；每列native及alien类型负例；Catalog全量校验 |
| theme_factor_daily | 42 | PASS_FAKE；每列native及alien类型负例；Catalog全量校验 |
| stock_opportunity_daily | 31 | PASS_FAKE；每列native及alien类型负例；Catalog全量校验 |
| job_run | 20 | PASS_FAKE；每列native及alien类型负例；Catalog全量校验 |
| provider_api_log | 9 | PASS_FAKE；每列native及alien类型负例；Catalog全量校验 |
| service_heartbeat | 8 | PASS_FAKE；每列native及alien类型负例；Catalog全量校验 |
| data_publication | 8 | PASS_FAKE；每列native及alien类型负例；Catalog全量校验 |
| data_publication_source | 5 | PASS_FAKE；每列native及alien类型负例；Catalog全量校验 |
| data_publication_row | 9 | PASS_FAKE；每列native及alien类型负例；Catalog全量校验 |
| data_publication_preimage | 4 | PASS_FAKE；每列native及alien类型负例；Catalog全量校验 |
| data_publication_scope | 6 | PASS_FAKE；每列native及alien类型负例；Catalog全量校验 |
| data_schedule_intent | 12 | PASS_FAKE；每列native及alien类型负例；Catalog全量校验 |

## 附录D：交付证据索引

仓库外同任务证据目录保留：baseline.json、original-18-protection.json、upstream-ci.json、environment-compile.json、ac-node-map.json、column-coverage.json、pytest-sealed.json/.log、sealed-unit-regression.xml、unittest-sealed.json/.log、unittest-w04a-final.json/.log、linux-platform-unittest.json/.log、ruff-sealed.json/.log、全部RED及中间运行日志、static-checks.json、delivery-sha256.json、new-files.diff、evidence-sha256.json。
最终JSON清单记录15文件各自大小与SHA256；diff仅新增15文件；JUnit仅对hostname作脱敏并保存脱敏前后摘要，不改变测试结果。完整命令存在外部runner元数据，文档内不复制敏感路径、环境值或原始Job SQL日志。

交付后停止等待ChatGPT独立代码审阅。本报告不是负责人最终验收，也不授予真实执行许可。
