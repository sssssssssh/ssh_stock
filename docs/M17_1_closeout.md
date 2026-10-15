# M17.1 验收与关闭记录

## 关闭依据

P1 整改与隔离 PG17 连续演练已完成；P2 交付边界及延期见下文。
**正式关闭必须以本交付最终 HEAD 对应的完整 CI SUCCESS 为准**，不能拿前一提交绿灯替代。
[本分支 CI 入口](https://github.com/sssssssssh/ssh_stock/actions/workflows/ci.yml?query=branch%3Amaster)。
复核时先 `git rev-parse HEAD`，再检查该次 Actions 的 head_sha 与它完全一致、所有步骤通过。
本文件随最后一批提交，不自填无法预知的自身提交 SHA；最终交付消息提供实际 SHA/CI 链接。
任何最终 HEAD 的失败都意味着尚未关闭，不以本文列出测试矩阵冒充提前通过。

基线：a3ee768127ee2ba5f4d02b9943583e07c35ca38c，master。
无新 migration，0050–0053 原文不变，head 仍为 0053_m17_decision_paper_foundation。
未对用户业务库执行查询型演练、写入测试、迁移、清理、拉取或重算；未开启自动运行/审批/实盘。

## 分批记录

| 批次 | 提交/证据 | 结果 |
|---|---|---|
| T01/T02 主体 | e3252cf / [38669352128](https://github.com/sssssssssh/ssh_stock/actions/runs/38669352128) | 定向 PG17 和完整流水线成功 |
| 预热契约补充 | 30ed272 / [38669794915](https://github.com/sssssssssh/ssh_stock/actions/runs/38669794915) | 识别既有 analysis_warmup_start，完整流水线成功 |
| T03/T07 演练 | 0a7a97e / [38671738207](https://github.com/sssssssssh/ssh_stock/actions/runs/38671738207) | 1710 pytest、88%、Ruff、0053、容器、122 前端及双视口成功 |
| 最后交付 | 当前提交的 CI | 增加原 SQL 对照、历史预算/版本/共存断言，以及 P2 审计与默认 loopback；必须同 HEAD 全通过 |

未接受的候选：1f0b0cf 的长行格式候选已取消；c57e4c2 的新演练有 4 个夹具错误。
其 Raw 修改触发了正确的 SOURCE_DERIVED_STALE，尚未进入预期的 hash drift 分支；现按
“Raw 已修正、实际行与新计算任务已重建”的一致夹具测试漂移。没有放宽原错误码/资金断言。

## 实现边界

- dirty.py 增加闭区间及非法区间的有界只读查询；显式 None 判断，start/id 稳定排序。
- decision/source.py 保留原独立 REPEATABLE READ / READ ONLY、Raw 质量、版本、当前任务与 hash 门禁。
- decision/dependencies.py 只读验证历史实际因子/状态/交易资格/市场/行业及 D 机会的任务范围、
  版本、时间、缺行、日历完整性和上下游顺序。历史变化不是因为 end<D 就被忽略。
- 同一任务内校验阶段顺序；不同任务要求上游结束后消费者才开始。D 新结果不能藏住未修好的
  中间历史行；之后修复上游也不能让更早算完的 D 继续冒充就绪。范围包含既有显式预热。
- 不新增 Dirty 管理器、修复队列、账户迁移、自动交易或 Job 架构。Raw 同步和重算算法不变。
- 未改任何既有 financial record_json/hash、0053 或 M13–M16 证据合同。只新增测试事实/审计附件。
- 前端依赖版本/锁文件不变，只有 dev 默认监听从 0.0.0.0 收紧为 127.0.0.1。

源码契约与操作建议：[Dirty Range Contract](M17_1_dirty_range_contract.md)。
准确改动清单可用 `git diff --name-only a3ee768 HEAD` 查看；不包含 .env、凭据、生成产物或数据库。

## 36 项对照

C = tests/integration/test_m17_1_dirty_dependencies.py；
F = tests/integration/test_m17_1_paper_continuity.py；
U = tests/unit/test_m17_1_dirty_contract.py；
R = tests/integration/test_m17_paper_capacity.py。
01–24 都是最终同 HEAD CI 的阻塞 PG 验收；P2 设计不替代任何 P1 失败。

| # | 任务书场景 | 证据/交付 |
|---|---|---|
| 01 | OPEN [D,D] | C closed_intersections；金融行数不变 |
| 02 | PROCESSING 结束在 D | 同上，闭区间拒绝 |
| 03 | FAILED 开始在 D | 同上，拒绝且无财务写入 |
| 04 | 历史 FAILED 不相交 | C proven_non_intersections；原单边 SQL 同 PG 事实会误拒绝的对照 |
| 05 | 未来 OPEN 不相交 | C future case，完整来源就绪可通过 |
| 06 | end=D 边界 | C closed_intersections |
| 07 | start=D 边界 | C closed_intersections |
| 08 | 仅一条覆盖 D，确定性 | C multiple_ranges_choose_first_closed_intersection_deterministically |
| 09 | 多条历史/未来、不同数据集 | C multiple_nonintersections，输出 hash 完全相同 |
| 10 | RESOLVED 覆盖 D | C resolved case；R 带保留 RESOLVED 的逐日链路 |
| 11 | start>end/空值/非法状态 | C malformed_dirty；PG 拒绝 NULL，应用拒绝反向/未知；U 零 ID 仍阻断 |
| 12 | 历史修正已无实际未修影响 | C historical_repair，旧观察 hash/json 不变；F 历史 FAILED 正常完成 |
| 13 | 历史滚动输入尚失效 | C 新 D 不能隐藏历史坏行、later_upstream_repair；无错误财务增量 |
| 14 | 所有依赖恢复后才就绪 | C repair、预热范围、逐层缺失与旧版本/坏 Job；状态 FAILED 不被删除 |
| 15 | 当前来源/质量/Job 失败 | 既有 test_m17_decision_sources readiness cases 与 C historical lineage |
| 16 | 旧观察之后源修正 | F propose/approve source_drift，0 委托/财务增量，原 JSON/hash 保留 |
| 17 | 观察/草案/审批重放 | C same-request observation；F manual_chain_replay，ID/hash 保持 |
| 18 | 仅无关历史脏时 EOD | F historical_failed_range；Fill/Ledger/Position/NAV 数学对账 |
| 19 | D 相交脏时 EOD | F dirty_eod_rejects，已审批委托仍 pending，无 Fill/Ledger/NAV 增量 |
| 20 | 前日成功后来源修正 | F correction_after_success，REVIEW_REQUIRED，旧财务逐项不变 |
| 21 | 周末/节假日连续推进 | F pause_gap_recovery，FIRST→SECOND→AFTER_HOLIDAY，真实 fixture 日历而非自然日 |
| 22 | 缺日、重试、手动追赶 | 同上，先拒绝跳日，再逐日恢复，手续费只计一次 |
| 23 | 并发/取消/丢响应 | F worker_recovery 四种故障，真实提交/回滚/显式重试，无双扣或锁死 |
| 24 | A/B 隔离 | F owner_boundaries；既有 paper_queries 全子路径 API 404 回归 |
| 25 | 策略/机会算法版本改变 | F algo/strategy/opportunity_version 三种合同漂移；版本策略文档 |
| 26 | 账户启停/关闭 | F pause/resume；既有 paper_daily pause_resume_and_close 保留历史 |
| 27 | 1/30/250 真推进、读成本 | R 两组独立逐日执行及三组冻结汇总，原 SQL/time 预算不放宽 |
| 28 | 各类长期行数增长 | 现有预算拒绝/分页已测；全账户聚合、近 30 日监控 DEFERRED，设计已交付 |
| 29 | 预警线 | 现有超限不加载 JSON/不改账测试；百分比预警 UI/API DEFERRED，未伪装实现 |
| 30 | npm dev/prod 审计 | Node 22 npm ci 后双报告；9 个审计工具测试；CI 附带锁文件摘要的原始报告 |
| 31 | 升级后双视口 | 依赖升级 DEFERRED；当前版本 1440/390 输入/图表/审批/XSS 回归通过，不表示 CVE 修复 |
| 32 | M13–M16.6 全回归 | 完整 pytest、旧报告/合同/比较许可/研究/策略及原浏览器脚本 |
| 33 | 0053/迁移 | 无新迁移；CI 空库往返、current=heads；既有非空 PAPER 拒绝降级测试 |
| 34 | 默认关闭、Agent 只读 | 既有 M17 foundation/job/API/Registry 测试，未新增工具/模式 |
| 35 | 截断、超预算、异常 | U 与 C 真实 101 Job 预算先拒绝；R 行/字节预算；不得加载历史全 JSON 或造空结果 |
| 36 | BACKTEST/PAPER 同库 | F manual_chain 同时保留真实 Legacy Run/NAV，PAPER 结算前后旧全部字段一致 |

## 实际验证与性能

环境：本地只跑单元测试、收集、Ruff、Node 22 前端及 Edge；全部 PG 写入只在 GitHub
disposable PostgreSQL 17 和随机测试库。旧与新增案例均不访问用户 stock_db。
本地 U 21 项及完整单元 1320 项通过（两条既有弃用警告）；最终数量以同 HEAD CI 为准。
前端 Node 22 npm ci、122 项覆盖率（82.22%）、构建、Edge 1440/390 通过；审计工具 9 项通过。
构建仍有既有 >700 kB chunk 提示，未为隐藏提示而抬高阈值。

阶段 0a7a97e 的真实执行：
`python -m pytest tests/integration/test_m17_decision_sources.py -q` 16 passed；
paper_daily 16 passed；paper_jobs 21 passed；新增 continuity 21 passed；
dirty_dependencies 26 passed；全量 `pytest --cov=backend/app --cov-report=term-missing --cov-fail-under=70`
1710 passed、192 warnings、88%；Ruff；Alembic upgrade/current/heads；Compose config/build、
Nginx -t；npm ci/test:coverage/build；M16.6 和 M17 Chromium 双视口全部成功。
最后一批另加原 SQL/真实历史容量和版本用例，并加强同库共存断言；本地完整收集 1716 项，
必须在本提交完整流水线再次通过，收集数量不冒充通过数量。

[阶段实测 JSONL](https://github.com/sssssssssh/ssh_stock/actions/runs/38671738207/artifacts/11944866544)：

| 类型 | 交易日 | 总 SQL | 单日最大 SQL | 总秒数 | 单日最大秒数 |
|---|---|---|---|---|---|
| 正常真实推进 | 1 | 207 | 207 | 0.286 | 0.286 |
| 正常真实推进 | 30 | 6268 | 209 | 7.249 | 0.296 |
| 正常真实推进 | 250 | 52248 | 209 | 61.318 | 0.308 |
| 保留已修复脏记录 | 1 | 233 | 233 | 0.426 | 0.426 |
| 保留已修复脏记录 | 30 | 7048 | 235 | 9.900 | 0.431 |
| 保留已修复脏记录 | 250 | 58748 | 235 | 131.684 | 1.329 |

冻结汇总 1/30/250 日均 12 SQL，0.054/0.092/0.608 秒。原预算 <=400 SQL/日、<15 秒/日，
汇总 <=14 SQL/<30 秒，均未修改。历史依赖验证增加固定 SQL，但日期/行增长仍增加 DB 聚合成本；
不声称无计算增长或可代表全市场吞吐。样本为两个合成证券、一次人工买入和持仓延续，每天检查
Job/三个阶段成功、现金/数量/费用/NAV 守恒、T+1 及冻结 Fill/hash 不变。排除准备/断言 SQL。

最终 CI 保留同名容量 JSONL、浏览器截图及 m17-1-dependency-audit 附件，均可对应其 head_sha。
最终 HEAD CI 门禁包含全部上述命令、补充测试和审计脚本，不以源码收集代替实际运行。

## P2 交付与延期

- [账户版本策略](M17_1_account_version_policy.md)：现行版本匹配、旧版本隔离方案与停止/新建规则。
  旧版本多代路由、账户继承、持仓/资金迁移 DEFERRED；不改冻结合同，也不承诺全部模块版本已覆盖。
- [容量盘点与设计](M17_1_capacity_design.md)：明确七类当前预算及未计的账本/审计/尝试/收据等。
  聚合 API、百分比/30 日增长、预警 UI、全账户限流和来源 Job 长期保留改造 DEFERRED。
- [依赖审计及升级方案](M17_1_dependency_audit.md)：实际总计 11（4 Critical/3 High/4 Moderate），
  omit-dev 4（2 High/2 Moderate）。库升级 DEFERRED；仅收紧开发监听，并保留可复现风险附件。
  库级漏洞仍开放，richText/转义/XSS 探针只属于输入链缓解，不是漏洞关闭证据。

## 运维与未执行项

没有生产部署、真实行情/LLM/券商测试、资金迁移或非空数据库 downgrade；没有改用户参数。
完整 Raw/日历与当前衍生结果齐备时，不需要因为这个补丁全部重新拉取。
遇 SOURCE_DIRTY_RANGE 使用原补算修复；SOURCE_DERIVED_STALE 按最早相关日期到最新 Raw
完整补算并核对 Job。缺日历/血缘先补齐证明；排队早于上游完成的旧任务不足以证明读取时点，
应等上游结束后提交新任务，不手改数据库时间。丢失来源计算 Job 的历史证据不能静默放行。
非法区间人工排查，不删除记录/账本。源 hash 漂移继续复核旧账，不重标 NAV。

本轮无新结构升级。部署前备份并核对现有 0053，等待活跃业务任务安全结束后，统一重启 API、
Worker、Scheduler 以加载相同代码；开发前端重新启动后默认只监听 loopback。
保持自动开关默认关闭；回滚优先停用 PAPER 和暂停账户，保留所有财务和证据，不清表或强降级。
