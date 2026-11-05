# ssh_stock 当前状态与唯一执行指针

## BIZ-PERF-04-B 当前接续（2026-11-06）

负责人已验收关闭04-A（9df4cfed），不追加其修复。当前仅04-B确定性离线生成器，
S1兼容、S1～S4显式生成/校验，交付后REVIEW_PENDING。无Worker/数据库/实验或04-C～F授权。
基线9df4cfed，本轮交付见[04-B](docs/acceptance/BIZ_PERF_04_B.md)。下方保留历史语境。

## BIZ-PERF-04-A SQL 终态计数一致性（2026-11-05）

本轮仅修复合成测量的终态快照与跨文件证据合同；基线为
`057dfe861f940a5284b594db9ef45c2257cec688`。旧进度快照已离线 RED 复现。
根计数在 create/claim/execute（含 Worker finally）返回后冻结，独立终态查询、
摘要核验和实验库销毁不计入根计数。历史文件仍可解析，但新完整证据必须绑定同一版本化快照。
真实 BIZ03 Run 41991816127 保留原件，不重跑；SQL SELECT/UPDATE 逐条差异仍 UNKNOWN。
仅授权 04-A 开发、定向验证、master 交付及自动普通 CI；04-B～F、实验和业务库均未授权。
交付后停止等待审阅；本轮不提供容量、性能或生产资格。详见
[04-A 交付与合同](docs/acceptance/BIZ_PERF_04_A.md)。


## BIZ-PERF-03-B 最小修正接续（2026-11-05，当前唯一任务）

负责人本次仅授权修复第七Workflow外部Action完整SHA固定与420秒内的清理/归档阶段切换，
允许master提交推送并等待普通CI；未授权真实性能dispatch或任何GitHub设置/数据库操作。
修改前HEAD/origin/master/实时远端均为de7081a77567081a8c31a41a8960455cbd2d874e，clean，已快进拉取。
官方Action SHA已从官方Git refs和commit页双核；新增27项离线边界/失败路径测试通过，
原治理合同与当时20项新用例合计117通过，Ruff通过。旧BIZ测试在Windows合跑105通过/9项POSIX
接口缺失，未改原断言或跳过，交由普通Linux CI核验；不可将本地结果冒充最终完整回归。
清理完成立即替换watchdog；归档截止=min(cleanup_finished+30,T0+420)，419可归档、420停止，
重复进入不续期；超时export失败不能触发最终上传。原提前INCOMPLETE前缀保留。
范围及官方来源见[修正记录](docs/acceptance/BIZ_PERF_03_B_actions_runbook.md)。
状态为PATCH_IMPLEMENTED / REVIEW_PENDING / LIVE_NOT_RUN；最终提交普通CI在推送后核验，
此处不追填自身SHA。交付后停止等待负责人审阅，不自动dispatch。
B0仍WITHDRAWN，原六份Workflow及原串行完整回归、70%覆盖率、实验协议/数据/开关不变；
业务性能继续PARTIAL/PERFORMANCE_OPEN。下方各段均为其原轮次历史事实，不授权扩大范围。

## BIZ-PERF-03-B 当前接续（2026-11-05，环境适配）

负责人已审阅通过W00/W01，批准Actions环境适配代码、离线合同及master提交推送；
未批准真实性能dispatch、Environment/reviewer/Secrets/Variables操作或W02业务优化。
修改前HEAD/origin/master/实时远端一致为b27fa109530002f2cddbb1a4c28b356bad11b398，clean。
新增第七个独立手动Workflow与最小controller，保留原六份Workflow和业务源码。
当前唯一执行任务为本适配交付，ADAPTATION_IMPLEMENTED / REVIEW_PENDING / LIVE_NOT_RUN。
离线255项通过；Ruff与diff检查通过。扩展历史合同213通过，另3项严格clean-tree门禁在未提交
工作区报A4235_DIRTY_TREE；提交后只复核这三项，不修改其断言，结果以交付回执及同SHA CI为准。
两项有界进程/失败前缀缺陷均先RED再修复；原始回执摘要见
[离线验证](docs/acceptance/biz_perf_03_b_actions_offline_verification.json)。普通CI不等于本实验通过。
真实根任务尝试0，PG/容器创建0，新实验NOT_RUN。下一步交付后仅等待负责人审阅，禁止自动dispatch。
CI-OPT-02 B0继续WITHDRAWN、原test串行；b27fa109 observer失败根因UNKNOWN，未修改该模块。
R1/业务性能仍PARTIAL/PERFORMANCE_OPEN；本阶段不关闭它们。
范围/协议/后续人工设置见 [Actions操作说明](docs/acceptance/BIZ_PERF_03_B_actions_runbook.md)。
下方CI-OPT-02等段落保留历史接续事实，不能解释为本轮恢复CI并行或修observer的授权。

## CI-OPT-02 当前接续指针（2026-11-04）

当前唯一执行任务为CI-OPT-02失败收尾，状态W03 PARTIAL / B0 WITHDRAWN。
负责人已确认方案B、上限2；实际Linux为pilot 8 passed、serial 5289 passed/128 failed。
本轮按停止条件撤回B0并恢复原串行，保留原5407测试；B1未启用，下一步审阅失败及前置差异。
详情与原始工件摘要见docs/tasks/CI-OPT-02.md及docs/acceptance/ci_opt_02/withdrawal.json。
修改前 master/远端/GitHub 均为252f7559f8ab86de3420c0aaad825e819fb38a40。
最新CI-OPT-01代码运行57edac41已有5407 passed、90.02%的完整工程证据；其前轮失败仍保留。
本轮先收集5407节点，实施阶段新增18项候选合同；候选执行后因128失败撤回。历史W00分片建议与当前停止结论见
[CI-OPT-02](docs/tasks/CI-OPT-02.md)。既有批准不自动允许继续迭代失败候选或进入B1；本轮不再追加修复刷绿。
以下原CI-OPT-01状态段保留历史时间，不作为当前唯一执行授权。R1仍PARTIAL，生产与性能资格不变。

状态版本：2026-11-04，CI-OPT-01 的 W01/W02 实现与定向验证通过；W03完整CI发现一处旧测试版本衔接失败，正在最小修复和重验，整体 PARTIAL。
BIZ-PERF-03-A/R1 仍 PARTIAL；GOV-20261102-001 仍 REVIEW_PENDING。
R1 实施前基线：32cf8f438061e95b1492fd2a5db15dd05c13e28d；当轮核查时本地/远端一致。
第 2 节保留 2026-11-02 治理修改前快照，不将其当作 R1 的实时 HEAD。
核查日期使用 Asia/Shanghai；历史治理基线核查时间为 **2026-11-02 16:29 +08:00**；本轮时间见第 2 节。
R1 基线 32cf8f43 的四条工程工作流已核查终结成功，完整测试 5322 passed、覆盖率 90.00%；
修复提交 16ef3062 的最终 CI 已核验 PASS（5347 passed、816 warnings、90.02%）；详见第 5 节。第 5 节中旧取样保留其时间和 SHA，不作为实时结论。
本文件记录带时间的修改前基线，不要求填写文档自身最终提交 SHA；新会话必须重新核验 Git，
不能把该快照当实时监控，也不因后续提交而持续刷新同一轮记录。

## 1. 当前主线与下一步

- 当前唯一业务主线：股票历史数据读取 → Python 转换与计算 → 候选查询与写入 → 质量核验 → 原子发布的性能问题；尚未收口。
- 当前唯一执行任务：**CI-OPT-02失败收尾，W03 PARTIAL / B0 WITHDRAWN**，以上方当前接续指针及新任务书为准。原CI-OPT-01的负责人“开始修改”批准只属于前轮，不延伸为本轮W01–W03许可。业务主线不变，R1仍PARTIAL；GOV仍REVIEW_PENDING。
- 治理交付状态：**已交付、等待负责人最终验收（REVIEW_PENDING）**，不得自行标记为 DONE。五份治理文件已在 31bf700 首次提交推送；AGENTS 新会话强制读取规则与 PROJECT_STATUS、docs/tasks/README 的入口收口修改已在 276cc262 提交推送；后续状态文件修正已在 306971b3 提交推送。
- 当前 R1 状态：PARTIAL。生命周期/归属/FETCH 最小修复已验证；有界定位 OFF 原生崩溃、ON 成功，未形成有效对照，停止完整性能矩阵。工程 CI 已通过；下一步仅审阅 Windows OFF 原生故障只读定位与环境处置方案，恢复有效配对后再做三对开销验证，不授权执行这些后续步骤。
- **BIZ-PERF-03-A = PARTIAL**；R1 已获本次明确批准，限方案内诊断修复及隔离小型验证。原治理记录中的未授权 R1 约束为历史边界，本次授权不覆盖生产、高成本专项或业务算法改动。详见 [R1 回执](docs/acceptance/BIZ_PERF_03_A_R1_closeout.md)。
- 未获批准不得自行进入热点优化、扩大功能或重新规划另一条开发主线。

## 2. 仓库基线

### CI-OPT-01 修改前核查

2026-11-03 重新核对：本地 master、HEAD、origin/master、GitHub master 均为
**e697fc80a098726f4e73f04ac71f5eb6cfb62b03**，工作区干净。
六份 Workflow/23 个 Job 已审计；最近三次主 CI 约63–65分钟，完整 pytest 步骤约50–52分钟。
Required Checks 与 Environment 实际 reviewers 为 UNKNOWN（读取权限不足），不新增全局路径忽略。
当前候选只修改 CI、只读脚本、编排合同及必要文档，无业务代码/Schema/策略/生产配置变化。
实施与验证进度见 [CI-OPT-01](docs/tasks/CI-OPT-01.md)；不追填本文件自身提交 SHA。

### 最终 CI 证据同步修改前核查

核查时间：2026-11-03T11:17:30+08:00。本地 master、HEAD、origin/master、GitHub master
均为 **16ef3062dc538b0f4def0f30edb297a831c32510**；工作区干净，亦为本轮工程证据唯一适用 SHA。
其为最近诊断实现提交；下列 32cf8f43/e610a928 等记录保留原时间及历史角色，
不表示本次 HEAD。文档交付后不追填自身实时 SHA，下一会话重新核验。

### 2026-11-03 R1 修改前核查

本地 master、HEAD、origin/master 与 GitHub master 均为
**32cf8f438061e95b1492fd2a5db15dd05c13e28d**。该提交仅更新治理状态；
修改前最近一次业务代码变更为 e610a928。本轮改动为获批诊断修复，
不要求在本文件追记自身最终提交 SHA。

### 2026-11-02 治理轮次历史快照

| 项目 | 核查事实 | 来源 |
| --- | --- | --- |
| 本地分支 | master | git status --short --branch |
| 修改前基线：核查时 HEAD / origin/master / GitHub master | 306971b3cf7a08c50bc32e24de55a41c52258052（2026-11-02 16:29 +08:00） | git rev-parse、git ls-remote --heads origin master |
| 核查时最新治理提交 / 状态文件修正提交 | 306971b3cf7a08c50bc32e24de55a41c52258052（306971b3） | git show --stat；单文件状态修正已提交推送 |
| 上一轮治理入口收口提交 | 276cc262d4b8be2008415683c9d5af42a913fbc2（276cc262） | git show --stat；入口规则与接续状态收口已推送，不是本次核查的 HEAD |
| 治理文件首次交付 | 31bf700c77b86fcb9be59787a0bde76d6f7d85bd（31bf700） | git show --stat；仅作历史交付 SHA，不是当前 HEAD |
| 最近一次业务代码变更 | e610a92890d89f0b58f1de6335ae918da07d67d9（e610a928） | git log -1 -- backend frontend config scripts migrations |
| 修改前基线提交标题 | docs(governance): correct delivered governance and business source baselines | git show 306971b3 |
| 16:29 核查时工作区 | 干净，含未跟踪文件检查 | git status |
| 16:29 核查时远端 master | refs/heads/master 指向 306971b3；远端仅 master 的完整分支清单为此前核查事实，本次仅复核 master | git ls-remote --heads origin master |
| 历史集成 | PR #1 合并提交 3940d9b；其后 BIZ-PERF-02 候选、撤回和 R1 均在 master 历史 | git log |
| 治理文件交付 | PROJECT_CHARTER、PROJECT_ROADMAP、PROJECT_STATUS、DECISION_LOG、docs/tasks/README 五份文件已在 31bf700 提交推送，441 行新增 | git show --stat 31bf700、此前推送成功及本轮提交链核对 |
| 入口与接续收口交付 | AGENTS.md、PROJECT_STATUS.md、docs/tasks/README.md 已在 276cc262 提交推送 | git show --stat 276cc262、此前推送成功及本轮远端 master 复核 |

2026-11-02 治理轮次修改前核查的 master 基线为 **306971b3**（状态文件修正）；**276cc262** 为上一轮治理
入口收口；**31bf700** 为五份治理文件首次交付；最近一次业务代码变更仍为 **e610a928**。
三次治理提交均未改动业务代码，BIZ-PERF-03-A 仍为 PARTIAL。各 SHA 仅对应其提交角色和
核查时间，不表示本文件后续提交的实时 HEAD，不要求为文档自身最终提交 SHA 追加修订。

## 3. 实际代码能力与证据层级

以下能力来自此前静态审阅的入口和调用。R1 仅进行获批诊断修复和隔离合成测试，
不把这些验证解释为生产库数据状态或完整业务功能验收。

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

## 5. CI 证据与历史快照（仅工程证据）

### 修复提交 16ef3062 最终工程结果

2026-11-03 独立核验：精确 SHA **16ef3062dc538b0f4def0f30edb297a831c32510**，
四条 push/attempt 1 工作流均 completed/success。主 CI 41558957304 的 test Job
125664629647，Step 23：5347 passed、816 warnings、coverage 90.02%；Step 27 Ruff 成功。
前端测试/构建、Docker 构建、PG17 隔离与迁移步骤均成功。
A4-1 41558957308 contracts 成功；A4-2 41558957295 contract-and-safety 为 342 passed；
Publication 41558957367 contracts 成功。合计 7 个 success Job、12 个 skipped。

A4-1 authorize/isolated-baseline、A4-2 authorize/laboratory/a42-acceptance-gate、
Publication authorize/candidate-performance 均 skipped，不是实验或授权通过。
主 CI authorize/capacity/publication-release-gate 等未执行阶段也不记 PASS。
完整 URL、Job/Step 与日志索引见 [R1 closeout 第 6 节](docs/acceptance/BIZ_PERF_03_A_R1_closeout.md#6-ci-执行结果与性能验收边界最终证据同步)
及 [verification.json](docs/acceptance/biz_perf_03_a_r1/verification.json)。

**工程 CI PASS + R1 PARTIAL + PERFORMANCE_OPEN** 同时成立；Windows OFF 原生异常
0xC0000005 根因 UNKNOWN、三对有效配对未完成、≤3% NOT_VERIFIED。
下文为历史取样，不能把旧 SHA 的等待状态当作 16ef3062 仍在等待。

2026-11-03 R1 执行更新：32cf8f43 的主 CI 41414072689、A4-1 41414072644、
A4-2 41414072701、Publication 41414072660 均 success；共 7 个成功 Job、12 个 skipped。
完整 pytest 5322 passed、coverage 90.00%，Ruff 通过。该证据只对应修改前基线，
不能关闭 R1 的 ≤3% 或修复后工程验收；细目见 R1_plan / R1_closeout。
以下 306971b3 及更早表格保留原治理快照语境。

修改前基线 **306971b3cf7a08c50bc32e24de55a41c52258052** 的 CI 本次未重新查询，
状态为 UNKNOWN，最终工程结论 PENDING；不得继承下列旧 SHA 的结果。

### 31bf700 历史 CI 快照（原样保留）

下列为 **2026-11-02 16:04 +08:00** 的历史取样，均为 push、attempt 1、精确 SHA
**31bf700c77b86fcb9be59787a0bde76d6f7d85bd**，不表示当前 HEAD 或实时 CI 状态：

| 工作流 | 16:04 核查状态 |
| --- | --- |
| [主 CI 41409940664](https://github.com/sssssssssh/ssh_stock/actions/runs/41409940664) | IN_PROGRESS，最终结论 PENDING |
| [A4-2 41409940696](https://github.com/sssssssssh/ssh_stock/actions/runs/41409940696) | IN_PROGRESS，最终结论 PENDING |
| [A4-1 41409940667](https://github.com/sssssssssh/ssh_stock/actions/runs/41409940667) | SUCCESS；工作流结果不等于性能实验验收 |
| [Publication V1.3 41409940658](https://github.com/sssssssssh/ssh_stock/actions/runs/41409940658) | SUCCESS；工作流结果不等于性能实验验收 |

### e610a928 历史 CI 快照（原样保留）

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
工程证据，不能贴为 e610a928、31bf700、276cc262 或 306971b3 的测试数或覆盖率。修改前基线最终覆盖率 PENDING。
即使工程 CI 后续通过，也不代表 BIZ-PERF-03-A 的开销、整链性能或百万行容量验收通过。

## 6. 不得丢失的问题台账

下表 e610a92 的验收数字及 CI 表述保留原证据时间与版本；修改前基线的 CI 核查范围见第 5 节，
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
这些是历史记录，原主体不改写，仅向 PERF-03-A 收尾文档追加 R1 记录；其“已完成/待合并/服务运行”须结合当时 SHA 和日期解释。

## 7. 阻塞、边界与接续

1. 五份治理文件、新会话读取/接续规则及 306971b3 状态文件修正均已提交推送；GOV-20261102-001 继续 REVIEW_PENDING，等待负责人最终验收，不自行标记为 DONE。
2. 修复提交 16ef3062 的工程 CI 已核查 PASS；诊断开销、最终根任务配对和完整插桩覆盖仍未验收，不能用工程通过关闭 R1。
3. 正式规模代表性夹具、合格执行资源及授权尚未核实满足；不能临时缩规模或放宽门槛。
4. 生产状态未知，现场读取/部署/数据库操作没有本轮授权。
5. AGENTS 的强制读取规则已在 276cc262 交付；2026-11-02 治理快照仅说明当轮范围。
   2026-11-03 R1 的新增授权仅限批准方案；未修改业务算法、Schema、生产配置、CI 或旧验收事实。
6. 本次负责人已批准 R1 方案内最小诊断整改；BIZ-PERF-03-A 与 R1 仍为 PARTIAL，未授权生产、百万行实验或下一阶段。原生失败使三对性能矩阵停止。

本轮 DOC-CLOSEOUT 的交付仅同步既有工程事实；不改变业务库 UNKNOWN、GOV 的 REVIEW_PENDING
或 R1 的 PARTIAL，不授权异常定位执行、性能实验或 B 阶段。

后续更新遵守[任务规范](docs/tasks/README.md)：记录核查时间、源码 SHA、证据范围、
唯一任务与下一步；主线变更先追加[决策](DECISION_LOG.md)，不能只改本文件的状态字段。

## 8. 五份治理文件的一致性核对

已按 AGENTS 顺序读取五文件：长期目标、历史性能主线、诊断未验收、治理待负责人最终验收
及后续实施需独立批准的规则一致。PROJECT_CHARTER、PROJECT_ROADMAP、DECISION_LOG 中
的草案/待审及旧 SHA 描述保留原任务语境，不表示新的业务授权；docs/tasks/README 所记
31bf700 是首次交付，其“本轮三文档收口”是 276cc262 的历史范围，不是本次修改许可。
上述存在跨轮次措辞时效差异，本轮保留历史语境；ROADMAP 同步异常定位→有效配对→三对验证顺序，
DECISION_LOG 追加工程/性能分层判定，任务规范登记 DOC-CLOSEOUT，CHARTER 保持不变。
交付状态与唯一下一步以本文件的带时间记录及负责人最新要求为准；实时 Git 基线需由
后续会话独立核验，不把本文件中的修改前快照视为随文档提交自动更新的 SHA。

## 9. CI-OPT-01 接续（本轮最新指针）

- W00 已审阅并获准实施；W01/W02 已完成本地实现与验证。2026-11-04 接续核验最终 JUnit：218 passed、0 failure/error/skip，335.14秒；默认插件及同盘临时目录，未改旧用例的30秒限制。Ruff 与 diff 检查通过。
- 精确说明块修改可走 docs；块外文档、验收 JSON、代码、迁移、工作流及未知比较继续 full。
- 原实验授权、Environment、正式 Gate、覆盖率和完整步骤不减少；旧编排合同仅做必要版本适配。
- W03 网络接续：先前连接器、旧代理及直连失败；2026-11-04 已确认系统代理改为本机7900，Git与GitHub API均成功；首次恢复取样master为e697fc80，后续已正常提交推送。仅按命令使用代理，不改全局Git设置。
- 负责人明确回复“提交并推送 master，继续 CI 验收”。已执行普通提交及说明实测；下一项为本节末记录的精确补丁回归，不强推或覆盖其他提交。当前补丁完整 Linux/PG17 回归仍 PENDING。
- doc-only已取得下列精确版本的真实端到端证据；代表性backend、PR远端事件仍DEFERRED，不创建无意义业务改动或新分支。
- 并行化 W04 暂缓；BIZ-PERF-03-A-R1 仍 PARTIAL，不执行新的性能实验或生产操作。
- 上文第7节的 R1/DOC-CLOSEOUT 为其历史轮次边界；本轮唯一执行任务以本节及第1节为准。
- [任务回执](docs/tasks/CI-OPT-01.md)与[验证摘要](docs/acceptance/ci_opt_01/verification.json)登记范围和剩余项；本地通过不代表正式工程或性能验收完成。
- 首轮f31aeef已推送；真实README说明提交1a4bda0的四条文档工作流通过，主CI46秒，完整pytest/迁移/Docker未执行。
- 首轮Observer合同41788897841发现漏接的第四个旧冻结用例，318通过/1失败，本机已精确复现。当前补齐同一严格投影并纳入轻量回归；当前修复的本地及新SHA完整CI仍PENDING，不用旧218项或README成功冒充。
- 530b214在Linux已通过上述初段；后续A42341 AT20又暴露直接比较旧Workflow原字节的第五处边界，当前补齐并加入轻量入口，原摘要/字节断言保留。
- 同版Windows扩大验证316通过/1失败，失败为CRLF及原POSIX目录FD能力限制，未放宽；413d452说明提交主CI37秒、四条说明工作流成功。最新修复完整Linux验收仍PENDING。
- f39f4a8主CI41795028412全量5402通过/1失败、覆盖率90.02%，其余四条工作流成功；唯一失败为business测试冻结清单尚未识别AT20。
  当前仅补精确全文投影后执行原business验证器，不改其生产脚本/适配清单或负例，并把该文件加入轻量入口。
- ab9be0f README说明实测四条通过，主CI41795754600为51秒，完整pytest/迁移/构建均NOT_RUN；这不是新补丁的完整回归证明。
- 2026-11-04本补丁修改前master已核实为ab9be0f8620d8fc50f56498ca057d90047cf5c1f，早前e697fc80等均为对应取样快照。
  最新只读API确认master无强制Required Checks；审批环境已有1名审批人/正确ACK/禁止管理员绕过，仍需管理员开启Prevent self-review。

<!-- ci-opt-01:noncontract-prose:start -->
此处可补充阅读提示，具体状态请查看各节记录。
<!-- ci-opt-01:noncontract-prose:end -->
