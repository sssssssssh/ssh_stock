# M17.1.1 验收与发布记录

## 身份与关闭门禁

基线 d5704da0e67de26426fc8384a3d97c0a8d98879c，持续 master，不新建开发分支。
**最终关闭只以本文件所属最终 HEAD 的完整 Actions SUCCESS 为准。**
本文件不能静态写入包含自身内容的提交 SHA；精确 40 位 HEAD、该次 CI URL、PG 主版本与
current=heads 由同一 CI 的 Summary 和 `m17-1-1-retention-evidence/m17_1_1-release.json`
自动留证，最终交付消息再次给出实际 SHA/链接。缺回执或最终 CI 失败即未关闭。
回执只证明前面的阻塞步骤通过，整个 Actions 的最终 conclusion 仍为权威。
[master CI](https://github.com/sssssssssh/ssh_stock/actions/workflows/ci.yml?query=branch%3Amaster)。

| 批次 | 精确提交与 CI | 已取得证据 |
|---|---|---|
| A | 44578b739e7713e741d86c690da92112e9967013 / [38679638700](https://github.com/sssssssssh/ssh_stock/actions/runs/38679638700) | 1764 pytest、88%、0054、Ruff、Docker/Nginx、122 Vue、双视口全通过 |
| B | 4cbb86d266b890960edfa79b8efaaa13fe421eee / [38682664315](https://github.com/sssssssssh/ssh_stock/actions/runs/38682664315) | 1803 pytest、88%、0054、百万行、真实连续清理/结算及其余完整门禁通过 |
| C | 本提交对应的自动精确回执 | 补冻结观察来源引用及提交响应未知；必须以新增 0055 与完整最终 CI 验证 |

A/B 是阶段证据，不代替 C。A 的本机重复全量在相同 SHA 完整 CI 成功后停止，未记为本机通过。
本地后续定向 PG、单测、收集也不冒充最终全量结果。最终 CI 在隔离 PG17 真正执行全部测试。

## 设计与实际变更

选择 A：直接保留实际 Job。B 摘要归档延期，不能用未来摘要替代今天的原任务证明。
[引用/FK 决策](M17_1_1_retention_decisions.md) 与 [Runbook](M17_1_1_retention_runbook.md) 为操作依据。

- 12 类类型化引用：8 个 Derived calc_run_id、Dirty.source_job_id、Quality.job_id、
  PaperDayRun.job_id、PortfolioBacktestRun.job_id，全部版本/状态按引用事实保留。
- 终验补充第 13 类逻辑引用：DecisionObservation.data.candidates[].calc_run_id。提案/委托/
  持仓的候选副本来自这个不可变观察及其 RESTRICT 关系链，不把 Agent 的 BACKTEST Run UUID 当 Job。
  历史重算替换全部类型化来源后，旧观察仍须保留原计算任务。只保护 12 个字段并不完整。
- 0054 新增 10 个 nullable NOT VALID RESTRICT FK、11 个来源前导索引及 Job 年龄索引；
  旧缺证不补填。0055 追加观察 JSON containment GIN 索引和仅 INSERT 的 KEY SHARE 保护 Trigger。
  不改写已发布 0054 结构或 0050–0053，不修改旧 record_json/hash，不建立第二套 Job 管理/摘要表。
- Retention 两阶段父行锁与 READ COMMITTED 新快照复核；外键与观察 INSERT Trigger 共同防竞态。
  受保护 Job 保留不代表有效：失败、缺失、时间/版本/范围错误继续按原 M17.1 拒绝。
- JSON 只在数据库侧有界核对并通过 GIN containment 判断引用；Python 不取全部快照或 calc UUID。
  观察写入若在捕获后丢失父任务，映射已有 SOURCE_CALC_LINEAGE_UNAVAILABLE，不制造空来源。
- 默认关闭 Job 删除。预检/显式确认、资源预算、候选预警、失证诊断、汇总日志与实际 RETURNING 计数。
  提交前异常整笔回滚；COMMIT 响应未知单独标识并将删除统计设 null，不谎称回滚/零删除。
- 单层直算无真实任务时不再生成悬空随机 UUID，而是空血缘；不因此获得 PAPER READY。
  完整队列计算继续传入真实 Job。策略、费用、Decimal、T+1、Dirty 传播、只读来源门禁不放宽。

主要路径：services/retention.py、retention_lineage.py、retention_frozen.py、retention_indexes.py、
core/retention_config.py、models/job.py/market_data.py/paper.py、cli.py、decision/application.py 的
窄错误码映射，两个新增迁移及相关测试。Scheduler 调度/Job 架构、Raw 同步算法、策略引擎不重构。

## 36 类场景

R = test_m17_1_1_retention；P = retention_paper；C = retention_capacity；M = retention_migration；
F = retention_frozen（均在 tests/integration，省略共同前缀 test_m17_1_1_）；
W = test_m17_paper_capacity；U = tests/unit/test_m17_1_1_retention_contract/cli。

| ID | 验收 | 真实证据/断言 |
|---|---|---|
| P01 | SUCCESS 179 天 | R original_strict_age，保留 |
| P02 | 恰好 180 天 | 同上，严格 <，保留 |
| P03 | SUCCESS 181 天无引用 | 同上，删除/计数正确 |
| P04 | FAILED 364 天 | 同上，保留 |
| P05 | FAILED 366 天 | 同上，删除；365 边界也保留 |
| P06 | Factor 引用旧 Job | R each_persistent_reference；独立真实 FK/清理 |
| P07 | State | 同上，逐表参数 |
| P08 | TradeStatus | 同上 |
| P09 | Market/Sector | 同上，行业父表真实约束 |
| P10 | Opportunity | 同上，不靠其他表掩盖保护 |
| P11 | 全部其余 calc 来源 | Signal/Theme 及 U 自动发现；F 冻结候选在替换所有类型化来源后仍保留 |
| P12 | Dirty.source_job_id | R 真实终态来源保留 |
| P13 | 多表/多天/状态 | R multiple_tables_days，独立 Job 去重计 1 |
| P14 | 三类 PAPER 任务 | R paper_types、原 paper_jobs FK/调度回归，任意年限排除 |
| P15 | FAILED 被引用 | R 四状态保留；P retained_job_does_not_certify，仍拒绝业务 |
| P16 | RESOLVED 历史 + 合格计算 | P 400_day，保留 400 天来源后审批/EOD/费用、现金、持仓、NAV 守恒 |
| P17 | 历史 FAILED 不相交 | 同上参数；hash 不变并正常观察/推进 |
| P18 | OPEN 覆盖 D | P invalid_lineage open 与原 M17.1 矩阵，继续阻断且无金融增量 |
| P19 | Job 已失 | P/M 旧缺证，F 旧冻结缺证，诊断可见、拒绝使用，不补造 Job/改快照 |
| P20 | 范围/预热错误 | P scope/warmup 与既有 M17.1 血缘测试 |
| P21 | 失败/上游后算 | P failed/order；保留证据而非变成 SUCCESS |
| P22 | 不同 Job/版本 | P version/order、F 真实重算替换身份，原观察字节不变 |
| P23 | 重复清理 | R dry_run_default_disabled_and_idempotent；后次无重复删除数 |
| P24 | 新引用/删除竞争 | R typed FK 两方向及快照后提交；F 观察 KEY SHARE、R JSON 快照竞争；无孤儿/SET NULL |
| P25 | 双清理并发 | R two_cleaners；实际删除合计 1、不死锁 |
| P26 | 中途 DB 错误/提交响应丢失 | R 晚期心跳删除失败回滚已删 Job/日志；真实提交后丢响应报 UNKNOWN/null |
| P27 | 漏登记新字段 | U 临时 ORM、R 真 PG future_derived/schema/index 缺失，拒绝全部清理 |
| P28 | 非空结构往返 | P nonempty，13 类冻结 JSON::text UTF-8/hash 一致；M 原任务/Derived 事实不变 |
| P29 | 索引故障/重试 | M 真 CREATE INDEX CONCURRENTLY 除零生成 INVALID，拒绝/显式修复/重试；GIN 同样严验 |
| P30 | 1/30/250 真推进 | W 六组，脏历史组在最后一天先真实清理再结算，原 SQL/time/费用/T+1 断言不放宽 |
| P31 | 周末/假日/180 天 | 原 M17.1 calendar/gap 演练 + P 400 天 + W 250 日跨 TTL，TTL 仍按 UTC 自然时长 |
| P32 | M13–M16 回归 | 同 HEAD 完整 pytest、旧报告/合同/比较许可/回测/证据及浏览器，不降断言 |
| P33 | 容量/慢查询 | C 真百万行/EXPLAIN、候选超限、实际 pg_sleep 超时；P 预算失败后独立 EOD 仍成功 |
| P34 | 用户/私有元数据 | 原 PAPER API owner 404；M 不读取/记录 Job JSON；U CLI 默认只读/确认门禁，无新用户 API |
| P35 | 原阈值/普通运营任务 | R SUCCESS/PARTIAL/CANCELLED 180、FAILED 365 及运行/排队排除，原五个 key 保留 |
| P36 | 其他非 PAPER FK | R Portfolio SET NULL 身份不变，含快照竞争；原 M13/M17 同库隔离回归 |

## 规模与验证范围

原 P30 预算不变：<=400 应用 SQL/日、<15 秒/日；冻结汇总 <=14 SQL/<30 秒。
Retention 独立预算为最多 10000+1 候选、1000+1 失证引用、3 秒/SQL、15 秒/调用、<=60
应用 SQL 的百万行验收。SQL 计数不含数据库 Trigger 内部语句，完整耗时包含其成本。
真实百万行是 1000 日期×1000 证券的合成 Factor、10 个过期任务，其中 1 个被引用，
不是两只股票推断全市场，也不声称覆盖百万个 PAPER 观察或重跑原数值算法。

CI 附件含 EXPLAIN (ANALYZE, BUFFERS) 前后计划、实际清理/保护/失证统计、物理 FK/索引矩阵、
真实 1/30/250 日 JSONL、双视口截图及独立 npm 审计。最终性能以同 HEAD 生成的附件为准，
不复制旧批次耗时冒充新实测。观察规模过大或慢查询时保守停删，不自动扩容或影响日终状态。

本地临时 PG17.6 只监听 loopback，独立于 .env 业务连接；全部 DDL/删除/并发只有合成数据。
本地前期组合 59 项、非空迁移、两类并发及 6 组连续推进分别通过；最终 0055 补丁的
73 项 Retention + 25 项 M17 foundation 联测（98 passed）和完整 1347 单测通过。
最终提交必须继续由全量 CI 验收，不以阶段数量或收集数冒充最终通过。
本轮没有前端功能/依赖版本变更，最终仍要求 Node22 npm ci/122 覆盖率/build、1440/390 浏览器，
以及 Docker Compose config/build、Nginx -t、Ruff、迁移往返/current=heads 全部成功。

## DoD 与运维

以下各项以最终同 HEAD CI 回执及 conclusion 为关闭依据，任一缺失即未关闭：

1. 精确 HEAD 与 CI head_sha 一致；全部阻塞步骤成功。
2. 12 个物理引用与规范冻结候选来源已盘点，实际 FK/GIN/Trigger 可机器复核。
3. 无引用过期运营任务可删除；有引用任何状态保留。
4. 真实 PG 并发无悬空 UUID、无 BACKTEST SET NULL 或重复删除统计。
5. 失败/失证/范围/时间/版本约束不松绑；丢失不自动补造，冻结源失效不授予当前就绪。
6. 1/30/250 财务守恒，旧快照/报告/Hash 字节不重写。
7. 百万行预算和超限/超时实测；结构或模块故障不退回无保护清理。
8. 新库与非空库 0054/0055 往返/索引故障测试成功，0050–0053 不变。
9. 业务库未被查询演练/清理/回填/迁移/重算；上线另行审批。
10. Runbook 含先只读、显式确认、备份、停旧删除、在线索引、失证恢复和无损回退。

默认仍不开 Job 删除/自动审批/实盘；本次未启动或重启用户服务。上线须按 Runbook 升级到 0055，
先停旧版删除，预检留证并单独审批。旧冻结源丢失需可信一致备份，重算仅创建新的当前来源，
不得 retarget 原冻结引用。生产真实容量/行情/LLM/券商验证未执行，也不属于此次验收。
长期摘要归档、跨版本继承、全账户容量 UI 与前端上游 CVE 升级继续 P2 延期，未伪装完成。
