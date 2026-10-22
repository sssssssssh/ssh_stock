# V1.4-A4-2.1 L2 容量诊断：验收 OPEN

## 范围与审阅摘要

拉取 master 后基线为 `66a5ca606734a0b0f80176093b1f0e79566d4505`，生产冻结仍为
`02c69c6127860f72adaf79071a9a11930b69e411`。本轮只增加测试驱动诊断、回归和 Markdown。
未修改 backend、models、migrations、config、frontend、生产发布或任何实际服务。

历史证据足以定位到慢表的候选阶段，但不能把这些区间进一步归因于 Python、网络、锁或具体计划。
因此**先补观测，不改变默认实现**：无批次大小、payload 缓存、ANALYZE、索引、planner 或服务优化。
不能将本轮解释为生产补算超时已经修复。`AB_MERGE_READ_ENABLED=false`，不进入 A4-3/B/C。

修改文件：

- `scripts/data_publication_capacity_v12.py`
- `tests/unit/test_capacity_progress.py`
- `tests/integration/test_capacity_level_isolation.py`
- `README.md`
- `PROJECT_RULES.md`
- `docs/股票机会发现系统_PRD_V1.0.md`
- `docs/股票机会发现系统_系统设计_V1.0.md`
- `docs/acceptance/v14_a4_2_1_l2_diagnosis.md`

## 任务 0：最新与历史证据

2026-10-22 首次核对最新 `66a5ca6`，attempt 1：

| 工作流 / Job | run / job ID | 首次核对结果 |
|---|---|---|
| [最新主 CI](https://github.com/sssssssssh/ssh_stock/actions/runs/39695837598) | 39695837598 | in_progress |
| Core test | 119552867373 | success |
| L1 / L3-scaled-10pct | 119552867626 / 119552867736 | success |
| L2 | 119552867625 | in_progress；尚无正式收据，不能预判 RESOURCE_DEFERRED |
| [最新实验](https://github.com/sssssssssh/ssh_stock/actions/runs/39695837594) | 39695837594 | 月链仍运行，最终 gate 未取得 |

以上状态是观察快照，不是最终验收。GitHub 未认证 REST 入口限流后改用已连接 GitHub 工具核对；
运行中的 L2 日志端点返回 BlobNotFound，未据此判断任务失败或停止。
最新 L1 工件 ID `12390631628`，L3 `12395722107`，Core `12392025896`；
未以它们或 c4 工件填补最新 L2/聚合门禁。

三份最新 ZIP 也已下载并比对 API digest：
Core `028902adeb375d2298ae8137cf68a76e1afed298a3df5e95ab6e85803d2732bd`，
L1 `6d6f65a453c9394862a56d6937306fc020804cc16030182ab6ac4e23a2135575`，
L3 `b6009a13020447b606315d4c6fb147b35b6b7f6016612d3caee03b85a9941579`。
66a5ca6 的 Core JUnit 为 2473 passed、0 failed/error/skipped（1159.186 秒）。
同 SHA L3 为 378240 行、write 7024.124 秒、publish 42.211 秒、WAL 1827403912 bytes、
reader_samples 113378、reader_errors=[]、max_running=1；它依旧不能替代 L2。

后续观察：66a5ca6 的 A4-2 已 23/23 Job success；聚合工件 ID `12399677318`，ZIP SHA256
`aa64407ed2c18ccb7c0a1767cd987f76c2949c3bf2e44d71b893cf255fd38885` 已重新下载比对。
工件 head/run/attempt 匹配、status=COMPLETE、safety_testcases=340、实验 INFRASTRUCTURE/CORRECTNESS=true；
21 分片汇总 1008 组（1002 必需+6 对照），READ_PERFORMANCE_PASS=false、生产与 A4-3 授权均 false。
这只关闭 **66a5ca6 的实验门禁**，不关闭其容量门禁，更不能替代本轮提交自己的验收。

### 66a5ca6 的最终 L2 失败（已取证）

主 CI 最终 failure，L2 Job `119552867625` 与发布 gate Job `119636605864` 均 failure。
L2 原始工件 ID `12401940419`，ZIP SHA256
`62c233bced9dc4ca40caf013f88813b9fc98eb282978c3c234b48dde5c0466e4` 已下载比对。
其 head/run/attempt 匹配 66a5ca6 / 39695837598 / 1，物理标记与独立 system ID 匹配，PG17。

正式收据 started_at=`2026-10-21T23:49:42.563989+00:00`，
finished_at=`2026-10-22T04:19:45.687361+00:00`，约 16203.123 秒。
**INCOMPLETE、results=[]、completed_groups=0、failure_code=RESOURCE_DEFERRED、
budget_exhausted=true、failure_type=OperationalError、sqlstate=null**。
不同于 c4 推断，这次分类有真实定时器标记，未按时长猜测，也未丢掉清理终态异常。

最后完整表仍是 strategy_signal，累计 503020 行；后续两表/探针/正式发布未取得完整结果。
相邻完成日志间隔：factor 3794.944 秒、state 3832.680 秒、opportunity 8059.412 秒、
signal 66.043 秒；慢区间与 c4 一致，但没有内部 Python/SQL/commit/锁分段，不能直接归因。
正式发布尚未完成，不能称为 publish 服务耗时超过 300 秒。

发布失败 gate 工件 ID `12401735823`，ZIP SHA256
`0115a342ccb96f96ce8e6834984ca04339dd1b724b10cfa5d4db3d6e9e7f2d3f` 已下载比对；
同 head/run/attempt，status=INCOMPLETE、errors=[UPSTREAM_NOT_SUCCESS]，
INFRASTRUCTURE/CORRECTNESS/READ_PERFORMANCE 与生产授权均 false。
这证明门禁失败关闭，不证明 L2 容量达标。本轮仍需用自己的提交重新验收。

历史 [c4 L2 Job](https://github.com/sssssssssh/ssh_stock/actions/runs/39658115015/job/119423683555)
日志已重新读取，原容量 ZIP 已重新下载并核对：

- head `c4f7d3e7a08fc084cbb8afdb8d36ac88980b5478`，run `39658115015`，attempt `1`。
- 工件 ID `12390041601`，ZIP SHA256
  `403bef1f79e0625400cebd1fc0f84babcec83934db3a2caa386705f85400b0f3`。
- 原始收据为 INCOMPLETE、completed_groups=0、results=[]、OperationalError、sqlstate=null。
- 原收据**没有**真实定时器标记，不能补写为已证明 RESOURCE_DEFERRED；旧报告的边界时刻推断仍只是历史推断。
- 原 ZIP 不修改；详细原始索引沿用 [c4 证据](evidence/v14_a4_2_1_c4_execution.json)。

## 任务 1：旧日志基线

下表耗时为**相邻已完成表日志时间差**，包含边界开销，不是原生精确阶段计时。
行数为日志累计值的差，batch/commit 是原驱动可推导的声明值，历史没有实际计数器。
每表实际 RSS、内部 SQL/commit 时间、WAL、锁、错误位置均为 NOT_AVAILABLE。

| 表 | 已观察行数 | 相邻区间秒 | 行/秒（近似） | 声明 batch / commit |
|---|---:|---:|---:|---:|
| stock_trade_status_daily | 100000 | NOT_AVAILABLE（首段含准备） | NOT_AVAILABLE | 200 / 20 |
| stock_factor_daily | 100000 | 3845.517 | 26.00 | 200 / 20 |
| market_daily | 20 | 0.925 | 21.62 | 20 / 20 |
| sector_factor_daily | 1000 | 43.569 | 22.95 | 20 / 20 |
| theme_factor_daily | 2000 | 0.987 | 2026.34 | 20 / 20 |
| stock_state_daily | 100000 | 3856.855 | 25.93 | 200 / 20 |
| stock_opportunity_daily | 100000 | 8057.107 | 12.41 | 200 / 20 |
| strategy_signal | 100000 | 66.637 | 1500.67 | 200 / 20 |
| signal_forward_eval | NOT_AVAILABLE | NOT_AVAILABLE | NOT_AVAILABLE | 200 / 20（计划） |
| data_quality_daily | NOT_AVAILABLE | NOT_AVAILABLE | NOT_AVAILABLE | 20 / 20（计划） |

最后完成日志为 UTC 23:28:27，累计 503020 行。任务 UTC 19:03:04.751469 开始、
23:33:08.363667 终止，总 16203.612 秒；整级未完成。
慢表区间发生在正式发布前，不能归咎于尚未到达的 `update_job(SUCCESS)`。
隔离/seed/public_digests、candidate 创建、record_scope、Python payload、signal ID 查询、
workspace.upsert 内部、逐日 commit、record_validation、统计/计划、两项 rollback、正式发布、
最终 root/ledger 与清理的独立耗时，在该历史失败收据中都为 NOT_AVAILABLE。

## 任务 2：原子进度与保护

新增独立 `CapacityProgress` 与 `observe_capacity`；原 `run_level` 整函数 AST 不变，原冻结测试保留。
观察包装仅在容量脚本进程生效；作用域结束恢复函数、Session 方法和 SQLAlchemy 监听器。
原生产文件没有修改，也没有调用额外业务 SQL。

`--output .../capacity.json` 的旁路文件为 `.../capacity.progress.json`：

- schema=`capacity-progress-v1`、artifact_kind=`DIAGNOSTIC_ONLY`，包含 SHA/run/attempt/model 与工作树身份。
- 记录 level/stocks/days、阶段/当前表、完成表数、表级 rows/batch/commit/payload、阶段耗时、固定 SQL 类型计数。
- 分离 isolation/migration、seed、digest、candidate 创建/清理、scope、payload、upsert、ID 查询、
  commit、validation、三类计划、统计、rollback、update_job 和子库清理。
- 表边界强制落盘；首次操作与连续批次低频 checkpoint。payload 逐行只在内存累计，不逐行落盘。
- 表级 rows 指 upsert 已返回的处理量，commit_count 指按日 commit 已返回次数；不是已发布行数或可续跑凭据。
- RSS 是**进程生存期高水位**，不是独占表峰值。SQL execute 是客户端墙钟（含服务器/网络/等待），
  嵌套于外层调用，不代表纯数据库 CPU，也不能与外层时间重复相加。
- 正常诊断终态 `DIAGNOSTIC_FINISHED` 仍不是正式 COMPLETE。中断/异常保持 INCOMPLETE，
  首发操作与最终清理异常分别脱敏保存；两项预期回滚异常不被记录成真正失败。
- 已有进度文件拒绝隐式覆盖/续跑，重复执行不能留下旧正式 COMPLETE。
- 进度初始化在物理隔离核验之后、业务导入之前；非法目标的原始拒绝提示优先于旧进度检查。
- 不记录 SQL、连接、绑定参数或逐行内容；原生正式计划沿用原逻辑。
- Windows 文件短暂占用最多五次、间隔 25ms，仅重写诊断原子文件，不重放数据库操作。

原 CI always 上传整个容量输出目录，已覆盖 sidecar，**无 CI 配置修改**。
`merge_capacity`、正式收据和 release assertions 原样保留，不接受 progress schema/文件。
软预算仍依赖真实 deadline 触发标记；普通 OperationalError 不能按时长分类。

## 任务 3：低成本诊断与优化决策

先执行 unit、正式 L1 和独立中规模合成回归，再考虑完整 L2。
未手工另开完整 L2，避免与尚在运行的 66a5ca6 重复；用户已授权后续本轮提交推送和 CI 验收。
默认 workload 不改，CI 自动容量运行须单独记录为本轮 SHA，不能复用历史工件。

首个本机中规模样本：600 stocks × 3 days，10 表，**11256 行**。
物理独立 PG17.6 / UUID 子库；本机 Windows，非受限 GitHub Runner、缓存 UNCONTROLLED、LOCAL_ONLY。
原始诊断 `.codex_tmp/l2-diagnosis/medium.json` SHA256：
`36933a9dcfeb16208a6d4ae2cb3c11c0f9b38a50e390f0dd617179090d6f0b20`。
此收据属于本轮开发工作树，不是 clean exact-SHA/正式容量证据。

| 表 | 行数 | 表秒 | payload 秒 | upsert 秒 | commit 秒 | batch / commit |
|---|---:|---:|---:|---:|---:|---:|
| stock_trade_status_daily | 1800 | 1.096 | 0.274 | 0.710 | 0.025 | 6 / 3 |
| stock_factor_daily | 1800 | 2.246 | 0.342 | 1.786 | 0.030 | 6 / 3 |
| market_daily | 3 | 0.099 | 0.001 | 0.038 | 0.015 | 3 / 3 |
| sector_factor_daily | 150 | 0.278 | 0.023 | 0.181 | 0.019 | 3 / 3 |
| theme_factor_daily | 300 | 0.619 | 0.079 | 0.457 | 0.025 | 3 / 3 |
| stock_state_daily | 1800 | 1.806 | 0.362 | 1.319 | 0.032 | 6 / 3 |
| stock_opportunity_daily | 1800 | 2.692 | 0.362 | 2.194 | 0.032 | 6 / 3 |
| strategy_signal | 1800 | 1.170 | 0.301 | 0.756 | 0.024 | 6 / 3 |
| signal_forward_eval | 1800 | 4.317 | 0.004 | 3.413 | 0.024 | 6 / 3 |
| data_quality_daily | 3 | 0.150 | <0.001 | 0.071 | 0.018 | 3 / 3 |

此样本 write=14.520 秒、publish=3.486 秒，RSS=232968192 bytes、实例范围 WAL=48565592 bytes；
reader_samples=358、reader_errors=[]、p95=97.843ms、max_running=1、采样 max_lock_waiters=0。
两项回滚 A digest 不变且占槽保留；最终 root=SUCCESS / ledger=PUBLISHED。
锁采样无等待不证明整个生存期无锁等待；WAL 包含测试探针，不能当作发布独占增量。

同一样本 isolation/migration=4.154 秒、seed=0.658 秒、三次 digest 合计 0.841 秒、
candidate 创建=0.464 秒、10 次 record_scope 合计 0.084 秒、48 次 upsert 合计 10.925 秒、
6 次 ID 查询=0.756 秒、3 次 validation=0.034 秒、两项 rollback 合计 3.912 秒、
candidate 清理=0.021 秒、子库清理=11.178 秒。最终 root/ledger 读取本身未单独计时。
全局 payload 11265 次含 seed 的 9 份模板，不代表新增 9 行；全局 day_commit 32 次含表外提交，
只有各表 commit_count=3 表示按交易日提交。三次 update_job 含两项预期失败探针，不能当作三次成功发布。
上述嵌套时间不能相加；旧样本阶段计数仍保留原值，不回写成后续实现/最终提交证据。

在这个小样本，因子/状态/机会的 WITH execute 分别约 0.765/0.710/1.414 秒，
SignalForwardEval 约 2.820 秒，属于 upsert 内部调用。Python payload/按日提交不能解释全部耗时。
**不把这些数值线性外推到 L2，也不以它们证明同一个生产 SQL 是唯一根因。**
没有等价优化候选，因此本轮无“优化前后提速”比率，不进行 500 vs 其他批次试验，不改变默认 500。

### 独立建议（未实施、需另行批准）

若完整 L2 的新检查点确认大头在 workspace.upsert 的 WITH/lookup，应另立诊断：
在同样 5000×20、同来源/字段/原像下，保留 SQL 原参数但只输出脱敏实际计划/行循环/BUFFERS，
对比统计信息与主键访问、JSON 解码/候选核对的成本；与生产实际情况分开验证。
任何生产实现、统计维护、索引、批大小或查找改写均需新的设计和回归审批。
必须保留首次 base_row、键遮蔽、取消/所有权检查、跨表原子发布、原预算和未知提交保守占槽。
当前收益未知，不批准生产更改，不购买/借用 Runner。

## 任务 4 / 5：验证与 Checklist

| 项 | 结果 |
|---|---|
| 最新 master/CI/历史 ZIP 核验 | 已执行；66a5ca6 实验成功，L2 RESOURCE_DEFERRED，发布 gate 失败 |
| L2 5000×20 / 603040 行公式、原 run_level AST | 冻结测试通过；完整规模实际结果 NOT_VERIFIED |
| 正式 L1、600×3 真实 upsert/commit/读者/两项回滚 | 通过；不能代替 L2 |
| 中途故障保留部分处理量/按日提交、非零退出 | 通过 |
| progress 不可 merge、伪 COMPLETE/重复/旧文件拒绝 | 已补回归 |
| 真实软预算被清理异常遮蔽、普通 DB 异常不误标 | 原回归保留；新增进度保留首发/终态证据 |
| payload 不逐行落盘、脱敏、Windows 有限文件重试 | 已补回归 |
| 首轮定向结果 | 109 passed；之后补充的旧正式收据回归纳入完整测试 |
| 启动优先级修复后的定向结果 | 126 passed（117.02 秒），包含原有非法目标 CLI 断言 |
| 最终完整 pytest | **2490 passed，0 failed/error/skipped；5170.04 秒**（JUnit 5169.945 秒） |
| Ruff / diff / 冻结范围 | 全部通过；生产目录、原 run_level AST、CI/门禁与 A4-1 证据未改 |
| Alembic（仅已验证专用 PG17） | upgrade head 成功；current=heads=`0058_data_publication`，无新增迁移 |
| 新提交 exact-SHA CI / A4-2 / 容量 / 两 gate | NOT_VERIFIED，提交后核对，不预写通过 |
| 云端业务库、真实 Worker/Scheduler | 未连接、未操作 |

早期诊断开发暴露的记录缺陷与本机文件占用失败保留在本地 JUnit；已通过定向回归验证修复，
没有改动原发布/容量断言或调高阈值。完整测试和本轮 exact-SHA 结果需要在交付时据实填写。
一次定向回归与全量共享同一合成实例并发，既有“数据库名单不变”反例因另一测试建/删子库而失败
（61 passed / 2 failed）；没有降低该断言。最终改为串行验证。旧源码快照的全量已主动中止，
仅终止本轮唯一匹配的 pytest 进程，不操作服务或业务库；最终源码的完整 2490 项已重新启动。
新增故障回归保证诊断文件写入失败也不能阻止已经取得资源的真实清理。

完整首轮实际为 **2488 passed / 2 failed（4387.93 秒）**。两项失败来自原有
`test_cli_derived_safety`：三次非法目标共用默认输出，第二/三次被新旧进度检查遮住原始隔离拒绝提示。
不是连接了非法目标；原有“非零退出、原始拒绝文字、无 Traceback”断言未改。
修复仅把 progress 构造移到真实隔离验证之后、业务导入之前；相关 126 项已通过。
最终源码已再次完整运行 **2490 项全部通过**，不是将首轮失败与定向通过拼接。
最终 JUnit 为 `.codex_tmp/a421-l2-checkout/.codex_tmp/l2-full-startup-fixed.xml`；
Windows 原工作树保持原样，以独立 LF 验证副本满足既有 A4-1 原字节冻结断言，三个改动源码文件逐一核对 SHA256 一致。
未修改既有断言、阈值或跳过用例；完整测试有 600 条既有弃用/记录格式告警，未作为本轮依赖升级处理。

最终执行命令：`python -m pytest`（附 JUnit 输出）、
`python -m ruff check backend tests migrations scripts`、`git diff --check`。
仅对物理验证后的合成 PG17 执行 Alembic upgrade/current/heads；不对业务库执行迁移。
本轮没有前端、依赖或容器配置变更，未运行本机 Docker build；原 CI 对这些流程的检查保持原样。

**总体 OPEN；READ_PERFORMANCE_PASS=NOT_CLAIMED；production_read_authorized=false。**
当前仍缺完整 L2 内部时间证据、完整 603040 行成功收据和本轮最新提交的最终聚合验收。
