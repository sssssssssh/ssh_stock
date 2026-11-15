# BIZ-PERF-P1-04-W05-LAB-02：单次真实业务调用适配、根指标边界与离线端到端验证

日期：2026-11-15。发起与独立审阅：ChatGPT；执行：远程 ssssssh 电脑 Codex 桌面软件中的 **GP 项目**。
**起始精确 Git SHA**：`109921758eb949b4e986b08c58b3d3f6b117bd94`，GitHub/master、origin/master、HEAD 一致、工作区干净；此 SHA 主 CI #43619637195，A4-1 #43619637276，A4-2 #43619637199，Publication #43619637196 全 SUCCESS。
核心目标：在**不创建、连接、执行任何真实 PG/Worker**的前提下，交付可供**后续单独批准**的 W05 单次根业务调用适配层和完整离线联调测试。必须有实质性的业务调用接线（真实函数签名/懒加载映射）与根/post 时间边界，不是 E06/PRETEST-02，不重复造新的审计/准入清单。

## P0 不可违反的执行边界

- 此任务仅开发代码、测试、文档；**绝不启动或连接** PG17/数据库、任何 Worker/Scheduler、Docker/Compose、K8s/阿里云、真实 SQL/迁移/Seed/EXPLAIN、真实根任务、网络或云资源；不触碰用户现有 DB/stock_db/生产或旧测试库；不运行全量本机 pytest。
- 不修改 `docker-compose.yml`、LAB-01 的 Compose、环境配置、CI workflow、依赖、后端业务、前端、数据库模型、迁移、原 E02–E05、PRETEST、W05-READY、旧 R1、历史回执及原有测试。五份冻结文件及 W04A 源码哈希不变。
- 新适配器**不提供直接可运行的 CLI**、`main`、自动数据库连接、从 .env/`DATABASE_URL` 初始化、生产凭据读取、Docker 创建/清理、修改文件或后台启动。**无实际执行器出口**；调用方将来必须先由独立审批的实验协调端提供经现场验证的全新隔离资源、专用 Session factory 及外部硬预算终止控制；这不是 `bool approved=True` 或一段自述 JSON 能绕过的。
- 默认实例、导入、反射、离线测试必须绝对无副作用；未来适配函数虽封装生产 create/claim/execute 调用，但当前没有任何公开程序入口可启动它。不要把“离线 fake 执行成功”说成真实执行已可用或已核验。
- 保持 `ROOT_ATTEMPTS=0`、`HOTSPOT=NONE_PROVEN`、`REAL_PG17=NOT_RUN`、`REAL_WORKER=NOT_RUN`、`B_GATE=NOT_APPROVED`、`TARGETED_PG17_GATE=NOT_APPROVED`、`AUTHORIZATION=AUTHORIZATION_PENDING`、`BUDGET=DRAFT_NOT_APPROVED`。任何运行未来实验必须新的明确用户授权，不因 CI/模拟通过自动跳转。

## W00 先核对源码（不能凭任务书假定签名）

按 AGENTS.md 顺序阅读五份治理文件，然后相关 PRD、系统设计、PROJECT_RULES、README、`docs/tasks/BIZ-PERF-P1-04.md`、PRETEST-01 与 W05-READY ASSESSMENT、LAB-01 PLAN/CLOSEOUT、E02 measure_wiring、E03 collector/evidence、E04/E05、冻结 `scripts/business_recalc_measure.py`（特别 300～430 行）、`scripts/v14_test_database.py`、`backend/app/services/recalculation.py` 中 `create_recalculation_job`、`backend/app/services/job_worker.py` 中 `claim_next_job` / `execute_claimed_job`、JobRun、DataPublication、ProgressStep、`scripts/business_sql_snapshot.py::RootCounts`；确认调用方式、commit/flush/refresh、单 root 身份，严禁凭旧描述臆造。
先 `git status --short --branch`、HEAD 和 origin/master；仅允许新任务书一个未跟踪项，远端漂移或意外 dirty 则停止。Codex 沙箱 SSH/.git 拒绝时不绕权，外层 ChatGPT 已核验起始 SHA；结束也如实交接外层正常提交。

## W05-LAB-02-A：具体的单根调用桥（必须有代码）

新增一个独立 `scripts/biz_perf_p1_04_w05_root_bridge.py`。设计必须体现：
1. 显式依赖注入：以 `ports`/Protocol 提供 `create_claim` 和 `execute_claimed_job` / `post_validate`；以单调时间、进程 CPU、指标 sink 输入；默认是固定 `EXECUTION_NOT_AVAILABLE` 拒绝。生产适配器函数只提供**精确真实签名懒导入映射**供未来审批后装配，**绝不在模块导入或离线测试时加载 app/psycopg/sqlalchemy/.env**。不增加一套签名/租约/许可框架。禁止调用 `scripts/business_recalc_measure.py::main`、`biz_perf_03_b_once.execute`、`isolated_v14_database`。
2. 以已有 `create_recalculation_job(db, start=2025-01-01, end=2025-01-31, evaluate_signals=False, mode='manual')` 创建且仅创建一个根；`claim_next_job` 必须查明只 claim 当前 ID，**若为空或非刚创建根 ID 则拒绝执行，不可继续领取、不可取消另一个任务**；真实 worker 只能一次调用 `execute_claimed_job(db, identity, expected_worker=job.worker_id, expected_token=job.execution_token)`（以当前真实源码为准）。禁止重试/恢复/重入和第二根；异常与 UNKNOWN_ACK 一律终止，保留已消耗尝试状态，不伪造 SUCCESS。
3. 计时严格：`root_elapsed_ms` 在 create/claim **之前**启动，在单次 `execute_claimed_job` 返回并退出其 finally 后立即冻结；`execute_claimed_job_ms` 是 root 子区间，不能与 root 相加。`post_root_validation_ms` 从冻结后开始，只读取 JobRun/Publication 等根结果，**不得回填根计数、CPU/SQL/FETCH/峰值**。阶段 inclusive 可能重叠，不可求和。RootCounts 与 E02 既有度量、E03 原始事件约定尽可能复用已有语义；若当前阶段实际无 SQL/FETCH 采集，不得假造，字段 `UNKNOWN` 或 `NOT_INSTRUMENTED`。
4. 在将来合法实机实现时需要独立验 Job `SUCCESS` 与 Publication `PUBLISHED`，检查公开范围/source/row counts 与无 B 泄露；无法证明则 `INCONCLUSIVE`，绝不 return 完成。当前仅注入 fake reader 测试与静态契约，**不得连接真实数据库**。
5. 提供明确不可执行的工厂或适配器准入文档；任何 `run-live`、`execute`、`--permit`、`--force` CLI 都必须不提供或固定拒绝退出2，不能允许任意传入 Session/Factory 就触发真实业务。建议把面向未来的真实函数映射封装为仅可注入的 `LiveBusinessPort` 方法，不在本次添加能自动实例化该 port 的调用器。
6. 外部 watchdog/cgroup、镜像可信、PG physical id、UUID/租约、seed/迁移、完成清理**不在本模块实现**，必须作为 W05-RUN 前的事实核验与硬拒绝项；不得以 `time.monotonic` 软件超时声称进程能强制停止或凭本模块完成保护。

## W05-LAB-02-B：最小业务采集契约（不要新造整套观测框架）

必须能在 fake ports 中稳定回放并验证：
- 一次 root 的 begin/create/claim/worker-return/root-freeze/post-read 顺序，单根 identity、run UUID 与 implementation SHA 不串样；
- root、Worker、post 的 wall 彼此正确隔离，CPU 差值与阶段计数不捏造；失败时记录固定脱敏错误码而不是 Exception/SQL/URL/参数/数据库凭据；
- stage 标签（已知的 `factors.compute`、`candidate_lookup_batch`、`candidate_store_batch`、`publication.verify`、`publish_inclusive`）只复用 E02 合法名字。没有采集就标 `NOT_INSTRUMENTED`。`FactorInputWindow._verify` 在五 OFF 下并不是必然可达热点，绝不能把它写成已观察事实；
- 严禁在进程或数据库异常上自动重试、从第二次检查拼接 root 快照、跨不同 job root 复用结果。post 校验失败不得转回 worker 或重跑。

## W05-LAB-02-C：高价值离线端到端测试

新增 `tests/unit/test_biz_perf_p1_04_w05_root_bridge.py`，至少 30 个有区别的用例而非重复凑数。全部纯 fake in-memory：
- create/claim 的参数、准确 job id/token/worker、仅一次执行、没有意外第二根、claim 错 ID/None、created != claimed、缺 expected_token、post SUCCESS/PUBLISHED 分别否、B 泄漏、未通过来源、缺根身份；
- 重入/重复执行、崩溃/已发生但未知 ACK、worker 失败、post 失败、RootCounts 封口后后验计数不能混入、monotonic 时间反转/overflow、CPU=0、阶段重叠不加总、stage 缺测、无 SQL/FETCH 不等于0、原始错误/连接串不得泄露；
- 完整正例断言单根唯一路径且 root/worker/post 时间、事件序列正确；子进程 import 测试确认不加载 backend app/sqlalchemy/psycopg/dotenv，不做连接/网络/文件写入；正例必须是 fake，不能误称 live；
- 参考安全旧测试用例，拒绝真实 connection URI、生产资源意外读取；不能引入新的许可伪造绕过。
旧 LAB-01/W05/W05-R1/PRETEST/E05/E04/E03/E02/frozen diagnostic/W04A/fake PG guard 必须一起离线回归；不执行数据库测试或全量 Windows pytest。RED→GREEN、`git diff --check`、AST、新文件空白及 frozen blob 检查；Windows 无 Ruff 则记 `ENV_BLOCKED`、不安装依赖，最终新 SHA Linux CI 判断。

## W05-LAB-02-D：真实执行缺口与实施决策书

新增 `docs/acceptance/BIZ_PERF_P1_04_W05_LAB02_INTEGRATION.md`，明确新模块中真实函数映射点和**仍缺**的真实环境及资源证据；贴合 LAB-01 compose 是单 PG 容器、私有 internal 网络、无宿主端口也无 Worker 容器这一事实，说明未来需要单独批准的 Worker 隔离连接方案与严格凭据来源、PG17 物理身份、硬时间/CPU/内存/磁盘/IO 约束、900 日历日 seed/迁移/预热计时、4 段成功/失败退出、外部 watchdog/UNKNOWN_ACK 人工处置和资源清理归属。一定要说明：**即使本轮所有离线测试通过，仍无可执行的一次性真实试验入口**；下一步不是 E06，而是用户决定批准资源与单次实验。
新增 `docs/acceptance/BIZ_PERF_P1_04_W05_LAB02_CLOSEOUT.md` 记录本轮白名单、精确 diff、RED/GREEN、离线测试实际结果、独立复测待外层、Ruff 与 CI 状态、剩余 blocker，不要把源码映射等同实机经验证。

## 白名单

**仅允许新增以下5份文件**，不改任何历史跟踪文件：
1. `docs/tasks/BIZ-PERF-P1-04-W05-LAB-02.md`（本任务书由负责人下发，不改原文）
2. `scripts/biz_perf_p1_04_w05_root_bridge.py`
3. `tests/unit/test_biz_perf_p1_04_w05_root_bridge.py`
4. `docs/acceptance/BIZ_PERF_P1_04_W05_LAB02_INTEGRATION.md`
5. `docs/acceptance/BIZ_PERF_P1_04_W05_LAB02_CLOSEOUT.md`

五份 frozen Git blobs 必须相同：
- `scripts/business_recalc_measure.py` = `782e45ba53c8de8df0d12ffa84c219855316cfda`
- `scripts/biz_perf_p1_04_diagnostic.py` = `714f78017ec252791ac6a89f9fb0e0a984333c37`
- `scripts/perf03_lnx_w04a_offline_contract.py` = `931fd4fec38551d9fac59791d2bde5ce0e6a1d48`
- `scripts/biz_perf_03_b_once.py` = `2ea473491f590893ad575b90a0ba42f932e37129`
- `scripts/business_sql_snapshot.py` = `e7532b0a0242f1e3d3b047fdc03fca7ffc3ce7c6`

## 交付、推送及独立审阅

任务必须在 Codex 桌面软件真正归属 GP projectId=`01a15f75-2c79-7d30-9232-651a6ef4253d` 的持久会话中执行，名称 `BIZ-PERF-P1-04 W05-LAB-02 真实调用适配`，不能使用独立 codex exec。
Codex 完成后：针对性安全测试→源文件仅白名单→五 frozen→普通一次 `git add/commit` 与**非 force**推送 `master`；若 .git/SSH 被 Codex 沙箱拒绝，明确保持工作区，不绕过，让 ChatGPT 外层 PowerShell 核实精确 HEAD/origin/master/GitHub master、diff、测试后常规提交与推送。若 remote 改变，停止而不是强推。
外层 ChatGPT 再对精确新 SHA 审阅主 CI/A4-1/A4-2/Publication；若 Ruff/测试失败，最小整改不得修改 pytest safety 或 CI。**最高结论 `LAB02_ADAPTER_OFFLINE_VERIFIED`，绝不宣称 `B_GATE APPROVED`、真实 PG17/Worker 已运行或测出瓶颈。**
GP 回执需有 `TASK`, `BASELINE_SHA`, `SAFE_TEST_COUNTS`, `CHANGED_PATHS`, `FROZEN_5`, `REAL_PG17=NOT_RUN`, `REAL_WORKER=NOT_RUN`, `ROOT_ATTEMPTS=0`, `B_GATE=NOT_APPROVED`, `PUSH`, `FINAL_SHA`, `CI_RUN`, `NEXT=CHATGPT_INDEPENDENT_REVIEW`。
