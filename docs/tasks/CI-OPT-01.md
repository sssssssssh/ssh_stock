# CI-OPT-01 GitHub Actions 安全分层

日期：2026-11-03 开始，2026-11-04 接续核验。状态：PARTIAL；W01/W02 本地通过，W03 网络已恢复且获提交推送授权，最终工程与端到端验收 PENDING。
修改前 master/HEAD/origin/master/GitHub 基线：`e697fc80a098726f4e73f04ac71f5eb6cfb62b03`，工作区干净。
负责人在 W00 审阅后明确回复“开始修改”；仅 master，不创建开发分支。

## 目标及边界

支撑历史数据读取、计算、候选处理性能主线；BIZ-PERF-03-A-R1 仍 PARTIAL，业务性能问题没有关闭。
只改 CI 编排、相关只读脚本、编排合同与必要文档，不修改业务代码、数据库、策略或实验协议。
普通 CI 不能授权生产、A4/G1、Publication、A4231/A4232 或新的百万行性能实验。

## W00 核查

六份 Workflow、23 个 Job、a421-pg/governance/cleanup/finish 已审阅。
Branch Protection 读取为 403，Required Checks UNKNOWN；可见 repo rulesets 为空不等于无保护。
Environment 的实际 reviewers 配置 UNKNOWN，仍需管理员核查 a4-expensive-measurements；
CI、A4-1、A4-2、Publication、A4232 原声明不改。本任务不配置管理员变量或审批。

| 基线 SHA / 主 Run | Run 观测时长 | 全量 pytest Step walltime |
| --- | --- | --- |
| 32cf8f43 / 41414072689 | 65分11秒 | 52分14秒 |
| 16ef3062 / 41558957304 | 62分43秒 | 50分08秒 |
| e697fc80 / 41571974306 | 65分06秒 | 52分02秒 |

Run 使用 created_at→updated_at，Step 使用 started_at→completed_at，不混用 pytest 自报时间。
最新主 CI 实际 5347 passed、816 warnings、90.02%；阈值70%。A4-2 普通合同另约8分49秒。
这些是历史工程证据，不是本候选结果，也不是性能/容量通过。

## W01 最小分流

- 保留四份原 Workflow 的触发、Job 名称、并发、审批和正式 Gate。A4232/A4233 不改。
- 保留 workflow-contracts 和 dependency-audit 的低成本检查；不通过 Workflow 路径过滤制造缺失检查。
- 原 test、lookup-diagnosis 与 A4-1/A4-2/Publication 普通合同 Job 在 checkout 后完整比较 Git，
  实际运行静态检查。只有 scope=docs 才跳过重步骤；空输出默认 full，异常不能产生成功凭证。
- 主 test 的 PG17 service 保留初始化；文档分支不运行迁移、全量 pytest、Docker build 或浏览器。
- 每 Job 的最终检查验证 scope 身份、真实步骤 outcome；always 汇总要求全部必要 Job 成功及当前 SHA 证明。
- 文档结果为 DOC_CHECKS_PASS + full_regression=NOT_RUN，不生成原 core/JUnit/容量证据。
- workflow_dispatch 一律 full，原 authorize/environment/protocol/target_sha/attempt/cleanup/finalize 不变。

### 精确快速名单与限制

阶段 A 保守地只允许 `.github/ci-opt-policy.json` 登记的 README、PROJECT_STATUS 和本任务文件
中 `ci-opt-01:noncontract-prose` 标记之间的普通说明内容变化。块外字节必须相同；块内不允许
链接、HTML、标题、代码、命令、身份和权限等契约内容。缺少或修改标记就 full。
这不是对所有 Markdown 的免测：新文件、文档其他章节、PRD、系统设计、PROJECT_RULES、AGENTS、
验收 JSON、manifest、fixture、未知路径、大小写异常、重命名、删除、force push、比较失败均 full。
SHA、任务状态、证据或授权变化不因扩展名为 Markdown 而免除原回归。
将来扩大快速名单必须单独评审消费者与负例，并由 policy/脚本变更触发完整 CI。

JSON 证据（包括 STATUS + R1 verification 的组合）执行静态 JSON 语法/重复字段检查，仍 full；
不冒充已实现任意治理/证据编辑的快速路径。明确非契约的局部说明才享受本轮安全提速。

### 编排合同适配

`ci_opt_contract` 将当前四份 YAML 与 e697fc80 的确定性变换逐项比较：只增加 scope、守卫、
原步骤 ID、路由结果、独立工件、汇总，以及追加新 CI 单测。任何原命令、coverage、Gate、
授权或服务对象变化均拒绝。不是简单换一个新摘要。
原测试仅三个编排相关函数做必要适配（test_a4_ci_governance 一个、test_a42331_ci_evidence 两个），
其余原函数 AST 保持相同，原测试节点没有删除；旧 test Job 摘要和历史对象继续校验。
`source_contract_pytest`、安全脱敏插件与历史 manifest 不改。

## W02 验证矩阵

| 场景 | 预期 |
| --- | --- |
| T01 README 普通说明块 | docs、真实文档校验、重步骤 NOT_RUN |
| T02 STATUS + verification JSON | 静态证据语法检查；JSON 属关键证据，full |
| T03 金融/发布/Worker/测试 | full，原回归不减 |
| T04 lock/迁移 | full，原 PG17/schema |
| T05 frontend/lock | full，原前端与跨栈检查 |
| T06 CI/actions/guard | full，原未授权实验继续拒绝 |
| T07 混合文档/代码 | full |
| T08 未知/改名/删除/大小写/diff 异常 | full 或明确失败，不能假成功 |
| T09 多提交 push / PR merge-base / dispatch | 完整比较，手动路径不走 docs |
| T10 skipped/cancelled/failure/缺证明 | 最终非成功；文档缺校验不能通过 |
| T11 完整回归等价 | 原步骤命令/插件/阈值/服务逐项等价，新测试另计 |
| T12 观测与回滚 | 精确 SHA/Run/Job/Step，历史不冒充候选 |

本地最终定向测试218项通过、无失败/错误/跳过；Ruff与差异检查通过，具体命令及边界见下一节。
完整 Linux/PG17 工程验收待当前候选 CI。
真实 doc-only 与 backend GitHub 端到端事件尚未构造，DEFERRED；不为演示创建无意义业务修改或新分支。
仅一次采样不能宣称 P50/P95 稳定或完整代码 CI 已降至10–20分钟。doc-only ≤5分钟仍待实测。

## W03/W04、回滚与接续

提交/推送按负责人明确授权执行；只记录修改前基线，不为追填自身最终 SHA 连续提交。
候选涉及 CI，因此其提交必须跑 full；业务库不用于测试，不能用历史成功替代当前完整回归。
提交后独立检查其精确 SHA 的普通 CI；文档快速路径和代表性 backend 端到端证据分别判定。
共享 PG/fixture 的安全并行化为 W04 DEFERRED，不自动执行。

若误分类、原回归遗漏、审批绕过或假成功，使用 `git revert <CI-OPT实现提交>` 正常回滚，
不强推、不改历史证据；重新核查原完整 CI。当前未修改 Branch Protection，无管理员规则迁移。
下一步：按已确认的远端基线一次性交付提交/推送，核验精确 SHA 的真实候选工程结果。

## 本地交付核验与未完成验收

2026-11-04 接续核验最终本地 JUnit：218 passed，0 failures/errors/skipped，pytest 自报335.14秒。
最终使用默认插件，没有设置 PYTEST_DISABLE_PLUGIN_AUTOLOAD；只将临时文件移到本仓库忽略区，
避开 Windows 跨盘收集耗时。未修改原用例的30秒超时、断言或安全插件。

```bash
python -m pytest tests/unit/test_ci_opt_01.py tests/unit/test_a4_ci_governance.py tests/unit/test_a42331_ci_evidence.py tests/unit/test_a421_artifacts_and_cli.py tests/unit/test_v14_workflow_evidence.py -q --tb=short --basetemp=.codex_tmp/ci-opt-final-tests-20261103 --junitxml=.codex_tmp/ci-opt-01-final.xml
python -m ruff check backend tests migrations scripts .github/actions
git diff --check
```

初轮为209通过/2失败：新大小写改名夹具已修正；旧子pytest在跨盘临时目录超时。随后隔离环境
217项通过；最终默认插件、同盘临时目录218项通过。保留这些过程事实，不将隔离插件结果冒充最终默认结果。
最终新增56项 CI 回归；原测试仅三个编排函数适配，AST核验其余原函数不变。四份YAML与基线的
确定性完整路径投影、步骤计划一致性及业务/迁移/授权/正式Gate空差异检查均通过。

| 验收项 | 本轮结论 |
| --- | --- |
| A01 原测试/金融与实验门禁保留 | 静态与定向回归通过；三个编排函数为已审阅的必要适配，历史Git/manifest不改 |
| A02 十二类触发安全场景 | 本地隔离证据通过；真实doc-only/backend/PR事件DEFERRED |
| A03 doc-only不执行全量pytest | 隔离路由与步骤守卫通过；GitHub实测≤5分钟/P50/P95 NOT_VERIFIED |
| A04 关键修改仍完整回归 | 分类与旧命令等价通过；当前Linux/PG17整体验证PENDING |
| A05 当前候选完整工程回归 | PENDING，不能用历史5347项或本地218项替代 |
| A06 手动授权与正式Gate | 原对象空差异及负例通过；未启动专项实验 |
| A07 真实旧/新耗时 | 历史三次已取证；候选GitHub耗时PENDING |
| A08 CI/业务性能分开 | R1仍PARTIAL，未进行业务性能或生产操作 |

网络事实：2026-11-04 GitHub连接器出现传输失败；原代理端口无监听，Git直连GitHub 443也失败。
本地HEAD和缓存origin/master仍为e697fc80，远端最新状态UNKNOWN。先恢复网络并核对远端，
不把无法访问当成远端未变化，不强推、不宣称已经推送或已经有候选CI。
汇总见 [verification.json](../acceptance/ci_opt_01/verification.json)。

网络接续：同日确认系统代理已改为本机7900，Git与GitHub API通过该端口均成功；实时远端master
仍为e697fc80。负责人随后明确回复“提交并推送 master，继续 CI 验收”，本轮按该授权继续W03。
上段UNKNOWN仅保留先前断网取样的历史语境，不是网络恢复后的当前结论。不修改全局Git代理。

<!-- ci-opt-01:noncontract-prose:start -->
本页按阅读顺序介绍反馈流程与记录位置。
<!-- ci-opt-01:noncontract-prose:end -->
