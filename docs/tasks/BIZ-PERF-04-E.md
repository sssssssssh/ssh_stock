# BIZ-PERF-04-E：统一证据合同与跨阶段证据包校验器

**任务编号：** BIZ-PERF-04-E\
**版本：** R0\
**日期：** 2026-11-06\
**仓库：** `sssssssssh/ssh_stock`\
**目标分支：** `master`\
**当前观察基线：** `946db5679a9cb2b7c12d9bd8ca035fe0f26f4bd8`\
**任务状态：** TASKBOOK_READY / IMPLEMENTATION_NOT_STARTED\
**实施授权：** 本文件仅定义下一阶段开发范围；Codex
开始实施前仍须遵守负责人最新指令。\
**提交推送：** 未授权自动 commit/push，须另行明确指示。

------------------------------------------------------------------------

## 1. 任务背景与目标

BIZ-PERF-04-A～04-D
已分别形成独立证据，但证据类型、身份字段和验收层级不同：

-   **04-A：** 合成测量器的 SQL 终态快照一致性合同；历史 Run
    `41991816127` 的 SELECT/UPDATE 逐条归属仍为
    `UNKNOWN`。离线合同通过不等于历史根任务问题已解决。
-   **04-B：** S1～S4
    确定性合成数据生成与流式校验；它证明合成文件生成合同，不证明
    PostgreSQL 装载、Worker 执行或真实行情语义。
-   **04-C：**
    资源、数据集、容量、性能资格、生产读取授权五类状态的独立合同；没有执行资源探针或容量实验，未评估字段必须继续保持
    `NOT_ASSESSED`。
-   **04-D：** Linux x86_64 / CPython 3.12.14 的 67 包完整 wheel
    锁与真实 Hosted Linux 安装。真实安装已在 Run `42156106471`
    完成，但当前归档文档仍保留安装前的 `NOT_RUN / NOT_VERIFIED`
    文字，需要追加实际运行证据。

**04-E 的唯一目标：** 建立一个只读、离线、确定性的 A～D
跨阶段证据清单（Evidence
Bundle）及校验器，验证证据文件的结构、摘要、身份引用和阶段语义边界，使不同类型的证据能够被统一检索和审计。

04-E 不是性能实验，不是容量
Gate，不是生产授权流程，也不是新的执行控制器。`bundle integrity = VALID`
只代表证据包结构和文件摘要一致，绝不代表 BIZ-PERF-04 整体性能通过。

## 2. 开发前必须完成的基线核验

### 2.1 Git 基线

开始前严格按 `AGENTS.md` 执行：

1.  `git status --short --branch`
2.  确认当前分支为 `master`。
3.  核对本地 `HEAD`、`origin/master`、GitHub `master`。
4.  不覆盖、不清理、不 stash、不 reset 用户已有改动。
5.  完整阅读
    `PROJECT_CHARTER.md`、`PROJECT_STATUS.md`、`PROJECT_ROADMAP.md`、`DECISION_LOG.md`、`docs/tasks/README.md`，再阅读相关
    PRD、系统设计、`PROJECT_RULES.md`、`README.md`。
6.  重新检查本任务涉及的代码、测试和证据文件；不得仅凭本任务书中的文件名猜测现状。

本任务书观察到的最新提交为
`946db5679a9cb2b7c12d9bd8ca035fe0f26f4bd8`，其只新增/更新了
`docs/acceptance/biz_perf_04_d_linux_install.md` 的归档内容。Codex
开始时必须重新核验，不能把该 SHA 当作永远有效的实时 HEAD。

### 2.2 最新提交 CI 前置门禁

截至本任务书编制时，精确 SHA `946db5679a9cb2b7c12d9bd8ca035fe0f26f4bd8`
的以下工作流仍在运行：

-   CI：Run `42156606243`
-   A4-2 isolated read experiments：Run `42156606260`

同一 SHA 的 Publication V1.3 Run `42156606217` 和 A4-1 Run `42156606225`
已为 `success`。

**实施前必须重新查询以上四个 Run。** 只有当前 SHA
所需工作流全部终结且应通过的工作流均为 `success`，才可进入 04-E
代码修改。若 CI 或 A4-2 失败、取消、超时，先停止 04-E
实施，单独报告原因；不得借用旧 SHA 的成功结果。

------------------------------------------------------------------------

## 3. 04-D 真实安装证据核对与归档前置任务

### 3.1 已核验的真实运行事实

GitHub Actions 精确记录：

  --------------------------------------------------------------------------------------------------------------------
  字段                                已核验值
  ----------------------------------- --------------------------------------------------------------------------------
  Workflow Run                        `42156106471`

  Run 状态                            `completed / success`

  Event                               `workflow_dispatch`

  Branch                              `master`

  Attempt                             `1`

  target SHA                          `ab5e29df5aa230076069dd587557720c2db382dc`

  Job                                 `installation`

  Job ID                              `127690531459`

  Artifact ID                         `13474492280`

  Artifact name                       `biz-perf-04-d-install-ab5e29df5aa230076069dd587557720c2db382dc-42156106471-1`

  Artifact 大小                       `5605 bytes`

  GitHub Artifact digest              `sha256:735addf5df05b36eba923ac4d8cbb257c8fafceb05a069c687ffba1fa67b0a13`

  Artifact 到期时间                   `2026-11-13T03:22:47Z`
  --------------------------------------------------------------------------------------------------------------------

Run URL：

`https://github.com/sssssssssh/ssh_stock/actions/runs/42156106471`

### 3.2 Artifact 内四份原始证据

必须从上述精确 Artifact 获取原件，解压后逐字节归档，不得手工重建或修改
JSON：

  --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
  文件                             SHA256                                                               核验内容
  -------------------------------- -------------------------------------------------------------------- --------------------------------------------------------------------------------
  `receipt.json`                   `c600d0468877d52c744371c7b1baaea5aa10b1f341228ec6a3b201abd6dec372`   `COMPLETE`、`target_installation=VERIFIED`、`transitive_lock_complete=true`、7
                                                                                                        个阶段均 PASS

  `runtime.json`                   `e2f525eab130f33b2a9e9c70e217e675d6f1a7e18d19e72ad4ef809787cf5f84`   CPython 3.12.14、Linux x86_64、64 bit、glibc 2.39、pip 25.0.1

  `dependency-verification.json`   `ecb21a5995585c5717cb78b5c86a28f3a6125f5b7841e7fdceed7d15169c5aaa`   expected/actual 均为 67、installed set verified、67 个发行包记录

  `tests.json`                     `7bb8ff898888eeab9826ee811f3057c365b89816a2e81df100c5d566c4ecf908`   148 passed、0 failed、0 errors、0 skipped
  --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

`dependency-verification.json` 中 `distributions` 必须为 67
项；`receipt.json` 的 `target_sha` 必须等于
`ab5e29df5aa230076069dd587557720c2db382dc`，`run_id`/`attempt`
必须分别为 `42156106471`/`1`。

### 3.3 归档方式

新增目录：

`docs/acceptance/biz_perf_04_d_runs/42156106471/`

其中只允许：

-   `receipt.json`
-   `runtime.json`
-   `dependency-verification.json`
-   `tests.json`
-   `artifact-index.json`

`artifact-index.json` 记录 Run、Job、Attempt、target SHA、Artifact
ID/name/size/digest/URL/到期时间，以及四份 JSON 的逐文件 SHA256。

要求：

1.  四份 JSON 必须与 Artifact 解压原件逐字节一致。
2.  不归档私有
    `install-report.json`、命令日志、stderr/stdout、堆栈、Wheelhouse、venv、Token、环境变量或任何凭据。
3.  不把 ZIP 二进制作为唯一证据；四份原始 JSON
    和索引应可在仓库中长期复核。
4.  不覆盖历史离线证据
    `docs/acceptance/biz_perf_04_d_validation.json`。该文件的
    `NOT_VERIFIED` 是安装前离线验证快照，应保留原样。
5.  对 `docs/acceptance/BIZ_PERF_04_D.md` 与
    `docs/acceptance/biz_perf_04_d_linux_install.md`
    采用追加式补充：记录实际 Run 的完成事实，并说明此前
    `NOT_RUN / NOT_VERIFIED` 是安装前记录，不能再作为当前最终结论。
6.  更新 `PROJECT_STATUS.md` 中 04-D 的当前状态：明确区分代码交付、真实
    Linux
    安装、负责人最终验收三种状态。没有负责人最终验收前，不擅自把任务状态写成
    `DONE`。

若 GitHub Artifact 无法下载、Artifact digest 或任一文件 SHA
不匹配，立即停止，不得从上一轮聊天摘要重建证据。

------------------------------------------------------------------------

## 4. 04-E 统一证据包设计

### 4.1 合同身份

-   新合同版本：`biz-perf-04-e.evidence-bundle.v1`
-   新校验报告版本：`biz-perf-04-e.validation.v1`
-   证据包是 append-only 的证据索引，不是执行授权、状态机或业务账本。
-   证据文件均通过仓库相对 POSIX 路径引用。
-   所有摘要基于原始文件字节计算 SHA256。
-   规范 JSON 摘要使用：
    `json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")`
-   计算 `bundle_sha256` 时排除 `bundle_sha256` 自身字段。
-   禁止
    NaN/Infinity、重复键、未知字段、重复路径、路径穿越、绝对路径、symlink、非普通文件和超出明确大小上限的输入。

### 4.2 A～D 固定证据清单

证据清单必须明确记录每个证据的
`stage`、`evidence_kind`、`schema`、`source_commit_sha`、`path`、`sha256`
和 `claim_scope`。字段名可由 Codex
根据现有项目风格确定，但必须形成严格、版本化、`extra-forbid`
的固定结构。

  ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
  阶段           源码身份                                               必须引用的仓库证据                                                 允许表达的事实                     必须保留的限制
  -------------- ------------------------------------------------------ ------------------------------------------------------------------ ---------------------------------- ------------------------------------------------------
  04-A           `9df4cfed0d0153b09b0f4038882fa8423fe732e1`             `biz_perf_04_a_offline.json`；`BIZ_PERF_04_A.md`                   SQL 终态快照合同与离线测试证据存在 历史 Run `41991816127` 的 SELECT/UPDATE 逐条归属仍
                                                                                                                                                                              UNKNOWN；不能声称历史根任务已修复或重新验收

  04-B           `decaaba86535575e307edd676221ec066517caf6`             `biz_perf_04_b_generation.json`、`biz_perf_04_b_validation.json`   S1～S4                             原始 JSONL 数据未归档；不能声称真实行情、PG
                                                                                                                                           合成数据生成元数据、数据集摘要和   装载、Worker 或容量测试通过
                                                                                                                                           413 项离线验证结果

  04-C           `c397821d45c755473bf627a40392d392bd1eab2b`             `biz_perf_04_c_validation.json`、`BIZ_PERF_04_C.md`                `biz-perf-04-c.status.v1` 合同及   没有资源探针或容量实验；未评估字段仍为
                                                                                                                                           442 项离线测试结果                 NOT_ASSESSED；不能把合同测试解释为性能资格或生产授权

  04-D           锁/验证器实现                                          第 3 节归档的四份原始 JSON 与                                      精确 Run 的 Linux 真实安装、67     不等于 PG/Worker/业务整链、容量、性能或生产验收
                 `4fe37aee77570b3377fb5ff41b85ab9e49fbbcef`；实际安装   `artifact-index.json`；`biz_perf_04_d_lock.json`                   包集合、pip check、148
                 Workflow target                                                                                                           项合同测试证据
                 `ab5e29df5aa230076069dd587557720c2db382dc`
  ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

注意：04-B 的 `dataset_sha256` 是合成文件数据身份；04-C 的
`dataset_sha256` 绑定状态合同输入；两者不可混用。04-D 的 `target_sha`
是安装执行的代码身份，不要求与 04-A～04-C 的历史源提交相同。

### 4.3 证据类型必须分开

至少区分以下证据类型，不能只用一个 `passed=true`：

-   `offline_contract_validation`
-   `synthetic_generation_metadata`
-   `historical_run_reference`
-   `runtime_installation_receipt`
-   `source_identity_reference`

每个证据条目必须说明它能支持什么结论、不能支持什么结论。没有真实运行的项目只能记录
`NOT_RUN` 或 `NOT_ASSESSED`，不得用缺字段、0、空数组或 skipped
伪装为成功。

### 4.4 阶段语义校验要求

校验器除验证摘要，还必须校验 A～D 的固定语义：

**04-A** - schema 必须为 `biz-perf-04-a.offline.v1`。 -
`historical_select_update_attribution` 必须继续为 `UNKNOWN`。 -
`performance_runs=0`、`database_connections=0`、`workflow_dispatches=0`
的历史记录不得被解释为性能实验通过。

**04-B** - generation schema 必须为 `biz04-b.offline-generation.v1`。 -
必须恰有 S1、S2、S3、S4 四档，不允许重复、缺失或额外档位。 - 每档
`dataset_sha256` 为 64 位小写
hex，`equal=true`，行数与既有四档合同一致。 - validation schema 必须为
`biz04-b.offline-validation.v1`；413 项测试 0
failures/errors/skipped；`large_generation_in_default_ci=false`、`worker_roots=0`、`database_connections=0`。 -
不要求仓库中存在 7.7 百万行的原始 JSONL 文件；不得把 manifest
元数据冒充原始数据复核。

**04-C** - schema 必须为 `biz04-c.offline-validation.v1`；442 项测试 0
failures/errors/skipped。 -
`worker_roots=0`、`database_connections=0`、`capacity_experiments=0`、`workflow_dispatches=0`
必须保持。 -
不能构造一个虚假的全量状态文档来冒充资源或容量评估；性能资格和生产读取授权不能被校验器提升为
true。

**04-D** -
`receipt.json`、`runtime.json`、`dependency-verification.json`、`tests.json`
四文件必须互相绑定同一 Run/Attempt/target SHA。 - receipt 必须
`COMPLETE`、`exit_code=0`、`target_installation=VERIFIED`、`transitive_lock_complete=true`，且七个阶段全为
PASS。 - runtime 必须为 CPython 3.12.14、Linux、x86_64、64 bit、glibc
版本不低于 2.28。 - dependency verification 必须 expected/actual 均为
67、`installed_set_verified=true`，发行包集合恰为 67。 - tests 必须为
148 passed，failed/errors/skipped 均为 0。 - `artifact-index.json`
必须与 GitHub Run/Artifact 的固定身份、大小和 digest 对应。 - 不将工具链
pip 版本计入 67 个业务发行包。

------------------------------------------------------------------------

## 5. 实现方案

### 5.1 允许新增文件

1.  `scripts/business_evidence_bundle.py`：标准库证据包校验器。
2.  `tests/unit/test_biz_perf_04_e.py`：04-E 单元与篡改测试。
3.  `docs/acceptance/biz_perf_04_e_bundle.json`：A～D 固定证据清单。
4.  `docs/acceptance/biz_perf_04_e_validation.json`：本轮校验器执行结果。
5.  `docs/acceptance/BIZ_PERF_04_E.md`：合同设计、字段语义、验证结果和边界。
6.  `docs/tasks/BIZ-PERF-04-E.md`：本任务书及执行回执。
7.  第 3 节定义的 04-D Run 原始证据归档文件。

允许追加更新： - `docs/acceptance/BIZ_PERF_04_D.md` -
`docs/acceptance/biz_perf_04_d_linux_install.md` - `PROJECT_STATUS.md` -
`PROJECT_RULES.md` - `docs/tasks/README.md`

除非负责人另行要求，不修改 PRD、系统设计、数据库
Schema、Alembic、业务后端、前端、策略配置、根依赖锁和既有 A～D 代码。

### 5.2 校验器职责

`business_evidence_bundle.py` 只允许使用 Python
标准库，不导入业务应用、SQLAlchemy、psycopg、FastAPI、Worker 或 Agent
模块。

建议接口：

``` bash
python -m scripts.business_evidence_bundle \
  --root . \
  --manifest docs/acceptance/biz_perf_04_e_bundle.json \
  --report docs/acceptance/biz_perf_04_e_validation.json
```

实现要求：

1.  读取固定 schema 的 bundle manifest。
2.  校验 manifest 的字段集合、类型、版本、路径唯一性、SHA256
    格式和规范摘要。
3.  对每个引用文件执行路径安全检查、文件类型检查、大小限制和原始字节
    SHA256 校验。
4.  解析 A～D 证据文件，执行第 4.4 节的阶段语义校验。
5.  检查跨文件身份：D 四份证据的 run_id、attempt、target_sha
    一致；artifact-index 与 receipt 一致；A～D
    源提交身份不被错误合并成一个 SHA。
6.  生成确定性 JSON 报告；`integrity` 只能表示 `VALID` 或失败，不输出
    `performance_pass=true`、`capacity_pass=true`、`production_authorized=true`
    等字段。
7.  报告写入采用同目录临时文件 +
    原子替换；验证失败时非零退出，不覆盖已有有效报告。
8.  不访问网络、不调用 GitHub API、不读取 `.env`、不连接数据库、不启动
    Worker/容器。
9.  不执行数据生成、SQL 计数、因子计算、回测、容量测试或性能测量。

### 5.3 报告语义

`biz_perf_04_e_validation.json` 的 `integrity=VALID` 只代表： - manifest
自身摘要正确； - 引用文件存在且摘要匹配； - A～D
的已知证据结构及身份关系符合合同； - 已知限制没有被篡改或提升。

报告必须显式列出非声明项，至少包括： -
`PERFORMANCE_ACCEPTANCE_NOT_CLAIMED` -
`CAPACITY_ACCEPTANCE_NOT_CLAIMED` -
`PRODUCTION_READ_AUTHORIZATION_NOT_CLAIMED` -
`BUSINESS_DATABASE_EXECUTION_NOT_PERFORMED` -
`WORKER_EXECUTION_NOT_PERFORMED`

不得设置统一的
`all_stages_passed`、`ready_for_capacity`、`release_ready` 或等价字段。

------------------------------------------------------------------------

## 6. 测试设计

新增测试必须先覆盖合法正例，再覆盖失败和篡改路径。不得通过降低旧断言、skip、xfail、吞异常或扩大容差制造通过。

### 6.1 正常路径

-   完整 A～D bundle 可稳定生成相同 canonical SHA256。
-   同一 manifest 重复校验结果逐字节一致。
-   D 四份原始 JSON 与 artifact-index 完全匹配。
-   A 的 UNKNOWN、B 的离线合成范围、C 的 NOT_ASSESSED、D 的真实安装
    VERIFIED 能同时保留，且互不覆盖。
-   合法输出不含任何性能、容量或生产准入字段。

### 6.2 负例与篡改

至少覆盖：

-   manifest 缺字段、额外字段、错误 schema、重复
    evidence、重复路径、错误 SHA 格式。
-   文件不存在、文件字节被修改、JSON 损坏、重复 JSON key、NaN/Infinity。
-   绝对路径、`..` 路径穿越、symlink、目录代替文件、超限文件。
-   A 的 UNKNOWN 被篡改为 PASS/true。
-   B 缺少某一 scale、增加未知 scale、重复 scale、`equal=false`、dataset
    SHA 格式错误、测试失败数非零。
-   C 把 NOT_ASSESSED 改为 true、capacity experiment
    改为非零、worker/database 计数改为非零。
-   D run_id、attempt、target_sha 任一不一致；receipt stage 缺失/非
    PASS；安装状态非 VERIFIED；67 包变为 66/68；安装集合 false；runtime
    Python/OS/arch/glibc 错误；148 项测试中任一 failed/error/skipped
    非零；artifact digest/size/ID 不一致。
-   将旧离线 `biz_perf_04_d_validation.json` 的 NOT_VERIFIED
    误当作真实安装结果，必须拒绝。
-   任意尝试添加性能通过、容量通过、生产授权的字段，必须拒绝。
-   验证失败时不覆盖已有合法报告，不输出成功退出码。

### 6.3 隔离检查

-   AST/源码检查确认新模块只使用标准库。
-   不导入 `backend`、`sqlalchemy`、`psycopg`、`fastapi`。
-   不读取 `DATABASE_URL`、`.env` 或业务 Token。
-   不进行网络请求、子进程业务执行、数据库连接或 Worker root。
-   不修改既有 8 份 Workflow，不新增第 9 份 Workflow，不改
    `test_a4_ci_governance.py` 的 Workflow 白名单。

------------------------------------------------------------------------

## 7. 验证命令与验收门槛

先运行新增测试，再运行 A～D 相关测试：

``` bash
python -m pytest -q tests/unit/test_biz_perf_04_e.py

python -m pytest -q \
  tests/unit/test_biz_perf_04_a.py \
  tests/unit/test_biz_perf_04_b.py \
  tests/unit/test_biz_perf_04_c.py \
  tests/unit/test_biz_perf_04_d.py \
  tests/unit/test_biz_perf_04_d_linux_install.py \
  tests/unit/test_biz_perf_04_e.py

python -m ruff check \
  scripts/business_evidence_bundle.py \
  tests/unit/test_biz_perf_04_e.py

git diff --check
```

验收要求：

1.  新增 04-E 测试全部通过，0 failed/errors/skipped。
2.  A～D 原有合同测试全部通过，不删改、不跳过原测试。
3.  Ruff 与 `git diff --check` 通过。
4.  `biz_perf_04_e_validation.json` 的
    `integrity=VALID`，并且摘要可重复复算。
5.  04-D 原始四份 JSON 的逐字节 SHA 与 Artifact 一致。
6.  04-A～04-D 原文件、旧 manifest、历史 Run、锁文件、原 Workflow
    和原测试断言未被重写。
7.  不触发新性能实验，不新增 Workflow，不连接业务数据库。
8.  最新 master 的普通 CI 结果必须绑定本次精确提交 SHA；不能借用历史
    CI。
9.  未执行项必须记录 `NOT_RUN`，未评估项必须记录 `NOT_ASSESSED`。

------------------------------------------------------------------------

## 8. 严格禁止事项

本任务不授权以下操作：

-   任何生产数据库、云端业务数据库或用户数据访问。
-   PostgreSQL 启动、迁移、DDL/DML、数据装载、全量重算。
-   Worker、Scheduler、根任务、回测、模拟持仓执行。
-   Docker/容器创建、性能探针、容量实验、百万行测量。
-   04-A 历史根任务重跑或 SQL 归属推断。
-   04-B 原始 S1～S4 大文件重新生成或数据库装载。
-   04-C 资源探针、容量状态转换、性能资格或生产读取授权。
-   04-D 重复下载/安装 67 包、重复 dispatch、rerun 或修改原 Workflow。
-   GitHub
    Environment、Secrets、Variables、reviewer、分支保护或其他仓库设置修改。
-   新增第九份 Workflow、修改现有 Workflow 触发器或扩展高成本执行路径。
-   修改股票策略、因子、金融公式、PIT、发布、Schema、依赖锁或部署入口。
-   自动 commit、push、merge、创建分支或清理用户工作区。

------------------------------------------------------------------------

## 9. 交付清单

Codex 最终必须提交以下审阅材料：

1.  修改前 HEAD / origin/master / GitHub master 与工作区状态。
2.  最新提交四条工作流的精确 Run 状态。
3.  04-D Run/Artifact 的核验结果、原始 JSON 归档路径及每份 SHA256。
4.  新增/修改文件清单、`git diff --stat`、完整 diff。
5.  新合同 schema、字段说明、canonical SHA 计算规则。
6.  新增测试统计、A～D 相关回归统计、Ruff、diff 检查结果。
7.  04-E 校验报告及明确的非声明项。
8.  未完成项、风险、回滚方法和下一步建议。
9.  明确说明本轮没有执行数据库、Worker、容量、性能或生产操作。

完成本地实现和验证后停止等待负责人审阅。除非负责人再次明确要求，不提交、不推送、不
dispatch。

------------------------------------------------------------------------

## 10. 退出标准与后续阶段边界

04-E 只有在以下条件同时满足后才可申请验收：

-   04-D 实际 Run 证据已追加归档，原始证据 SHA 完整匹配。
-   A～D 证据包结构、身份和语义均通过校验。
-   篡改、缺失、错身份和越权状态负例全部拒绝。
-   A～D 历史实现、原始工件和限制未被覆盖。
-   普通工程回归通过，完整 diff 可审阅。

04-E 完成只表示**跨阶段证据索引与完整性校验能力可用**。它不关闭
BIZ-PERF-03-A 的 PARTIAL，不代表 BIZ-PERF-04 的容量/性能验收完成，不授予
P2/P3、生产读取或发布资格。

04-F、正式容量/性能实验、真实业务数据库操作和部署现场验证均保持独立任务、独立方案和独立授权，不因本任务完成自动启动。


## 执行回执（2026-11-06）

负责人最新明确指令“根据任务书进行修改，推代码”授权本轮master实现和正常提交推送，
覆盖本附件中的默认禁止自动提交；不扩展为实验、生产、设置或04-F授权。
本文件保留原任务书内容（仅清理表格行尾空白），以下只追加实际执行事实。

### 基线与前置

修改前HEAD/origin/master/实时GitHub master均为946db5679a9cb2b7c12d9bd8ca035fe0f26f4bd8，CLEAN。
等待基线主CI终结后才写入源码，四条工作流同SHA均completed/success：
CI42156606243、A4-2 42156606260、Publication42156606217、A4-1 42156606225。
主CI test Job成功；跳过的实验不视为通过。GitHub连接器传输失败，改用只读官方API，
凭据只在内存中使用，下载存储重定向不携带GitHub Authorization。

### 交付范围与合同

新增标准库校验器、108项离线测试、12项固定证据manifest、可复算validation报告、
04-E设计说明、本任务回执、04-D原件4JSON及artifact-index。
追加PROJECT_STATUS、PROJECT_RULES、任务README和两份D归档说明；
不修改原8份Workflow、白名单、A～D代码/旧测试、旧锁/manifest/validation、PRD/设计/README或业务文件。
合同与字段、固定源码身份、canonical JSON摘要、输入上限、失败关闭及原子输出详见
[04-E设计](../acceptance/BIZ_PERF_04_E.md)。完整diff在交付时提供，不把当前文件自身最终SHA追填为实时基线。

04-D原始Artifact13474492280（Run42156106471/Job127690531459/attempt1）的ZIP与四份JSON
已从GitHub原件实际下载核对；四份归档逐字节一致，文件摘要见
[artifact-index](../acceptance/biz_perf_04_d_runs/42156106471/artifact-index.json)。
原件target为ab5e29df5aa230076069dd587557720c2db382dc，真实安装VERIFIED/完整67包。
不补造runtime/tests/dependency中不存在的Run字段，使用同工件固定摘要与索引绑定。
旧离线NOT_VERIFIED保持原样，04-D负责人最终验收REVIEW_PENDING，不自动DONE。

### 实际本机验证

| 检查 | 实际结果 |
| --- | --- |
| 新04-E测试 | 最终108 passed，0 failures/errors/skipped，真实平台Windows/Git LF原字节副本 |
| 可执行A/C/D/E子集 | 319 passed，0 failures/errors/skipped，34.77秒；其中108项为E，不能重复累计 |
| 子集分布 | A34、C29、D22、D Linux126、E108 |
| 任务书全A～E命令 | 旧04-B import resource触发1个收集错误；不是PASS，没有修改/跳过旧断言 |
| 确定性报告 | integrity=VALID；同manifest两次校验/归档报告逐字节一致 |
| Ruff | 新模块与新测试PASS，exit 0 |
| Diff/范围检查 | 工作区及暂存Diff检查PASS，exit 0；精确16文件，保护文件不变，四原件暂存Git blob摘要一致 |
| 新提交Linux普通CI | PENDING；推送后仅查询自动运行的精确SHA结果，未完成前不借用基线成功 |

本机第一次E回归97 passed/3 failed，原因为Git archive受到本机core.autocrlf影响，
历史证据字节变成CRLF。随后仅在忽略目录重新物化Git原始blob，并逐项确认与git show相同；
没有修改历史文件或把Windows执行伪装成Linux。此后100项以及追加边界后的108项均通过。
旧04-B的resource限制保留原失败，不创建替代resource模块、skip或xfail。

测试覆盖manifest缺失/额外/错版本/重复/path/hash、JSON重复键/非有限数/损坏、路径穿越/
symlink与大小、A UNKNOWN提升、B四档缺失重复/行数/哈希/离线限制、C执行/授权提升、
D Run/Attempt/SHA/平台/七阶段/67包/版本/哈希/148测试/Artifact错身份，
旧NOT_VERIFIED冒充安装、报告覆盖输入/越权目标、原子替换失败及重复结果稳定性。
Windows symlink能力使用显式mock验证拒绝；Linux分支实际创建symlink，不能把mock当Linux实测。

### 交付状态、风险与回滚

IMPLEMENTED / REVIEW_PENDING；仅证据完整性VALID，不设置性能、容量或生产准入字段。
最终完整Linux回归必须绑定本次提交；未核实时保留PENDING，不标04-E DONE。
不为追填本文件自身SHA连续追加提交；提交SHA、普通CI链接和实时结果随最终交付说明提供。
Windows CRLF checkout应失败关闭，使用Git原字节LF checkout；不静默换行归一化。
GitHub工件有到期日，但原始四JSON及索引已经按字节长期归档；未归档的私有pip report
和04-B原JSONL仍不作重建或额外事实声明。
正常revert本轮独立提交可撤回新增校验入口；不重写历史或改写原件，保留Git可审计历史。
下一项仅精确提交普通CI和负责人审阅，不进入04-F或新实验。

本轮没有数据库访问/迁移、PG/Worker/Scheduler/容器启动、S1～S4大文件重生成、
重复67包安装、容量/性能/生产操作、Environment/Secrets/Variables/审批设置或dispatch/rerun。
BIZ-PERF-03-A/R1继续PARTIAL，B0 WITHDRAWN与金融/PIT/发布/授权边界不变。
