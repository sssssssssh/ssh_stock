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
原测试仅六个编排相关函数做必要适配（test_a4_ci_governance 一个、test_a42331_ci_evidence 两个、Observer冻结用例一个、A42341 AT20一个、business测试版本衔接一个），
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
真实doc-only已取得下文精确版本证据；backend与PR远端事件仍DEFERRED，不为演示创建无意义业务修改或新分支。
现有说明样本不能宣称P50/P95稳定或完整代码CI已降至10–20分钟；当前补丁需独立核验。

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
初轮新增56项 CI 回归；初次本地验证仅三个编排函数适配，CI反馈后补齐Observer与AT20两个旧冻结用例，再增加business版本衔接和4项严格投影回归，AST核验其余原函数不变。四份YAML与基线的
确定性完整路径投影、步骤计划一致性及业务/迁移/授权/正式Gate空差异检查均通过。

| 验收项 | 本轮结论 |
| --- | --- |
| A01 原测试/金融与实验门禁保留 | 静态与定向回归通过；六个编排函数为必要版本适配，历史Git/manifest不改 |
| A02 十二类触发安全场景 | 本地隔离证据通过；真实README多版本通过，backend/PR事件DEFERRED |
| A03 doc-only不执行全量pytest | 已有精确版本51秒等实测；当前补丁待验，稳定P50/P95 NOT_VERIFIED |
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

### 首轮真实 CI 反馈与修复

- 实现提交f31aeefe6f68761662603bb054c778f8e1b531af已经推送；Observer合同41788897841为318 passed/1 failed。
- 本机精确复现失败用例test_frozen_baseline_bytes_and_old_workflows_unchanged：旧用例只恢复test Job，
  尚未验证/恢复整份Workflow的已批准分流变换，导致旧整文件比较失败。历史manifest/hash断言本身没有失败。
- 最小修复：复用同一个严格restore后保留原比较和历史哈希/当前业务合同断言，并将整个Observer单元文件加入轻量合同入口。
  AST登记仅追加这一函数，其余原测试不变；本次补丁的本地验证与新CI仍需完成，不继承初次218项或失败提交的结论。
- README真实说明提交1a4bda0f0550a8fd0b475c32a356184f1fba51b8的四条工作流全部成功：主CI41789236152用时46秒，
  A4-1为18秒、A4-2为16秒、Publication为18秒。完整pytest/迁移/Docker build确实skipped，最终汇总实际执行成功。
  这是首轮源码的文档分流证据，不是后续修复SHA的完整工程证明，也不代表P50/P95已稳定。
- 530b214修复后，Linux轻量合同与Observer初段通过；Observer41792615185的后续A42341 AT20仍直接比较旧Workflow原字节，
  本机精确复现后补上同一严格投影。原A4233 additions摘要、原字节比较及未修改的A4232原字节约束保留；AT20加入轻量入口。
- 530b214本机扩大验证为316 passed/1 failed：Windows工作副本的历史清单CRLF导致字节拒绝；临时LF克隆进一步到达原POSIX文件描述符拒绝点，
  不对Windows加跳过或放宽断言，使用原GitHub Linux环境验收。主工作区历史清单和全局Git配置未改。
- 第二次README说明提交413d45211e576b7f797e3d0957ea2f60eb153dfc的四条工作流成功，主CI41793077538实测37秒，
  A4-1为16秒、A4-2与Publication各18秒；仍只适用于该精确说明提交及对应代码版本。

### 完整回归反馈与最终兼容补丁

- f39f4a804969f5b72a5b6ccf0878ced167311f4c 的主CI41795028412全量结果为5402 passed/1 failed、816 warnings、90.02%覆盖率。
  pytest步骤07:58:07Z至08:38:22Z，40分15秒；完整测试集合5403项，没有删减原5347项和新增56项。
- 唯一失败节点为test_business_source_contract.py的test_exact_function_compatibility_keeps_negative_cases_signatures_and_assertions。
  旧business适配清单只登记同文件另一个函数，不能识别本轮AT20变换。原Windows工作副本还存在既有CRLF差异；
  LF临时克隆逐项验证后仅该AT20边界失败，明确区分环境问题与Linux真实失败，不修改历史文件或全局Git设置。
- 最小补丁只在普通测试中将精确登记的AT20全文变换还原到e697fc80，再调用原business验证器；
  新投影拒绝任何额外字节修改（只兼容LF/CRLF文本换行），不扩大业务合同TEST_ADAPTATIONS、不修改生产guard或历史manifest。
  原负例/断言/签名保留，新增真实红→绿与断言、块外、函数体篡改三个负例；该测试文件加入轻量合同入口。
- f39f4a8的其余四条工作流通过；ab9be0f8620d8fc50f56498ca057d90047cf5c1f纯README说明实测四条通过，
  主CI41795754600为51秒，A4-1为22秒、A4-2/Publication各18秒；未生成完整回归/容量凭证。
  这些记录不能代替本补丁最终SHA的CI，仍待新的精确版本回归，不为追填自身SHA/CI结束再循环提交。
- 本补丁默认插件、隔离LF工作副本定向68项通过（283.77秒），原编排兼容163项通过（175.49秒），两组不重叠合计231项；Ruff和diff检查通过。当前补丁完整Linux/PG17仍PENDING。
- 最新只读API核查：master无Branch Protection，适用rules为空；实际没有强制Required Checks。
  a4-expensive-measurements已有1名审批人、禁止管理员绕过、分支限master、Environment级ACK正确，
  但Prevent self-review=false，需管理员开启。本轮未修改仓库设置或触发高成本实验。

<!-- ci-opt-01:noncontract-prose:start -->
本页按阅读顺序介绍反馈流程与记录位置。
<!-- ci-opt-01:noncontract-prose:end -->
