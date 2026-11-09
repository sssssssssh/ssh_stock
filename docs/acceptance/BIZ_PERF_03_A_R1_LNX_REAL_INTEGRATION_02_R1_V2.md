# P0_LNX_REAL_INTEGRATION_02_R1_V2_DELIVERY_REPORT

## 结论与身份

- 工程状态：`CI_ROOT_DIAG_BLOCKED`，不是 `R1_V2_ENGINEERING_CLOSED`。
- V2.0 完整替代未开工的 V1.0；本轮没有另立 CI 修复任务。
- 本地初始 HEAD：`b6ffb7bf8ec7d26f771d9b89923e4f7e926edbed`。
- 经工作区和远端核查，执行 fetch 和 fast-forward 到批准基线
  `e7b783ee70dcf5326f5d4a7797f099308495df43`。
- 开发结束 HEAD、origin/master、实时远端 master 均为上述 e7b783ee 完整 SHA。
- `commit=NOT_COMMITTED`，`push=NOT_PUSHED`，新 SHA CI=`NOT_TRIGGERED`。
- 原有两个审阅 ZIP 和一个 Patch 保留，未清理、覆盖或加入交付范围。
- 本地 Python 3.12.14 / pytest 9.1.1 / macOS；历史 CI 使用 Linux Python 3.12.16 /
  pytest 9.1.1。本轮没有把 macOS Fake 结果冒充 Linux/PG17 验证。

## W00–W07 执行结果

| 阶段 | 实际工作与状态 |
| --- | --- |
| W00 | 核对基线、治理与任务书；在仓库外保存跟踪原件哈希，保留用户归档 |
| W01 | 分别保全两轮 CI 日志、元数据、4 个失败工件 ZIP；完成独立 JUnit 探针；CI-01 缺 PG17 授权环境而 BLOCKED |
| W02 | Guard/Exporter 控制显式事务，同连接双 SHOW，读取期间复核，所有清理均尝试，离线回归通过 |
| W03 | 独立 AST/default oracle，修复 is_active 默认值，18 表 4024 行逐字段一致；exchange 按负责人澄清保留实际 fixture |
| W04 | Exporter 关闭先于 Worker ACK；Owner 保留不可逆历史故障，离线回归通过 |
| W05 | CI-02 已复现并修复 pytest subtest XML 路径；CI-01 未取得确切断言，未改业务诊断/Worker |
| W06 | 定向和历史回归 149 passed、1 failed、1815 subtests passed；唯一失败为未修改的历史 W04-A 字节哈希检查；Ruff/编译/范围检查通过 |
| W07 | 未执行；本轮没有 commit/push 授权，也没有触发、重跑 Actions |

## 六项整改

### P0-01：事务（离线合同 PASS，真实 PG17 NOT_VERIFIED）

connector 必须交付新建且 libpq 状态为 IDLE 的连接。拒绝 busy、已进入事务和未知状态。
在该连接上明确 autocommit=True，再执行显式 RR/READ ONLY BEGIN；不与驱动的自动 BEGIN 混用。
同连接实际 SHOW 必须分别精确返回 `repeatable read` 和 `on`，身份读取前后、导出各表和批次
均验证。原最小权限、物理标记、schema、资源预算及原子身份检查保留。

stateful Fake 重现默认驱动自动 BEGIN 后重复 BEGIN 被忽略，服务器仍为 read committed/off。
旧实现错误接受；新实现拒绝且不发出身份查询。rollback 失败仍尝试 close，任何清理失败均无 ACK。
这是离线连接合同验证，不是实际服务器状态已经验收。

### P0-02：Seed（按负责人澄清后的原件一致性 PASS）

任务书对第二只股票 exchange 的事实与指定基线不一致：原 fixture 第 30–32 行对两只股票均
明确传入 SZSE。负责人已在本轮确认“以实际原 Seed 为准，两只均保留 SZSE，报告任务书事实差异”。
原 fixture、模型、旧 recipe 未修改；将第二只 exchange 改为 None 的负例仍被旧 recipe 以
`R1_SEED_VALUE` 精确拒绝。

独立 oracle 不调用生成器，不导入 ORM/Settings、不执行 seed、不连接数据库；从固定原件 AST
提取 supplied 字段，从 mapped_column AST 获取 default/server_default，按可空和序列规则补齐。
每个 populated 字段记录 explicit_seed、orm_default、nullable_absent、frozen_timestamp 或
serial_state 来源。只允许原五个列的 UTC 微秒冻结；其原 server_default 声明保留在目录身份中。
未知表达式、server default、缺失必填字段及行数变化直接拒绝。

发现并修复另一处实际差异：原 Sector.is_active 的 ORM default 为 True，旧生成器通用 bool
默认填成 False。FrozenSeed 改由独立 oracle 校验，替换生成器为同一个错误输出不能蒙混过关。

| 表 | 行数 |
| --- | ---: |
| stock_basic | 2 |
| trade_calendar | 420 |
| stock_daily / stock_adj_factor / stock_daily_basic / stock_limit_daily / index_daily | 各 600 |
| sector / sector_member | 各 1 |
| data_quality_daily | 600 |
| stock_st_daily / stock_suspend_daily | 各 0 |
| 六张 theme 输入表 | 各 0 |
| 总计 | 4024 |

420 为自然日，其中 300 个 weekday；保留原两证券、两指数和质量 PASS 输入。
五个时间列共 2402 个冻结值。序列：sector 1/未调用，sector_member 1/已调用，
data_quality_daily 600/已调用，increment 均为 1。

完整实体摘要：`0584c782d04cb1baf6e5a8c2ffb2f0c5044018df2a9123192cce52debf358e0d`。
`owner_selection=NOT_SELECTED`，`real_input_equal=false`，`load_real=HARD_DENY` 保留。

### P1-03：ACK（离线 PASS）

先完成全部 Exporter 游标关闭、rollback、连接 close，再调用独立 Worker evidence。
旧 connections_closed 字段只表示 Worker 连接；新摘要 r1.export-summary.v2 分别公开
worker_connections_closed 和 exporter_connection_closed，并明确 WORKER_ONLY 的旧字段范围。
回调仍必须精确匹配 root/worker/token/binding/KNOWN commit/CONFIRMED lease/cleanup/OS exit；
缺失、未知、错误身份与任何清理异常不返回 ExportResult。
PG_TYPED_UNVERIFIED 仍不能改标进入 SYNTHETIC_ONLY 比较。

### P1-04：Owner（离线 PASS）

ever_fenced、expired、first_error、cleaned 保留不可逆事实；首次观测到过期即写入 journal，
即使注入时钟随后回退也不能 confirm。FENCE 后允许真实 cleanup 追加，但其详情保留首次原因
与历史状态。重复 cleanup、错误句柄、未知回收、后续 fence/confirm/spawn 都不恢复运行资格。
保留 reservation，重启只读 journal 不恢复授权。持久化或校验失败继续拒绝。
external_fencing_proven=False，真实 Linux 回收仍未验证。

macOS 的 /var 是符号链接；Owner 测试把自建 TemporaryDirectory 解析成实际目录后使用，
没有降低生产路径的“不允许符号链接”检查。

### CI-01：固定 error-0（BLOCKED / UNKNOWN）

| SHA | Run / test Job | 真实历史结果 |
| --- | --- | --- |
| 8443b7cd524a6964b24cecd60df5be5b6c46783b | [42578748521](https://github.com/sssssssssh/ssh_stock/actions/runs/42578748521) / 129032263125 | 6392 passed、1 failed；3285.78s |
| e7b783ee70dcf5326f5d4a7797f099308495df43 | [42591472675](https://github.com/sssssssssh/ssh_stock/actions/runs/42591472675) / 129073842697 | 6437 passed、1 failed、1 skipped；2982.63s |

两轮均为指定 test_real_root_parity_and_local_reports[error-0]，第 24 步 pytest 失败；
第 44 步安全证据失败、第 57 步 mandatory route 失败分开记录，不将后者当首因。

原断言链已核查：Job FAILED、Publication ABORTED、active_trace 清理、report 数量、error 状态、
execute_calls > 0、金融输出全等。原断言与原文件字节均保留。
已下载的 safe-ci ZIP 均缺 m17_1_2-full.xml，failure.json 均 INCOMPLETE /
evidence_complete=false / full_test_counts=null。safe-errors 中的 tests.json 没有能与目标节点
绑定的历史身份，不能把其中 RuntimeError 直接归为 error-0 的确切失败。

`first_failing_assertion=NOT_OBSERVED`，`root_cause=UNKNOWN`。
`PG17_DIAGNOSTIC_BLOCKED / ISOLATED_PG17_NOT_AVAILABLE`。
目标单节点、success/cancel/error 全体及真实模块回归均 NOT_RUN_BLOCKED。
没有改 performance_diagnostics.py、Worker、原测试、事务或发布代码；没有凭静态推断声称已修复。

### CI-02：安全 JUnit（离线重现路径 PASS，历史触发条件未完整恢复）

纯 1 PASS + 1 FAIL 探针的旧插件正常退出 1 并可脱敏，未复现普遍的退出写入时序故障。
加入 2 个成功 unittest subTest 后稳定重现：pytest 9.1.1 JUnit 声明 tests=4，但只有
2 个 testcase。旧 sanitizer 严格拒绝，抛 A42331_JUNIT_SANITIZATION_FAILED。
失败 subtest 同样覆盖。历史两轮也使用 pytest 9.1.1，但原完整 XML 缺失，不能断言这是其唯一首因。

补丁在原生 JUnit hook 处理每个真实 subreport 后 finalize 其 XML 节点，保留所有真实计数、
测试结果、nodeid、失败退出码和既有严格 sanitizer；不容忍计数不符，不伪造通过数。
该小适配依赖已锁定的 pytest 9.1.1 内部 JUnit API，未来升级需独立合同验证。

插件始终在 finally 保存有界失败 JSON；即使 XML 被破坏，原失败类别、节点 SHA256 及
junit_sanitized=false 仍可保存，XML/CI 继续失败。成功脱敏才记录 true。
正常、失败、collection/setup/teardown error、多 suite、properties、参数化、敏感正文、
重复脱敏、坏 XML、空 XML、伪造计数、DTD/ENTITY 负例均覆盖。
同时检查 a42331-errors 与 a42331-ci 输出，没有上传原始敏感 XML。
collect 在测试失败但证据完整时仍为 INCOMPLETE，evidence_complete=true 不代表 CI success。
无需 Workflow 变更，覆盖率、mandatory gate 和 always 收集规则均未改。

## 测试及失败证据

- 最终组合命令使用原默认 source_contract_pytest，加 -p scripts.a42331_pytest_safety，
  显式选择 12 组 R1/W04-A 单元模块及两组 A42331 模块；没有执行完整 pytest。
- 最终：**149 passed、1 failed、1815 subtests passed，exit 1，74.79s**。
- 安全 XML：1965 testcase，tests=1965、failures=1、errors=0、skipped=0；
  150 个顶层用例与 1815 个 subtest 分开计数，没有相加冒充独立业务验收。
- 唯一失败：tests/unit/test_perf03_lnx_w04a_offline_contract.py::W04AContracts::
  test_A20_four_files_original_reports_and_sources_unchanged_no_writes。
- W04-A 为 19 passed / 1 failed；原 REAL-ADAPTER 的 42 个单元节点、原 REAL-INTEGRATION
  的 44 个单元节点已包含在组合集合中，不另累计。Linux integration 文件未运行；其独立
  LabPermit 不存在，不能把该环境条件视为通过。
- 唯一失败的首项为 AGENTS.md 历史字节哈希期望 56fc204c…，当前 HEAD 与工作区均为
  6ab8120d…。静态对照发现 14 个历史差异项全部精确匹配当前 HEAD 转为 CRLF 后的哈希。
  没有写回换行符、修改历史哈希或放宽断言；完整列表保存在仓库外 w04a-baseline-conflicts.json。
- 新 A42331 故障证据测试单独为 12 passed（exit 0）；子进程故意失败保留退出码 1/2，
  损坏证据故意失败不被算成成功。
- 四组 R1 定向测试、ACK/Owner 原件断言及新增负例在最终组合中通过。
- 全库 Ruff：All checks passed!；10 个新增/修改 Python 文件 py_compile 成功。
- git diff --check 通过；原跟踪文件的差异仅限 9 个获准文件；另新增本报告和 1 个测试文件。
- AST 对照保留原四个测试文件的所有既有断言/断言调用，没有删除、skip 或弱化。

早期 RED 与中间失败全部保留：事务旧路径、ACK 过早、Owner 不可逆事实缺失、Seed 自比对、
subtest JUnit 计数错位。一次中间组合测试期间存在源码编辑，其结果不作为稳定验收；稳定组合
又发现新增 Seed 负例预期错误码不准确，修为既有 recipe 的精确 R1_SEED_VALUE 后才执行最终组合。
最终仍如实保留历史 W04-A 失败，没有重跑刷绿。

补充有界基线回放直接读取 e7b783ee 原件到独立内存模块，复用当前六个回归断言，
有效回放为 6/6 RED、exit 1；对应六节点在最终 GREEN 组合中均通过。
首版回放器存在独立模块 dataclass 类型身份不匹配，仅作为无效辅助诊断保留，未计入验收。

## 文件范围及审阅附件

实际修改：scripts/r1_integration_pg_guard.py、r1_integration_pg_export.py、
r1_integration_seed_loader.py、r1_integration_durable_owner.py、a42331_pytest_safety.py，
以及前四模块各自的 tests/unit 单测。
仅新增 tests/unit/test_a42331_failure_evidence_regression.py 与本报告。

仓库外私有 evidence 目录保存：完整 r1-v2-complete.diff、交付文件 SHA256、基线跟踪原件
SHA256、全部 RED/GREEN 日志、最终脱敏 JUnit、两次原始 Job 日志和下载工件 ZIP。
安全工件的历史 ZIP 身份：

| Run | 工件 ID | ZIP SHA256 |
| --- | --- | --- |
| 42578748521 | 13658926685 safe-errors | 25805d61517ceb31feac8eca8597d87773e89892423b33030b1646c3845bf536 |
| 42578748521 | 13658792080 safe-ci | 6f4bbf3b003c8d634fa48ba432a67ec1565d810f9ab8123b6a7042afe2b5a488 |
| 42591472675 | 13664821429 safe-errors | a979af2cfed81ca0509860b02701dc189339b59d2ad50761b1705af2581dd963 |
| 42591472675 | 13664552614 safe-ci | 781961b317f2871605ebc8f8b4df170c779f1677704b10d95f150909edebca69 |

最终安全 JUnit SHA256：664dfddd5d7cd811472554f6940bb31a0d0d8d68b7c9901e5f4123f232b99eb0。
逐文件和所有证据的完整哈希在仓库外清单提供，避免报告引用自身摘要形成递归。
原始诊断只保存在私有目录，没有提交或上传。

## AC 与剩余门禁

AC01–04、AC06–10、AC14–17 的适用离线合同通过；AC05 使用负责人澄清后的实际 Seed。
AC11 已保全历史；AC12/13 因 PG17 条件 BLOCKED；AC18/19 的历史原件字节校验存在上述
平台换行冲突，范围保护本身通过；AC20 未触发；AC21 授权边界保留。

physical_test_pg17_connections=0，production_stock_db_connections=0，real_worker_roots=0，
perf_OFF_ON_pairs=0，capacity_run=0，production_read_authorized=false。
R1=PARTIAL，AC05=PARTIAL，REAL_PG17_INTEGRATION=NO_GO，REAL_WORKER=NO_GO，OFF_ON=NO_GO，
PERFORMANCE_ACCEPTANCE=NOT_MEASURED，experiment=NO_GO。

下一步仅 CHATGPT_INDEPENDENT_REVIEW。需独立决定合规 PG17 诊断授权及历史字节冻结冲突
处理方式；本轮不扩大修改范围、不申请或实施业务修补、不提交推送、不运行实验。
