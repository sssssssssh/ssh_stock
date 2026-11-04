> 历史快照：负责人确认前的 W00 审计交付。后续实施状态见 ../tasks/CI-OPT-01.md；本页的“尚未修改”仅指 W00 交付当时。

# CI-OPT-01 W00 审计与实施方案（待负责人确认）

审计日期：2026-11-03，Asia/Shanghai。范围：只读仓库及 GitHub 工程证据审计。
本文件不是实施验收，不构成性能实验、生产操作或后续阶段授权。

## 1. 基线与结论

- 本地分支为 `master`；HEAD、origin/master、GitHub master 均为 `e697fc80a098726f4e73f04ac71f5eb6cfb62b03`。
- 开始时工作区干净。已按 AGENTS 顺序阅读五份治理文件，再核查相关 PRD、系统设计、PROJECT_RULES、README 和本任务书。
- 当前六份 Workflow 中，四份对普通 master 文档提交也启动检查；另外两份已有路径过滤。没有 schedule、workflow_run、repository_dispatch 或 pull_request_target 触发。
- 最近三次普通 push 的主 CI 约 63–65 分钟，全量 pytest 步骤约 50–52 分钟，是主要耗时来源。依赖安装、Docker 和前端不是这三次的主要瓶颈。
- 不能只给 ci.yml 加 `paths-ignore`：实际 Required Checks 未能读取，而且 A4-2 的普通合同检查单独约 9 分钟，仍会拖慢文档反馈。
- 推荐阶段 A 采用精确文档白名单、保留现有 Workflow/Job 名称的步骤级守卫、真实静态检查和失败闭合汇总；不在此阶段拆分全量测试或改 pytest 收集。
- **存在实施前合同冲突**：旧测试要求历史 Workflow 几乎整体相等，且 test Job 有精确摘要固定。必须先由负责人确认最小编排合同适配范围，否则不能安全实施 W01。不能把这类失败当作已通过或通过改历史 SHA 规避。
- W00 已交付供审阅；W01–W03 尚未实施，W04 并行化 DEFERRED。业务主线及 BIZ-PERF-03-A-R1 的 PARTIAL 保持不变。

## 2. 实测耗时：三次普通提交

来源：GitHub Actions Run、Job、Step API 起止时间戳；全部为 push / attempt 1 / completed / success。
Run 总时长采用 created_at 到 updated_at，表示观测窗口，可能含排队/尾部更新；Job/Step 使用 started_at 到 completed_at。
各列是同一 test Job 内步骤耗时，不可再与并行 Job 时长相加当作 Workflow walltime。

| 指标 | 32cf8f43：仅 PROJECT_STATUS | 16ef3062：R1 代码修复 | e697fc80：六份证据/治理文档 |
| --- | ---: | ---: | ---: |
| CI Run ID | 41414072689 | 41558957304 | 41571974306 |
| Run 观测时长 | 65分11秒 | 62分43秒 | 65分06秒 |
| test Job 时长 | 65分08秒 | 62分39秒 | 65分02秒 |
| 全量 pytest Step 23 | 52分14秒 | 50分08秒 | 52分02秒 |
| pip 升级 + lock 安装 | 1 + 19秒 | 3 + 24秒 | 2 + 20秒 |
| PostgreSQL 服务初始化 | 14秒 | 13秒 | 13秒 |
| 另一个物理隔离 marked PG17 创建步骤 | 2秒 | 3秒 | 2秒 |
| Alembic 五个独立步骤合计 | 7秒 | 7秒 | 8秒 |
| compose config / build | 0 / 35秒 | 1 / 45秒 | 1 / 37秒 |
| Worker 队列与原子发布容器验收 | 24秒 | 25秒 | 26秒 |
| npm ci | 5秒 | 6秒 | 6秒 |
| 前端 coverage / build | 13 / 13秒 | 13 / 12秒 | 13 / 13秒 |
| 两组浏览器步骤合计 | 49秒 | 48秒 | 51秒 |
| test Job 的 upload-artifact 步骤合计 | 18秒 | 12秒 | 15秒 |

Alembic 合计为 Step 12/13/14/25/26；仅指隔离 CI 合成库中的 upgrade/downgrade/current/heads，不授权本地或业务库执行降级。
artifact 为主 test Job 的 13 个上传步骤，不是全仓所有并行 Job 上传耗时。API 秒级时间戳的 0 秒不代表没有运行。

全量 pytest 时间戳（UTC）：

| SHA | Step started_at | Step completed_at |
| --- | --- | --- |
| 32cf8f43 | 2026-11-02T08:44:34Z | 2026-11-02T09:36:48Z |
| 16ef3062 | 2026-11-03T01:28:47Z | 2026-11-03T02:18:55Z |
| e697fc80 | 2026-11-03T03:34:06Z | 2026-11-03T04:26:08Z |

e697fc80 的原始 Job 日志另确认：`5347 passed, 816 warnings in 3102.75s`，coverage 90.02%，原阈值 70%。
pytest 自报时间与 Step walltime 有进程收尾差异；16ef3062 的 2990.28 秒是 pytest 自报，不是该 Step API 的 3008 秒。不能混用。

三次提交的其他 Workflow Run 观测时长（同样按 created_at→updated_at）：

| Workflow | 32cf8f43 | 16ef3062 | e697fc80 |
| --- | --- | --- | --- |
| A4-1 | 41414072644 / 3分01秒 | 41558957308 / 2分54秒 | 41571974387 / 2分00秒 |
| A4-2 | 41414072701 / 6分07秒 | 41558957295 / 6分42秒 | 41571974396 / 8分49秒 |
| Publication | 41414072660 / 2分38秒 | 41558957367 / 2分42秒 | 41571974264 / 3分01秒 |

这些 Workflow 彼此并行，不能把该表加总当作单次 push 的 walltime。最新文档提交的主要自动 Job：

| Workflow / Job | Run ID | Run 观测时长 | 实际主要 Job 时长 | 专项实验 |
| --- | --- | ---: | ---: | --- |
| A4-1 / contracts | 41571974387 | 2分00秒 | 1分57秒 | isolated-baseline SKIPPED |
| A4-2 / contract-and-safety | 41571974396 | 8分49秒 | 8分45秒 | laboratory / formal gate SKIPPED |
| Publication / contracts | 41571974264 | 3分01秒 | 2分57秒 | candidate-performance SKIPPED |
| CI / workflow-contracts | 41571974306 | 与主 CI 同一次运行 | 34秒 | 不执行专项实验 |
| CI / dependency-audit | 同上 | 同上 | 20秒 | 不执行专项实验 |
| CI / lookup-diagnosis | 同上 | 同上 | 1分39秒 | 历史 P0 证据重放，不是新容量验收 |

三个样本的主 CI Run 观测时长中位数为 65分06秒；样本不足以宣称稳定 P95。候选耗时、doc-only ≤5 分钟与完整回归等价性均 PENDING。

链接：

- [基线文档主 CI](https://github.com/sssssssssh/ssh_stock/actions/runs/41571974306)
- [R1 代码修复主 CI](https://github.com/sssssssssh/ssh_stock/actions/runs/41558957304)
- [此前状态文档主 CI](https://github.com/sssssssssh/ssh_stock/actions/runs/41414072689)
- [最新 A4-1](https://github.com/sssssssssh/ssh_stock/actions/runs/41571974387)
- [最新 A4-2](https://github.com/sssssssssh/ssh_stock/actions/runs/41571974396)
- [最新 Publication](https://github.com/sssssssssh/ssh_stock/actions/runs/41571974264)

## 3. 六份 Workflow 的触发与依赖盘点

| 文件 | 自动触发 | 手动触发 | 当前路径过滤 | 主要 Job 依赖关系 |
| --- | --- | --- | --- | --- |
| ci.yml | 所有 push、pull_request | experiment=none/capacity/a4231，加五项授权输入 | 无 | 四个独立自动根 Job；authorize → lookup-tail-attribution；authorize + lookup-diagnosis → capacity；test + capacity + lookup-diagnosis + dependency-audit → publication-release-gate |
| ab-read-a4-baseline.yml | master push、所有 PR | 五项授权输入 | 无 | authorize → contracts → isolated-baseline；普通事件 authorize 跳过后 contracts 仍运行 |
| ab-read-a4-2.yml | master push、所有 PR | 五项授权输入 | 无 | authorize → contract-and-safety → laboratory；contract-and-safety + laboratory → a42-acceptance-gate |
| publication-v13.yml | master push、所有 PR | 五项授权输入 | 无 | authorize → contracts → candidate-performance |
| a4232-statistics-tail-diagnostic.yml | master push、PR | 五项授权输入 | 该 Workflow、scripts/*a4232*.py、tests/**/test_*a4232.py、docs/acceptance/*a4_2_3_2* | authorize → contracts → attribution |
| a4233-observer-contracts.yml | master push、PR | 无 | 对应 a4233/a42331/a4234/a42341 脚本、测试、验收文档、该 Workflow | 单一 contracts Job |

“五项授权输入”为 target_sha、confirm_expensive_run、run_reason、protocol_id、protocol_sha256；确认默认 false。

Job 清单及执行条件补充：

- CI 自动根 Job：workflow-contracts（Python 静态合同与 Ruff）、dependency-audit（锁定 npm 审计）、lookup-diagnosis（PG17 小测试及固定历史证据重放）、test（完整 Python/PG17/Alembic/Docker/前端/浏览器串行）。
- CI authorize：仅 workflow_dispatch 且 experiment != none。lookup-tail-attribution：还要求 a4231、固定单次 protocol ID；capacity：还要求 capacity、capacity_ready=true。两者均要求确认、精确 SHA、master、attempt 1。
- publication-release-gate：always + 手动 capacity + 明确确认；即使上游失败或缺证据也应运行并拒绝，不是 success-only 跳过。
- CI ui-visual-acceptance：仅遗留 codex/ui-visual-upgrade 的 push 或该分支指向 master 的 PR；当前 master push 不运行。本轮不顺带删除该定义。
- A4-1/A4-2/Publication/A4232 的 contracts：always、未取消、普通事件或手动授权成功。普通事件不运行 authorize，却可正常运行低成本合同。
- A4-1 isolated-baseline、A4-2 laboratory、Publication candidate-performance、A4232 attribution：有效手动授权后才可执行，均有 master / 精确 SHA / attempt 1 / 确认条件；A4232 另有固定单次 ID。
- a42-acceptance-gate：always + 手动确认；拒绝失败、跳过、取消及不完整证据。
- A4233 contracts：相关路径命中后无额外 Job 条件，执行小 PG17、Observer/Archive/安全合同与脱敏证据。

并发：五份可手动实验的 Workflow 共用手动组 ssh-stock-a4-expensive，cancel-in-progress=false；普通事件组包含 workflow + run_id，因此不同 push 不会互相取消。A4233 也按 run_id 分组。阶段 A 不改变这些并发/取消语义。

## 4. Required Checks、权限、审批与 Artifact

| 核查项 | 结果 | 处理原则 |
| --- | --- | --- |
| master Branch Protection | UNKNOWN；GitHub API 返回 403 Resource not accessible by integration | 不能宣称没有必需检查；不做 Workflow 级 paths-ignore，不移除或重命名现有 Job |
| 仓库可见 Rulesets | API 返回空列表 | 仅表示本连接可见列表为空，不能替代 Branch Protection 或组织继承规则核查 |
| Environment 实际 required reviewers / prevent self-review / branch 限制 | UNKNOWN；连接器不支持该资源读取 | YAML 的 environment 名不等于审批已配置，须管理员核查 |
| YAML 审批环境 | a4-expensive-measurements | 所有既有 authorize 与专项性能 Job 的环境声明原样保留 |
| 默认权限 | contents: read；CI lookup-diagnosis 另 actions: read | 不增加写权限、生产 Secrets 或外部不可信 action |
| 额外管理员确认 | A4_REVIEW_POLICY_ACK == a4-ci-1.0-reviewed | 保留冻结 guard 的显式拒绝逻辑；本轮不修改仓库变量 |

仍需管理员确认 Environment 的 Workflow：CI、A4-1、A4-2、Publication V1.3、A4232；A4233 本身没有性能审批环境。只读审计无法证明它们的审批者已配置。

稳定检查名保留：CI 下 test / workflow-contracts / dependency-audit / lookup-diagnosis；A4-1 与 Publication 的 contracts；A4-2 的 contract-and-safety；现有正式 release gate 名及依赖不变。相同 contracts 名在多个 Workflow 出现，实际规则如何绑定仍 UNKNOWN，不擅自改名消歧。

GitHub 官方说明：Workflow 被路径过滤跳过可能令必需检查 Pending；Job 条件跳过与真正执行检查并不等价，失败上游也可能让依赖 Job 跳过。因此必须验证实际检查配置和失败闭合，而不是以 skipped 视为全量验证通过。
参考：[GitHub Required Checks 故障说明](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks)。

已核查的 composite actions：

- a421-pg：CI 独占 PG17 容器，read 默认 2CPU/3GB；loopback 端口、测试库命名、Run/attempt/job 标签、marker 与 pg_controldata system ID；verified_test_url 验证身份。
- a4-governance：本地 guard.py + policy.json；验证手动事件、确认、40 位精确 SHA、master、attempt、仓库、管理员 ACK、原因、固定 protocol/source hash、冻结生产路径及证据输入。
- A4231/A4232 历史单次 token 已消费，guard 明确拒绝；不能因新 CI 路由重新开放。
- a4-cleanup/a4-finish：仅清理本次拥有的容器，记录真实执行/清理状态；不是容量验收凭证。

Artifact 必须保持的契约：

- 正常完整路径仍生成原 exact-SHA + attempt 的 JUnit、安全状态、core、audit、lookup、queue、浏览器、迁移、保留策略等收据；原 cleanup/finalize/脱敏顺序不能改变。
- 正式 Gate 读取 a421-* 等固定证据、所有必需上游 success、容量层级和实际样本；缺失或失败拒绝。scripts/ci_release_gate_v14_a4_2_1.py、a42_receipt_contract.py 及金融/发布验证器不改。
- doc-only 使用单独 ci-opt 文档检查收据，明确 full_regression=NOT_RUN、performance_eligible=false；不得生成伪造的 m17_1_2-full.xml、a421-core、安全状态或容量证据。
- 手动路径一律走原完整检查和原授权，不能凭 doc-only 收据满足 release gate。
- 不缓存 .env、数据库、私有证据或 Token。阶段 A 不做新的缓存策略。

## 5. 风险文件分类方案

分类针对完整文件变更集和修改内容，不看 docs: 标题。只有明确允许、类型为普通文件的修改才可 doc-only；任一文件高风险则整个提交 full。

| 类别 | 拟定路由 | 已核查理由/约束 |
| --- | --- | --- |
| backend、migrations、Python 测试、requirements.lock、pyproject、alembic.ini | FULL | 全量 pytest、PG17、迁移、发布/Worker、覆盖率原样保留 |
| frontend、package-lock、前端测试 | FULL（阶段 A 保守跨栈） | 现有 Docker/浏览器跨栈耦合；此阶段不拆组 |
| Workflow/actions、分类器、测试治理、授权 policy | FULL + Workflow/guard 合同 | 分类器不得将自身修改放入快速路径 |
| config/strategy.yaml、PIT/schema/金融/身份/Golden/fixture/SQL/来源规范 | FULL | 无论扩展名是否 Markdown/JSON |
| PROJECT_RULES、PRD、系统设计、AGENTS | FULL | 业务/执行权威文档；原 source guards 的 AUTHORITY 与 tests/unit/test_a42361_source_entrypoints.py 等明确引用 |
| 历史 manifest/protocol、source snapshot、验收 JSON 与 fixture | 默认 FULL | a4235/a4236 系列读取 manifest/hash；policy 固定 protocol Markdown SHA，不能把 docs/acceptance/** 一律免测 |
| 普通 README 说明段落 | 条件 DOC_ONLY | scripts/data_queue_container_acceptance.py 打包 README，source guards 也登记 README；必须保护命令/配置/契约段，不能对整个 README 无条件免测 |
| PROJECT_STATUS / ROADMAP / CHARTER / DECISION_LOG / tasks README | 条件 DOC_ONLY + 治理一致性 | 状态/说明更新可快；权限边界、业务定义或契约变更进 FULL；状态不得把 PARTIAL 改成无证据 PASS |
| biz_perf_03_a_r1/verification.json | 条件 DOC_ONLY + 精确证据校验 | 仅允许已登记报告元数据/CI 事实字段；不开放任意验收 JSON，不允许改冻结哈希、身份或权限字段 |
| 未登记文件、新增不明路径、重命名、删除、大小写冲突、symlink、比较失败 | FULL | 不猜测安全性；分类结果写明原因 |

README 的处理不是“执行任意 Markdown 代码块”，而是将可改说明块与受保护结构/命令投影显式登记；无法证明受保护部分没变则 FULL。W01 提交具体白名单和正/负例供审阅，不自动泛化目录规则。T01 仅证明普通说明修改，不授权 README 中任意安全口径变化免测。

JSON 静态校验包括语法、必要字段、SHA/Run/attempt 格式、证据状态及链接一致性；已有历史记录只读，不自动改写。远程不可访问的证据标 UNKNOWN，不伪造成功。

## 6. 推荐最小实施方案（尚未授权执行）

### W01：阶段 A 安全分流

1. 新增只读分类器和显式 policy。checkout 保留足够历史；push 比较 before..after 全集；PR 使用实际 base/head 与 merge-base。使用 Git -z 解析路径，不将文件名/PR 输入拼进 shell。
2. before 全零、force push/非祖先、缺 Git 对象、差异读取/分页/API 失败、空/未知输出均 FULL；分类器自身无法运行时也不能令重步骤被跳过。无法保证完整比较就不走快速路径。
3. 在原自动 Job checkout 后加入共用 scope/静态检查入口，不引入外部写权限。只在确认 DOC_ONLY 且静态检查成功后跳过该 Job 的重步骤；保持既有 Workflow 与 Job 名称。
4. main test 保留原 Job 身份与现有重步骤次序，对 pytest、迁移、marked PG、Docker、浏览器、完整证据出口加统一 full 守卫。FULL 路径应与原命令、环境、插件、阈值、超时和证据等价。
5. 为减小改动，主 test Job 原 PostgreSQL service 定义先保留，文档路径仍有约十余秒的服务初始化，但不迁移/计算/测试数据库。此方案不是“零容器文档 CI”；避免为省十余秒搬移整个 Job 和身份契约。若要求完全不启动 PG，需要另行评审 Job 拆分，不混入本次最小方案。
6. A4-1/A4-2/Publication 的普通合同 Job 也加相同安全分流，否则 A4-2 仍约 9 分钟。doc-only 实际运行静态检查，重 PG/pytest 步骤 NOT_RUN；FULL 与手动路径仍跑全部原合同。
7. 保留 CI workflow-contracts（34秒）及 dependency-audit（20秒）作为低成本安全反馈，避免阶段 A 不必要改动。lookup-diagnosis 的 doc-only 分支只生成明确的文档检查收据，不伪称诊断或 capacity_ready。
8. 新增 always 汇总检查用于报告分类与真实结果；已有稳定 Job 在文档模式实际执行校验而非空壳 success。无需以重命名 Required Checks 为前提上线，但实际管理员规则仍应核实。
9. FULL 所需任一 Job/关键步骤 failure/cancelled/skipped/缺收据，汇总必须非成功；doc-only 仅允许预期重步骤 NOT_RUN，静态检查必须 success。整个运行取消时不能留下全量成功凭证。
10. 所有 workflow_dispatch 强制 full/原协议路径；既有实验 authorize、environment、protocol、矩阵、预算、门禁 needs、cleanup/finalize 不改。正式 Gate 仍拒绝缺少容量实测。

不使用全局 paths-ignore，不加 [skip ci]，不改取消策略，不添加新分支，不在阶段 A 删除重复或慢测试，不使用 pytest-xdist。

### 必须先确认的旧合同冲突

以下不是业务失败，而是旧编排合同与本次目标的实际冲突：

- tests/unit/test_a4_ci_governance.py::test_only_reviewed_job_conditions_change_from_ci_1_0：将 Workflow 与 d123bdad 历史对象整体比较，仅允许少量 if 变化。新增 scope/静态步骤也会失败。
- scripts/a42331_ci_contract.py::normalize_test_job：固定 test Job 摘要 `701504087872320ae808129f1526cac6bebdda2198aea320048444cd024e5a9a`，任何新步骤/守卫都会触发 A42331_UNREVIEWED_CI_TEST_JOB。
- test_ci_l0_authorization_and_formal_gate_trigger_matrix：要求四个自动 Job 无 needs 且所有普通/手动组合都可运行；方案保留其根 Job 结构，不能为了分流误改成只在上游成功时才运行。

任务书既要求不改原测试，又要求 Workflow 改造及新增路由测试。严格一字不改编排冻结断言时无法同时完成。建议负责人确认：**只对 Workflow 编排合同做版本化适配，保留历史版完整正/负例与 Git 对象，增加当前版路由/重步骤等价与失败闭合断言；不修改金融/PIT/发布/Owner/未知 ACK 断言。**
具体修改需在实施 diff 中精确列出，不用简单更新摘要或放宽整目录来制造通过，不改历史 manifest、历史提交或 protocol。若负责人不批准该最小适配，W01 保持 BLOCKED，只交付 W00；不偷偷改收集插件把冲突测试挪走。

### W02：新增触发、安全与等价测试

| 测试 | 计划证明 |
| --- | --- |
| T01 | README 普通说明 DOC_ONLY，静态检查通过；full pytest/Docker build 未执行；旧检查名仍真实完成 |
| T02 | STATUS + 指定 verification JSON 执行治理/证据校验；修改安全字段则 FULL 或拒绝 |
| T03 | 金融/发布/Worker/测试变更全量 Python、PG17、迁移、原合同 |
| T04 | 锁定依赖与迁移变更 FULL，版本/schema 不变 |
| T05 | 前端变更 FULL，coverage/build/browser 全保留 |
| T06 | Workflow/guard/policy FULL；所有未授权专项实验继续拒绝 |
| T07 | docs + backend 混合 FULL |
| T08 | 未知、大小写、改名、删除、symlink、diff/API 不完整 FULL |
| T09 | push 多提交/before 全零/强推/PR merge-base/手动事件均无绕过 |
| T10 | 分类器失败、上游取消/跳过/失败/收据缺失不会被汇总成通过 |
| T11 | FULL 原命令/插件/test node IDs 不减少；新增测试另计；coverage 仍≥70% |
| T12 | 相同类型负载的历史/候选 SHA、Run/Job/Step 时间戳与回滚记录 |

W00 当前这些候选测试全部 NOT_RUN，不把现有基线成功当成候选通过。

### W03：一次完整交付与验收

- 本地先跑分类器/安全静态合同、Ruff、diff check；业务库 DSN 不用于测试。完整 PostgreSQL 回归仅在明确允许的隔离 PG17 或 GitHub CI 合成环境执行。
- 一次性整理代码、测试、必要文档，提交前完整 diff；获批后仅 master 一次主要提交，核验其精确 SHA 的完整 CI，不因自身 SHA 变化重复制造证据提交。
- Workflow/分类器变更本身走 FULL，用这次候选 CI 证明完整工程回归等价。
- 后续一条有实际内容的普通文档提交验证 DOC_ONLY；代表性 backend 端到端案例如无法在不制造无关业务变更下构造，则标 DEFERRED，不能拿 Workflow 提交或旧 backend SHA 冒充。
- 不创建分支/PR 来造场景；PR 逻辑先隔离测试，真实 PR 实测若无合规事件则 DEFERRED。无真实样本时不宣称 Required Checks/PR 端到端已全部验收。
- 目标文档反馈≤5分钟，实际样本不足时只报告单次值，不伪称 P50/P95 已稳定；完整代码 CI 可能仍约65分钟。

### W04：并行化暂缓

全量 pytest 是主要瓶颈，但共享数据库、全局 fixture、历史合同与覆盖率合并尚未完成隔离证明。慢测试分组/前端与 Docker 并行另行提出补丁，不在阶段 A 顺手重构，不执行任何百万行或业务性能实验。

## 7. 拟修改文件范围

这是供批准的清单，当前尚未修改这些文件。

| 路径 | 目的 |
| --- | --- |
| .github/workflows/ci.yml | 文档/完整步骤守卫及真实汇总；保留原 Job 身份、原完整回归与手动 Gate |
| .github/workflows/ab-read-a4-baseline.yml | 普通合同 Job 的精确文档分流 |
| .github/workflows/ab-read-a4-2.yml | 普通合同 Job 的精确文档分流；正式 gate 不改 |
| .github/workflows/publication-v13.yml | 普通合同 Job 的精确文档分流；candidate-performance 不改 |
| .github/actions/ci-scope/action.yml（拟新增） | 共用只读路由和检查输出 |
| scripts/ci_change_scope.py、ci_docs_check.py、ci_status_summary.py（拟新增） | 完整 diff 分类、文档契约校验、失败闭合 |
| config 之外独立的 CI 路由 policy（拟在 .github/ 下新增） | 明确安全白名单/受保护字段，不触及业务配置 |
| tests/unit/test_ci_opt_01.py（拟新增） | T01–T12 的静态/隔离负例 |
| tests/unit/test_a4_ci_governance.py、scripts/a42331_ci_contract.py | **待负责人明确批准的最小编排合同版本适配**；不直接将新摘要当作安全证明 |
| PROJECT_STATUS、docs/tasks/README、CI-OPT 专项验收报告/verification | 一次性同步支撑任务和真实验收事实，R1 仍 PARTIAL |
| 其他权威文档 | 仅若项目维护规则要求描述新 CI 使用方式，实施前登记最小文档范围；不变更业务权威口径 |

不拟修改另外两份已有路径过滤的 A4232/A4233 Workflow、既有授权 composite/guard/policy、发布 Gate/receipt 验证器、业务 backend/frontend、迁移、策略、pytest 收集与安全插件、历史证据。发现额外必要改动须先说明，不顺带扩大。

## 8. 回滚与当前验收状态

实施后保持单个独立主要提交；如出现误分类、金融回归跳过、审批绕过、伪 success，停止并以普通 git revert 回滚该提交（不强推/重写历史）。若有后续真实文档验收提交，不为回滚 CI 而改历史证据；按依赖正常 revert。回滚后重新核验完整原 CI，管理员规则若曾变更需独立恢复记录。

| 项目 | W00 状态 |
| --- | --- |
| master/工作区/治理阅读 | 已核查 |
| 六 Workflow / 四组 composite / 授权与发布门禁 | 已审计 |
| 三次普通提交时间戳 | 已取证，见相邻 JSON |
| Required Checks / 环境审批实际配置 | UNKNOWN，权限不足，需管理员核查 |
| 分类矩阵/最小实施/合同冲突/回滚 | 已给出方案，待负责人确认 |
| 候选 T01–T12 / 工程等价 / ≤5分钟 | NOT_RUN / PENDING |
| 新专项实验、生产读取/写入 | 未执行，未授权 |
| BIZ-PERF-03-A-R1 | PARTIAL；本任务不关闭或替代其业务验收 |

本轮检查：六份 YAML 已解析，23 个 Job 已盘点；实际运行 Job/Step 时间戳顺序与审计文档基础一致性检查通过；git diff --check 通过；已跟踪文件 diff 为空，master 工作区干净。未运行本地 pytest、迁移或新 CI。

本轮未修改任何已跟踪文件、Workflow 或业务代码，未提交推送。审计报告、时间戳 ci_opt_01_w00_evidence.json 与包含全部 Job if/needs/steps/artifact 的 ci_opt_01_w00_inventory.json 仅保存在已被 Git 忽略的 .codex_tmp。等待负责人审阅本方案，尤其是旧编排合同最小适配范围，再进入 W01。
