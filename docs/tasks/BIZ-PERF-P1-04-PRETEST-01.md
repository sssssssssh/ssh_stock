# BIZ-PERF-P1-04-PRETEST-01 开发任务书：受控性能验证准备与热点定位报告（E05 后收口）

- 负责人：用户；执行者：远程 ssssssh 的 Codex 桌面软件 GP 项目；独立复测与最终审阅：ChatGPT。
- 日期：2026-11-14；基线：GitHub/master、origin/master、HEAD = `b5207a39fd98b1508b8745fadae799ff34a3609d`。
- E05 主 CI：`43574455659` attempt 1 `completed/success`；pytest 7180 passed、1 skipped；覆盖率 90.02%；A4-1、A4-2、Publication V1.3 同 SHA 成功。
- 定位：**这不是 E06，也不再扩建审计/权限框架**。E03–E05 的离线安全验证已收口。本次是通向实际性能定位的最后一个**不执行真实测量**的准备阶段：把已有采集合同转化为清晰的热点分析视图和一次性隔离测试申请，让负责人能够判断是否批准一次有边界的真实试验。

## 0. 不可逾越的安全与业务边界

**绝对禁止**连接/启动真实 PostgreSQL17、Worker、Scheduler、Docker、云、现存测试数据库或生产业务资源；不执行 DDL/DML、迁移、真实因子计算、实际 SQL/EXPLAIN、性能实验、应用 HTTP 请求或网络扫描；不调用 `business_recalc_measure`、`business_recalc_matrix`、`business_recalc_diagnosis` 的真实运行入口，不触发 03-B 或任何 root/job。禁止通过 CI、离线报告、虚拟 ACK、路径或命令行参数生成 permit 或开启测试。新增 CLI 若提供 `execute`，固定 `AUTHORIZATION_PENDING` 和 exit 2。

本阶段状态始终：`ROOT_ATTEMPTS=0`，`HOTSPOT=NONE_PROVEN`，`B_GATE=NOT_APPROVED`，`TARGETED_PG17_GATE=NOT_APPROVED`，`AUTHORIZATION=AUTHORIZATION_PENDING`。预算 `DRAFT_NOT_APPROVED`，不允许因本次交付自动改变。

以下五份历史冻结文件必须保持确切 Git blob：
1. `scripts/business_recalc_measure.py`：`782e45ba53c8de8df0d12ffa84c219855316cfda`
2. `scripts/biz_perf_p1_04_diagnostic.py`：`714f78017ec252791ac6a89f9fb0e0a984333c37`
3. `scripts/perf03_lnx_w04a_offline_contract.py`：`931fd4fec38551d9fac59791d2bde5ce0e6a1d48`
4. `scripts/biz_perf_03_b_once.py`：`2ea473491f590893ad575b90a0ba42f932e37129`
5. `scripts/business_sql_snapshot.py`：`e7532b0a0242f1e3d3b047fdc03fca7ffc3ce7c6`

其余 E02/E03/E04/E05 及业务服务、Repository、模型、数据库迁移、配置、前端、依赖和 CI workflow 全部不改。不得改 PIT/发布原子性/来源校验/窗口预热/策略权重/候选身份/排序规则。保留所有之前的离线拒绝门禁，不做“审批接口”新框架。

## 1. W00 和阅读顺序

先 `git status --short --branch`、HEAD 和 origin/master；对比远端 GitHub master；除本轮负责人已下发的 `?? docs/tasks/BIZ-PERF-P1-04-PRETEST-01.md` 外存在脏文件时停止并报告，不覆盖用户修改。沙箱 `git ls-remote` 因 SSH 被拒则依负责人外层核验的基线继续，不能声称自己核实远端；不改 SSH/Git 配置、index、权限或仓库历史。

按 `AGENTS.md` 顺序阅读 `PROJECT_CHARTER.md`、`PROJECT_STATUS.md`、`PROJECT_ROADMAP.md`、`DECISION_LOG.md`、`docs/tasks/README.md`；再阅读股票机会发现 PRD、系统设计、`PROJECT_RULES.md`、`README.md`、`docs/tasks/BIZ-PERF-P1-04.md` 和 E02/E03/E04/E05 closeout；以**现有源码和测试**为准识别指标、证据结构和安全边界，勿凭旧报告推断当前真正的耗时热点。

## 2. PRETEST-A：已有测量输出的业务化“热点分析视图”（必须有代码）

新增**最多两个**只读 Python 模块，推荐单文件 `scripts/biz_perf_p1_04_pretest_report.py`，及对应 `tests/unit/test_biz_perf_p1_04_pretest_report.py`。仅从**现有完整的、明确为 `OFFLINE_FIXTURE` 的证据和 E02/E03 冻结解析/Replay/summary**中获取已支持的字段；不要自创日志格式、双写另一套事件总线、重实现 SHA/准入/审计/日志。直接复用现有 `scripts.biz_perf_p1_04_diagnostic`、`scripts.biz_perf_p1_04_measure_wiring` 的只读函数和类型；必要时先阅读原测试夹具及 `Replay.summary` 的真实输出结构。输入为显式 expected SHA 和新建的离线 fixture 目录或已经验证过的 JSON 对象，绝不自动扫描用户磁盘。

结果须支持以下归因视图，所有项目使用现有合同的真实字段名，**没有字段就明确 UNKNOWN/NOT_INSTRUMENTED 而不是 0**：
- `root_elapsed_ms`（从 create/claim 前到 Worker 返回边界）和 `post_root_validation_ms` 分离，后者不得混入根 Wall；
- `execute_claimed_job_ms` 是根 Wall 的子区间，绝不可相加；
- 阶段的 inclusive wall 可能重叠，禁止求和作为全局份额或排名结论；必要时仅按“离线样本阶段 inclusive 排序，非已证实瓶颈”表达；
- SQL execute 次数/耗时、驱动 FETCH 行数/耗时、进程 CPU、RSS 各自分列，明确 SQL+FETCH 可能重叠，RSS 不是阶段分配；`cpu_ms=0` 导出的比率为 `UNDEFINED`；
- 聚焦 `factors.input_verify`（若已有 stage 命名不同，基于代码映射并显式标注），`factors.compute`、`candidate_lookup_batch`、`candidate_store_batch`、`publication.verify` 等具体诊断位置；
- 允许给出 `investigation_priorities`（**待证实假设**），但拒绝声称速度提升、真实性能结果、真实资源状态、P95/P99、SQL 最优执行计划等没有凭据的结论。
- 报告固定 `source_evidence_kind=OFFLINE_FIXTURE`、`status=HYPOTHESIS_ONLY`、`hotspot_decision=NONE_PROVEN`、全部未审批门禁。输入损坏、重复键、非有限数、错误 SHA、跨根/缺结束/超界、不可信路径或证据缺失必须固定脱敏错误码拒绝，不能部分成功冒充完整结论。全部运行离线，CLI 如有仅允许 `summarize-offline` 并输出 bounded JSON 到 stdout，不创建报告文件、数据库或进程。

## 3. PRETEST-B：源代码可复核的三条性能假设与优先测试点

从当前源码**实际确认**，在 `docs/acceptance/BIZ_PERF_P1_04_PRETEST_01_REPORT.md` 中建立固定清单，逐条记录：源码路径/函数/具体调用点、可能的复杂度或 SQL 往返机制、当前证据是否支持、需要真实测量的指标、预期通过哪种事件区分假设。至少覆盖：
- 因子计算的历史窗口准备与 raw/input fingerprint 检验（例如 `FactorInputWindow._verify`，要阅读现有代码）；
- 候选是否已存在/已发布查找、批次存储及行级序列化路径（从 `PublicationWorkspace` 当前实现出发追踪，不要假定旧的“每 500 行一次查询”仍然成立）；
- 候选原子发布前后验证、SQL/FETCH、阶段边界重叠风险（从当前源码定位）。

要求区分 `CODE_OBSERVED`（源码确认）、`HYPOTHESIS`、`MEASURED_OFFLINE_FIXTURE`、`REAL_NOT_RUN`。如无法从现有证据判断哪条最慢，必须写 `HOTSPOT=NONE_PROVEN`。不要修改业务实现以追求一个凭空的“优化百分比”。

## 4. PRETEST-C：只提交“真实隔离测试申请草案”，不提供执行程序

新增 `docs/acceptance/BIZ_PERF_P1_04_ISOLATED_RUN_REQUEST_DRAFT.md`，按照现有 P1-04 W05 表格写成负责人可人工审阅的**单页或精简分节**申请：
- 范围：8 股，2025-01-01～2025-01-31，**同 900 日历日合成 Seed 规则**，原任务静态预期 5320 股日行但因子/派生表实际行数不得编造；根任务一条，一次尝试，失败、超时、未知 ACK 即停止，不自动补样；
- 五开关 false；模型/配置/设计 SHA/实施 SHA/数据及策略 fingerprint 固定；交易日、PIT、250 交易日预热、430 日历日回看、500 行候选批和 300 秒发布预算仅按原规则引用，不改变；
- 仅未来**全新隔离** Linux x86_64 + PG17 UUID 实例、物理 system identifier、专用 PGDATA、网络/cgroup/数据库所有权/清理权限，禁止复用用户生产或旧 PG；
- 预算草案：最多 20 分钟含末 5 分钟清理、Worker 3GiB、PG 4GiB、卷 10GiB、原始脱敏证据 10MiB；CPU/磁盘/中止条件待签字；
- 人工审批待填写：负责人批准、操作主体、窗口、独立审阅、精确 SHA 的真实 CI 证明、资源观测及卷归属、新建资源成本、清理负责人、异常人工处理和结束条件；
- 明列`B_GATE=NOT_APPROVED` / `TARGETED_PG17_GATE=NOT_APPROVED`，文档只是草案，绝不作为执行凭证。未来如要实际测量必须发起**新的明确用户授权请求**，同一任务不能自动切换到执行。

## 5. PRETEST-D：测试、回执和范围验收

先 RED 失败探针，再 GREEN，再补以下负例（至少 20 个有意义的针对性测试；不为凑数复制先前审计套件）：root/post 双计、子区间重复相加、阶段重叠、UNKNOWN vs 0、缺 CPU、零 CPU、缺 FETCH、SQL/FETCH 时间重叠、候选 lookup/store 阶段不全、完整 mock 证据、伪造对象、跨实施 SHA/UUID、缺行尾 LF、重复键、NaN、非有限、坏 digest、源角色/权限伪造、执行 CLI 拒绝、超大输入、旧 03-B 混入。是否覆盖取决于现有冻结证据能否支持，不要假造不存在的字段。禁止整包输出敏感原始事件。
测试须与 E05/E04/E03/E02 的指定安全离线模块、冻结 diagnostic/W04A/fake DB guard 做回归；Windows 本机**不要运行可能连接 DATABASE_URL 的全量 pytest**。只用 `python -B -m pytest` 运行确定不触及真实资源的测试，使用新系统临时目录。Windows 无 Ruff 可记录 ENV_BLOCKED，不安装/升级依赖；以精确 SHA 的 GitHub CI 校验 Ruff 和 Linux 完整回归。`git diff --check`、新增文件语法/空白、五 frozen Git blob SHA、原业务文件零 diff、工作区路径白名单必须逐一核对。

仅允许新增：
1. `docs/tasks/BIZ-PERF-P1-04-PRETEST-01.md`（本任务书）；
2. `scripts/biz_perf_p1_04_pretest_*.py`（不超过两份）；
3. `tests/unit/test_biz_perf_p1_04_pretest_*.py`（与源码对应）；
4. `docs/acceptance/BIZ_PERF_P1_04_PRETEST_01_REPORT.md`；
5. `docs/acceptance/BIZ_PERF_P1_04_ISOLATED_RUN_REQUEST_DRAFT.md`；
6. `docs/acceptance/BIZ_PERF_P1_04_PRETEST_01_CLOSEOUT.md`。

**严格不更改上述白名单以外任何跟踪文件**，不修改 `PROJECT_STATUS` 等历史/全局治理文件和现有 E05/E04/E03/E02 源码。交付须含源码、针对性测试、待证实热点清单和执行申请草案；不是只有文档、也不是新的权限/审计框架。

## 6. Codex GP 交付及后续审阅

本任务通过 Codex app-server `thread/start(projectId=GP)` 创建**真正归属 GP 的持久会话**，名称 `BIZ-PERF-P1-04 PRETEST-01 性能验证准备`，而不是独立 `codex exec`。在该会话中展示代码分析、RED→GREEN、测试统计和收尾回执。

验收的先后顺序：完成所有允许文件 → 运行针对性安全测试 → 5 frozen 和零业务 diff 审核 → 普通单次 `git commit` + 非 force `git push origin master`（若 Codex 沙箱内 `.git` 或 SSH 拒绝，保留工作区，报告阻断，交 ChatGPT 外层 PowerShell 安全提交推送）→ 核实远端精确 SHA → 观察该 SHA 主 CI / A4-1 / A4-2 / Publication → ChatGPT 独立审阅、决定是否收口或最小整改。

必须如实报告 `FINAL_SHA`、`PUSH`、`CI_RUN`、`TEST_COUNTS`、`FROZEN_5_SHA`、`REAL_PG17=NOT_RUN`、`REAL_WORKER=NOT_RUN`、`ROOT_ATTEMPTS=0`、`HOTSPOT=NONE_PROVEN`、`B_GATE=NOT_APPROVED`、`TARGETED_PG17_GATE=NOT_APPROVED`、`NEXT=CHATGPT_REVIEW_AND_OWNER_APPROVAL_DECISION`。

**本轮不是 E06：结束后必须停止安全框架类迭代。** 若代码与 CI 验收通过，下一步是负责人审阅是否批准一次隔离实际测量，而非自动再派一个 PRETEST-02。
