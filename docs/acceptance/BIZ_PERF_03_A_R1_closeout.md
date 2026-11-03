# BIZ-PERF-03-A-R1：最小生命周期修复及停止条件回执

日期：2026-11-03；实施前基线 32cf8f438061e95b1492fd2a5db15dd05c13e28d。
负责人已明确确认阶段一方案并要求开始修改，最终提交推送已获授权。
状态：**PARTIAL / LIFECYCLE_FIX_VERIFIED / LOCAL_NATIVE_FAILURE / OVERHEAD_OPEN**。

## 1. 实做与边界

- SQLObserver.install 在三个事件的任意安装位置失败时回滚已登记的监听器。
  登记意图先于 listen，兼容事件适配器“先安装再报错”的情况；不增加 SQL。
- close 先禁用 observer，逐项清理，单项拆除瞬时异常最多尝试两次，继续其余项。
  永久事件 API 故障的回归已验证：保留未清理列表和固定 warning，回调保持禁用，不声称已拆除；
  这只重试本地事件清理，不重放业务 SQL/事务。
- execution_context 中计时记录绑定 observer 归属；finish 同时核验归属、有效状态和
  ContextVar，避免另一根 observer 消费计数。并发/交错和关闭其中一个的场景有回归。
- 诊断 setup 部分失败时先拆除事件、恢复 ContextVar，再执行原业务函数；原返回值/异常保留。
- FETCH 失败后完整 fetched_rows=null，另提供 known_fetched_prefix_rows，保留已知成功前缀，
  不把失败批次未知行数当作 0。Schema 的 database_summary 原本允许对象内附加字段。
- 新增单次 root-arm 隔离测试入口，仅接受现有物理 marker/system_identifier 校验的测试库。
  该入口不是自动性能矩阵；需由独立父进程执行计划中的 setup/root/cleanup deadline。
  清理异常即记录 FAILED，即使 root 已成功发布，也不能将整个定位过程标为 COMPLETE。

仅改两个诊断模块、必要测试、离线诊断脚本与说明。未修改 job_worker、calculation_policy、
calculation_frame、data_publication、job_run 调用点；金融 engine、SQL、500 行批次、事务、
取消/未知提交、Provider、迁移、生产配置、前端和工作流均不变。原 A 阶段证据不覆盖。

## 2. RED → GREEN

原源码新增四个参数用例实跑：**3 failed、1 passed**。
安装第 2/3 个事件失败后原实现残留监听器；交错两个 observer 时第一根错误累计 3 次，
预期仅 1 次，第二根预期 2 次。这是独立可复现缺陷，并非 Windows 停滞根因证明。
最小修复后通过。新增测试追加于原文件，旧测试和断言不改写。

定向测试覆盖：默认 OFF、setup/flush/清理故障、并发/交错归属、部分安装、单独关闭、
SQL 脱敏及 128+overflow、已知/未知 FETCH、取消和未知提交诊断终态、原返回值保护。
这些单元级状态用例不能冒充真实 PG17 的整套失败/取消/未知提交发布验收。

## 3. 有界定位结果与停止

独立本机 PG17 测试实例复用已由本任务确认的专用目录，启动后只绑定 loopback。
每臂通过既有 major=17、marker、离线 control system_identifier 与服务器值核验，
再创建 UUID 合成库。输入与期限按[预注册计划](BIZ_PERF_03_A_R1_plan.md)执行。
运行时未并行大型 pytest；定位期间有一次轻量单测，不作为正式性能条件。

完整摘要见 [localization.json](biz_perf_03_a_r1/localization.json)：

| 臂 | 结果 |
| --- | --- |
| OFF | 原生退出码 3221225477，即 0xC0000005；没有最终 Python receipt，记 INCOMPLETE |
| ON | exit 0；SUCCESS/PUBLISHED；完整函数 wall 34673.8398ms；受控摘要记录输出 hash 与 SQL/写操作次数 |

OFF 的 30 秒 dump 有心跳线程 Event.wait 与 pandas indexers 附近的不完整主线程栈。
这是 Windows 原生访问冲突的证据，不足以归因于 pandas、faulthandler、内存、驱动或诊断代码。
尤其不是“仅 ON 停滞”，不能据此动业务 SQL。实际模块来自用户 site-packages，
PYTHONNOUSERSITE=1 的只读可用性检查显示该 conda 环境缺少本项目全部主要依赖；
这是环境隔离缺口，不是已证明的崩溃根因。本轮未修改全局依赖或安装包来刷过。

没有有效 OFF 终态，结果等价与配对开销均 UNAVAILABLE。按停止条件，**未进入 W04
三对验收**，不删除失败、重跑凑样本或将 ON 成功解释为 ≤3%。
独立测试实例已停止；未操作用户服务或业务库。未删除未知业务任务、解锁 Writer 或恢复 BIZ-PERF-02。

## 4. 验证与验收矩阵

定向命令使用隔离应用配置、禁用 dotenv 读取，数据库环境为不可连接的合成占位目标；
单测使用 SQLite/模拟事件，不连接业务 PG。完整 pytest 也通过同样的安全启动器运行。

```bash
python -m pytest tests/unit/test_performance_diagnostics.py tests/unit/test_calculation_frame.py -q
python -m pytest
python -m ruff check backend tests migrations scripts
git diff --check
```

完整本机 pytest 在收集阶段终止：10 个既有 fcntl/resource Linux 平台导入错误，
exit 2，最终复跑 11.34 秒；没有跳过/删除原测试或降低门槛。定向和 Ruff 的最终结果在交付回执中记录。
基线普通 CI 已核查 5322 passed / 90.00%，只适用于 32cf8f43；不能当修复提交的结果。
修复提交 16ef3062 的普通 Linux CI 已独立核验通过，见第 6 节；不 dispatch 高成本实验。

| 编号 | 当前判定 |
| --- | --- |
| R01 | 单测通过；默认 OFF 不创建 Trace/监听器/文件，业务返回值不变；PG 数量对照未完成 |
| R02 | 单测通过；子终态不改根，重试 trace 独立；完整逐根发布身份待真实对照 |
| R03 | 单元状态与异常保护通过；真实 PG 失败/取消/未知 ACK 组合验收仍待验证 |
| R04 | 部分安装 RED/GREEN 与逐项清理测试通过 |
| R05 | 交错/并发和独立关闭测试通过 |
| R06 | SQL 脱敏、128+overflow 与缓存上限测试通过 |
| R07 | 单测覆盖失败总数未知及已知前缀；原读取器测试保留，真实 PG 全覆盖待验证 |
| R08 | flush/link 错误、pending 清理及原异常保护单测通过；永久 OS 拒绝清理仍有明确 warning |
| R09 | INCOMPLETE：OFF 原生崩溃，无配对完整输出 |
| R10 | NOT_RUN：停止条件触发，≤3% 仍未通过 |
| R11 | 工程回归 PASS：16ef3062 的 Linux CI 完整 pytest/Ruff 成功；本机 Windows 平台限制仍保留，见第 6 节 |
| R12 | 文档、CLI 和既有 Schema 兼容性定向检查；保留 PARTIAL 缺口与回滚 |

## 5. 使用、回滚与下一步

单次合成定位入口（必须先配置已验证的独立测试库，父进程按计划监督）：

```bash
python -m scripts.performance_diagnostics_overhead --root-arm off --output NEW_OFF.json
python -m scripts.performance_diagnostics_overhead --root-arm on --output NEW_ON.json
```

两个命令不能直接作为完整性能验收；现有函数不证明逐列全等或三对达标。初始持久化
INCOMPLETE 前缀可在 native crash 后保留，完整回执只在成功收尾后更新。
原默认纯 CPU fixture 保留，不能当 root 替代物。新定位 CLI 未在故障后重启实验刷结果。

PERF_DIAGNOSTICS_ENABLED 继续默认 false；回滚可关闭开关并在安全边界重启后续 Worker，
无需降级迁移或清理业务数据。源码回滚用新 revert，不覆盖旧证据。
下一步为单独审阅 Windows 原生失败/合格测试环境及有界方案，验证成功后才重启完整对照。
本轮可交付最小安全修复，但整体 R1 与父任务仍 PARTIAL，不进入 BIZ-PERF-03-B 或百万行实验。


## 最终本机验证回执

- 定向读取器/诊断回归：53 passed、0 failed/error/skipped，3.96 秒，退出码 0。
- Ruff backend tests migrations scripts：通过，退出码 0。
- root CLI 安全预检：缺少隔离 marker 时在应用配置读取与文件创建之前拒绝，已验证。
- 完整 pytest：最终复跑 11.34 秒，10 个既有平台收集错误，退出码 2；不标全量通过。
- 有界定位：OFF 原生异常 / ON SUCCESS-PUBLISHED；不能合并为配对成功。
- W04 三对、当前修复源码的真实完整配对、≤3%：NOT_RUN / OPEN。
- 初次推送时 Linux CI 尚未终结；现已独立核验 16ef3062 的最终工程结果，见第 6 节。

因原生失败停止继续负载；本交付为 PARTIAL 的最小修复，不宣称完整任务已验收。

补充 RED/GREEN：span 起始时钟异常、setup 失败后 cleanup 再异常分别新增复现，原实现均失败；
修复后原业务异常/返回值保留，ContextVar 恢复。该补充只涉及同一诊断文件，不修改调用点。


## 6. CI 执行结果与性能验收边界（最终证据同步）

任务：BIZ-PERF-03-A-R1-DOC-CLOSEOUT；核查时间：2026-11-03T11:17:30+08:00。
本轮修改前 HEAD / origin/master / GitHub master 均为
**16ef3062dc538b0f4def0f30edb297a831c32510**，master、工作区干净。
以下四条均为此精确 SHA 的 push、attempt 1、completed/success，不引用文档提交的未来 CI。

| 工作流 / Run | 成功执行的 Job | skipped Job（均未执行，不记 PASS） |
| --- | --- | --- |
| [CI / 41558957304](https://github.com/sssssssssh/ssh_stock/actions/runs/41558957304) | test、dependency-audit、workflow-contracts、lookup-diagnosis | authorize、lookup-tail-attribution、ui-visual-acceptance、capacity、publication-release-gate |
| [A4-1 / 41558957308](https://github.com/sssssssssh/ssh_stock/actions/runs/41558957308) | contracts | authorize、isolated-baseline |
| [A4-2 / 41558957295](https://github.com/sssssssssh/ssh_stock/actions/runs/41558957295) | contract-and-safety | authorize、laboratory、a42-acceptance-gate |
| [Publication / 41558957367](https://github.com/sssssssssh/ssh_stock/actions/runs/41558957367) | contracts | authorize、candidate-performance |

合计 19 个 Job：7 success、12 skipped，无 failure/cancelled。工作流成功表示已执行 Job 成功，
不能解释为 authorize 已批准、历史性能实验已执行或正式 Gate 通过。
API 全部 Job 与逐步结论见 [verification.json 的 ci_evidence](biz_perf_03_a_r1/verification.json)。

### 关键步骤与原始日志定位

下表行号是工具解码的**完整 Job 日志**行号，非 GitHub 单步界面的局部行号；
同一日志行的 UTC 时间戳和摘录保存在 JSON 的 log_evidence。全部证据绑定上述 SHA/attempt。
没有下载或声称复验完整 JUnit/artifact 内容；结论依据 Job/Step API 与对应完整日志。

| 证据 | Job / Step | 原日志定位与结论 |
| --- | --- | --- |
| 完整 pytest 与 coverage | [125664629647 / 23](https://github.com/sssssssssh/ssh_stock/actions/runs/41558957304/job/125664629647#step:23:1) | L2672：5347 passed、816 warnings、2990.28s；L2670：90.02%，原 70% 门槛未变 |
| Ruff | 同 Job / 27 | L2906：All checks passed! |
| PG17 隔离与迁移 | 同 Job / 7–9、12–14、25–26 | 步骤均 success；L2862/L2884 的 current/heads 均 0058_data_publication (head)；降级仅为 CI 隔离库步骤，本轮没有执行迁移 |
| Compose/Docker/Nginx | 同 Job / 29–30、33 | 均 success；L3694 前端、L3756–3774 后端及运行角色镜像导出；L4060–4061 nginx 检查成功。镜像构建不是生产部署验收 |
| 前端测试/构建 | 同 Job / 36–37 | L4195–4196：23 文件、162 测试通过；L4271：built in 6.16s |
| A4-1 合同/安全 | [125664629976 / 6](https://github.com/sssssssssh/ssh_stock/actions/runs/41558957308/job/125664629976#step:6:1) | L604：49 passed、34 warnings；L605 Ruff 通过；不是 isolated-baseline 结果 |
| A4-2 合同/安全 | [125664629771 / 8–9](https://github.com/sssssssssh/ssh_stock/actions/runs/41558957295/job/125664629771#step:8:1) | L679：342 passed、217 warnings；L700 Ruff 通过；不是 laboratory/acceptance gate 结果 |
| Publication 合同 | [125664629853 / 9–10](https://github.com/sssssssssh/ssh_stock/actions/runs/41558957367/job/125664629853#step:9:1) | L673：85 passed、53 warnings；L693 Ruff 通过；不是 candidate-performance 结果 |

### 当前验收结论与本次文档校验

- **工程回归 PASS**：仅对应 16ef3062，不把 32cf8f43 的 5322/90.00% 或本机 53 项拼入统计。
- **R1 整体验收 PARTIAL**：Windows OFF 0xC0000005（3221225477）根因 UNKNOWN；ON 成功不能证明开关导致崩溃。
- W04 三对有效配对：NOT_RUN_STOP_CONDITION，配对等价 UNAVAILABLE；≤3% 额外开销 NOT_VERIFIED。
- R09/R10 及既有失败样本、RED/GREEN、Windows 收集错误全部保留；不以工程绿灯关闭性能问题。
- verification 保留 v1 原字段、类型与本机事实，只将 final_sha_linux_ci 更新为 PASS，追加独立 ci_evidence。
  仓库未发现该验收回执的独立 schema 或代码消费者；现有 biz_perf_03_a/schema.json 是 trace schema，不能误套。
  JSON 解析、既有字段兼容性、逐 SHA/Run/Job/Step 对照与 Markdown 链接检查适用；不编造 schema validator 通过。
- 本轮仅证据/治理文档，不重跑 pytest 全套、性能实验、迁移、应用服务或业务库操作。

任务登记沿用 [docs/tasks/README.md](../tasks/README.md) 的编号与存放机制。
后续仅建议先审阅 Windows OFF 原生异常只读定位方案，再恢复可重复 OFF 基线与有效配对，
之后才进行三对开销验证；上述后续执行不属本轮授权，不进入 B 阶段。


### 本轮逐文件交付及 AC-01–AC-09

| 文件 | 修改原因 |
| --- | --- |
| 本 R1 closeout | 补最终 Run/Job/Step/日志，校准 R11，保留原失败与性能缺口 |
| biz_perf_03_a_r1/verification.json | 保留原 v1、本机计数与字段类型，追加精确 SHA 的 CI 证据与文档校验 |
| PROJECT_STATUS.md | 以 16ef3062 工程 PASS 更新执行指针；R1 PARTIAL、治理 REVIEW_PENDING 不变 |
| PROJECT_ROADMAP.md | 固定原生异常定位→配对恢复→三对开销验证顺序，不进入 B |
| DECISION_LOG.md | 追加 DEC-20261103-002，记录 workflow/性能判定分离及权限边界 |
| docs/tasks/README.md | 在既有任务编号/存放规则下登记 DOC-CLOSEOUT，不另造索引体系 |

候选 localization.json 不修改：其是原 Windows OFF/ON 定位事实，不是 CI 结果；
预注册计划不修改。业务代码、测试、脚本、工作流、迁移、开关与阈值均无变化。

本地验证：`python -m json.tool docs/acceptance/biz_perf_03_a_r1/verification.json` 通过；
既有字段与历史值兼容、4 个 Run/19 个 Job 的 SHA/URL/attempt/状态与日志统计一致；
Markdown 本地路径/章节锚点、六文档范围与 `git diff --check` 通过。
未发现该验收 JSON 的独立 validator，未声称运行其不存在的 schema 合同。
额外执行既有静态治理合同四个显式节点（不导入业务配置）：
`test_static_and_history_versions_cannot_authorize_any_high_risk_purpose`、
`test_unknown_versions_never_fall_back_to_current_or_history`、
`test_all_eleven_historical_manifests_keep_original_git_bytes`、
`test_historical_subprocess_cannot_hide_failure_skip_or_missing_cases`，
均来自 tests/unit/test_source_contract_governance.py，共 **19 passed，11.49s**。
该统计仅属于本轮文档安全校验，不并入精确 SHA 的 5347 或本机旧 53 项。

| 条目 | 文档范围验收 |
| --- | --- |
| AC-01 | PASS：修改前 master 与证据唯一 SHA 均为 16ef3062；旧 32cf/治理 SHA 明确为历史 |
| AC-02 | PASS：四个 Run、逐 Job/Step、测试数字和日志索引已核实 |
| AC-03 | PASS：各 authorize 及性能阶段逐项 skipped，未写成性能通过 |
| AC-04 | PASS：R1 PARTIAL、三对未完成、≤3% NOT_VERIFIED |
| AC-05 | PASS：0xC0000005 根因 UNKNOWN，失败证据未删除 |
| AC-06 | PASS：收尾/JSON/状态/路线图/决策指向一致 |
| AC-07 | PASS：JSON 解析、字段兼容、静态治理合同、链接/锚点与格式检查通过；专用 schema 不存在已披露 |
| AC-08 | PASS：仅六份现有文档/状态文件，localization 原样保留 |
| AC-09 | 由最终 Git 交付回执确认 master 提交、推送与干净工作区；不在本文追记自身最终 SHA |

本表验收的是证据同步，不标记 R1 COMPLETE/ACCEPTED/CLOSED，也不代替负责人最终业务验收。
