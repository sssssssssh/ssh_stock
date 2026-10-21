# V1.4 A4-2.1 执行报告：L2 RESOURCE_DEFERRED，整体验收 OPEN

## 结论与身份边界

P1/P2 已交付；P3 在 `c4f7d3e7a08fc084cbb8afdb8d36ac88980b5478` 完成全部 A4-2 实验、
主 CI、L1 和 L3-scaled-10pct。L2 在 270 分钟软预算附近退出，完整发布结果缺失；
publication release gate **正确失败**，因此 DoD **未通过**，不能将报告名称理解为封版。

用户确认暂无独立 Runner，超预算保留 **RESOURCE_DEFERRED**。不采购资源、不操作业务 ECS/数据库、
不改负载、SQL 300 秒、发布 300 秒/1000 万行保护。整体仍为
`INFRASTRUCTURE_PASS=false`、`CORRECTNESS_PASS=false`（容量证据未齐）、
`READ_PERFORMANCE_PASS=false / NOT_CLAIMED`、`A4_2_NO_SAFE_WINNER`；
`production_read_authorized=false`、`authorize_a4_3=false`。

本报告所在追补提交还修复“软截止被 rollback 异常遮蔽”的**测试收据分类**。
下列远程结果严格属于 **c4f7d3e**，不能填充追补提交自己的 exact-SHA/attempt 门禁。
追补提交的完整远程 CI 尚未验收，继续 OPEN；它没有修改 SQL、workload、生产事务或门禁断言。

## 提交与修改文件

基线：master `02c69c6127860f72adaf79071a9a11930b69e411`。保留 master，无切分支、重置或历史重写。

| 阶段 | SHA | 内容 |
|---|---|---|
| P1 | `9dd81d538d0b014e683421fc6e9ffb19e4e42b6f` | 历史取证、ADR、1002 组契约与负向门禁 |
| P2 | `5593d58246f573a5d90d45416c7904c212bdc5a4` | scope、原子工件、容量拆级与严格聚合 |
| P2 修复 | `7f5857ee08000fd77d5ddb4ce2e59146ad150008` | 冻结采样器标签、旧 CLI stderr、软截止与反例 |
| P3 | `c4f7d3e7a08fc084cbb8afdb8d36ac88980b5478` | 参数隐私、中断 profile、真实执行与 OPEN 交付 |
| P3 资源追补 | 本报告所在提交 | 保留真实预算触发、最终证据索引与资源延期 |

修改文件分组，完整清单用 `git diff --name-only 02c69c612786 HEAD`：

- CI：`.github/actions/a421-pg/action.yml`、`.github/workflows/ab-read-a4-2.yml`、`.github/workflows/ci.yml`。
- 新脚本：`scripts/a42_ci_contract.py`、`a42_receipt_contract.py`、`a42_artifacts.py`、`a42_scope.py`、
  `a42_gate_io.py`、`ci_release_gate_v14_a4_2_1.py`、`publication_release_checks_v14_a4_2_1.py`。
- 原脚本：`ab_read_experiment_v14_a4_2.py`、对应 summary/resources、`data_publication_capacity_v12.py`。
- 测试：三个 A4 unit 文件、两个 PG17 integration 文件；ADR、矩阵、资源预案、证据索引及四份权威 Markdown。

backend、config、migrations、frontend 无变更。442 份冻结源文件/原 A4-1 证据校验通过。
原 run_level 和全部 release assertions 保持 AST 相同，原主 CI 核心步骤未裁剪。

## c4f7d3e 的真实 CI、工件与覆盖

- [A4-2 实验及门禁](https://github.com/sssssssssh/ssh_stock/actions/runs/39658114980)：23 个必需 Job 成功
  （338 项安全回归、21 分片、1 聚合门禁）。
- [主 CI 与独立容量](https://github.com/sssssssssh/ssh_stock/actions/runs/39658115015)：核心、L1、L3 成功，
  L2 失败；publication release gate 失败。原 master 不适用的 UI 分支专用 Job skipped，不作必需验收替代。
- [冻结 A4-1](https://github.com/sssssssssh/ssh_stock/actions/runs/39658114924)、
  [Publication V1.3](https://github.com/sssssssssh/ssh_stock/actions/runs/39658115184)：均成功。
- [脱敏证据索引](evidence/v14_a4_2_1_c4_execution.json)：全部 Job 时间、工件 ID/链接/ZIP SHA256、
  物理 ID、逐组复核摘要、原始三轮比较、月链/RR2、L2 阶段检查点及两个门禁结果。

全部 23 份实验 ZIP 已下载并比对 GitHub digest，再逐组检查 gzip SHA256、manifest、
物理身份、Golden、键集合、NULL/dtype、EOF/close、原生实际计划和锁探针。
**1002 required + 6 auxiliary = 1008**，21 个物理 ID 均不同，无缺组/重复混算；重新执行 validate_lab 通过。
覆盖两档参数、三轮、六窗口、三个月 430 自然日真实根读集/链尾 T8、RR2、15 形态与 E3；
E3 仍 UNPROVEN，不参与生产安全赢家选举。

实验 gate 的 INFRASTRUCTURE_PASS=true / CORRECTNESS_PASS=true **只属于实验工作流**，
不是包含容量的整体 DoD；其 READ_PERFORMANCE_PASS=false 和生产授权 false 保持不变。

| 工件 | ID | ZIP SHA256 |
|---|---:|---|
| 实验成功 gate | 12387263351 | `a5b0dd280f23845b9b81c9f0a91c56ef25ed195657e6db62ed7c0a33ca8705af` |
| 完整 Core | 12377070461 | `adfeeaa862fbbc22da9a95781956de8df655f2f38fd511067e626902f52a013c` |
| L2 中断 | 12390041601 | `403bef1f79e0625400cebd1fc0f84babcec83934db3a2caa386705f85400b0f3` |
| 发布失败 gate | 12389403415 | `c58c78c627fd91ad24795bdd73d69d72db0268b81c53c91e0be43186ff651882` |

原 ZIP/覆盖率/归档不提交 Git，仅提交脱敏索引；工件有保留期限。

## c4f7d3e 的预算与实耗

以下为 **CI Job 总时长（含初始化/压缩/上传）**，不是纯 SQL 或读取时间；
manifest/setup 另存建表/导入/ANALYZE/census、读取/计划/工件分段。

| Job | 分钟预算 | 实耗秒 | 状态 |
|---|---:|---:|---|
| contract-and-safety | 45 | 350 | success |
| a42-million-full-0 | 240 | 3679 | success |
| a42-small-10k | 120 | 239 | success |
| a42-million-plans-full-0 | 240 | 1465 | success |
| a42-small-100k | 120 | 1233 | success |
| a42-million-plans-full-1 | 240 | 2026 | success |
| a42-million-plans-window_matrix-0 | 240 | 1497 | success |
| a42-million-window-0 | 240 | 3083 | success |
| a42-million-full-1 | 240 | 3051 | success |
| a42-million-monthly | 300 | 8382 | success |
| a42-million-window-1 | 240 | 2970 | success |
| a42-million-plans-window_matrix-1 | 240 | 1500 | success |
| a42-million-readers | 240 | 3560 | success |
| a42-million-plans-monthly-0 | 240 | 2341 | success |
| a42-million-plans-monthly-1 | 240 | 2142 | success |
| a42-million-plans-monthly-2 | 240 | 2134 | success |
| a42-shapes-partial | 120 | 82 | success |
| a42-shapes-b_only | 120 | 77 | success |
| a42-shapes-high | 120 | 82 | success |
| a42-shapes-mismatched | 120 | 65 | success |
| a42-event-prototype | 120 | 228 | success |
| a42-shapes-a_only | 120 | 84 | success |
| a42-acceptance-gate | 30 | 9 | success |
| test（核心） | 原配置 | 2189 | success |
| capacity L1 | 300 / 软 270 | 36 | success |
| capacity L2 | 300 / 软 270 | 16240 | failure / RESOURCE_DEFERRED |
| capacity L3-scaled-10pct | 300 / 软 270 | 6438 | success |
| publication-release-gate | 30 | 8 | failure / UPSTREAM_NOT_SUCCESS |

核心约 36.5 分钟完成，不再等容量结束才执行前端、容器与 Worker 验收。
最长实验分片月链 8382 秒（约 139.7 分钟），未触及 300 分钟预算；无裁剪原矩阵。

## c4f7d3e 的测试与容量

| 验证 | 实际结果 |
|---|---|
| 远程完整 pytest | **2471 passed，0 failed/error/skipped**；JUnit 1455.510 秒 |
| Core 原覆盖率阈值 / Ruff / 迁移循环 | 均 success；阈值 70% 未改；Alembic current=heads=`0058_data_publication` |
| 前端 coverage/build、compose build/nginx | 原全部步骤 success |
| 真实 Worker 容器 | 单 Worker 完成 6、双 Worker 完成 6、双 Worker 原子发布完成 7；max_running 均 1 |
| runtime browser | 桌面/窄屏 **28/28 passed** |
| contract-and-safety | **338 cases**；收据 COMPLETE |
| L1 | 10 stocks × 2 days，164 行，write 0.117026 秒，publish 0.070123 秒 |
| L3-scaled-10pct | 500 stocks × 120 days，378240 行，write 6326.282767 秒，publish 39.457425 秒 |
| L2 | 5000 stocks × 20 days，预期 603040 行；完整结果 **未取得** |

L1/L3 两项回滚探针（row budget / 57014）均通过，A 摘要不变、ledger PREPARING、
根 RUNNING、执行槽保留；最终 SUCCESS/PUBLISHED，读者无错误、max_running=1。
这不代表完整 L3，也不能代替 L2。

本地此前 7f 完整测试为 2468 passed / 89.28% coverage；P3 定向 unit 129 + PG17 integration 6 通过；
c4 本地完整 10k 为 236/236、224.527938 秒。这些不替代上述 exact-SHA CI。
本次资源追补 97 项定向测试已通过；全量重跑结果在交付前单列，不能预写为通过。

## c4f7d3e 百万级性能

每个 fraction 分属自己的 Job，仅在其内部对比。各自 PG17、2 CPU/3 GiB、SQL 300 秒，
A=2570000、当前 B=1350000、其他根 B=2800000、输出 **3104443** 行。
三样本及 p50/p95/嵌套阶段/FETCH 在索引；**不跨 Runner/冷热缓存拼接“提速”**。

| variant | fraction .1 p50 / p95 秒 | fraction 1.0 p50 / p95 秒 |
|---|---:|---:|
| Q0_LEGACY_RAW | 29.854 / 53.805 | 28.973 / 31.610 |
| Q0_SERVICE_CONTROL | 28.167 / 28.982 | 26.944 / 31.764 |
| Q0_SAFETY_EQUIVALENT | 107.121 / 108.947 | 82.970 / 89.613 |
| Q1_CURRENT | 108.323 / 110.963 | 83.728 / 92.569 |
| Q2_CURRENT | 118.233 / 121.318 | 93.074 / 96.229 |
| S3 | 112.209 / 112.526 | 88.952 / 93.323 |
| S3_INLINE | 107.128 / 109.761 | 90.543 / 94.368 |
| S3_KEYS | 109.132 / 111.892 | 92.502 / 94.493 |
| S4 | 108.044 / 110.096 | 91.613 / 93.606 |
| S5 | 104.002 / 104.078 | 88.854 / 88.874 |

前两项 NOT_EQUIVALENT，不能冒充安全基线。S5 在 .1 略快于 Q1，但 1.0 更慢，**不宣称性能达标**。
三个月逐轮实际累计后，等保护 Q0 / Q1 / Q2 / S5 的 p50 分别为
264.841 / 273.593 / 284.750 / 269.855 秒；不是月度中位数相加。
窗口/RR2/原生计划完整数据见同 SHA 工件，锁持有与 T3/T4/T8 是嵌套量，不重复相加。
RSS 为采样下界峰值，不是每方案独立生存期峰值；不能把数据库后台 CPU 冒充后端 PID CPU。
生产 AB_MERGE_READ_ENABLED=false，不选安全赢家。

## L2 RESOURCE_DEFERRED 与追补

c4 L2 从 UTC 19:03:04.751469 到 23:33:08.363667（约 270 分钟）。
最后完整表段为 23:28:27 的 strategy_signal，累计 **503020** 候选行；
signal_forward_eval / data_quality 及正式发布/回滚未完整取得。阶段检查点不能当作整级完成。

原收据记录 OperationalError、failure_code=null、rollback 清理栈。
**预算触发按配置和边界时刻推断，旧收据没有保存定时器标记，不回填或改写旧 ZIP。**
SIGALRM 的 BudgetExhausted 可在清理时被驱动异常遮蔽，暴露测试收据可观测性缺陷。

追补只在 deadline 包装器保存真实定时器触发事实，并附到逃逸异常；
failure 保留终态异常类、SQLSTATE、脱敏栈，仅在真实触发时输出
failure_code=RESOURCE_DEFERRED / budget_exhausted=true。
普通数据库异常不得仅因“运行很久”归为资源不足。
新回归先在旧实现失败、修复后通过，断言 INCOMPLETE/非零退出/0 完整级别/无凭据泄漏。
没有修改生产 rollback 或冻结 run_level。

用户没有可用独立 Runner，保留资源延期，不自动采购或连接业务环境。
[Runner 预案](v14_a4_2_1_runner_feasibility.md) 不构成资源采购或操作授权。

## 历史及未关闭项

历史原取消任务、早期错误与阶段诊断分别在
[历史索引](evidence/v14_a4_2_1_history.json)、
[P2 失败](evidence/v14_a4_2_1_p2_ci_failure.json)、
[7f 快照](evidence/v14_a4_2_1_execution_progress.json)。
旧日志 531 次读取横跨三个规模（各 177 次），不是 531 次百万读取或完整验收。
P2 实际失败 gate 为 INCOMPLETE/UPSTREAM_NOT_SUCCESS，没有靠上传部分文件变绿。

1. **L2 RESOURCE_DEFERRED，整体 DoD OPEN**；发布 gate 失败，不用 L1/L3 代替。
2. **追补提交完整 exact-SHA CI OPEN**；c4 的成功证据只属于 c4，任何新 SHA/attempt 必须独立验收。
3. **READ_PERFORMANCE_OPEN / NO_SAFE_WINNER**；不进入 A4-3/B/C，不启用或部署生产读取。
4. 既有依赖审计 11 项漏洞（4 moderate / 3 high / 4 critical）保留，本轮未改依赖。
5. 非计时计划探针关闭完整参数日志，序列化去除 Query Parameters，保留 DECLARE/actual/EOF/close；
   中断 profile 保持 INCOMPLETE，未被 manifest 引用的旧 gzip 拒绝混入。

全部必需容量、新 HEAD 两门禁与工件完整成功后才能关闭；目前按用户指示保留资源延期，等待审阅。
没有生产库操作、业务任务修改或后续阶段开发。
