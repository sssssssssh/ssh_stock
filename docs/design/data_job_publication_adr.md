# ADR：数据任务候选隔离与原子发布

状态：W01 盘点与候选方案；旧单表直写 CLI 的产品兼容决策待用户确认。
W02 尚未开始，不把本 ADR 当作实现或验收完成。
基线：master@ff3f221b4fcade5f9b8477d7df1acc66498abaf4。业务公式、原表自然键、
版本/hash、PIT、金融 Artifact 与人工审批不变。没有业务库操作授权。

## 1. 实际写入与血缘清单

日期 d、股票 c、算法 a、行业 s、题材 t；所有名称均为现有实际表。

| 表 | 现有 PK / 自然唯一键 | 身份 | 写入与提交 | 消费/历史引用 | 规模模型（不是生产测量） |
|---|---|---|---|---|---|
| stock_trade_status_daily | d,c | calc_version/config_hash/calc_run_id/calculated_at | TradeStatusService.recalc；replace_slice；每次调用 commit | Factor、执行/会计、Research、PAPER 来源校验；Job RESTRICT | 股票数×交易日，250 日约 125 万行/5000 股票 |
| stock_factor_daily | d,c | 同上 | FactorService.recalc；replace_slice；按月 commit | Market/Sector/Theme/Trend/Opportunity、股票/池/看板、Research、组合来源 | 同上；约 60 列，不能每任务复制全部历史 |
| market_daily | d | 同上 | MarketService.recalc；replace_slice；每次 commit | 看板、Trend/Opportunity、PAPER/组合校验 | 每日 1 行 |
| sector_factor_daily | d,s | 同上 | SectorService.recalc；replace_slice；每次 commit | 行业/股票/机会池、Trend/Opportunity、组合校验 | 行业数×交易日 |
| theme_factor_daily | d,t | 上述字段 + source_strategy_config_hash | ThemeFactorService.recalc；replace_slice；按月 commit | 题材、Opportunity、Research 题材评价 | 题材数×交易日；必须容量测量 |
| stock_state_daily | d,c,a | 上述字段 + algo_version | TrendService.recalc；replace_slice，与信号同次 commit | 股票历史/趋势池、Opportunity、Research、组合 | 每算法约股票数×交易日 |
| stock_opportunity_daily | d,c,a | 上述字段 + source_strategy_config_hash | OpportunityService.recalc；replace_slice；按月 commit | 左右侧/趋势池、看板、Research、Backtest/PAPER、Agent | 每算法至多股票数×交易日 |
| strategy_signal | PK id；UQ d,c,signal_type,a | calc_version/config_hash/calc_run_id/calculated_at | TrendService.recalc；replace_slice，与状态同次 commit | 信号统计/股票详情/SignalEvaluation；被 signal_forward_eval 引用 | 股票数×日期×信号类别的稀疏子集 |
| signal_forward_eval | PK id；UQ signal_id,eval_version,entry_basis | algo_version/eval_version/entry_basis | SignalEvaluationService.evaluate；upsert 后 commit | signals API/历史信号评价；signal_id ON DELETE CASCADE | 信号数×评价版本×入场口径 |
| data_quality_daily | PK id；UQ d,dataset | job_id/checked_at，issue_codes | quality 服务经 upsert；原 Raw ERROR 先提交；cross-table 按范围提交 | system 日历/质量、来源门禁；Job RESTRICT | 日期×数据集；失败诊断不能被成功旧行掩盖 |
| data_dirty_range | PK id | source_job_id/status/processing_started_at | 既有 Dirty 状态服务独立 commit | 补算、Research/PAPER 来源依赖；Job RESTRICT | 按 Raw 变更区间，不是派生发布目标 |

Research 三表不在数据任务内计算：opportunity_forward_eval 的自然键为
(d,c,a,strategy_config_hash,opportunity_calc_version,opportunity_config_hash,
research_version,research_config_hash,eval_version,entry_basis)；theme_forward_eval
对应题材/题材版本键；research_transition_eval 使用
(event_trade_date,c,event_key,a,trend_calc_version,opportunity_calc_version,
strategy_config_hash,opportunity_config_hash,research_version,research_config_hash)。
它们使用 replace_slice_rows_with_stats、由独立 Research Job 分批提交；数据与 Research
运行互斥继续保留。既有冻结研究/合同/报告/金融账本不回填、不重算、不重解释。

Raw、目录/成员事实不放进派生发布：stock_daily/adj/basic/index/ST/suspend/limit，
ThemeDaily/Moneyflow/Limit、StockBasic/Sector/Member/ThemeMemberSnapshot/Interval 等仍由
Ingestion 的原事务保存 Provider 事实。发布层不伪装 Raw 可回滚，也不删除这些记录。

`replace_slice_rows` 先查 scope 的键，删除 stale_keys，再 upsert surviving/new keys；
仅加 SUCCESS 过滤无法保护已经被覆盖的 A。信号原 id 与幸存行必须保留，否则评价 FK/引用变化。

### 1.1 已复现与待确认的入口边界

隔离 PostgreSQL 17 的 `test_data_publication.py` 红灯证据已复现：A 的同键因子值 10，
B 经真实 Worker 派发并使用原 replace_slice_rows 提交检查点后，独立读连接看到 20/B Job。
随后失败收尾也不能恢复 A。该测试是待修复回归，不表示当前分支已通过完整门禁。

`backend/app/cli.py` 的 recalc-factors、recalc-market、recalc-sectors、recalc-states
直接调用相应 Service 并 commit，没有 Job/执行 token/完整发布门禁；evaluate-signals 亦直接
写 signal_forward_eval。它们不是 `_queue_cli_job` 路径。
原样保留会留下绕过统一发布的正常入口；自动改为完整重算会扩大原单表命令的计算范围，
而停用直写会改变现有使用方式。本任务未明确授权这项兼容取舍，必须先由用户确认。
建议保留命令名称与明确迁移提示，但拒绝直接写库，转由完整补算队列执行；不静默扩大请求范围。

## 2. 方案比较与决策

| 维度 | A：旁路 staging + 原子 publish（选择） | B：原表代际并存 + published pointer（不选） |
|---|---|---|
| 原表键/既有 FK | 不改自然键；候选额外带 root Job 键 | 至少八表改 PK/UQ/FK，信号/评价关系随代际迁移 |
| 对外读取 | 原 public 表就是集中 published slice；原索引/JOIN/分页沿用 | 所有 ORM、JOIN、latest、窗口/来源读取必须解析指针 |
| 内部计算 | 候选 overlay：本次新行/删除掩码 + 未改动已发布历史 | 所有阶段显式携带 generation，需迁移所有历史读取 |
| checkpoint | 仅写正式迁移创建的候选表，分块 commit 不暴露 | 写新代际，分块 commit 不暴露 |
| 发布 | 一次有界事务把候选 patch 应用到 public，并写发布审计和 SUCCESS | 一次指针事务更小，但每次读取代价/迁移面较大 |
| 磁盘 | 候选 patch + 必要旧行审计，不克隆整库/全年事务 | 所有历史代际常驻，指针/索引与 GC 设计范围更大 |
| 锁/WAL | 发布 patch 期间有行锁与 WAL，必须预算/测量/超限拒绝 | 发布短，但建代际索引与旧数据迁移影响大表 |
| 旧 NULL 来源 | public 原样保留；不编造历史 Job | 需要明确 legacy generation，否则容易遗漏旧行 |
| 故障 | 发布前 A 完整；取消/失败留候选；发布提交未知仍保守占槽 | 候选可留存，但必须证明指针与源身份全链路兼容 |

B 不能在不改变八表自然键/下游引用的条件下落地：StockFactorDaily(d,c) 不能保存相同键的
A/B，SignalForwardEval 还引用稳定的 signal_id。这是结构约束，而不是过滤器可修补的问题。
A 的正确性先以真实 PG17 A/B 同键、取消/失败、跨表并发快照、JOIN/分页测试证明；不把纸面设计
视为已完成验证。若实现测试不能满足下述条件，停止发布，不以切段或大事务绕过。

## 3. A 的具体存储与路由

0058（或下一合法修订）增量创建正式候选存储、publication ledger、来源 Job 引用和删除掩码。
不修改 0057、原表键或历史行。候选按根 Job 隔离；父 catchup 的同步子任务共用根候选，
子计算身份仍为子 job_id，不能在子 SUCCESS 时提前对外发布。

候选写入复用 upsert/replace_slice 仓储，不复制任何计算引擎。候选写只到 schema-qualified
staging 表；删除只形成本次键掩码，不能向 public 删除。信号及评价幸存 id 保持原值，新 id
使用现有序列分配（失败可留序列间隙，不改已有 id）。Raw 质量按原证据路径；派生质量候选与
本次候选绑定，不能覆盖旧 A 的已发布 PASS，也不能拿 A 的质量替 B 背书。

计算 Session 固定一条专用连接，用会话私有临时只读 VIEW 对同名派生表提供 overlay：
候选自身行 UNION ALL 未被本次行/删除掩码取代的 public 行。只读 VIEW 不承担持久化结构，
所有候选存储来自正式 Alembic；无需每 Job 建持久表、RLS/superuser 假设或复制全部历史。
事务 commit 保留候选视图；连接归池前清除视图，清除失败必须 invalidate 连接，不得污染普通读者。
连接断开不恢复/重放本次执行；新连接上不得静默失去候选 overlay 继续写 public。

普通 API/Agent/Research/Backtest/PAPER 连接从不安装候选 overlay，只读取 public published slice。
统一读会话边界对跨语句请求采用一致 MVCC 快照；同一 SQL JOIN 天然只看一个事务快照。
任务内部来源过滤知道当前候选身份，不以外部 SUCCESS 条件屏蔽当前计算；候选质量额外核查
本次表/范围覆盖、run/hash/version 与质量凭据，不能因为 overlay 回退 A 而误验成功。

## 4. 发布粒度与状态

粒度为根任务已验证的完整计算范围，跨全部派生表一起发布；不新增逐月对外发布产品口径。
暖启动范围沿用已有算法，不因本任务缩小或改变。在途计算有独立 PREPARING/VALIDATED/
PUBLISHED/ABORTED 或等价 publication 状态，不能用处理行数宣称已发布。

发布前再次检查：根 RUNNING、原 worker/token、未取消、冻结配置未变、所有子任务已正确结束、
候选完整性/范围/质量/身份合格。终态竞争遵循原锁序及 CAS。单次发布事务保存
publish_started_at/published_at/identity、旧行审计和来源引用，应用所有 patch，并把根 Job
置 SUCCESS；任何中间故障整个发布回滚，其他连接继续看 A。提交响应丢失不另写 FAILED 或重放。

发布不是新的全年计算大事务：计算仍分块提交候选；只有已计算 patch 的合并是发布事务。
发布行数/时间/锁预算需显式配置和隔离测量，超限明确失败保留 A，不能偷偷分段发布。
失败候选/旧行审计默认保留；本期不实现自动删除、GC、DROP 历史或生产回收脚本。
新增 Job FK/来源引用同步纳入 retention manifest，保留不等于来源验证通过。

## 5. 读取面矩阵与兼容

| 读取面 | 已审阅入口 | 保护方式 |
|---|---|---|
| 股票/历史/池 | api/v1/stocks.py，analysis_filters | 全部主表、关联、latest、count 都落到稳定 public slice |
| 机会与详情 | api/v1/opportunities.py，OpportunityCandidateProvider | 同上；保留原版本/hash、排行/分页条件 |
| 看板/信号 | api/v1/dashboard.py，api/v1/research.py 的 /signals/stats、/signals/buckets | 信号/评价同时发布；原 signal_id 不换代 |
| 行业/题材 | api/v1/sectors.py、themes.py | 行业/题材因素和机会 JOIN 同一 MVCC 快照 |
| 覆盖/就绪 | api/v1/system.py、quality/* | 外部只计 public；内部校验当前候选，不复用 A 的 PASS |
| Research | research/opportunity_eval.py、theme_eval.py、transition_eval.py | 互斥与完整身份保持；当前选择只见发布结果 |
| Portfolio/执行/会计 | portfolio/candidates.py、source_integrity.py、accounting_market_data.py；execution/market_data.py | public 原索引/身份过滤；来源捕获跨语句一致 |
| PAPER | decision/source.py | 已有独立 REPEATABLE READ/READ ONLY；冻结旧快照不改 |
| Agent | core/agent_db.py 与九个只读工具 | 只读快照 public，不授予候选、写或任意 SQL 工具 |
| 冻结历史 | M14–M17 Artifact、报告/合同/观察 | 原字节/Hash 不变，不把历史快照重定位到新结果 |

旧 ff3f221 之前已经覆盖且无历史副本的结果不能凭空恢复；诊断应明示 legacy 证据缺口，
不伪造 A 或用当前数据重写旧 Artifact。新机制保证启用后 A/B 的隔离与可审计发布。

## 6. 后续门禁

W02/W03 必须真实证明 A 在 B 每个 checkpoint/取消/失败后仍可查；B 全表一致验收后原子发布；
缺 A 明确不可用；B 不合格不能依靠 A 通过质量；latest/JOIN/count/分页和并发请求快照一致；
候选连接失败不泄漏/自动接管。随后完成 W04 只读诊断/人工审批手册、W05 调度补偿、
W06 小范围状态展示，最后同 SHA 执行 S01–S22、PG17 非空迁移、双 Worker、全量测试/构建。
