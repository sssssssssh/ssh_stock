# A4-CI-1.0 工作流治理与验收

## 范围与基线

基线 master `c076fa49fdd82ea07f5939f4ec6c190b1b19785b`，与 origin/master 一致、工作区干净。
W00 的全部五条工作流/Job/资源/工件盘点见 [原始清单](a4_ci_workflow_inventory.md)。
本轮仅修改工作流、工作流辅助 Action/合同测试与说明文档，不进入任何后续性能阶段。
原生产源码、配置、迁移、实验驱动、历史 evidence/manifest/protocol/closeout 不改写。

## W01 自动 / 手动边界

| workflow | 之前普通 push/PR | 之后普通 push/PR | 明确授权的手动部分 |
|---|---|---|---|
| CI | audit/Core；lookup 使用 capacity PG；提交标记可启动 A4231；容量只依赖 readiness | 原 audit/Core 全部步骤、治理合同、read 级 PG 小型查找安全测试、固定历史工件离线复核；严格 release 仍 always 执行 | authorize -> 选定 a4231 或 capacity；容量还必须原 readiness=true，不能由输入设置 |
| A4-1 | 单 Job 安全测试后自动10k/100k/million | contracts：原 observer/Golden/A-B 安全测试与 read PG | isolated-baseline：原120m及全部三规模命令 |
| A4-2 | 原 contracts 后自动21分片矩阵 | 原 contract-and-safety；laboratory skipped；always aggregate 明确拒绝缺实验 | laboratory：原21分片/1002必需组+6对照、预算、max-parallel4不变 |
| Publication V1.3 | 原330m安全及多规模、多重复基准 | contracts：原候选等价/锁/取消/进度/原像回归和 read PG | candidate-performance：原330m、全部 baseline/current/empty/existing/scope/keys/receipt命令 |
| A4232 | 路径 contracts 使用 capacity；提交标记可启动归因 | 路径 contracts 改 read；attribution 永不因 push/PR 标记启动 | 显式 dispatch + 旧 token/协议核验；旧 token 已消费，仍拒绝执行 |

没有新增 workflow_run、schedule、repository_dispatch 或 pull_request_target 链。
主 CI 保留完整 pytest/cov70、Ruff、迁移/容器/Worker/前端/浏览器既有检查，不通过删除测试降成本。
低成本合同中原有微型真实游标、A/B 反例、L1/中规模驱动故障及范围适配检查仍保留；
它们不是三规模阶梯、1002组矩阵、正式603040行L2或128样本归因，不作为性能认证输出。
本轮没有执行上述高成本矩阵或归因脚本；只运行只读 guard/静态/YAML/合同测试及自动安全回归。

## W02 手动授权与权限

五条 workflow 共享显式输入：完整 `target_sha`、boolean `confirm_expensive_run`（默认false）、
非空 `run_reason`、固定 `protocol_id` 和 `protocol_sha256`。主 CI 另有单选 experiment，
none 不授权任何任务；一次只允许 capacity 或 a4231 的对应 Job，不能顺带启动另一实验。
控制和昂贵 Job 均在 checkout 后、依赖安装/PG 创建前运行同一只读 guard。
昂贵 Job 不使用会在 guard 前创建数据库的 services。

`.github/actions/a4-governance/guard.py` 只用标准库，不导入业务 Settings、不读取 .env、不连接数据库。
输入从 GitHub event JSON 结构化读取，不直接插入 shell；CLI 的 suite 通过环境变量与引号传递。
未知 schema、空原因、错误类型、非 master/tag、非 dispatch、短/错 SHA、attempt>1、dirty tree 全部拒绝。
校验 git HEAD == github.sha == target_sha，工作区包括未跟踪文件，来源 freeze 在基线后台/配置/迁移/前端。

协议 ID/hash 与测量脚本白名单记录在 `policy.json`；比较 Git canonical blob，
避免 Windows CRLF 被当成协议版本，实际 clean checkout 仍必须成立。
另核验模型树、候选原像实现、fixture/矩阵/观测合同源哈希，记录 dataset recipe 与 model hash。
不导入或执行测量器；原测量脚本内部的冻结/物理身份/规模/预算检查继续保留。

| suite | 固定协议 ID | 当前可执行性（不是授权） |
|---|---|---|
| a41 | a4-1-frozen-baseline-v1 | 仅日后获批 dispatch；本轮不运行 |
| a42 | a4-2-frozen-matrix-v1 | 同上；不变更原矩阵 |
| publication-v13 | publication-v13-frozen-baseline-v1 | 同上；不变更原性能合同 |
| capacity | a4-2.1-formal-capacity-v1 | 还需真实 readiness 与全部原门禁，当前未准入 |
| a4231 | [a4231-attribution-once] | 已由 run39820748153 消费，任何新 run 亦拒绝 |
| a4232 | [a4232-statstable-once] | 已由 run39833706083 消费，任何新 run 亦拒绝 |

protocol_sha256 必须使用 policy 中完整值，不允许 dispatch 临时指定任意协议或跳过 hash。
当前一次性登记全部关闭：不得删除 consumed_run_ids、用新 run ID 或 rerun 伪装新许可。
即使将旧登记误清空，guard 也拒绝未单独审阅的新 one-shot；新的协议需另立任务、独立审阅和执行登记。
历史消费记录只作拒绝凭据，不是本轮测量或性能通过凭据。

### 管理员仍需配置的 Environment

本轮只读 API 查询 `GET /repos/sssssssssh/ssh_stock/environments` 返回空列表；
**没有创建/配置 Environment 或声称审批已生效**。所有手动 authorize 和昂贵 Job 都引用：

`a4-expensive-measurements`

涉及 A4-1 authorize/isolated-baseline、A4-2 authorize/laboratory、Publication authorize/candidate-performance、
CI authorize/lookup-tail-attribution/capacity，以及 A4232 authorize/attribution。

管理员须在仓库 Settings -> Environments：

1. 创建上述 Environment，配置 Required reviewers，开启 Prevent self-review。
2. 禁止管理员绕过审批，Deployment branches/tags 只允许 master 分支，不允许任意 tag。
3. 完成人工核验后，仅在该 Environment 设置非秘密变量
   `A4_REVIEW_POLICY_ACK=a4-ci-1.0-reviewed`。缺此确认值 guard 默认失败，不创建 PG 或安装测量依赖。
4. 为 master 和 `.github/` 变更配置受保护分支及必要代码审阅，防止有写权限者绕过治理。
5. 核实仓库套餐支持所需 reviewer 保护；权限/套餐不具备则保持手动执行未批准。

ACK 是管理员的配置声明，不是实时读取 GitHub protection rules 的密码学证明。
仅添加 environment 名称会自动产生无保护 Environment，**不等于 reviewer 审批**；
变量被误配为允许也不能证明审阅存在，管理员须对实际保护设置负责。
普通 L0 不引用该 Environment，不能因审批等待阻塞普通安全测试。
本轮没有提交 dispatch 请求或以实跑验证 reviewer；现场审批行为仍为 NOT_VERIFIED_LIVE。
参见 [GitHub Environment 文档](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments)。

## W03 并发、清理与中断

五条 workflow 的 **手动** run 共用 `ssh-stock-a4-expensive` workflow-level mutex，
cancel-in-progress=false；普通 L0 按 workflow/run ID 使用独立组，不抢占手动队列。
同一时刻只运行一条手动性能 workflow，不让 A4-1/A4-2/Publication 无意并发。
原 A4-2 四分片并行、三容量等级独立执行是冻结协议内部明确允许的并行，不扩大。

采用当前 Actionlint 支持的基础 concurrency 语法，而不依赖新 queue 扩展。
GitHub 默认只有一个 pending 名额，新等待者可能替换旧 pending；这不是无限 FIFO，也不取消正在运行者。
被平台取消的等待者保持 cancelled/未验收，不能当成完成或自动重发。
管理员应一次只批准一个待运行实验；恢复需要新审批，attempt2 默认拒绝，不假装支持断点续跑。
参见 [GitHub concurrency 规则](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)。

自建 PG 名称为 `a4-ci-<run>-<attempt>-<随机12hex>`，purpose/stage 与 run/job/attempt label 明确，
端口只绑定127.0.0.1，read 为2CPU/3GiB；capacity 仅在授权昂贵 Job 内保留原资源合同。
Core 的独立物理 PG 同样唯一并限资源；原 stock_db service 的名字和 teardown 由 GitHub 原生管理，
不把数据库名当 Docker 容器名，不处理非当前 runner 的服务。
PG17 marker 与独立 pg_controldata/pg_control_system 的双身份验证、正式测试迁移仍保留在原测试环境中。

所有自建容器路径都有 always 清理：先 docker ps/inspect 验证名字、purpose 和 run/job/attempt，
不匹配不删；Docker 不可用、检查/删除失败均返回非零，不使用 continue-on-error 掩盖风险。
没有创建容器时为 NOT_CREATED，不误删固定名字或其他 run 的数据库。
原测量 always 上传及部分 checkpoint/status 不删不重算；追加独立 GOVERNANCE_ONLY 终态，
失败、取消、超时或清理失败均为 INCOMPLETE，保存首发与清理终态错误。
此 schema 不包含任何正式 PASS/容量准入，原 merge 必须拒绝它。

平台硬终止、runner 丢失时不能保证 always 真正执行；缺收据和未知清理仍失败关闭。
未来自托管 runner 如有残留，应由管理员只读核对当前标签与真实进程后再单独授权清理，
不以此文档授权盲删、不借用业务机器，也不自动释放未知任务占槽。

## W04 Release Gate 与历史证据

以下代码/语义保持基线：ci_release_gate_v14_a4_2_1.py、a42_receipt_contract.py、
publication_release_checks_v14_a4_2_1.py；CI publication-release-gate 和 A4-2 aggregate Job 完整内容不改。
audit/Core/lookup/全部容量的依赖、always、exact SHA/run/attempt、source/model/fixture hash、
1002组、Golden、原发布断言、SQL/发布/行数预算均保留。
capacity 只是在原 readiness==true 条件外增加 dispatch 授权，绝不能从手动输入设置 true。

普通提交缺性能/容量证据时，相关实验 skipped，aggregate/release 仍可能 FAILURE。
CAPACITY_NOT_AUTHORIZED、skipped、缺工件、错 SHA、INCOMPLETE 都不能转 PASS。
轻量合同绿色只表示治理/安全检查通过，不是性能通过或生产切换许可。
历史 JSON、baseline、source manifest、冻结协议和旧 closeout 字节不变，不用新报告覆盖。

## W05 验证与 Checklist

新增 `tests/unit/test_a4_ci_governance.py`：YAML1.2 on/boolean 解析、实际 if 子集求值、
push/PR/dispatch/误确认、完整 SHA、分支/dirty/协议/数据集、消费 ID/attempt、跨 workflow mutex、
容器归属/清理失败、取消/超时/部分/旧身份、真实 guard CLI 非零且脱敏、原 gate 和历史文件冻结。
旧五份 workflow 测试只调整合法治理变更对应的断言；原测试数、保护和严格性能/来源断言不删不弱化。

本地实际结果：新治理合同 **57 passed**（50.95 秒）；Ruff（含新增 .github/actions）及 Actionlint1.7.12 通过。
补入原 receipt gate 正反例后的提交前集合 **105 passed**（43.39 秒），退出码0；
包括全部57项治理合同，不是把失败与单独重跑拼接成通过。
Actionlint Windows ZIP 的 API SHA256
`6e7241b51e6817ea6a047693d8e6fed13b31819c9a0dd6c5a726e1592d22f6e9` 已核对，
只放本地忽略目录，不提交二进制。校验全部 workflow 的表达式/Actions schema，未启用本机没有安装的 shellcheck/pyflakes。
首轮较大相关集合 **284 passed / 5 failed**：三项既有 LF 原字节冻结检查遇到 Windows CRLF，
两项 POSIX os.killpg 在 Windows 不存在。没有 skip、改哈希、修改生产文件或降低断言；
这些用例仍在 Linux CI 原命令中完整执行，最终结果以本提交自己的 exact-SHA CI 为准，不借旧 SHA 通过。

```bash
python -m pytest -q tests/unit/test_a4_ci_governance.py
python -m ruff check backend tests migrations scripts .github/actions
actionlint -shellcheck= -pyflakes=
git diff --check
```

只执行低成本验证，不 dispatch、rerun 或启动任何高成本实验来证明治理。
推送后的新 workflow-contracts Job 独立执行本合同，原 Core/轻量 PG 回归仍自动执行。
W05 最新结果、退出码、HEAD/run/attempt 和链接在最终交付据实列出；未取得的检查不能预写 PASS。

| ID | 验收方式 / 保留状态 |
|---|---|
| G01 | 五条 workflow 完整基线清单，所有事件/Job/资源/命令/工件均记录 |
| G02–G04 | 实际 if 求值覆盖 push/PR 即使输入确认、readiness=true 也不测量；原安全案例保留 |
| G05–G08 | guard 正反例 + 真实 CLI 先于 PG/依赖拒绝；来源/协议/模型与 fixture 冻结 |
| G09 | attempt2/消费ID拒绝，共用非取消 mutex；pending名额限制明确，不承诺无限排队 |
| G10 | 静态 always + 取消/超时/部分/清理失败和错归属合同；未实跑昂贵中断 |
| G11–G12 | 原 gate Job/脚本和历史文件冻结；容量 skipped/缺失仍拒绝，合法证据沿用原正例测试 |
| G13 | 仅静态/合同和自动安全回归，无手动高成本 dispatch；实际 Actions 步骤在交付核对 |
| G14 | 提交后核对本次 HEAD 的 Actions/JUnit，不借基线或较小样本代替 |
| G15 | 下述保守回滚，审批设置待管理员完成，不进入新阶段 |

## 日后操作（当前不要执行）

先审阅本任务，再单独批准某次诊断；管理员完成 Environment 配置后，在 Actions 选择相应 workflow，
Run workflow 的分支选 master，填入当前已审阅完整 HEAD 和 policy 中的准确协议/hash，
选择唯一实验、填写非敏感原因并显式勾选确认。审批人核对输入、源码、消费记录与资源再批准。
不能用更小 target、修改原因字符串或点 rerun 绕过身份；失败保留证据并重新审阅，不自动重跑。
当前 a4231/a4232 ID 无法再执行；capacity 当前没有实际性能许可，不能人工填写 true 放行。

## 回滚与遗留风险

不要直接 revert 治理提交后 push：旧 workflow 会再次在 push 上自动启动大矩阵。
安全顺序为：管理员停止批准新实验、撤掉 Environment ACK；必要时先禁用相关 workflow，
保留正在执行任务的检查点与原清理，不自动强杀；审阅分支仅修复治理问题并保持 dispatch/false 默认边界，
通过同样静态/合同检查后才恢复轻量自动检查。不能在修复时恢复无条件昂贵触发。
若必须完整恢复旧代码，应先由管理员禁用全部受影响工作流并安排替代必需安全检查，
否则 required checks 未完成，发布继续拒绝；不恢复、伪造或改写任何历史 evidence。

管理员配置、现场 reviewer 行为与真正手动实验未验证，这是本轮刻意不执行的边界；
不能把配置治理完成表示为 C1 P95 修复、正式L2通过或生产启用。
本轮提交推送完成后 **等待审阅，不自动进入下一阶段**。

## 修改文件清单

- 工作流五份：`.github/workflows/ci.yml`、`ab-read-a4-baseline.yml`、`ab-read-a4-2.yml`、
  `publication-v13.yml`、`a4232-statistics-tail-diagnostic.yml`。
- Action 六份：`.github/actions/a421-pg/action.yml`、`a4-governance/action.yml`、
  `a4-governance/guard.py`、`a4-governance/policy.json`、`a4-cleanup/action.yml`、`a4-finish/action.yml`。
- 合同测试六份：`tests/unit/test_a4_ci_governance.py`、`test_a421_artifacts_and_cli.py`、
  `test_lookup_diagnostic_a422.py`、`test_lookup_tail_attribution_a4231.py`、
  `test_lookup_tail_review_a423.py`、`test_tail_stability_a4232.py`。
- 文档六份：`README.md`、`PROJECT_RULES.md`、`docs/股票机会发现系统_PRD_V1.0.md`、
  `docs/股票机会发现系统_系统设计_V1.0.md`、`docs/acceptance/a4_ci_workflow_inventory.md`、
  `docs/acceptance/a4_ci_workflow_governance.md`。

共23份，Action helper只属于工作流基础设施，不建立业务平行实现；DOCX未更新。
