# M17.1.1 引用与并发决策

基线 d5704da；继续 master，先做 T00，再实现方案 A。方案 B 的不可变任务摘要归档延期：
当前没有足以替代原 Job 时间、范围、状态和实际计算行的归档合同，不得先删后补。

## 修改前的真实 PG 调查

2026-10-15，独立临时 PostgreSQL 17.6，仅 loopback；由全部正式迁移构建至 0053。
未使用业务库、未读取业务数据。调查在 REPEATABLE READ / READ ONLY 内执行。
代码扫描整个 Base.metadata 的 calc_run_id/source_job_id/job_id 及指向 job_run.id 的 FK；
物理盘点使用 pg_constraint、pg_indexes/pg_index、pg_attribute，不能凭 ORM 猜测。
12 类引用初始非空引用数和失证数均为 0（空隔离库，不是生产规模声明）。

| 表 | 字段 | 0053 FK / 删除动作 | 原可用前导索引 | 保留原因 |
|---|---|---|---|---|
| stock_factor_daily | calc_run_id | 无 | 无 | 滚动输入来源 |
| market_daily | calc_run_id | 无 | 无 | 市场计算来源 |
| sector_factor_daily | calc_run_id | 无 | 无 | 行业计算来源 |
| stock_trade_status_daily | calc_run_id | 无 | 无 | 交易资格来源 |
| stock_state_daily | calc_run_id | 无 | 无 | 状态递推来源 |
| stock_opportunity_daily | calc_run_id | 无 | 无 | 机会来源 |
| strategy_signal | calc_run_id | 无 | 无 | 持久化策略信号来源 |
| theme_factor_daily | calc_run_id | 无 | 无 | 持久化题材来源（无 ThemeOpportunityDaily 表） |
| data_dirty_range | source_job_id | 无 | 无 | 含终态的 Raw 修正证据 |
| data_quality_daily | job_id | 无 | 无 | Raw/Derived 质量检查来源 |
| paper_day_run | job_id | RESTRICT | 无 | 不可变金融阶段的真实任务 |
| portfolio_backtest_run | job_id | SET NULL | UNIQUE(job_id) | 防止清理改写旧回测身份 |
| decision_observation | record_json.data.candidates[].calc_run_id | 无（JSON） | 无 | 计算行替换后仍有冻结来源引用 |

前 12 行是实施前只读物理盘点，第 13 行在终验追踪候选副本时补充；不能把物理字段盘点冒充
全部语义引用。0055 单独追加，避免重写 A/B 已提交的 0054 结构；不新增平行归档或重建旧证据。
研究/实验 FK 目标是 PortfolioBacktestRun 等独立 Artifact，不是 JobRun；保留其 Job 由
portfolio_backtest_run.job_id 覆盖。Agent 冻结投影中的 calc_run_id 来自 research adapter 的
PortfolioBacktestRun.id，不应误认成 Job UUID。PAPER 派发审计的任务由三个 PAPER 类型永久排除；
候选快照却引用普通计算 Job，必须另行保护，不能因不是物理 FK 就忽略。
其他提案/委托/持仓的候选副本来自不可变观察的 RESTRICT 关系链；不扫描任意 JSON 中的 UUID。
本轮不修改、解析重写或重新哈希任何旧 JSON，只在 DB 端有界验证并投影小标量诊断。

可复核 SQL 的完整版本见 retention_lineage.py::SCHEMA_REFERENCES；引用缺失 SQL 模式为：

```sql
SELECT f.calc_run_id, f.trade_date
FROM stock_factor_daily f
WHERE f.calc_run_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM job_run j WHERE j.id = f.calc_run_id)
LIMIT 1001;
```

实际对所有 12 项执行。T00 用真实 181 天 Job + Factor 执行原版 run_retention，结果为
old_deleted_jobs=1、job_missing=true、derived_reference_remaining=1；外层事务最终回滚。
修复后相同年龄/真实引用必须保留；无引用同龄任务仍删除。集成测试保留该正反向契约。

## 选择 A 与数据库互斥

0054 对 10 类无 FK 的 nullable 字段增加 NOT VALID / RESTRICT FK，不扫描或修复遗留失证。
新引用/变更引用必须指向真实 Job；原来的 orphan 保持可诊断且业务校验仍拒绝。
补齐 11 个前导引用索引及 Job(status, finished_at, id) 年龄索引，保留原 Portfolio UNIQUE。
0050–0053 不改写。线上大表必须按 Runbook 预建同名 CONCURRENTLY 索引后再迁移；
新库事务内建索引。迁移有锁等待/语句超时，已有无效或不匹配索引拒绝而非跳过。

清理在单事务中按 finished_at/id 确定顺序锁可删 Job，FOR UPDATE SKIP LOCKED；
数据库侧 12 个 EXISTS 排除仍被引用任务，不加载全量 calc UUID 或 JSON。
FK 的父行 KEY SHARE 与删除锁互斥：写入先赢则清理跳过或重新检查失败回滚；
删除先赢则新引用等待后收到 23503，不能提交孤儿。NOT EXISTS 自身不承担跨事务安全保证。
任务正常非键进度更新不与 KEY SHARE 冲突；PAPER 任务永不进入年龄候选，不引入市场表锁。
并发清理返回真正 DELETE RETURNING 的数量，不能拿预估候选数冒充删除数。
对已有 SET NULL 外键还需处理快照竞争：先锁父行，再用新的 READ COMMITTED 语句复核引用。
新引用在锁查询快照后、实际取锁前提交时，删除语句必须看见并保留；不是依赖同一条 CTE 的
NOT EXISTS。真实 PG 测试用仅测试的 advisory barrier 定位该时序，验证 Backtest.job_id 不变。
实现不引入全局 advisory 锁；其他隔离级别拒绝清理。
观察候选使用专用 GIN containment 查询，INSERT Trigger 对真实父 Job 持有 KEY SHARE；
父任务在 capture 后消失则写入失败并映射原 SOURCE_CALC_LINEAGE_UNAVAILABLE。
保留旧快照引用不授予业务合法性。缺失/非法旧引用保留原文，只读告警或保守停删，不补 Job。

直接计算服务没有真实任务参数时，过去会生成无 Job 的随机 UUID。现在保留 nullable 的
未知来源（calc_run_id=None），不新增伪任务或伪造 SUCCESS；Trend 两个输出仍共用调用身份。
已有完整入队 daily/recalculate/catchup 继续传入真实 Job。金融可信来源仍要求非空且完整验证，
直接单层计算不因此取得 PAPER 来源资格。没有更改策略公式/版本、旧行或任何冻结 Hash。

## A 批验证状态

本地隔离 PG17：35 项真实引用/边界/并发/回滚用例通过；定向单测 18 项通过。
完整回归、百万行预算、Runbook 与最终同 HEAD CI 是后续阻塞交付，不能据此提前封版。
A 批 44578b7 的 CI 38679638700 已完整成功；B 批进一步加入快照竞争、百万行 EXPLAIN、
运维预检和恢复入口，必须由其自身及最终提交 CI 验证。
