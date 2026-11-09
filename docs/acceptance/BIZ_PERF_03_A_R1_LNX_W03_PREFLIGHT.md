# P0-LNX-W03-PREFLIGHT-01：真实 Linux 单对实验前置审查与预注册

版本：V1.0；核查日期：2026-11-09，Asia/Shanghai；证据取样截至 09:38 +08:00。
执行者：Codex；独立审阅者：ChatGPT；最终批准者：项目负责人。
授权来源：负责人本轮明确批准 W00～W03，仅新增本文，禁止真实执行、Git 交付及治理更新。
外部任务书作为需求来源，本文记录实际核查与设计；其中既有验收声明不冒充本轮重新取得的批准。

## 1. Executive decision

**W03_PREFLIGHT_NO_GO / NO_GO_PENDING_OWNER_DECISION**。

本轮 HEAD、origin/master、实时 GitHub master 均为
`b6ffb7bf8ec7d26f771d9b89923e4f7e926edbed`，分支 master，开始工作区 CLEAN。
没有拉取、切分支或重写历史。当前报告为唯一新增的未跟踪文件。

普通工程 CI 与固定 Mock 的 Linux 回收场景有真实证据；未来实验机、R1 真实适配器、
物理 PG17 身份、输入装载快照、全列比较器、持久可信回执与外层硬阻塞处置均未就绪。
本轮批准的是审查，不是 OFF1→ON1 执行。缺少风险裁决和执行授权，不能进入真实试验。
R1=PARTIAL、原 AC05=PARTIAL、Windows 原生异常根因 UNKNOWN、三对 ≤3% NOT_VERIFIED、
04-E CLOSED、04-F NOT_STARTED、正式容量 PENDING、生产读取 NOT_AUTHORIZED。

W00 身份/证据、W01 十二门禁/环境比较、W02 单对预注册设计、W03 NO-GO 建议已形成。
文档检查完成不表示十二门禁通过；真实实验次数为零。

## 2. Evidence provenance

### 2.1 读取范围、身份与治理冲突

按 AGENTS 顺序读取 PROJECT_CHARTER、PROJECT_STATUS、PROJECT_ROADMAP、DECISION_LOG、
docs/tasks/README；业务依据按 PRD→系统设计→PROJECT_RULES→README 的相关诊断、隔离、
性能及历史证据边界核对。再核查 R1 plan/closeout、LNX W01/W02 回执、04-D/E 合同与归档，
以及下表源码。所有代码只静态读取；没有 import 应用或调用其中函数。

| 当前冲突 | 证据与处理 |
| --- | --- |
| PROJECT_STATUS 顶部仍为 2026-11-06 G0 最终交付，正文有更早 CI-OPT/04-E 指针 | 这些是带日期的历史快照；实际 Git 已包含 W01/W02，不从旧指针推断当前运行许可 |
| docs/tasks/README、DECISION_LOG 仍要求另批 P0-W01/W02 | LNX W01/W02 后续批准记在各自回执；本轮明确批准 W03 审查，优先适用，但不修改治理文件 |
| W01/W02 回执保留 LOCAL_REVIEW_PENDING、NO_COMMIT_NO_PUSH、新 CI NOT_RUN 等提交前文本 | 实际提交与远端 CI 已发生；历史文本保留，本文追加当前独立查证，不倒改旧事实 |
| 外部任务书说明 W01/W02 已独立验收，仓库没有完整最终审阅批准链 | 标记 OWNER-SUPPLIED_ACCEPTANCE_CLAIM；本轮可独立证明工程结果，不能替负责人新签发真实运行授权 |

最近提交链：eb8cfe7 G0 文档→1d002be W01→53f2974 W01 修复→da15e71 W02→b6ffb7b
协作 actor 退出修复。未来 target_sha 必须在下一次批准时重核；master 变化即 BASELINE_CHANGED。

### 2.2 GitHub 当前工程证据（只读 GET）

四条 Run 均绑定上述完整 b6ffb7b SHA、master、push、attempt 1、completed/success。
下列时间为 GitHub updated_at，UTC；括号为上海时间。Job ID 来自实际 jobs API。

| Run / 完成更新时间 | 成功 Job（name / ID） | skipped Job（name / ID） |
| --- | --- | --- |
| [Main 42490454748](https://github.com/sssssssssh/ssh_stock/actions/runs/42490454748)，2026-11-08 15:37:53Z（23:37:53） | test/128761453533；dependency-audit/128761453765；workflow-contracts/128761453810；lookup-diagnosis/128761453873；ci-opt-01-ci/128777673239 | ui-visual-acceptance/128761454389；authorize/128761454519；lookup-tail-attribution/128761454954；capacity/128761771966；publication-release-gate/128777675035 |
| [A4-1 42490454756](https://github.com/sssssssssh/ssh_stock/actions/runs/42490454756)，14:37:07Z（22:37:07） | contracts/128761453608；ci-opt-01-ab-read-a4-baseline/128762140975 | authorize/128761454655；isolated-baseline/128762142402 |
| [A4-2 42490454820](https://github.com/sssssssssh/ssh_stock/actions/runs/42490454820)，14:41:35Z（22:41:35） | contract-and-safety/128761454108；ci-opt-01-ab-read-a4-2/128763250560 | authorize/128761455158；laboratory/128763252152；a42-acceptance-gate/128763252247 |
| [Publication 42490454667](https://github.com/sssssssssh/ssh_stock/actions/runs/42490454667)，14:36:46Z（22:36:46） | contracts/128761453742；ci-opt-01-publication-v13/128762058554 | authorize/128761454251；candidate-performance/128762059958 |

合计 23 Job：11 success、12 skipped。所有 skipped 都是未执行，不提供授权或实验通过。
Main test 的 full_tests、Ruff、迁移、前端 test:coverage/build、Compose config/build 均 success；
这是既有 CI 隔离环境中的操作，不是本轮在本机执行或生产验收。
日志重新只读取得：6331 passed、816 warnings、3033.58 秒；coverage 90.02%，原门槛70%。
setup-python 实际路径为 Python 3.12.16/x64，不能与 04-D 3.12.14 合并为同一环境。

Main Artifact **13623516968**，146348 bytes，API 绑定 Run/SHA，未过期：

- ZIP SHA256：`1e08356213194e8fbe538ffec391ec28d5dfd8797296564c1e803b3b39e00811`，与 API digest 相同。
- `m17_1_2-full.xml` 原字节 SHA256：`7fa91c4d0bace4ccabb378796bff898647f1e58fab2112f9aba09a3471a99946`。
- 本轮标准库离线解析 6331 testcase，failure/error/skipped 各0。
- `tests.integration_offline.test_perf03_lnx_hard_watchdog_linux` 恰好18节点，异常/跳过各0。
  用源码 AST 的参数字面量和原 safe_identifier 的 SHA256 前16位规则核对完整节点集合，完全一致。
  包含原失败 `child_term_before_spawn-False` 对应后缀 `b96f901ee0b27f98`；这证明该节点当前通过，
  不恢复旧失败的具体 traceback，也不将固定 Mock 变为真实业务证明。

W01 历史工程 [Run 42385427776](https://github.com/sssssssssh/ssh_stock/actions/runs/42385427776)：
SHA `53f297430e432e9c7f018f6414556022aeda0a58`，push/attempt1/completed/success，
2026-11-07 16:01:57Z 更新；test Job128441681589、workflow-contracts128441681352、
dependency-audit128441681576、lookup-diagnosis128441681520、ci-opt-01-ci128453033393 success。
authorize128441682785、UI128441682719、tail128441682830、capacity128442100935、
release128453034442 skipped。该历史 Main 已重新查证；不声称本轮下载了该 Run 的 JUnit。
W01 当时278项本地结果属于 W01 回执；当前6331项不能倒填为历史 W01 数量。

### 2.3 04-D 实际安装与 04-E 完整性

[04-D Run42156106471](https://github.com/sssssssssh/ssh_stock/actions/runs/42156106471)
本轮 API 重核：workflow_dispatch/master/attempt1/completed/success，
target `ab5e29df5aa230076069dd587557720c2db382dc`，installation Job127690531459 success，
runner label ubuntu-24.04；2026-11-06 03:22:52Z 更新。
归档索引 [artifact-index.json](biz_perf_04_d_runs/42156106471/artifact-index.json)，Artifact13474492280。
本轮下载既有工件，5605 bytes，ZIP SHA256
`735addf5df05b36eba923ac4d8cbb257c8fafceb05a069c687ffba1fa67b0a13`，与索引一致；
四份原始 JSON 与归档逐字节一致：

| 原件 | SHA256 |
| --- | --- |
| receipt.json | c600d0468877d52c744371c7b1baaea5aa10b1f341228ec6a3b201abd6dec372 |
| runtime.json | e2f525eab130f33b2a9e9c70e217e675d6f1a7e18d19e72ad4ef809787cf5f84 |
| dependency-verification.json | ecb21a5995585c5717cb78b5c86a28f3a6125f5b7841e7fdceed7d15169c5aaa |
| tests.json | 7bb8ff898888eeab9826ee811f3057c365b89816a2e81df100c5d566c4ecf908 |

原件支持：CPython3.12.14、Linux x86_64/64bit、glibc2.39、pip25.0.1；67包集合核验、
七阶段PASS、pip check及148 tests（0 failed/errors/skipped），target_installation VERIFIED。
这只是固定历史目标安装 VERIFIED，不是当前实验机安装 VERIFIED；未重复安装或下载67包。
原 runtime/dependency/tests 无独立 Run 字段，依靠同工件、固定字节摘要及索引绑定，不补造字段。

04-E [bundle](biz_perf_04_e_bundle.json) / [validation](biz_perf_04_e_validation.json)：
标准库只读解析并重算 canonical bundle SHA256
`cf79a5312aae5aecf174caf3435e0e4e6a93ee934f8cc971e46c952f64bb4502`，与原报告一致。
12项引用的 **Git HEAD 原始 blob** 摘要全部匹配；source_commit_sha 分别为：
A `9df4cfed0d0153b09b0f4038882fa8423fe732e1`；B `decaaba86535575e307edd676221ec066517caf6`；
C `c397821d45c755473bf627a40392d392bd1eab2b`；D锁 `4fe37aee77570b3377fb5ff41b85ab9e49fbbcef`；
D安装 `ab5e29df5aa230076069dd587557720c2db382dc`。E代码交付为
`63cbc04bc257e62080df34561f7865a5f18941f4`；不将这六种身份改为当前 master。

本机 checkout 的 A～C 六文件及 D锁 manifest 共7项原字节不匹配，Git blob全部匹配；
这是本地换行表示差异，不改文件、不静默归一化、不运行旧校验器重写报告。
其余5项（D四原件及索引）checkout 原字节匹配。原 validation 的 integrity=VALID 是已归档事实；
本轮只复核摘要/结构，不宣称当前 CRLF checkout 完整校验通过或复跑了 E 语义校验器。
未来实验须使用逐字节核验的 LF checkout。完整性不是签名、性能、容量或生产许可。

### 2.4 源码边界与当前可信事实

以下 exact_sha 统一为当前完整 b6ffb7b；表列 SHA256 来自 `git show HEAD:<path>` 原始字节。

| 文件 / 实际入口 | SHA256 / 核查结论 |
| --- | --- |
| requirements-biz-perf-linux-py312-v1.lock | 88549dce3164364430e20970fa10eb2125b60ff05f456d7bef4474876a98dcfc；历史67包hash锁 |
| requirements.lock | aa8d7f344bc70c749cb91375950ad0620a551add2933329b82520c35bd7c59b5；Main仍安装此直接依赖锁 |
| scripts/performance_diagnostics_overhead.py / root_arm | 98dbd99f94f2c784ca862bbadce43228350d72aca4f36ac4eca9110c9e763693；单臂定位入口，不是配对控制器 |
| tests/integration/test_perf03_root_diagnostics.py | 7f9a5a16e19d64e7215466e8593f9fad3e1ab630a23cd036d087fba81fb9683a；同进程OFF/ON，排除全部id等列，不满足完整身份闭包 |
| scripts/v14_test_database.py / verified_test_url | 5a7edc5707b5b21a97e711d043dbcff082739699376be88955f74c6c3625f1ca；显式loopback测试库、major17、UUID marker及system_identifier核验 |
| scripts/perf03_lnx_offline_supervisor.py / supervise,batch | c6d71d7f923995af5bcf12acc48c71828ad6aaea2b2d206cfe33ad199c64edb5；固定mock_child、内存owner票据；同步Popen/文件I/O无硬抢占 |
| scripts/perf03_lnx_hard_watchdog.py / run | 02d8c6f939c694410c04fb7bc449f030e0e2c8708c1c801b08e5a2eba5940454；固定actor、100～1000ms Mock、TERM/KILL各0.2s |
| scripts/perf03_lnx_hard_mock_actor.py | e4c4a2cf9c5478cbd85c4f4fe17277c535e8eeba29427846b473e9065109d264；固定角色/有限协议，无业务适配 |
| docs/acceptance/biz_perf_03_b_actions_once_protocol.json | 56e81fcbfe23071dde631d1eab9eb7b5d74e4011f0f27b6b98e2b8f845a92d17；4股/900日/2025-01/单根、全五开关false，与R1不兼容 |

root_arm 调用 verified_test_url 后禁用 dotenv 配置，再由 isolated_v14_database 建随机库、正式迁移、
seed、create_recalculation_job→claim_next_job→execute_claimed_job→读 JobRun/DataPublication。
但模块顶层已导入诊断业务模块；不能把函数内先验证描述成整个 Python 进程启动前完全无应用导入。
其本地前缀/最终replace不提供外部持久可信确认；原 wall 包围完整 execute_claimed_job 返回，
没有完整配对控制器、全表导出或外部CPU/RSS闭环。旧 CPU measure() 更不是根任务。

03-B controller/Workflow 仅是静态参考：固定 workflow_dispatch、Environment、target_sha、
protocol_hash、唯一run/attempt1及五开关false；有受限网络/容器归属/资源检查。
它只执行一个诊断根，ON被合同拒绝，不能拿来直接调度R1单对；其历史成功不授予本轮运行许可。
Environment 实际设置和未来审批人当前状态本轮未查询，UNKNOWN；不读取Secrets/Variables值。

| 事实维度 | 可证明事实 / 证据等级 | 当前仍缺 |
| --- | --- | --- |
| 源码/工程 | 当前SHA四Run工程成功 / API+日志+JUnit | 不提供实验授权 |
| 版本/依赖 | 04-D历史3.12.14完整67包安装 / 原工件VERIFIED | 当前目标机解释器、venv、ABI/镜像身份 |
| Linux runner | Main在Linux运行固定Mock18节点 / 真实工程测试 | 合格R1资源规格、独占性、噪声和配额 |
| Mock监督 | W02已列回收与FIFO场景 / MOCK_ONLY | 真实业务adapter及全生命周期硬监督 |
| PG17隔离 | 静态helper与CI历史实例隔离步骤存在 / 代码+工程证据 | 未来实验物理实例/marker/system ID未核验 |
| 数据快照 | 原seed函数可追溯 / 静态 | 未来逐表实际行数、全输入digest与冻结装载证明 |
| 真实根 | 既有定位入口与历史Windows ON事实 / HISTORICAL | 当前Linux单对NOT_RUN |
| 准确清理 | Mock OS核验 / 限定场景 | 真实Worker/PG/后代/外层监督者清理确认 |
| 结果等价 | 单元/旧集成对照存在 / 有限字段 | 完整实体闭包和列级映射、dtype、失败/ACK原语 |
| 性能比较 | 历史+5.650109%根、+22.531557%CPU / 非当前闭环 | 当前单对及新三对≤3%均NOT_VERIFIED |
| 生产许可 | 固定证据明确排除 / NOT_AUTHORIZED | 本轮不申请生产权限 |
| Windows崩溃 | 历史OFF 0xC0000005 / 原失败保留 | 根因UNKNOWN，Linux成功不反向证明已修复 |

## 3. Hard-gate matrix G01–G12

每项只有一个 status；PARTIAL 也不是放行。exact_sha_or_hash 中 S 指本节统一的
`b6ffb7bf8ec7d26f771d9b89923e4f7e926edbed`；第2节给出对应原字节摘要。
责任人是拟议解除职责，不表示对方已接受或批准。所有解除动作仅为下轮方案。

| Gate / status | evidence_path_or_run；exact_sha_or_hash | what_was_checked | gap / owner_decision_needed 与解除责任 |
| --- | --- | --- | --- |
| G01 NOT_AUTHORIZED | 本轮用户批准、外部V1.0第1/7节；S | 仅审查及一份报告授权 | 无真实实验许可；负责人须另批任务版本、目标机、数据、次数、风险及执行人，ChatGPT独立审阅 |
| G02 MISSING | ci.yml test/runs-on；Main test128761453533；S | 仅证明历史hosted Linux runner可跑工程测试 | 未来CPU/内存/磁盘/架构/内核/用户/网络/时钟与配额、独占性UNKNOWN；负责人选路径，资源所有者提供签认基线 |
| G03 PARTIAL | 04-D runtime/dependency/receipt；Run42156106471；target ab5e29df5aa230076069dd587557720c2db382dc；锁hash88549dce…dcfc | 历史3.12.14/67包安装与当前锁字节一致；Main实际3.12.16 | 新机未验证；负责人选3.12.14及原锁，运维在另批任务提交目标机安装/包/ABI证明；另选版本先审批重验 |
| G04 MISSING | scripts/v14_test_database.py；S；hash5a7edc57…f1ca | 检查major17、marker、独立control system ID及写前/删前核验逻辑 | 无未来物理PG身份/归属证据，NOT_VERIFIED；负责人授权隔离准备后由资源所有者核验，禁止以CI旧实例代替 |
| G05 MISSING | R1_plan§5、test_business_recalc_performance.seed；S | 固定2股420自然日，weekday输入，含原退市边界；不缩250/430 | 缺未来实际装载行数/表清单/摘要、完整输入冻结；负责人批准原规模，执行人另批准备后提供manifest |
| G06 PARTIAL | overhead.root_arm、test_perf03_root_diagnostics、W01/W02固定入口；S | 原create→claim→execute→publication存在；Mock不接受业务命令 | 无合格Linux真实根adapter/阶段证据/ACK与取消失败闭包；需独立设计审阅及限定实现授权，禁止直接更换Mock actor |
| G07 NOT_PROVEN | R1_plan§5；W01 AC05；W02 NOT_PROVEN；S | 原180/180/30、六臂2700；Mock与03-B预算独立 | FIRST_SPAWN、WATCHDOG_SYSCALLS、D状态未证明；真实资源/CPU/RSS封顶及外层期限缺签认；负责人明确接受限定风险或批准外部隔离方案，不能凭多测Mock解除 |
| G08 PARTIAL | R1_plan§5与本文§5；S | 同SHA/参数/PG大版本/fixture/资源、OFF1→ON1、独立进程/库设计 | 未有可执行冻结协议、无目标机冷启动/缓存/线程策略证据；负责人确认，执行人提供静态配置与双臂输入身份 |
| G09 PARTIAL | test_perf03_root_diagnostics、R1_plan R09/R10；S | 原比较排除id/calc/job/time列；SQL/FETCH及心跳应分列 | 缺真实全表列级映射、owner/root/job/calc/generation闭包、dtype导出及未知ACK凭证；需限定adapter/比较器设计与另批实现，不放宽断言 |
| G10 NOT_PROVEN | W01 owner/consume_final与W02回执；S；04-D原工件摘要见§2 | 内存票据、OS组核验、持久可信边界已审 | 无真实跨进程/持久可信消费凭据；首次spawn/未知后代/组消失和DB残留独立确认不足；负责人选外部可信归档/监督责任与故障裁决，另行审阅验证 |
| G11 PARTIAL | 四Run/23Job见§2；ci.yml、03-B Workflow/controller；S | 当前工程全绿与12 skipped分离；旧手动协议有SHA/run/env绑定 | 当前没有R1专属批准执行入口；Env实际设置UNKNOWN，旧03-B五flag=false拒绝ON；负责人另批流程，不能dispatch旧协议或改Env凑准入 |
| G12 PARTIAL | R1_plan/closeout停止规则、本文§7；S | 原失败即停、不补样、默认OFF、仅清已知资源原则 | 真实adapter未知ACK/资源收尾证据缺失；负责人批准可核对资源清单、截止和恢复责任，执行人另批实现/演练后才可审真实单对 |

优先级：P0=G01/G02/G04/G06/G07/G10；P1=G03/G05/G08/G09/G11/G12，均须在真实执行前解除。
G01只能由负责人新批准解除；对未知安全事实，批准不能替代事实核验，风险接受也不能写成硬保证。

## 4. Execution environment choice

以下是基于仓库现有入口与已取得回执的方案判断，无资源创建/登录/探针、无即时价格调查。
成本只列类别，实际金额、账号额度与配额 UNKNOWN；不承诺任何现成资源可用。

| 维度 | A：GitHub托管Linux Runner | B：专用隔离Linux VM/ECS |
| --- | --- | --- |
| 重复性 | 已有CI能跑Linux；ubuntu-latest与3.12浮动，不是固定R1镜像；要冻结镜像/解释器/锁及每次运行事实 | 可作为固定镜像、独占时窗和持久审计的候选；实际机器/镜像尚无证据 |
| 环境可信度 | Run/Job/Artifact溯源已有；临时runner不能冒充持续可用实验机 | 需资源所有者、创建记录、镜像digest与独立核查；尚未取得 |
| 资源可比性 | CPU竞争/频率/IO/主机噪声未测，两个job不同机风险；同job两臂也须资源基线 | 候选独占VM同机顺序两臂；宿主超售/CPU steal/频率及缓存仍需登记，不能承诺无噪声 |
| PG17 | CI工程服务存在；R1必须独立新实例、持久物理身份验证及每臂新合成库 | 候选专用非生产实例/隔离数据目录；真实版本/marker/system ID全UNKNOWN |
| Python/依赖 | 04-D曾在hosted ubuntu-24.04验过3.12.14/67包；Main3.12.16不能替代 | 拟固定x86_64、CPython3.12.14、glibc兼容原wheel；须另验新机安装 |
| 凭据风险 | 最小read权限/不加载业务Secrets；旧03-B需Env绑定，不能复用运行许可 | 专用无生产凭据用户与网络隔离；初始资源访问凭据通过受控渠道，不能进入报告/仓库 |
| 用户负担 | 审批和现有Actions体验较少运维；当前无R1单对工作流，需另批入口/审批设计 | 初始机器与隔离责任较重；明确操作者/停止与回收责任后可控 |
| 成本 | runner分钟、Artifact留存/下载；实际额度与价格UNKNOWN | VM/磁盘/快照/闲置时长和运维；实际价格/预算UNKNOWN |
| 可实现性 | 有工程先例，但旧03-B固定单根且禁ON，无可直接运行的R1入口 | 无现成机证明，但更便于固定同机资源与外部监督；仍缺真实adapter |
| 工件留存 | 现有Artifact有到期日；须批准受控外部归档，不能只依赖临时URL | 可设计独立归档与保留规则；持久可信不是文件hash本身 |
| 未知 | 后续runner规格/内核/配额、R1 workflow/Env、硬阻塞处置 | 机器归属/规格/镜像/网络/内核/PG/解释器及运维权限全部待核 |

**候选优先 B，A 为备选；结论 NO_GO_PENDING_OWNER_DECISION。**
理由是当前目标需要同机顺序两臂、固定资源与可审的外层监督；专用机更便于设计这些约束，
这属于方案推断，不是已验证B可用。没有现成B时，不转用普通CI直接试跑；负责人可另选A，
但仍须完成相同门禁及独立R1入口审阅。不沿用03-B数据、总420秒预算或ON=false审批。

## 5. One-pair experiment preregistration

**DESIGN_ONLY / NOT_RUN / PENDING_OWNER_APPROVAL**。本节是冻结设计边界，尚不是可直接执行的
runbook；下列未定值使其不可执行，必须在下一版经独立审阅填实，禁止执行时临时猜测。
本文不提供真实CLI、DSN、自动连接脚本或实验dispatch命令。

### 5.1 身份与输入冻结

| 字段 | 候选/规则；当前状态 |
| --- | --- |
| target_sha | 当前候选 b6ffb7bf8ec7d26f771d9b89923e4f7e926edbed；实际批准时重核，若实现新adapter则使用另审最终SHA及其工程证据 |
| protocol | 本文V1.0 DESIGN_ONLY；真实单对协议版本、审核摘要和批准记录 PENDING_OWNER_APPROVAL |
| dependency lock | requirements-biz-perf-linux-py312-v1.lock，SHA25688549dce3164364430e20970fa10eb2125b60ff05f456d7bef4474876a98dcfc；67包，无更换版本 |
| interpreter/image | CPython3.12.14/Linux x86_64/glibc>=2.28候选；实际解释器路径/二进制hash、glibc、OS镜像与PG17镜像digest UNKNOWN，必须冻结后审批 |
| host/resource | 候选B；实际主机审计标识、CPU/内存/磁盘/内核/用户/网络/线程上限 UNKNOWN；须批准非生产配额和独占时窗 |
| run_id | 实际获准后生成随机全局唯一ID并外部登记，OFF1/ON1从属同一pair；当前未生成，禁止复用旧Run或Mock run_id |
| PG physical identity | 独立实例、PG17 major、随机marker、离线control system_identifier与服务器值双核；每臂随机隔离合成库；当前均NOT_VERIFIED |
| fixture | 原seed(factory,include_closed=False,history_days=420)，2合成证券；fixture源码绑定S；未来装载manifest/dataset_sha256 UNKNOWN，禁止使用04-B元数据代替 |
| flags/config | PERF_DIAGNOSTICS_ENABLED仅OFF1=false→ON1=true；其余优化开关固定false；worker_diagnostics等其余配置双臂一致并单独记录；strategy/config/source hash不得改 |

固定日历2025-01-01～2026-02-24，共420自然日；请求2026-02-23～24，manual、evaluate_signals=false。
原seed含一个原退市边界证券，不人为改成两只始终在市证券。交易日为weekday合成日历，非真实市场日历。
静态推导300个weekday；stock_daily/adj_factor/daily_basic/limit_daily各600行（合计2400），
trade_calendar420行、stock_basic2行、sector1行、member1行；index_daily为300×冻结benchmark指数数，
stock_st/suspend_d输入质量记录各300行。以上是源码推导，不是实际装载证明；原退市后事实布局保留。
未来必须逐表读取并核实精确行数、列/类型、自然键排序、空值、数据摘要及全部外键关系。
保留250交易日预热、430自然日查询范围，记录实际起点/缺失；420日布局不保证每块有完整430日行情。

### 5.2 时间与资源预算（按权威来源区分）

| 来源 | 原限制 | 本设计处理 |
| --- | --- | --- |
| R1_plan§5第一轮 | 每臂setup180s、完整root180s、cleanup30s；root30s起每30s最多5次受限栈 | 原样保留；根超时保存前缀并停止后续臂；栈只限本次合成进程且去私有路径/局部变量 |
| R1_plan§5第三轮 | 同一每臂限制，六臂执行窗口最多45min=2700s | 保留历史三对上限，不授权六臂；单对没有权威独立总窗口数值，须在下轮协议明确，不能把2700当作可扩展每臂预算 |
| 03-B protocol/controller | init180、root180且绝对T0+330、cleanup60、archive30、总420；PG2CPU/3GiB、worker RSS3GiB、可用内存/磁盘各8GiB且CPU>=4 | 仅记录另案合同，不导入R1，不将cleanup30扩成60或套用420；不是当前R1资源批准值 |
| W01/W02 Mock | W01(1,1,1)/10s；W02 root100～1000ms、TERM/KILL各0.2s，actor child清理0.1s | 工程模拟参数，不用于真实业务时限或真实杀停宽限 |

R1 root wall 外部包围完整 execute_claimed_job（含诊断setup/flush与原Worker finally）；
实验库创建/seed/预检单独归setup，实验资源清理归cleanup。不要把环境setup180秒与根内部诊断setup混淆。
根内部 report wall 只是辅助，不能充当性能分母。OFF/ON记录外层生命周期wall、root wall、
进程CPU/RSS与峰值、PG资源分别列出，时间重叠阶段不相加。

R1原计划没有完整的TERM/KILL分配、外层首次spawn/监督者阻塞硬截止、归档/单对总上限及
Linux CPU/RSS硬配额。**这些全部PENDING，阻断执行**；下一轮必须在不延长180/180/30的前提下
明确监督/归档/收尾关系与上限，并经负责人裁决。不能虚构本轮已冻结了数值。
独立外层资源监督方案与D状态故障处置需先审阅；即便采用VM/容器，也不承诺所有内核I/O可抢占。

### 5.3 未来获批后的唯一顺序

1. 冻结最终源码、依赖、镜像、资源/线程/缓存策略、协议hash、批准记录与外部证据目录；
   干净LF工作树逐字节核验。无并行大测试/实验；不得读业务.env或生产凭据。
2. 经独立获准的准备步骤核验非生产机器和PG物理身份，任何写前比对major17、随机marker、
   离线/在线system ID与资源归属。loopback或随机库名单独不足以证明物理隔离。
3. 为OFF1/ON1准备相互独立的新进程与隔离合成库；同实例还是两实例须在下轮冻结，
   本建议同一已验证专用实例上的两新库。输入规范快照/dtype/config/hash完全相同。
   两臂均遵守相同新进程/新库冷启动规则，不声称OS或PG物理冷缓存。
4. OFF1仅一次；保留初始INCOMPLETE前缀、阶段时间、根调用、退出与清理原件。
   任何崩溃/失败/超期/未知ACK/缺证/未确证清理立即停止，禁止ON1。
5. OFF1成功且全部资源/快照/身份复核通过，才ON1仅一次。无重新seed改参数以迁就结果，
   无重试、补样或继续OFF2/ON2。两个根必须分别SUCCESS/PUBLISHED且退出/收尾可证。
6. 业务快照必须在各自隔离库销毁前，以受控外部导出完整冻结；每份原件绑定run/arm/根及摘要。
   发布后独立核验查询/摘要不混入根执行SQL计数；清理只能针对已确认属于本次实验的资源。
7. 外部逐根比较后独立审阅，缺任何原件停止。只有全套证据齐备才可建议
   PAIR_DIAGNOSTIC_COMPLETE，仍需独立确认；不能产生R1_PASS。

### 5.4 比较、动态字段与计数合同

必须提供真实 ORM/表清单和列级导出规格；以当前 data_publication.MODELS/KEYS 的实际发布表为基础，
扩展核查 JobRun/DataPublication、计算运行、generation/owner/source身份及质量/审计引用。
所有业务值、自然键、排序、dtype、Decimal scale、null/NaN、原因码、质量、版本/config/source hash、
根/子任务及发布终态完全一致；不得排除全部id或以总体输出hash单独宣称全等。

动态映射只允许预先审批的逐表逐列清单：随机root/job/calc_run/generation UUID按实体kind及自然键
一一映射，所有引用同时验证；owner不允许跨臂改名，不能以宽泛UUID替换改变所属关系。
生成时间戳仅逐列映射，保留类型/时区/顺序及事件因果；交易/业务日期不映射。
原测试排除的calculated_at、checked_at、created_at、updated_at等只是待审候选字段名，
不是本文已批准全表忽略清单。**完整表列清单和真实导出/比较实现尚缺，G09阻断**。

逐臂记录主执行上下文的业务SQL/写语句量、心跳/控制SQL、独立核验SQL和实验销毁SQL，
按原终态快照范围冻结，保持业务finally计入根、独立查询/销毁排除。driver FETCH与partition/
execute嵌套分列，失败未知行数保持null；不把execute/fetch耗时叫纯服务器或网络时间。
OFF不能因新PERF诊断关闭而缺失可比基准：需要两臂对称外部受控计数器及其成本/归属证明。
计数本身不得新增业务查询/改变Result消费；心跳次数受wall调度影响单列，不拿其波动直接归因。

仅输出本对原始wall/CPU/RSS及描述性比值，不用一对中位数、P95或算术≤3%签发R1资格。
后续新三对另批并预注册OFF1→ON1→OFF2→ON2→OFF3→ON3，全部原值保留，
原阈值 `(median ON / median OFF - 1) ×100% ≤3%` 不变，P95=null。
历史根+5.650109%、CPU+22.531557%不具备当前闭环验收资格，也不预测未来Linux结果。

### 5.5 最小外部证据与失败状态

审批身份/日期/版本/hash、前后target SHA与树状态；主机/解释器/67包/镜像/配置身份；
数据逐表manifest与hash；PG major/marker/system ID的脱敏绑定及资源创建归属；
两臂root/job/calc/generation/trace身份、开始/结束、外层wall/root wall/CPU/RSS、SQL/FETCH摘要；
初始前缀、不可改写首错、退出码/信号/超期、ACK已知或未知、发布终态、进程wait/组核验、
DB/文件/容器等已知资源收尾凭证；导出原件hash、独立对照报告、外部可信确认及归档留存责任。
只保留脱敏安全摘要，不存SQL参数、私有DSN、口令、Cookie、环境全文或原始业务日志。

失败要分别记录：首个异常码/阶段、原生退出码或信号、timeout、cleanup errors、
ownership unknown、ACK unknown、publication failed、artifact unavailable；不压成一个success=false。
成功回执不能只靠子进程自报、同进程owner或可重算hash；独立消费确认/持久信任尚未支持时NO-GO。

## 6. Known unknowns / risk acceptance

| 未知/风险 | 现有证据及需要的裁决 |
| --- | --- |
| FIRST_SPAWN | 同步首次Popen可能阻塞，无句柄时不能推断未创建；真实外层独立资源监督及归属证据缺失，阻断 |
| WATCHDOG_SYSCALLS | 监督者自身目录/pipe/read/fsync/close/signal/wait可能阻塞；W02固定Mock不提供全路径硬保证，需单独方案/责任/有界退出裁决 |
| UNINTERRUPTIBLE_D_STATE | SIGKILL不是所有D状态立即完成的保证；未测且本轮不制造；需明确资源隔离/冻结与停止人工升级路径，不能声称可彻底回收 |
| DURABLE_TRUST | W01内存票据丢失不能从工件重签；W02没有真实持久票据；独立归档与消费确认主体/故障原语未定 |
| 未登记后代及真实进程域 | W02固定child与WNOWAIT边界不等于任意Worker后代；真实归属/遗留核验未证明，不能扫描全机或向未知PID发信号 |
| 当前目标环境 | 没有CPU/内存/磁盘/内核/用户/时钟/网络实际基线；不以普通CI runner标签代替 |
| Windows 0xC0000005 | OFF原生崩溃根因UNKNOWN；历史ON成功、当前Linux Mock成功均不能归因或关闭Windows问题 |
| 治理/接受记录 | 旧G0指针与后续源码/外部独立验收声明存在时效差异；需要负责人单独同步治理，但本轮不改 |
| 字节完整性 | 本机7项历史checkout字节不符；Git原件与D工件已核，未来运行须原字节LF，不修改旧证据刷绿 |

截至本报告，没有发现独立批准接受上述真实执行残余风险的有效路径。风险接受须指明
具体目标、适用范围、未知项、外部停止/恢复责任和失败证据；不能将NOT_PROVEN改写为VERIFIED。

## 7. Stop/rollback/authorization

任一门禁缺证、基线变化、身份不符、资源超限、根失败/原生异常/超期、ACK或提交未知、
未确证进程回收、发布失败、结果不等、原件缺失，都立即NO-GO并停止后续臂。原件和慢样本保留，
不重跑/补样/拼接旧批次。未知归属资源不删除、不解锁业务Writer，不回滚用户业务数据。
仅在下一轮明确批准范围内停止本实验已验证句柄及资源，删前再次物理核验；不能从随机库名推断归属。

业务默认PERF_DIAGNOSTICS_ENABLED=false继续有效；未来测试ON只在独立进程受控配置生效，
不得热改运行中用户Worker。失败时关闭本次执行入口、冻结脱敏证据并交独立审阅。
本轮报告回滚只涉及这一个新增Markdown，若不接受可由负责人决定撤回；无数据/迁移回滚。

批准职责：负责人选择目标/数据/预算/风险与真实执行许可；ChatGPT独立审阅协议/门禁和证据；
资源所有者核实隔离、配额及外部监督/回收责任；执行人只能在最终批准文本内执行。
审批记录需写身份、日期、范围和协议摘要，不能索取或存储实际凭据。
本轮文档不能授权下一步代码、机器、PG17、Worker、OFF/ON、Actions、容量或部署。

## 8. Acceptance checklist AC-01–AC-16

这里PASS仅表示本轮只读审查交付项满足，不表示对应真实运行门禁通过。
本任务AC-05与历史W01/AC05不是同一个验收项；后者仍PARTIAL。

| AC | 状态 | 本轮只读证据与边界 |
| --- | --- | --- |
| AC-01 | PASS | §1/2 Git三方完整SHA相同，master/CLEAN起点可追溯 |
| AC-02 | PASS | §2 Run/Job/API/日志/JUnit/Artifact分离成功与skipped |
| AC-03 | PASS | §2历史source/target/安装/完整性各自记录，旧文件无改写 |
| AC-04 | PASS | §3完整G01～G12，每项唯一状态、证据、缺口和解除责任 |
| AC-05 | PASS | §4两路径比较、B候选及未知/成本类别，NO_GO待负责人选择 |
| AC-06 | PASS | §2/3/5真实root_arm、旧集成与两套Mock接口边界清晰 |
| AC-07 | PASS | §3/6 FIRST_SPAWN等缺口及风险接受缺失明确列阻断 |
| AC-08 | PASS | 本轮无DB/主机/资源探针；G04未来物理身份NOT_VERIFIED |
| AC-09 | PASS | §5完整单对预注册设计；未定字段明确阻断，不伪装可运行runbook |
| AC-10 | PASS | 180/180/30与2700原预算、03-B及Mock限制明确区分；未扩大预算 |
| AC-11 | PASS | 仅OFF1→ON1，失败停后续臂，无自动六臂、重试、补样 |
| AC-12 | PASS | 仅静态解析/摘要与文档检查，无业务import/运行/真实连接 |
| AC-13 | PASS | §1/3/6 W03_PREFLIGHT_NO_GO有证据且未自动READY |
| AC-14 | PASS | 残余风险/审批主体/解除条件清楚，不能凭Mock关闭 |
| AC-15 | PASS | §9下一任务仅草案且NOT_AUTHORIZED，不开展实现 |
| AC-16 | PASS | 原3%/三对不变，无全路径硬保证、容量或性能通过声明；白名单检查见§10 |

真实执行的G01～G12仍有阻断；AC审查PASS不会把它们升级。

## 9. Next scoped task

建议 **P0-LNX-W04-SINGLE-PAIR-READINESS-DESIGN**，状态 **NOT_AUTHORIZED**。
先补齐真实适配与目标选择设计，不直接执行单对；不重排项目主线或扩展Mock功能。

- 范围：选定A/B及资源责任，列真实root adapter/全表导出与动态列映射、独立监督/持久证据设计，
  冻结单对外层预算和R1 CPU/RSS配额，列函数/文件白名单及验证计划；默认仍仅设计。
- 准入：ChatGPT审阅本文；负责人单独批准该设计任务与读取范围，资源所有者提供非秘密的隔离基线资料。
- 验收：十二门禁缺口各有可验证解除路径；原180/180/30不变；真实adapter/持久信任边界可审，
  未证明风险有明确裁决，数据/映射/停止规则固定。实现、资源准备和真实单对执行仍各需明确许可。
- 回滚：设计文档拒收可撤回独立新增内容，无用户数据变更。不能以“设计通过”自动部署或运行。
- 谁批准：负责人批准范围/资源/预算，ChatGPT独立技术审阅；最终实际执行另立
  P0-LNX-W04-SINGLE-PAIR-APPROVAL或负责人指定编号，不由本文启动。

### Owner decision questions（只供独立审阅后决策，非本轮索取凭据）

1. 是否选择B专用隔离Linux为首选，或改选A；由谁负责机器、资源基线及独占窗口？
2. 是否具备可证明物理隔离的非生产PG17与合成数据准备条件；是否沿用原2股/420日/原请求范围？
3. 是否固定04-D的3.12.14/67包；若另选环境，是否先批准独立兼容与安装核验？
4. FIRST_SPAWN/监督者I/O/D状态/持久可信回执由何种外部控制与责任处置；哪些剩余风险可明确接受？
5. 是否先批准上述最小readiness设计任务；代码、资源准备及真实单对仍分别审阅批准？

## 10. 本轮验证与零操作记录

实际仅执行Git只读查询、文本读取/检索、GitHub GET元数据/既有Job日志/既有Artifact下载、
Python标准库隔离模式下JSON/XML/AST/hash解析（没有导入项目模块），以及创建本文和文档检查。
临时证据只在项目外：Run摘要、既有safe-ci ZIP、既有04-D ZIP；没有提交原始日志或私有内容。
本轮无安装、pytest、数据库连接、PG/容器/服务启动、业务CLI、Worker、真实root/OFF/ON、
容量、部署、GitHub配置变更、dispatch/rerun/cancel、git add/commit/push。

验证：git diff --check；对未跟踪报告单独逐行检查尾随空白、九个固定章节、
G01～G12唯一状态、AC-01～AC-16完整性、本地相对链接和文件范围；不能将空tracked diff作为报告受检证明。
开始及交付三方SHA相同；tracked diff为空，唯一untracked为本文。报告原始字节SHA256在聊天交付中给出，
不在本文嵌入自身hash造成循环。没有新CI Run。

本轮计数：pg_connections=0；workers=0；real_roots=0；off_on_pairs=0；capacity=0；
deploys=0；workflow_dispatches=0。历史CI内部操作不计为本轮动作，也不转换成新实验资格。

最终技术建议：**W03_PREFLIGHT_NO_GO**。交付后等待ChatGPT独立审阅及负责人下一步明确批准。
