# M17.1.1 Retention 运维与恢复

适用 PostgreSQL 17、0054_retention_lineage；不修改策略、人工审批、T+1 或旧 Hash。
本次交付不授权生产清理、升级、重算或恢复。写入步骤须先备份、核对目标并单独审批。
密码、连接串、Cookie、备份和业务诊断附件不得提交仓库或聊天。

## 保守上线与只读盘点

保持 `config/app.yaml` 的 `retention.job_deletion_enabled: false`。配置缺失也默认关闭 Job 删除，
不必因此停止行情、EOD 或整个 Scheduler。PAPER 自动开关保持默认关闭。
先记录审批、备份位置、迁移 HEAD、旧 retention 最近执行时间和 Job 类型/状态分布。
统一升级 API/Worker/Scheduler，避免旧 Scheduler 继续执行无保护 Job 删除。

已有 Python 环境和依赖时，从项目根目录执行；已有 PYTHONPATH 时不必重设：

```powershell
$env:PYTHONPATH = 'backend'
python -m app.cli retention-inventory
python -m app.cli retention-indexes
```

默认只读。inventory 输出物理 FK/索引、有界引用/失证数量，可用于 0053 升级前。
observed 是已观察行数；truncated=true 表示超过上限的下界，不能当成总数。
命令仅面向持有部署凭据的运维终端，没有新增跨用户 API 或 Agent 工具。

## 0054 在线索引与迁移

先在预发布演练并评估磁盘、WAL、活跃长事务；大表先预建同名 CONCURRENTLY 索引。
以下两条会写结构，须在目标核对、备份及人工审批后执行：

```powershell
python -m app.cli retention-indexes --apply --confirm
python -m alembic upgrade head
python -m alembic current
python -m alembic heads
```

预建使用独立 AUTOCOMMIT、逐个 CREATE INDEX CONCURRENTLY；锁等待 1 秒，单索引上限 10 分钟。
失败已成功的索引保留，重试验证 READY 后复用，不删除业务行。0054 在新库事务内建索引，
在线复用预建的有效同名索引；INVALID、错误表/列/部分索引明确拒绝，不用 IF NOT EXISTS 掩盖。
迁移锁等待 2 秒、语句 30 秒；10 个新 FK 使用 NOT VALID，不扫描或修补旧 orphan。
current/heads 均应为 0054_retention_lineage；0050–0053 不改写。

失败并发索引可能留 INVALID。先查 pg_index.indisvalid/indisready、pg_get_indexdef，核对
具体名称、定义和占用情况。经审批后只对指定失败的新索引独立执行 DROP INDEX CONCURRENTLY，
再预建重试。隔离演练示例：`DROP INDEX CONCURRENTLY ix_stock_factor_daily_calc_run_id;`。
不是生产批量删除命令；程序不会自动 drop/reindex。真实 INVALID、显式修复、非空往返有 PG 测试。

## 预检、计数与审批

```powershell
python -m app.cli retention-check
# 仅获准查看来源细节的运维人员使用，输出可能含业务 UUID 和日期。
python -m app.cli retention-check --details
```

check 使用 READ ONLY，结束回滚，不删除事实。原五个统计 key 保留并表示实际删除数：
provider_api_log、successful_jobs、failed_jobs、auth_sessions、service_heartbeat；预检均为 0。

| 输出 | 含义 |
|---|---|
| eligible_success_jobs | SUCCESS/PARTIAL/CANCELLED 严格超过 180 天的候选 |
| eligible_failed_jobs | FAILED 严格超过 365 天；恰好边界保留 |
| protected_referenced_jobs | 本批候选被来源引用的独立 Job 数，不按事实行重复计数 |
| deleted_success_jobs/deleted_failed_jobs | DELETE RETURNING 实际数量，回滚后归零 |
| missing_provenance_references | 非空 UUID 引用不存在 Job 的事实行数；不代表空 UUID 已就绪 |
| missing_reference_tables/samples | 仅 --details；表/字段、数量、日期范围和有界 UUID 样例 |
| candidate_scan_rows | 最多 max_candidate_rows+1 个年龄候选，仅 UUID/status，无 Job JSON |
| candidate_capacity_warning | 达配置比例时预警，默认 80%，不自动扩大预算 |
| skipped_locked_or_changed_jobs | 实执行因锁/并发变化未删除的其余候选，未尝试时 null |
| sql_count/duration_ms | 显式应用 SQL 数和调用耗时，不含驱动隐式事务命令 |
| blocked/error_code/error_count | 资源/结构/数据库异常整批回滚；未知统计 null，不伪报 0 |

默认上限：候选 10000、失证事实行 1000、样例 20、SQL 3 秒、锁等待 1 秒、总调用 15 秒。
数据库 anti-join + LIMIT，不把全部 calc UUID/JSON 载入 Python。超限整批拒绝（含运营删除），
只记录汇总告警，不改变独立 EOD 的状态/账本。长期保留来源会占用容量；不要删证据或自动抬高上限。

审批预检证据后才可修改 job_deletion_enabled=true、重启 Scheduler 加载，并人工首次实执行：

```powershell
python -m app.cli retention-run --confirm
```

缺确认或配置未开启则命令拒绝。daily_retention 仍为原 03:15 调度，不新增自动审批/实盘。
清理要求干净 Session、READ COMMITTED；按 finished_at/id 锁 Job、SKIP LOCKED，再用新语句
快照复核引用并删。这对旧 BACKTEST SET NULL FK 也必要，不能用旧快照清空新提交引用。
FK KEY SHARE 阻止锁后的引用提交；任何异常回滚 Job 与已经删除的日志/Session/心跳。

## 失证、错误与恢复

- Job 存在且合格：保留并继续原 M17.1 校验。保留本身不授予有效性。
- FAILED、范围/预热/版本错误、过早或上游后算：保留错误证据，仍失败关闭。
- Job 已丢：--details 定位表、最早/最晚日期、数量与样例。优先从验证过的同一一致性备份
  恢复完整来源集合，或经批准执行现有全范围补算；不按 UUID 拼凑互不一致的备份。
- RETENTION_*_BUDGET_EXCEEDED/RETRY_REQUIRED：未提交，排查规模、慢查询、锁/FK 并发及事务。
  原因消失后重新预检/审批，不退回无保护删除。
- REFERENCE_*_MISMATCH/PROTECTION_UNAVAILABLE：核对代码、0054、全部 FK/索引，保持删除关闭。

获准补算时，起点至少为失证最早日与最早相关 Dirty 日的较早者，终点 latest_raw_trade_date。
先核对 Raw/日历完整，等已有上游结束，再提交新范围任务；开始时间晚于修正及相关上游完成。
优先使用现有数据页“开始补算”。脚本使用已有鉴权 API，不另起修复队列；下例要求已经过
现有登录流程取得本人 WebRequestSession `$Session` 及已核对的 `$BaseUrl`，并替换批准的日期。
不要在命令行/文档写入登录密码或 Cookie。

```powershell
$Body = @{start='2025-01-02'; end='2026-10-14'; mode='manual'; evaluate_signals=$true} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/jobs/recalculate" -WebSession $Session -ContentType 'application/json' -Body $Body
```

响应 accepted 仅代表入队；已有 Worker 时不必重复启动，否则按 README 启动 Worker。
不要用 recalc-factors/recalc-market/recalc-states 的单层直算冒充有完整任务血缘的全范围修复。

核对真实新任务 SUCCESS、实际 calc_run_id、Calc Version/Config、范围/analysis_warmup_start、
calculated_at/started_at/finished_at 和上下游先后。重新观察，失效提案须重新人工审批。
不 INSERT 假 Job、不把旧 calc_run_id 指向别的任务、不改时间戳/删 Dirty/重新标 NAV。
封账漂移继续 REVIEW_REQUIRED，旧 Fill/Ledger/NAV、报告、Hash 不改。
直接单层计算没有真实任务参数时为空血缘，不再生成悬空 UUID，不因此取得 PAPER READY 资格。

## 留证与回退

保留审批、脱敏 inventory/check、实际/受保护/失证统计、错误码、CI SHA、迁移 HEAD、索引
定义和测量。CI 百万行 EXPLAIN/BUFFERS、计数、引用矩阵只有合成数据，不代替生产容量评估，
不证明原数值算法重跑。异常先设 job_deletion_enabled=false、重启新 Scheduler，其他日更可继续。
优先停删除/前滚修复；不得恢复旧无保护清理。模块故障默认不删 Job。
生产不建议降级 0054：会丢失 FK 保护。若获准回退结构，先停所有 Job 删除，保留全部任务、
事实、财务和备份；0053 有 PAPER 历史时拒绝降级仍有效，不能清表硬降。
摘要归档、版本继承、容量 UI、上游 CVE 升级仍为独立 P2 延期。
