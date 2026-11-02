# ssh_stock 当前状态与唯一执行指针

状态版本：2026-11-02 治理基准 v1 收口草案，REVIEW_PENDING（已交付，待负责人最终验收）。
核查日期使用 Asia/Shanghai；本轮 master/CI 核查时间为 **2026-11-02 16:04 +08:00**。
这是带时间的事实快照，CI 后续可能变化；新会话必须重新核验，不能当实时监控。

## 1. 当前主线与下一步

- 当前唯一业务主线：股票历史读取 → Python 转换/计算 → 候选查询/写入 → 质量核验 → 原子发布的性能诊断及可靠性；问题尚未收口。
- 当前唯一执行任务：**GOV-20261102-001，长期项目治理基准建设**。
- 当前状态：**已交付、待负责人最终验收（REVIEW_PENDING）**，不得自行标 DONE；五份治理文件已按负责人指令提交推送，本轮入口与状态收口修改仍待审阅，禁止本轮提交、推送或业务开发。
- 下一项仅为：诊断整改方案，待负责人安排/审阅；不得据此开始实施、实验或生产操作。
- **BIZ-PERF-03-A 保持 PARTIAL**；部分实现已在 e610a92，开销与完整回归未收口。诊断整改方案为 PENDING_APPROVAL，**本轮未授权开始 BIZ-PERF-03-A-R1**。
- 未获批准不得自行进入热点优化、扩大功能或重新规划另一条开发主线。

## 2. 仓库基线

| 项目 | 核查事实 | 来源 |
| --- | --- | --- |
| 本地分支 | master | git status --short --branch |
| HEAD / origin/master / GitHub master | 31bf700c77b86fcb9be59787a0bde76d6f7d85bd | git rev-parse、git ls-remote --heads origin、GitHub 同 SHA 工作流 |
| 最近提交 | docs(governance): establish project charter roadmap status and task workflow | git show HEAD |
| 本轮开始工作区 | 干净，含未跟踪文件检查 | git status |
| 远端 master | refs/heads/master 指向上述 SHA；远端仅 master 的完整分支清单为上一轮核查事实，本轮仅复核 master | git ls-remote --heads origin master |
| 历史集成 | PR #1 合并提交 3940d9b；其后 BIZ-PERF-02 候选、撤回和 R1 均在 master 历史 | git log |
| 治理文件交付 | PROJECT_CHARTER、PROJECT_ROADMAP、PROJECT_STATUS、DECISION_LOG、docs/tasks/README 五份文件已在 31bf700 提交推送，441 行新增 | git show --stat HEAD、此前推送成功及本轮远端 master 复核 |
| 本轮改动 | 仅 AGENTS.md、PROJECT_STATUS.md、docs/tasks/README.md 的治理收口；尚未提交 | 交付时再次核验 diff/status |

最新 master 为 **31bf700**，其中业务实现最近一次变更为 **e610a92**，31bf700 仅交付五份
治理文档。本轮未提交的收口补丁不属于上述提交。以后分别记录代码基线、治理交付 SHA 和
核查时间，避免通过自写“当前 SHA”冒充已提交或为自引用 SHA 无限追加提交。

## 3. 实际代码能力与证据层级

本轮静态审阅入口和调用，不运行应用、不连接数据库，也不重新执行功能验收。

| 能力 | 已核查代码路径 | 本轮能确认 / 不能确认 |
| --- | --- | --- |
| 数据接入与管理 | backend/app/providers/base.py、jobs、services/quality、api/v1/system.py | 有 Provider 协议、采集/质量与管理入口；当前数据完整性 UNKNOWN |
| 因子与重算 | services/recalculation.py、factors/service.py、factors/engine.py | 有预热、月分块、因子计算与持久化；全市场运行耗时/覆盖 UNKNOWN |
| 市场、板块、趋势与股票池 | services/market、sector、theme、trend、opportunity；api/v1/router.py | 路由接入且有 Service 调用；实际最新行情/选股结果 UNKNOWN |
| 历史研究/回测/策略候选 | research/signal_eval.py、portfolio/backtest_application.py、portfolio/policy.py | 有历史评价、组合执行/会计及回测编排；策略收益/有效性 PENDING |
| 绩效/风险、实验与 OOS | performance/application.py、experiment、experiment_evaluation、walk_forward/application.py | 有独立模型/服务/路由；不因模块存在断言研究结论有效 |
| 模拟持仓 | paper/job_application.py、paper/execution.py、api/v1/paper.py | 有启用门禁、owner 与执行/会计调用；账户/持仓实况 UNKNOWN |
| 智能体 | agent/registry.py、chat、llm/factory.py、archive/contracts | 九个只读工具及可选 LLM 适配存在；是否配置/启用、外部模型连通 UNKNOWN |
| 交互与部署 | frontend/src、main.py、docker-compose.yml | Vue/FastAPI、migration/backend/worker/scheduler/frontend 服务定义存在；实际部署/运行 UNKNOWN |
| 任务与发布 | services/job_worker.py、data_publication.py、repositories/job_run.py | 有 owner/token、候选及根提交路径；当前任务队列/Worker 状态 UNKNOWN |
| 可选诊断 | performance_diagnostics.py、performance_sql_diagnostics.py、scripts/performance_diagnostics_report.py | 默认关闭的部分实现已入 e610a92；诊断验收未完成 |

## 4. 数据库与数据状态

| 项目 | 当前结论 |
| --- | --- |
| 项目数据库基线 | PostgreSQL 17，来自项目规则和代码约定，不代表实际业务服务器版本已探测 |
| 仓库迁移末端 | 文件 20261018_0058_data_publication.py 定义 revision=0058_data_publication、down_revision=0057_data_queue；本轮未运行 Alembic |
| 业务库实际 Alembic current / 版本 / 大小 / 位置 | UNKNOWN |
| Raw 覆盖区间、行数、重复/缺失、源质量 | UNKNOWN |
| Derived、候选、已发布身份与完成日期 | UNKNOWN |
| Research、回测、模拟持仓的实际数据 | UNKNOWN |
| 当前 RUNNING/卡住任务、服务、Scheduler | UNKNOWN |
| 实际 .env/开关/令牌/LLM 连通 | UNKNOWN；本轮不读取凭据或启动应用验证 |

上一轮报告记录本机隔离 PG17 测试曾运行并停止，仅为历史测试环境事实；不能据此推断
当前云端业务库状态。本轮无业务库连接、DDL/DML、迁移、清理、重算或生产部署操作。

## 5. 当前 GitHub CI（仅工程证据）

本轮取样均为 push、attempt 1、精确 SHA **31bf700c77b86fcb9be59787a0bde76d6f7d85bd**：

| 工作流 | 16:04 核查状态 |
| --- | --- |
| [主 CI 41409940664](https://github.com/sssssssssh/ssh_stock/actions/runs/41409940664) | IN_PROGRESS，最终结论 PENDING |
| [A4-2 41409940696](https://github.com/sssssssssh/ssh_stock/actions/runs/41409940696) | IN_PROGRESS，最终结论 PENDING |
| [A4-1 41409940667](https://github.com/sssssssssh/ssh_stock/actions/runs/41409940667) | SUCCESS；工作流结果不等于性能实验验收 |
| [Publication V1.3 41409940658](https://github.com/sssssssssh/ssh_stock/actions/runs/41409940658) | SUCCESS；工作流结果不等于性能实验验收 |

### 历史 CI 快照（原样保留）

下列为 **2026-11-02 15:56 +08:00** 的历史取样，均为 push、attempt 1、精确 SHA
e610a92890d89f0b58f1de6335ae918da07d67d9，不能当作当前 master 的实时状态。

| 工作流 | 核查状态 | Job 级事实 |
| --- | --- | --- |
| [主 CI 41408003394](https://github.com/sssssssssh/ssh_stock/actions/runs/41408003394) | IN_PROGRESS，最终结论 PENDING | test 在运行；workflow-contracts、dependency-audit、lookup-diagnosis 成功；authorize、capacity、lookup-tail-attribution、ui-visual-acceptance skipped |
| [A4-2 41408003417](https://github.com/sssssssssh/ssh_stock/actions/runs/41408003417) | SUCCESS | contract-and-safety 成功；authorize、laboratory、a42-acceptance-gate skipped |
| [Publication V1.3 41408003398](https://github.com/sssssssssh/ssh_stock/actions/runs/41408003398) | SUCCESS | contracts 成功；authorize、candidate-performance skipped |
| [A4-1 41408003426](https://github.com/sssssssssh/ssh_stock/actions/runs/41408003426) | SUCCESS | contracts 成功；authorize、isolated-baseline skipped |

skipped 不表示性能通过；成功的合同工作流未执行其高成本实验。本轮只读取 GitHub，
不 rerun/dispatch/取消工作流。旧 8f4e607 的 5297 测试与 89.99% 覆盖率是 R1 归档的历史
工程证据，不能贴为 e610a92 或 31bf700 的测试数或覆盖率。当前 master 最终覆盖率 PENDING。

## 6. 不得丢失的问题台账

下表 e610a92 的验收数字及 CI 表述保留原证据时间与版本；当前 master 的 CI 状态见第 5 节，
不以治理文档提交或工程 CI 结果关闭历史性能问题。

| 编号 | 事实与来源 | 状态 / 关闭条件 |
| --- | --- | --- |
| PERF-H01 | 20261019 记录缓冲读取 300.703 秒触发 57014；同快照服务端游标读取 1,439,327 行耗时 541.828 秒；不是当前数据量 | HISTORICAL / PERFORMANCE_OPEN；需要当前身份的读取/传输/转换证据和整链验收 |
| PERF-H02 | 候选 lookup/store、逐批核对、质量写入及约 144 万行工作负载，见 BIZ-PERF-01、Worker 与批次观测记录 | OPEN；阶段占比、来源、资源、事务与整链成本仍须可靠分解；1,443,097 行正式工作负载不等于 H01 实测行数 |
| PERF-H03 | BIZ-PERF-02 九对小样本输出相等，局部质量阶段改善约 42%–46%，但 1 月整链退化 5.34% 超过 5% 保留上限，8f4e607 撤回 | WITHDRAWN；实验撤回完成，原性能问题未解决；不得默认恢复候选 |
| PERF-H04 | BIZ-PERF-02-R1 A05/A06 的当前质量失败路径和最终逐根血缘证据不足 | PARTIAL；需另行批准的对应源码/逐根证据，不用历史候选测试填补 |
| PERF-H05 | e610a92 诊断前版 5 项 PG 测试通过，但三对成功根任务额外开销 5.6501%；离线计时器 22.532%；缓存版复测 INCOMPLETE | OPEN；3% 开销门槛尚未过，不能择优删样；当前源码有效三对、结果一致性及根身份需复核 |
| PERF-H06 | 诊断缺独立 queue/claim、纯筛选、可靠线程/网络归因；部分环境来源未知；后续停滞最后涉及因子收尾/机会计算，原因未定 | OPEN；先审代码和证据，不凭 ClientRead/心跳/部分栈归因或自动改 SQL |
| ENG-H01 | e610a92 本机针对性 28 项通过、Ruff 通过；Windows 全量 10 个 fcntl/resource 收集错误；最终 Linux CI 在运行 | PENDING；当前精确提交完整回归，不能把前版 5 项 PG 与当前单测拼为同版全绿 |
| CAP-H01 | 正式百万行、1/3/12 月、各至少三轮、整链≥30% 等对应验收未关闭，历史 RESOURCE_DEFERRED | DEFERRED / PERFORMANCE_OPEN；合格资源、代表性夹具、独立批准及原严格合同证据 |

证据：[读取超时](docs/acceptance/20261019_recalculation_read_timeout.md)、
[批次观测](docs/acceptance/20261019_calculation_batch_progress.md)、
[PERF-01](docs/acceptance/BIZ_PERF_01_closeout.md)、
[PERF-02/R1](docs/acceptance/BIZ_PERF_02_closeout.md)、
[PERF-03-A](docs/acceptance/BIZ_PERF_03_A_closeout.md)。
这些是历史记录，本轮读取而不改写；其“已完成/待合并/服务运行”须结合当时 SHA 和日期解释。

## 7. 阻塞、边界与接续

1. 五份治理文件已提交推送，GOV-20261102-001 已交付、待负责人最终验收；本轮三文档收口待审阅，不自行标 DONE。
2. 当前源码主 CI 未终结；诊断开销、最终根任务回归和插桩覆盖未验收。
3. 正式规模代表性夹具、合格执行资源及授权尚未核实满足；不能临时缩规模或放宽门槛。
4. 生产状态未知，现场读取/部署/数据库操作没有本轮授权。
5. 本轮仅更新治理入口、状态与任务接续规范；AGENTS 保留原业务权威关系和安全约束，
   旧 Milestone 16.3.1 当前阶段表述已修正。四份原业务权威文档与历史验收记录未修改。
6. 下一项仅为待审诊断整改方案；BIZ-PERF-03-A 仍为 PARTIAL，不授权 BIZ-PERF-03-A-R1 实施、性能实验或生产数据库操作。

后续更新遵守[任务规范](docs/tasks/README.md)：记录核查时间、源码 SHA、证据范围、
唯一任务与下一步；主线变更先追加[决策](DECISION_LOG.md)，不能只改本文件的状态字段。
