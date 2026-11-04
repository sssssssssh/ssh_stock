# CI-OPT-02 — W00 审计与待批准实施方案

## 当前批准与实施接续

负责人在W00交付后回复“已确认”，批准方案B、分片并发上限2及先B0后条件B1的顺序。
本节为当前状态；下文W00的未授权文字保留原审阅语境。
W01集合/回执/覆盖率合同与W02 B0源码已实现，等待最终精确SHA的Linux结果。
B0为pilot 8节点与serial其余节点，当前全集5425（新增18项CI合同测试）；不把原5407当固定应有数量。
B1仍禁用，原两个PG分片提案没有进入执行选择器。W03同SHA串行和至少两次候选尚未完成，状态PARTIAL。

### 实现及实际本地验证

- `.github/ci-test-manifest.json`固定当前节点、所有tests Python文件摘要及纯单测的四个依赖源摘要。
  `python -m scripts.ci_test_shards manifest`只收集和生成待审manifest，不执行fixture或连接数据库。
- 新python-scope Job复用原CI-OPT-01分流；docs不启动分片matrix，原主Job与Required Check名保留。
- python-tests使用独立GitHub VM/PG服务/V14容器，matrix最大2，fail-fast=false；各Job内串行。
  当前只有serial分片运行PG测试；pilot禁止socket连接。没有启用PG并行或xdist。
- 收集在子进程完成，实际pytest的导入仍被coverage测量；两个分片独立隐藏coverage文件及精确JUnit。
  汇总校验SHA/run/attempt、每组exit0、完整节点多重集、分组所有权、JUnit真实节点/结果和文件摘要。
  coverage真实combine后仍≥70%，再生成原full XML供原安全证据及端到端步骤使用。
- 任何新增文件、fixture变化、收集差异进入原全集serial fallback，拒绝分片合格声明，需审阅后更新manifest。
  汇总开始即写INCOMPLETE，失败不会留下新的FULL_PASS。已有serial/full失败和取消仍让Required Check失败。
- 原正式迁移upgrade/downgrade/upgrade、目标回归、Docker/前端/浏览器/队列端到端等步骤保留。
  主Job在分片完成后继续这些原步骤；B0预期没有可观整链提速，增加成本需如实评估。
- CI-OPT-01精确投影新增CI-OPT-02层；旧生产/历史字节与授权规则不变。
  两个旧拓扑测试的断言做精确兼容：主Job依赖必须等于python-scope/python-tests，其余Job仍无依赖；
  原full命令由真实分片及70%组合门禁替代，其他命令逐条相等。没有删除旧测试或默认skip/xfail。
- RED新增合同在模块不存在时真实收集失败；修复后18项通过，真实coverage两份合并100%、破坏工件拒绝。
  扩展合同回归183项通过；本地pilot从5425项选8项通过，其他5417属于serial。
  早期18个旧依赖断言失败及脏树guard拒绝均保留日志，不冒充最终结果。
- 本机Docker daemon不可用，未连接/启动业务数据库；本地不执行PG大套件或高成本A4/G1/Publication实验。
  PG资格、最终覆盖率及Linux整套结果以推送后的同SHA工件为准，不把本地18/183/8相加为完整套件。

### 未关闭事项和回滚

W03尚缺同SHA、固定Runner规格的串行基线及两次候选、queue/wall/CPU/成本报告；不得宣称20–30分钟或性能PASS。
B1前置的双物理实例/fixture所有权和真实Linux稳定性证据尚未齐备，保持禁用。
实际CI普通提交可自动触发，无手动高成本授权扩展；现有连接器不提供workflow dispatch写入，
若需要额外同SHA运行，应由有权限的Runner/操作端执行已审阅方案，不以换SHA的提交替代对照。
本轮单一实施提交可整体revert恢复W00前串行路径；不涉及业务schema/数据或金融逻辑。
最终CI结果通过交付回执和工件给出，不为追记自身SHA生成循环状态提交。


日期：2026-11-04（Asia/Shanghai）。负责人：项目用户；方案编制：Codex。
状态：**REVIEW_PENDING / W01–W03 NOT_AUTHORIZED**。
需求来源：CI-OPT-02 完整 pytest 拆分与安全并行化开发修改任务书。
当前会话授权：拉取最新代码、完成 W00、提交推送审计方案；任务书明确要求另行确认分片及并行上限。

## 1. 基线与证据边界

- 开始时本地为 codex/biz-worker-02，工作区干净。该远端分支已不存在，首次 pull 没有可合并的 upstream。
  fetch 已取得最新 master；依据本任务“仅 master”要求切到 master 并快进，未丢弃或改写历史。
- 本轮修改前 HEAD / origin/master / GitHub master：`252f7559f8ab86de3420c0aaad825e819fb38a40`。
- 治理章程、状态、路线图、决策、任务索引及相关 PRD/设计/规则/README 已复核。
  CI-OPT-01 的旧 PARTIAL 文字与最新成功 Actions 有时间差；本轮保留历史，更新执行指针。
- 不将本审计文档提交的 SHA 当作下述历史代码运行的 SHA；不循环补提交自身 CI 状态。
- 当前只读收集 **5407 个唯一 nodeid，319 个模块，0 重复，退出码0**。
  应用 dotenv 在实例化 Settings 前关闭，URL 为不可连接的合成 loopback 目标，socket.connect 被拒绝。
  没有执行测试、fixture、迁移、网络连接或数据库操作。收集不代表测试通过。

机器证据位于 [ci_opt_02](../acceptance/ci_opt_02/summary.json)：
[节点全集](../acceptance/ci_opt_02/nodeids.json)、[模块/fixture/风险](../acceptance/ci_opt_02/modules.json)、
[工作流拓扑](../acceptance/ci_opt_02/workflow-inventory.json)、[Top30](../acceptance/ci_opt_02/top30.md)。
风险是静态信号及实际 fixture closure，未出现信号不证明无副作用；unit 目录不是纯函数证明。

## 2. 两次真实完整代码 CI

| 代码 SHA / Run | test Job wall | 全量结果 | 解释 |
|---|---:|---|---|
| 57edac41 / [41803501811](https://github.com/sssssssssh/ssh_stock/actions/runs/41803501811) | 3731秒 | 5407 passed；90.02%；pytest 2965.99秒 | 成功历史基线，不是当前候选性能验收 |
| f39f4a80 / [41795028412](https://github.com/sssssssssh/ssh_stock/actions/runs/41795028412) | 2900秒 | 5402 passed / 1 failed | 保留旧合同失败；后续部署/前端等步骤未完整执行，不能当提速对照 |

原始逐步骤 started_at/completed_at、结论、JUnit逐节点时间、Top30及模块累计时间分别在
[成功记录](../acceptance/ci_opt_02/run-41803501811.json)和
[失败记录](../acceptance/ci_opt_02/run-41795028412.json)。两份 ZIP 的 CRC 与 GitHub SHA256 已核对；
JUnit 摘要写入各记录，原始工件仍可按 artifact ID 下载。安全插件原先脱敏的错误不尝试还原。
两个 Runner 均标签 ubuntu-latest，实际 runner_name 不同；不是同机型受控候选对照。
队列时间与 CPU/RAM 规格本轮未可靠取得，保持 UNKNOWN，不能把 wall 当 CPU。
逐测试时间包含 setup/call/teardown，父子阶段不得重复相加。

最新 [252f7559 docs CI 41803968797](https://github.com/sssssssssh/ssh_stock/actions/runs/41803968797)
只为已登记说明文字快速路径，完整 pytest skipped；约52秒来自任务书，未拿它作完整代码基线。

57edac41 的5407条脱敏JUnit记录通过现有 pytest mangle 与安全参数摘要映射，全部匹配当前收集全集。
f39f4a80 的5403条中5402条匹配当前同名节点；旧 `test_T11_only_five_reviewed_test_functions_changed_and_no_original_test_removed`
为后续合同修复前名称，未匹配的原始记录继续保留。其余当前节点不填造历史耗时。
同名匹配只提供规划索引，不证明跨提交代码、数据或性能完全相同。

## 3. 耗时与真实隔离边界

| 层 | 当前节点 | 历史JUnit累计秒 | 当前安排 |
|---|---:|---:|---|
| tests/integration | 943 | 2371.009 | PG/迁移/金融/发布/Worker敏感；默认串行 |
| tests/integration_offline | 100 | 149.226 | fork、Unix socket、pidfd、原生工具链；独立工作目录，组内串行 |
| tests/unit | 4364 | 412.803 | 含SQLite、全局patch、进程和历史guard；逐文件审阅后才能提取纯单测 |

合计2933.038秒；与pytest wall的差额保留为collection/coverage/报告等未归因时间。
主要瓶颈是PG集成层，不能用纯单测局部提速冒充整条CI达到目标。

当前 test Job 独占 service postgres:17（5432）及带 marker/system_identifier 的 V14 容器（55438）；
部分旧测试清理固定服务表，部分创建UUID子库。`tests/integration/conftest.py` 有全局鉴权覆盖。
独立session或不同数据库名不足以证明物理隔离；同一PG里绝不能并行这些清理/发布测试。
历史源码测试会clone历史checkout并启动嵌套pytest；它们必须留在独立Job串行，不能继承当前性能权限。
固定端口在不同GitHub VM可重复，在同一VM使用xdist则冲突。tmp_path不能隔离cwd下固定工件路径。

## 4. 可比方案与建议

| 方案 | 关键路径 / 成本估计 | 风险 | 回滚 |
|---|---|---|---|
| A 原串行 | 已观测约49分25秒pytest、62分11秒test Job；并行新增Runner分钟0 | 安全基线，反馈慢 | 无改造 |
| B 独立Job分片（建议，分步） | 两份隔离负载理论下界约24分27秒累计测试；加重复安装/迁移/coverage/末端验证，20–30分未证明；总Runner分钟可能增加 | 跨Job聚合、测试所有权和覆盖率必须证明 | 单一实施提交revert恢复A |
| C 同Job pytest-xdist | 首先只可能用于已证明纯单测，收益上限小；新增依赖与进程资源成本待测 | 固定PG/文件/进程/global fixture冲突，不允许全套-n auto | 不引入xdist或撤回其有限分组 |

**拟批准方案B，最大同时执行测试Job数为2，组内一律串行，不安装xdist。**
分片清单见 [proposal.json](../acceptance/ci_opt_02/proposal.json)，仅为待批准数据，不是可执行选择器。

1. B0 首次小试点：只提取 `tests/unit/test_m15_1_experiment_grid.py`（8节点），
   其余5399节点保持原敏感串行路径；最大2。该纯数据候选未运行并行资格证明，
   W01须沿其 app.domain.experiment / portfolio_config 依赖复核无IO、全局持久状态、网络或固定工件。
   不满足即仍用A；预计几乎没有整链提速，不标性能PASS。
2. B1 目标分片：proposal逐文件给出两个独立所有权集合，依据历史模块耗时做固定整模块平衡，
   不按nodeid hash打散fixture。任何模块不能跨Job；分片中每条当前nodeid只出现一次。
   **B0资格和两套物理PG隔离证据通过后才能启用**；未证明时保持B0/A。
   排布只用于审阅，历史时间是估计，不是候选实测。线程/进程/历史guard在所属Job内串行。
3. 同一精确实现SHA做串行基线及至少两次候选；固定Runner规格、CPU/RAM、镜像/依赖/seed与数据库口径。
   当前ubuntu-latest标签不证明同机型；资源或证据不足则W03 PARTIAL，停止继续试跑。
   先审查现有CI是否支持同SHA串行路由，不能用不同SHA近似配对。

## 5. W01–W03必须实现的合同（尚未实施）

- 版本化manifest绑定精确源码/测试集合与每模块摘要；实际collect失败、未知文件、重命名、重复、缺失均失败关闭。
  sorted nodeid用Counter精确比较，不只比数量或集合。新增/变更先走原串行全集；本次候选不发FULL_PASS。
- 两PG Job各有独立VM、service/container、数据目录、UUID marker、system_identifier及库名。
  服务5432与标记容器均分别拥有；仍先核验物理身份再DDL。保留正式upgrade/downgrade/upgrade、
  PG17/原子发布/取消/未知ACK/金融金标，不用SQLite替代。不同Job不共享volume、发布身份或连接信息。
- 保留source_contract_pytest与a42331_pytest_safety、脱敏、超时及always上传失败证据。
  artifacts绑定SHA/run_id/attempt/shard ID；不使用旧缓存或别轮结果证明当前分片。
- coverage使用独立 `.coverage.<shard>`，上传隐藏文件；统一相对source/path规则，聚合真实coverage combine，
  所有必需分片缺失/损坏则拒绝，组合仍须≥70%；同时报告相对90.02%基线变化。
  单分片不要求全仓70%，但不得取消最终组合70%；历史嵌套进程覆盖语义与原串行一致，不伪造覆盖。
- fail-fast=false保存其他分片证据，但最终Gate always且严格检查所有必选Job结果success、
  exit0、全集多重集、覆盖与端到端工件。失败/缺失/skipped/cancelled/超时均不能FULL_PASS。
- 主工作流保留Required Check名称 `ci-opt-01-ci`；其真实仓库保护配置不可读（403，分支API protected=false），
  不声称已安装分支保护。更改拓扑必须同步ci_opt_contract、step清单与summary合同的精确版本迁移，
  禁止删除旧负例或把新拓扑伪装为旧基线。docs模式仅允许原登记纯文字；未知/混合/YAML/脚本仍full。
- 浏览器/前端/Docker/端到端单列串行尾部，只有Python分片/迁移合格才进入；每Job的成功不能代替总Gate。
  仍保留workflow-contracts/dependency-audit/lookup-diagnosis及其失败闭合；不改A4/G1/Publication高成本授权。

验收A01–A14逐项为 W01–W03 NOT_RUN；W00只有收集/静态规划与历史证据，不签发性能或生产资格。
W03记录wall/queue/CPU/Runner分钟、两个候选中位数/最差、最大分片和整条CI时间；无法取得的字段明确UNKNOWN。
出现混库、卡死、随机红灯、身份混淆、coverage异常或遗漏，保留失败，撤回该分片为串行，禁止无限刷绿。

## 6. 本轮交付与停止线

只新增审计文档/机器证据并同步治理指针；业务、tests、scripts、工作流、模型/迁移及策略未改。
本地验证仅collect-only及文档JSON/全集/摘要/diff检查；不执行完整pytest、服务或性能实验。
新审计文件不在CI-OPT-01纯说明白名单，推送将按现有策略自动走普通full CI；不临时扩白名单绕过。
该自动CI不是分片性能实验，不因它完成再造状态提交。W01–W03必须等待负责人具体批准。

建议负责人确认：**方案B，测试Job并发上限2，先B0纯单测试点；B1仅在独立物理实例、fixture所有权及Gate合同通过后启用。**
若不批准B1，只交付B0资格结论并保持敏感测试串行；不宣称达到20–30分钟。
回滚范围为未来单一实施提交，不涉及业务数据、schema、历史manifest或生产部署。
CI优化不关闭 BIZ-PERF-03-A-R1 或股票业务性能问题。
