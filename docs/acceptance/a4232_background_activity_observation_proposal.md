# A4-2.3.2 后台维护活动归因观测提案

**PROPOSAL / NOT APPROVED / NO MEASUREMENT EXECUTED**

提案标识：`a4232-background-observation-v1-draft`。本文件不是已批准的测量协议，
没有实现观测器、运行校准、采集新样本或获得生产/容量准入。以下频率、预算与安排均为
待审阅设计参数，不是实测性能数字。不得以本次普通提交激活任何一次性实验入口。

## 1. 问题与历史边界

历史来源保持 `3916dc4dc72f83f2470a96ff265428bd2e9549e2` /
[run 39833706083](https://github.com/sssssssssh/ssh_stock/actions/runs/39833706083) / attempt 1。
原批次只采集 64/128 个记录，完整合同仅验证 32 个，末尾四条缺后置计划签名。
已记录的四表统计和计划身份未见变化，但 worker 计数从 0 变 1，故停止。
计数不能识别具体 PID、目标关系、操作或实际开始时刻，更不能等同于自动 ANALYZE。
保留 `INCOMPLETE_ENVIRONMENT_DRIFT / INSUFFICIENT_EVIDENCE`，不改写历史 ZIP、manifest、
协议、审阅 JSON 和原有报告，不补采缺失样本，不归因生产性能根因。

下一轮拟回答：哪个维护进程在什么时间边界内处理哪张关系，是否与 lookup 窗口重叠，
是否同时出现目录统计或计划身份变化。时间重叠仍只是关联，不自动构成因果机制或唯一修复候选。

## 2. PostgreSQL 17 只读字段白名单

2026-10-23 已核对官方 **17** 版文档，不以其他主版本的字段替代：
[进度视图](https://www.postgresql.org/docs/17/progress-reporting.html)、
[活动与累计统计](https://www.postgresql.org/docs/17/monitoring-stats.html)、
[预定义角色](https://www.postgresql.org/docs/17/predefined-roles.html)。
未来实现必须在采样前只读核验服务端主版本、视图存在性、字段类型和权限；
任一必要字段不存在或被权限遮蔽时，输出 `INCOMPLETE_OBSERVABILITY` 并停止，不静默删字段。

| 来源 | 拟保存的显式列 | 用途/限制 |
|---|---|---|
| `pg_stat_activity` | `datid`, `pid`, `backend_type`, `backend_start`, `query_start`, `state`, `wait_event_type`, `wait_event` | 不 SELECT 原始 query；PID 与 backend_start 一起标识进程，避免 PID 复用 |
| `pg_stat_progress_vacuum` | `pid`, `datid`, `relid`, `phase`, `heap_blks_total`, `heap_blks_scanned`, `heap_blks_vacuumed`, `index_vacuum_count` | 仅代表被捕获的普通 VACUUM 进度；不能由空结果断言没有维护 |
| `pg_stat_progress_analyze` | `pid`, `datid`, `relid`, `phase`, `sample_blks_total`, `sample_blks_scanned`, `ext_stats_total`, `ext_stats_computed`, `child_tables_total`, `child_tables_done`, `current_child_table_relid` | PG17 提供这些字段；只描述采样时的 ANALYZE 进度 |
| `pg_stat_user_tables` | `relid`, `schemaname`, `relname`, `last_autovacuum`, `last_autoanalyze`, `autovacuum_count`, `analyze_count`, `autoanalyze_count`, `n_live_tup`, `n_dead_tup`, `n_mod_since_analyze`, `n_ins_since_vacuum` | 边界累计信息可能延迟可见，不是精确事件时间线 |

关系映射在当前合成 UUID 库内用 `datid + relid` 连接 `pg_class/pg_namespace`，保存白名单
schema/table 标签；索引用 `pg_index` 映射父表。只记录批准的四张关键表、候选表及其索引/TOAST
的预注册 OID 映射，未知关系保持 `UNKNOWN_RELATION`，不靠 query 文本猜测。
跨数据库 relid 不可在当前库直接解析；实例上其他数据库的维护进程只记匿名 database scope，
保持未知，不为补关系映射连接其他库。未知目标的维护活动也触发停止，不能过滤后继续测量。

测量边界另存：物理 marker 与独立 system identifier、PG17 版本、模型/索引定义摘要、
输入键/源码/协议哈希、MVCC snapshot 身份、关系与索引的 `reltuples/relpages/reloptions`、
已有统计摘要、前后计划结构 hash、generic/custom 计数。数据快照、统计、计划和缓存计数分列，
不以其中一个证明其他三个稳定。计数自然递增不自动算计划漂移；指纹及允许变化字段须先冻结。
统计内容只在服务器端归约成摘要，不导出直方图、MCV 或数据值。

## 3. 连接、采样与时间关联

- 仅使用新建、已批准、双物理身份核验的隔离 PG17 合成实例。实例验证先于应用导入或任何建库，
  观测器只连被批准的合成库，不读业务 `.env`、不连接阿里云或运行中的业务任务。
- 独立观测进程拥有一条只读 AUTOCOMMIT 连接，不共享 lookup 的 RR 连接或事务，
  不把累计统计缓存在整轮长事务内。观测线程/进程异常必须传回主进程，不能悄悄退出。
- 拟定活动/进度轮询周期固定 **250ms**，基于同一主机 monotonic 时钟排程，
  从预检起连续覆盖样本前、中、后。一次轮询用一条有界白名单 SELECT 读取活动与两个进度视图，
  各视图同时采样并不保证跨视图原子性，关联矛盾须标记而不是补造事件。
- 每个样本单独记录 lookup 开始/结束 monotonic 与 UTC、observer tick 开始/结束、
  数据库 `clock_timestamp()` 和观测 SQL 墙钟。`query_start` 在非 active 时可能属于上次查询，
  `backend_start` 是进程起点，不冒充维护操作起点。
- 样本前完成最新只读统计/计划指纹检查，样本中只做固定轻量活动轮询，样本后再次检查并保留
  最后一次 post tick。计划探针不进入原 lookup 计时器，仍须承认它可能改变缓存与后续负载。
- 关系统计与计划边界采集执行次序固定；每次 query 用新的 AUTOCOMMIT 语句。
  实例身份在批次前后和每个独立子进程入口核验；不访问/修改业务数据。
- 固定轮询不做失败重试、追赶式密集补 tick 或自适应降频。tick 间隔超过 **500ms**、
  单次观测语句超过拟定 **100ms** 上限、数据缺失/映射不完整即停止为 `INCOMPLETE_OBSERVABILITY`。
  数值须在审批时确认并冻结；观察结果不理想不能临时改预算。
- 仅把事件定位到被捕获的 `[tick_start, tick_end]` 区间；未捕获的短操作可能发生在 tick 之间。
  与 lookup 窗口相交或无法排除相交时保守标记受污染，不宣称精确起止，也不筛除慢点继续。

## 4. 观测开销校准与控制

监控会消耗数据库 CPU/目录扫描和客户端 CPU/序列化成本，独立连接不代表零干扰。
未来必须先批准一个独立校准阶段，不能把这轮 64 条历史记录当作新监控的控制组。

拟议校准采用同一合成输入、原始计时器、固定 C0/C1 顺序，对 observer off/on 做
预注册交错配对：每种配置八个配对，起始方向均衡，四个独立进程；
原始 lookup、SQL 保护、自然 GC 和已有 full/minimal 合同不改变。
小样本校准只判断开销是否可接受，不作 P95 优化或正式 5/100 性能认证。
需在批准前给出配对总数/样本公式与确定顺序文件，不能将其擅自并入原 128 样本协议。

校准证据应包含每 tick SQL/处理/序列化/写盘墙钟、tick 间隔、丢 tick 数、
observer 自身 CPU/RSS、数据库进程累计计数差，以及 on/off lookup 的全量原始配对分布。
客户端 CPU 和数据库计数分别保存；RSS 高水位不是当前样本独占峰值，嵌套阶段不能相加。
observer off 不具备同等后台可见性，必须标注这项不可比性；不能单独由 off/on 差异证明维护因果。

固定设计开销闸门拟为每 tick 总处理时间不超过轮询周期的 10%、零丢 tick，
其余配对 lookup/数据库 CPU 允许开销阈值由人工审阅在执行前确定，未确定则不批准运行。
不能测后择优选择阈值或以减去监控/GC 时间修正 lookup。
失败保留校准全部数据、标记 `OBSERVER_OVERHEAD_UNQUALIFIED`，不启动归因阶段，不自动重跑。

拟定缓冲为固定容量、非逐行日志；tick 先完整保存在有界内存批次，再按固定边界写新工件。
容量和落盘节奏在实现前冻结，缓冲满、写盘失败或 stop/join 超过拟定 **2 秒** 即失败关闭，
不允许丢记录、无声覆盖或 daemon 线程退出。与主样本计时窗口重叠的写盘成本必须记录。
本轮未执行上述校准，也未证明这些参数足以抑制观测自身引起的尾延迟。

## 5. 分类与停止规则

| 捕获的证据 | 允许的描述 | 禁止的结论 |
|---|---|---|
| 仅 worker 计数变化 | `ENVIRONMENT_ACTIVITY_ONLY`，目标/操作未知 | 自动 ANALYZE、指定表或因果已定位 |
| activity PID 对应 vacuum 进度和本库 relid | `VACUUM_OBSERVED`，列出关联区间/关系 | VACUUM 就是 ANALYZE，或它必然造成某个慢点 |
| activity PID 对应 analyze 进度和本库 relid | `ANALYZE_OBSERVED`，再对照时间/统计/计划 | 仅凭关联就证明唯一性能修复 |
| 只有 last_autoanalyze 或累计计数前后变化 | `POSSIBLE_IN_BRACKET`，可能发生于边界内，考虑统计报告延迟 | 捕获了精确 PID/起点或确定与某次 lookup 重叠 |
| 已知维护但统计/计划没变 | `MAINTENANCE_OBSERVED_WITHOUT_RECORDED_PLAN_DRIFT` | 已证明维护无性能影响 |
| 无进度行、字段 NULL 或权限不足 | `NOT_OBSERVED` 或 `INCOMPLETE_OBSERVABILITY` | 无维护，或将未知填 0 |

固定停止条件拟为以下任一项：

1. marker/system identifier、版本、模型/输入或源代码身份变化。
2. 目标表/索引目录统计摘要或已冻结的计划结构指纹变化；保留前后快照。
3. 维护 worker/进度进入样本窗口，包括不能映射目标的 worker。
4. 观测权限不完整、tick 缺失/超时、线程/连接清理失败或缓冲/工件失败。
5. 样本计数、次序、前后计划/统计合同不完整或存在无法关联的进程/时间信息。

停止后仅允许受控关闭当前采样、回收本轮独立 observer 并保存部分证据；
记录首发异常与清理终态，清理未知不得伪报成功。已采慢点与不完整末样本全部保留，
不补样、不重新排序、不重放实验、不自动关闭 autovacuum 再测。
任何未来定时器也须记录真实触发标记，不凭运行时长猜 `RESOURCE_DEFERRED`。

## 6. 权限与敏感信息

提议 observer 使用专用 `NOINHERIT` 非超级用户登录角色，只有批准合成库的 CONNECT、
系统目录/指定摘要读取权限和必要的 `pg_read_all_stats` 可见性；后者权限较宽，
优先考虑管理员预置的白名单投影和受限统计摘要接口，不授予 `pg_monitor` 的额外扫描权限。
如采用接口需另行审核其 search_path/参数白名单，不能在此任务中创建或授权。
物理 system ID 由既有隔离验证器以已有受限能力验证，不为 observer 获得超级权限。

普通角色可能看不到其他进程的完整活动字段，必须在采样前验证实际可见性。
不授予业务表 SELECT、DDL、DML、MAINTAIN、信号/终止进程、服务端文件访问权限。
只读事务不阻止用户调用有副作用的函数，因此仍须数据库权限和语句白名单双约束。
不调整 autovacuum/analyze 参数，不执行 ANALYZE、VACUUM、统计重置或手动强制统计刷新。

禁止 `SELECT *`、原始 query 文本、SQL 参数、client 地址、用户标识、凭据、连接串、
MCV/直方图和用户数据进入内存日志或工件；只读经过白名单选择的列，操作类型由进度视图分类。
异常仅保存固定错误类、SQLSTATE、阶段与脱敏栈，不上传数据库驱动原异常文本。
未知字段/NULL 保留原因，不能悄悄忽略。

## 7. 人工审批闸门与新工件

**执行仍为 DEFERRED。** 批准前须形成单独的新版本协议及提交，人工确认：

- 专用 PG17 双身份、资源级别、角色/白名单权限、必要字段预检。
- 输入、模型、lookup/观测器源码、统计/计划签名规则、协议和顺序文件的 SHA256。
- 校准及归因各自的样本数、进程数、确定随机种子/交错顺序、完整计数公式。
- 轮询/查询/缓冲/落盘/清理预算、开销阈值、停止及失败关闭规则。
- 是否仅观测或含单因素干预；任何干预须独立获批，不能从本提案推导许可。
- 唯一授权的执行 SHA/run/attempt，以及所有工件和日志的脱敏策略。

建议新目录/前缀 `a4232-background-observation-v1/<SHA>/run-<ID>/attempt-<N>/`，
工件独立保存 `observer-ticks`、`lookup-samples`、`boundary-snapshots`、`calibration`、
`manifest` 和失败收据；每份都绑定新 schema/协议/input/source hash，原子落盘，拒绝覆盖旧路径。
运行后汇总文件也只是 `DIAGNOSTIC_ONLY`，明确 `production_read_authorized=false`、
`capacity_ready=false`；不接入或替代现有正式容量/release schema。

历史证据继续按原 ZIP/hash/来源 SHA 只读复核，不能拿新解释回填历史原始记录。
本轮既不授权此观测器实现/执行，也不授权新的 128 样本、正式 5/100、L2、生产 SQL、A4-3 或 B/C。
