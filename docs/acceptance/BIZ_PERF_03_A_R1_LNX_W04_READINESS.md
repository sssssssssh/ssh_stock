# P0-LNX-W04-READINESS-01：真实 Linux Root 准备与准入缺口设计

## 1. BASELINE_AND_SCOPE

2026-11-09，Asia/Shanghai；V1.0；执行者Codex，独立审阅者ChatGPT，批准者项目负责人。
本轮用户批准W00～W04只读审计与本文设计，授权优先于附件内的历史叙述；附件不是运行令牌。
状态：**W04_DESIGN_READY_FOR_REVIEW / EXPERIMENT_NO_GO / DESIGN_ONLY**。
G01=NOT_AUTHORIZED；R1=PARTIAL；历史AC05=PARTIAL；REAL_OFF_ON=NOT_RUN。
下文所有候选函数、工件schema、配额及组件均是待审设计，不表示已实现或已批准运行。

开始HEAD、origin/master、实时远端master均为
`b6ffb7bf8ec7d26f771d9b89923e4f7e926edbed`，简称S。没有切分支或拉取改写。
tracked无变更；唯一既有untracked是[W03报告](BIZ_PERF_03_A_R1_LNX_W03_PREFLIGHT.md)，
本轮完整读取，原字节SHA256核实为
`21e9f0acc048d1724be985b13667a2cd71572992096abea9d8fbd57699455c9d`，保持untracked/preserved。
只新增本文，不暂存、不改W03及其他文件。本机绝对地址、凭据、业务数据不进入报告。

按AGENTS完整读取五份治理文件，再按PRD→系统设计→PROJECT_RULES→README相关业务边界审阅。
治理仍保留2026-11-06 G0、CI-OPT等旧执行指针；当前S包含W01/W02代码，W03仅本地。
这是状态时效差异，按本轮用户明确授权只做W04设计，不修改治理或从旧指针恢复运行许可。
W01/W02独立验收为任务书提供的接受事实；源码和历史工程CI证明范围仍限Mock/工程，
不签发真实Worker资格。04-E CLOSED、04-F NOT_STARTED、容量PENDING、生产读取NOT_AUTHORIZED。
Windows OFF 0xC0000005根因UNKNOWN、三对额外开销≤3% NOT_VERIFIED继续保留。

## 2. SOURCE_EVIDENCE_INDEX

索引的source身份均为S；line指当前Git源码一基行号，精确符号及范围/文件blob摘要见附录A。
confidence=STATIC表示源码事实，不表示实机验收；HISTORICAL表示归档/既有运行；LOCAL_BYTES表示本地文件字节。
源码路径均仓库相对；本轮只读文本/AST，未导入应用、ORM或运行所述入口。

| ID | source_path / symbol | observed_behavior / evidence_sha_or_line | boundary / confidence |
| --- | --- | --- | --- |
| E01 | AGENTS.md；五份治理文件 | 读取顺序、master、安全与授权边界 | 历史阶段不重新授权；STATIC |
| E02 | docs/股票机会发现系统_PRD_V1.0.md；系统设计；PROJECT_RULES.md；README.md | PIT、版本、缺失非零、append-only、默认OFF | 不改金融及生产口径；STATIC |
| E03 | W03本地报告 | §1～10，hash见§1 | NO_GO；LOCAL_BYTES，不是GitHub已审阅文档 |
| E04 | BIZ_PERF_03_A_R1_plan.md / §5 | 2股420日、原180/180/30、45min三对、≤3% | 原冻结合同；STATIC |
| E05 | BIZ_PERF_03_A_R1_closeout.md / §3/4/6 | Windows OFF原生失败、ON成功但配对不可用 | 原失败保留；HISTORICAL |
| E06 | BIZ_PERF_03_A_R1_LNX_W01.md；perf03_lnx_offline_supervisor.supervise | 原固定Mock、进程内票据、同步I/O缺口 | 不复用真实CLI/ticket；STATIC |
| E07 | BIZ_PERF_03_A_R1_LNX_W02.md；hard_watchdog.run/_drive/_cleanup | 固定actor、持有leader/组核验、原期限内协作退出 | FIRST_SPAWN等NOT_PROVEN；STATIC |
| E08 | tests/integration_offline/test_perf03_lnx_hard_watchdog_linux.py | 18参数节点、FIFO实际阻塞、TERM三个时点 | 固定Mock；STATIC；历史18/18来自W03 |
| E09 | BIZ_PERF_04_D.md；安装目录receipt/runtime/dependency/tests与artifact-index.json | Run42156106471/Job127690531459/Artifact13474492280，target ab5e29df5aa230076069dd587557720c2db382dc | 历史3.12.14/x86_64/glibc2.39/67包安装VERIFIED；HISTORICAL |
| E10 | BIZ_PERF_04_E.md；bundle/validation | 固定12证据与canonical digest cf79a5312aae5aecf174caf3435e0e4e6a93ee934f8cc971e46c952f64bb4502 | 完整性不等于真实性能；HISTORICAL |
| E11 | scripts/performance_diagnostics_overhead.py / root_arm | 验库、seed420、create→claim→execute，局部前缀/最终replace | 定位入口；模块顶层有业务导入，不是合格安全启动器；STATIC |
| E12 | tests/integration/test_perf03_root_diagnostics.py / test_real_root_parity_and_local_reports | 同进程两臂，排除一组id/time列；成功/取消/错误 | 无完整身份比较、外部监督；STATIC |
| E13 | scripts/business_recalc_measure.py / main | 验PG后导入业务，900日/4股月窗、采样、终态计数 | 不直接调用作R1；STATIC |
| E14 | scripts/biz_perf_03_b_once.py / authorize,check_environment,Lab | Actions-only、SHA/run/attempt绑定、固定命令、资源先登记后创建 | 旧许可不可移用；STATIC |
| E15 | biz_perf_03_b_actions_once_protocol.json；biz-perf-03-b-once.yml | 全五开关false、单根、180/180/60/420等 | ON与R1参数被拒绝；STATIC |
| E16 | .github/workflows/ci.yml / test.full_tests,authorize,capacity | 普通工程与显式实验门禁分离 | 无新增R1执行授权；STATIC |
| E17 | scripts/v14_test_database.py / verified_test_url,isolated_v14_database | loopback测试URL、major17/marker/system ID；建库前/删库前验证 | 当前helper非每次写操作都重核、无持久ownership票据；STATIC |
| E18 | tests/integration/test_business_recalc_performance.py / seed | 原两股、420日、weekday、退市边界、sector101及质量输入 | 不移植03-B的constant-price-frozen-audit-v2；STATIC |
| E19 | backend/app/services/recalculation.py / create_recalculation_job,run_recalculation | 根入队与TradeStatus→Factor→Market→Sector→Theme→Trend→Opportunity→Quality | evaluate_signals=false不执行SignalEval；STATIC |
| E20 | backend/app/services/job_worker.py / claim_next_job,execute_claimed_job | 取得随机execution_token、所有权校验、心跳、候选workspace、finally收尾 | 不是启动run_worker常驻循环；STATIC |
| E21 | backend/app/services/job_guard.py / data_queue_identity,request_fingerprint,create_queued_ingestion_job | 版本/config快照、活动去重、串行锁、入队 | 不改锁序/幂等；STATIC |
| E22 | backend/app/services/job_execution.py / Execution,checkpoint；job_worker._hold_unconfirmed_execution | owner/token检查；未知ACK保留RUNNING/不释放Writer | 外部不得标成功或补写终态；STATIC |
| E23 | backend/app/repositories/job_run.py / _update_owned_data_job | terminal CAS事务内finish_publication、commit后terminal | 退出0不证明业务完成；STATIC |
| E24 | backend/app/services/data_publication.py / MODELS,KEYS,PublicationWorkspace,finish_publication | 10发布表、候选/原像/source/scope、预算与原子发布 | 固定500批/原发布预算不改；STATIC |
| E25 | backend/app/models/market_data.py | 28个本路径输入/输出/边界表定义 | 列表与逐列策略见附录B；STATIC |
| E26 | backend/app/models/job.py；data_publication.py；data_schedule.py | 归属、ledger、候选、原像、调度边界表 | 无本路径独立generation实体；STATIC |
| E27 | calculation_policy.py / ExecutionPolicy.freeze,snapshot,QueryObserver,DriverFetchObserver | 三优化flags/source冻结；计数/秒数分列 | PERF开关与旧worker_diagnostics区分；STATIC |
| E28 | performance_diagnostics.py / observe_worker,bind_task,Trace.flush；performance_sql_diagnostics.SQLObserver | decorator finally内拆监听和flush | ON失败不能仅凭root SUCCESS接受；STATIC |
| E29 | calculation_progress.py；worker_observation.py；execution_diagnostics.py | Job JSON包含进度/心跳/会话与耗时；观测非进程退出证明 | 原件保留，不能全JSON排除；STATIC |
| E30 | calc_metadata.calculation_metadata；trend/service.py；opportunity/service.py；quality/daily_quality.py | 计算时间/来源、JSON理由和质量写入 | 业务JSON严格比较；STATIC |
| E31 | migrations/versions/20261018_0058_data_publication.py | revision0058_data_publication/down0057_data_queue；表约束 | 迁移文件不是实库current；STATIC |
| E32 | W03§2 GitHub证据索引 | S主Run42490454748/Job128761453533/Artifact13623516968：6331、90.02%、18/18；另三Run见W03 | 只引用前轮已核证据，本轮不复跑/不新取运行；HISTORICAL |

### 2.1 可以复用与必须新建

真实业务链：create_recalculation_job→create_queued_ingestion_job→claim_next_job（必须恰好命中刚建root）
→装饰后的execute_claimed_job（owner+token）→PublicationWorkspace.open→run_recalculation
→update_job/_update_owned_data_job→finish_publication→同事务terminal CAS/commit
→Worker finally→observe_worker finally关闭SQLObserver/flush→函数返回。
根manual、evaluate_signals=false，dirty_ranges=[]；不走Provider拉取、不启动Scheduler/API/常驻Worker。

| 对象 | 可复用粒度 | 必须新建/禁止替代 |
| --- | --- | --- |
| 原业务Service/Repository/identity/事务 | 直接调用原接口与版本/日期规则 | 禁止另建计算/SQL/选股实现；claim未命中本root即停 |
| verified_test_url | 已审逻辑作为核验原语；只在受控非生产配置下调用 | 需封装新OwnershipRecord和写前/销毁前重核，不把URL后缀当隔离证明 |
| 原seed | 固定算法与参数作为唯一fixture内容来源 | 不改退市证券/预热/值；生成时间默认值的输入冻结裁决见§7.4 |
| 03-B controller（实际类Lab） | 注册意图先于副作用、label归属、物理ID、最小环境、预算和脱敏原则 | 新R1清单/双臂状态机/消息/导出器/监督器；不调用旧execute/Lab.child_command |
| 03-B measurement | create/claim/execute位置、SQL终态freeze边界可参考 | 不调用main：它自设优化flags、4股/900日、不同seed、含额外观测/可选profile，旧digest删时间且只替根UUID |
| W01/W02 | 固定命令、期限不续期、sticky首错、pid复用拒绝的设计原则 | CLI/schema/ticket/短Mock期限保持原样；不得换actor路径或加real参数 |
| root_arm | 作为业务入口阅读参照 | 新受限安全启动器须验清单/源码/PG再导入业务；原root_arm缺完整导出/CPU/RSS/外部票据，不包装成已合格adapter |
| SQL/Fetch既有observer | 保留业务消费与嵌套口径 | 新对称外部计数/导出边界单独设计测试；不打开profiler/EXPLAIN替代root，也不更改生产observer |

## 3. ENVIRONMENT_SPEC + PG17_ISOLATION_SPEC

### 3.1 ENVIRONMENT_SPEC

候选B专用隔离Linux VM/ECS优先，资源尚不存在或未核实。本表所有observed均为NOT_ASSESSED；
expected是准入设计，不是事实。实际值、金额、账号、连接信息不预填。

| 属性 | expected | verification_method（下轮获批后） | evidence_artifact | observed | blocking_if_absent |
| --- | --- | --- | --- | --- | --- |
| owner/lease/独占窗 | 非生产专用资源、签认owner、租约期限、两臂独占 | 资源所有者出具脱敏租约/实例绑定/无其他负载声明 | host-lease | NOT_ASSESSED | yes |
| OS/内核/镜像 | 固定发行版、内核release/build、镜像digest | 受控只读系统证据与供应方身份交叉核查 | os-identity | NOT_ASSESSED | yes |
| 架构/glibc | x86_64、64bit、glibc>=2.28 | 解释器运行平台与系统包/loader核验 | runtime-identity | NOT_ASSESSED | yes |
| CPU | model/逻辑核/频率策略/配额/steal计数记录，同机同配额 | owner核查CPU与cgroup cpu.max/cpuset，不猜规格 | resource-baseline | NOT_ASSESSED | yes |
| 内存 | host可用、worker/PG分离上限、禁止资源竞争；数值待裁决 | cgroup memory.max/events、进程RSS计量方法核查 | memory-contract | NOT_ASSESSED | yes |
| 磁盘/IO | 独立PGDATA/日志盘；容量、介质、IOPS/带宽上限和余量明确 | 卷归属、挂载/配额/空间只读证据 | storage-identity | NOT_ASSESSED | yes |
| cgroup v2 | 候选必需：独立pair/arm域，owner可核内外域，pids/cpu/memory/io限制 | 控制器存在性/委派/权限/事件与域对象核验 | containment-proof | NOT_ASSESSED | yes（替代方案须另审） |
| 线程/进程 | pids.max、BLAS/native线程固定、原心跳线程可计 | 冻结环境白名单及实际线程库配置 | process-limits | NOT_ASSESSED | yes |
| 时钟/时区 | UTC事件戳、业务Asia/Shanghai；monotonic_ns不倒退，宿主时钟配置固定 | 独立时钟基线与异常处理合同 | clock-identity | NOT_ASSESSED | yes |
| Python | 精确CPython3.12.14，禁user site，解释器二进制hash | 干净venv/二进制身份与运行时核对 | python-identity | NOT_ASSESSED | yes |
| 依赖 | 原67包hash锁、wheel/ABI/安装集合/pip check、工具链另列 | 复用04-D严格安装校验规范，真实新机另验 | dependency-receipt | NOT_ASSESSED | yes |
| 源码/配置 | 完整SHA、tree/config hash与实际LF字节一致；无业务未跟踪脚本 | Git对象/工作字节核验，所有输入文件白名单 | source-binding | NOT_ASSESSED | yes |
| 网络 | 非生产；优先同机loopback/隔离namespace，仅本实验PG可达；无公网拉数/LLM | owner核路由/网络域/出口策略，写前绑定PG | network-proof | NOT_ASSESSED | yes |
| 权限/日志 | 实验独立非root用户、受控FD、目录0700/文件0600、私有日志不导出 | 权限/卷owner/输出大小与脱敏出口核查 | evidence-boundary | NOT_ASSESSED | yes |
| 外部停止 | 独立于adapter和监督者的租约watcher、受限fencing操作者 | 资源对象句柄/权限/响应流程、期限批准 | outer-lease-proof | NOT_ASSESSED | yes |

04-D旧target ab5e29df5aa230076069dd587557720c2db382dc安装VERIFIED、67包、glibc2.39；
锁SHA256 `88549dce3164364430e20970fa10eb2125b60ff05f456d7bef4474876a98dcfc`。
新VM的安装、镜像/ABI与配额NOT_ASSESSED。Main历史3.12.16不能替代3.12.14；换版本需新身份/安装验收。
W03识别7项checkout换行差异，不能改原件或把文本等价冒充原字节相同；新运行须干净LF checkout。

### 3.2 PG17_ISOLATION_SPEC

拟同一专用物理PG17实例上，OFF1/ON1两个独立随机UUID合成库，同一schema/配置/输入快照。
实例/容器/VM均须独立owner批准；不复用云端业务库、生产DSN或旧CI实例。
传入连接能力是由A切片创建并由owner持有的受控FD/本机配置引用，非manifest中的自由URL，
禁止.env读取、默认DATABASE_URL回退、外部HTTP/SQL和自由命令。真实连接/密码不记录在文档或证据。

候选OwnershipRecord（未实现）：run_id/arm、host lease ID、namespace/cgroup/PGDATA卷对象、
PG17 image digest、随机marker、离线control system_identifier、在线control值、随机db名、
db创建意图/创建确认/owner角色、创建ACK状态、物理身份核验时间、清理授权及二次确认hash。
公开报告只存安全绑定摘要；原身份由可信owner私有保管，不能只信actor传回的hash。

状态：REGISTER_INTENT→VERIFY_INSTANCE→CREATE_REQUESTED→CREATE_CONFIRMED→MIGRATED→
SEEDED_SNAPSHOT_BOUND→ARM_EXCLUSIVE→EXPORT_FROZEN→CLEANUP_REQUESTED→CLEANUP_CONFIRMED。
任何UNKNOWN_ACK/身份漂移进入OWNERSHIP_UNCONFIRMED，不重放CREATE/DROP，不自动进入下一臂。
建库、迁移、seed、写入阶段、销毁前均核major17+marker+独立control/在线system ID和owner；
运行中保持已绑定连接和实例租约，连接重建/物理身份变化时STOP，不能把helper初次检查当全程证明。
销毁只允许已确认本run创建的精确资源对象和库；无模糊名称、全局清理或业务数据回滚。

SnapshotSpec绑定：schema revision（仓库0058_data_publication只是期望，不是实库current）、
完整ORM/DDL fingerprint、seed源码/参数、每表计数/有序自然键/列型/nullability/FK、
输入原始字节及canonical digest、序列状态、配置/依赖/SHA、创建/导出/清理确认。
目前所有实机/库/快照工件均NOT_CREATED/NOT_VERIFIED，不运行A的准备步骤。

### 3.3 HOSTED_VS_DEDICATED_COMPARISON

| 维度 | A hosted runner | B专用VM/ECS（候选首选） |
| --- | --- | --- |
| 工程先例 | W02 Linux18节点、04-D安装已发生 | 当前无已验目标 |
| 重复性/资源 | label/Python会浮动，主机噪声和额度UNKNOWN；需新R1入口 | 可冻结同机租约/镜像/独占窗；宿主超售/IO干扰仍须测证 |
| 权限/凭据 | 旧03-B需Actions/Env且禁止ON，不可直接复用 | 专用非root、无生产凭据、受限运维代理；实际权限待核 |
| 回收/归档 | 临时runner及Artifact到期，不等于持久可信 | 可设计独立lease/fencing与归档；仍不能保证D状态可立即回收 |
| 用户负担/成本 | runner分钟与保留额度；当前价格/余额UNKNOWN | VM/卷/保留时长/运维费用；当前价格/预算UNKNOWN |
| 可用性结论 | NOT_ASSESSED，非GO | NOT_ASSESSED；仅方案上更适合同机两臂及外部控制 |

## 4. ROOT_ADAPTER_BOUNDARY + SINGLE_PAIR_SEQUENCE

### 4.1 COMPONENT_INTERFACE_MAP

设计分owner审批/监督者/adapter三方；下列签名都是候选，不是现有Python API。
清单与消息新namespace为`r1.single-pair.*.proposal.v1`，不被旧Gate消费，不生成令牌文件。

| 组件/API | 类型输入与输出 | 责任及拒绝条件 |
| --- | --- | --- |
| owner.reserve(manifest_hash,S,host_lease,arms) | 一次性清单→持久reservation | 独立确认签名/审批记录、租约/数据库范围；只准OFF1/ON1各1次；未知保存ACK即不能再reserve |
| validate_manifest(manifest,approval_ref) | 严格对象、extra=forbid→ValidatedManifest | 只允许固定schema/SHA/协议hash/run_id/arm与外部资源引用；拒自由URL、路径、SQL、PID、命令、预算超批准值 |
| verify_source(validated,source_fd) | 原始Git对象/白名单文件hash→SourceProof | 在任何业务导入前核SHA/tree/原字节/配置/解释器；不设置任意PYTHONPATH/import模块 |
| verify_pg_physical_identity(validated,owned_capability) | 隔离配置能力→PhysicalProof | 沿原verified_test_url语义并绑定外部owner/租约；不读取业务配置选库 |
| prepare_owned_synthetic_db(proof,fixture_recipe) | 已验证PG/固定fixture→OwnedDbProof+InputSnapshot | 先登记后创建、正式迁移、原seed内容、精确快照；生成/装载只在A/D另批动作中允许 |
| run_exactly_one_root(db_proof,arm) | 独立新进程、固定日期/manual→RootObservedClaim | create→claim必须同root；调用原execute一次；禁止常驻run_worker、Provider、自动调参或二次root |
| capture_evidence(root_claim,snapshot_policy) | 根返回后独立只读导出→DraftEvidence | 完整业务public表+候选/原像/ledger/Job；计数已冻结；导出失败不复跑root |
| finalize_owned_cleanup(resource_record) | 外部已知句柄/PG对象→CleanupClaim | actor只自报；外部监督者与资源owner分别确认后才能产生有效证据 |
| supervisor.attest(draft,os_proof,resource_proof) | hash/外部OS归属/lease→未授权审阅包 | 原件只追加；不消费Mock ticket，不用文件自报hash签发成功 |
| independent_compare(off,on,schema) | 两原件+列级合同→差异或PAIRED_DIAGNOSTIC_SAMPLE | typed比较/身份闭包/首错/可信确认同时核验；不能输出R1_PASS |

清单的固定调用命令由新监督者内部构造，固定已审核解释器和adapter文件，不让请求指定任意路径。
adapter是独立真实实现（拟scripts/r1_single_pair_adapter.py），监督者拟r1_single_pair_supervisor.py；
不更名包装W02 Mock代码，不继承其CLI或票据。A的资源权限与B的业务进程权限分开，
建库权限通过受限broker，业务连接仅本次库，不能持有整台生产数据库管理员能力。
进程环境从空白白名单构造，禁dotenv/user site/生产Token；必要的源码路径内部固定且hash绑定。

### 4.2 SINGLE_PAIR_SEQUENCE

DESIGN_ONLY：PREFLIGHT→owner单次批准→OFF1新进程/新库→完整终态与导出冻结→OS退出/资源清理确认
→ON1新进程/等价新库→完整终态与导出冻结→OS退出/资源清理确认→独立全等比较
→seal draft evidence→独立审阅。任何OFF异常使ON1=NOT_STARTED，不能“只看ON结果”。
每臂仅一次root，无补样/重试/自动六臂。OFF/ON固定同一最终SHA、schema、依赖、PG版本/配置、
输入/PIT/资源/线程/逻辑冷启动策略；只切PERF_DIAGNOSTICS_ENABLED。其他优化开关false、
worker_diagnostics_enabled保持原配置且两臂一致，不把不同诊断系统当同一开关。

语义终态：仅`PAIRED_DIAGNOSTIC_SAMPLE / NOT_PERFORMANCE_ACCEPTED`，不以单对≤3%认证R1。
正式三对另批，原顺序OFF1→ON1→OFF2→ON2→OFF3→ON3，
`(median ON / median OFF - 1) ×100% ≤3%`不变，P95=null。历史5.65%根/22.53%CPU不预测Linux。

## 5. SUPERVISION_AND_STOP_MATRIX

### 5.1 FAIL_CLOSED_STATE_MACHINE

PRE_REGISTERED→SOURCE_BOUND→RESOURCE_BOUND→SPAWN_INTENDED→SPAWN_OWNED→SETUP→ROOT_RUNNING
→ROOT_RETURNED→SNAPSHOT_FROZEN→ADAPTER_EXITED→REAPED→RESOURCE_CLEANED→EXTERNAL_ATTESTED。
最后状态只允许进入下一臂/审阅，不是性能通过。first_failure只写首次；cleanup_errors追加不覆盖。
失败状态：REFUSED、SETUP_FAILED、ROOT_FAILED、TIMED_OUT、ACK_UNKNOWN、EVIDENCE_UNAVAILABLE、
OWNERSHIP_UNCONFIRMED、CLEANUP_UNCERTAIN、FENCING_PENDING；全部禁止下一臂与重试。
`OWNER_PROVEN`与`CLEANUP_CONFIRMED`只来自独立OS/资源证据；actor消息字段名称不能授予这些状态。

| 场景 | 监督/OS设计 | 状态、停止与证据 |
| --- | --- | --- |
| FIRST_SPAWN前/创建中阻塞 | owner先登记租约与cgroup域；外部launcher在exec前纳入已验证域，避免启动后才登记的窗口 | 无句柄不推断没创建；OWNERSHIP_UNCONFIRMED，外部lease接管，不再启动另一臂 |
| leader/后代归属 | 自有Popen/可能的pidfd绑定PID生命周期；核PID/PGID/SID/start身份及cgroup对象；WNOWAIT保留leader至信号阶段完成 | pidfd只保护单进程，不证明组消失；cgroup委派能力待实机验收，不能接受外部PID/全机扫描 |
| 协作退出 | 停止请求只是意图，持续观察原绝对deadline内实际退出、读尽有界消息 | 不在正常收尾窗口重复TERM，不重置deadline；DONE/exit0仍要业务与OS核验 |
| deadline/资源超限 | 只向已验证本臂域发TERM→在固定子截止后KILL→final wait；信号前重核句柄/组，reap后不向可能复用PID发信号 | TIMED_OUT/RESOURCE_LIMIT首错保留；信号成功不等于回收成功，缺wait/组域退出即UNCERTAIN |
| 监督者自身syscall/宕机 | 外部lease watcher在独立控制进程/资源域，固定lease到期通知/受限fence | WATCHDOG_SYSCALLS/机器宕机NOT_PROVEN；无外部ACK禁止宣称清理成功 |
| D状态/不可回收 | 禁止升级为任意kill-all；按精确VM/卷对象交已批准操作者fencing | CLEANUP_UNCERTAIN/FENCING_PENDING，冻结后续运行；发起VM停止不等于完成，须供应方/OS后验确认 |
| ACK未知/DB断开 | 保存原error/SQLSTATE安全码及原RUNNING/PREPARING事实；只读核验能力也须独立授权 | ACK_UNKNOWN；不重放事务、不标FAILED掩盖未知、不释放业务Writer、不靠删除实验库“证明回滚” |
| final写入/fsync/归档失败 | 预注册前缀+只追加事件+独立原件hash；没有外部确认的final永不消费 | EVIDENCE_UNAVAILABLE；不从候选文件恢复签发、覆盖或重试root |
| 心跳线程未确认结束 | 原join(timeout=5)在root调用内；父进程最终退出、域清空由监督者确认 | join返回不是线程已结束；没有进程退出证明则CLEANUP_UNCERTAIN |

### 5.2 RESIDUAL_RISK_REGISTER / 持久可信

FIRST_SPAWN、WATCHDOG_SYSCALLS、UNINTERRUPTIBLE_D_STATE、DURABLE_TRUST持续NOT_PROVEN。
候选外部owner以独立权限持有预注册清单/资源ledger；原件hash+run/arm/SHA/租约/单次消费状态
在受控只追加账本绑定，签认主体与adapter分离。签名/受控确认机制由负责人选定并独立审阅，
不自行引入密钥服务或把可重算hash当签名。注册/消费ACK丢失一律UNKNOWN、不补签；
重启后需独立审阅原证据，不能从本地final自动恢复成功。账本/存储本身失败仍NO-GO。

pidfd/cgroup v2/租约/fencing是待实现的分层措施，不是100%硬抢占保证。
VM外部控制路径也可能超时，不假定不可回收D状态必然在某个秒数内结束；
负责人须接受明确剩余风险、停止后不继续试验、资源隔离不触及生产，并指定升级操作者和证据责任。

## 6. BUDGET_INVENTORY

| 独立合同 | 冻结数值/来源 | 本设计采用及限制 |
| --- | --- | --- |
| R1_plan§5定位 | 每臂setup180s/root180s/cleanup30s，root30s起每30s最多5次受限栈 | 保持；不能增加业务超时或将未返回当成功 |
| R1_plan§5三对 | 六臂总45min=2700s，每臂同上，失败即停不补样 | 保留，不将2700当单对许可 |
| 03-B协议/phase_deadline | init180/root180，root=min(start+180,T0+330)，cleanup60且不晚T0+390，archive30/总420 | 仅03-B；根poll在deadline-3提前拒绝是实现reserve，非R1预算 |
| W02固定Mock | root100～1000ms，TERM/KILL各0.2s，actor child清理0.1s | 不迁移到真实root |
| 业务内部 | 原SQL/发布预算及Worker join5s等保持源码值 | 外层180s可先触发；不能把发布300s上限当延长root的理由 |

有向预算图（候选设计，数值未定项显式阻断，不是可运行配置）：

```text
外部owner lease起点 L0 ─────────────────────────────────────> T_LEASE（待裁决）
  └─supervisor预注册/资源绑定─> arm t0（首次spawn之前）
      ├─spawn + verify + create/migrate + seed/input核验 [setup <=180s]
      └─root t1: create/claim已完，立即调用装饰后的execute_claimed_job
           └─业务计算→terminal CAS/commit→Worker finally→decorator flush/cleanup→返回 t2
              [root wall=t2-t1 <=180s；内部阶段重叠不相加]
                └─导出/归档 [T_EXPORT待裁决]→已归属资源清理[<=30s]→独立confirm
异常任何点 ─> 原deadline/固定TERM子截止→KILL→final wait→未证实则外部fence
两臂外层上限 T_PAIR、TERM/KILL/final-wait分配、T_EXPORT、T_LEASE/fence升级期限均待批准
```

root计时从调用装饰后execute前到返回后，包含其诊断setup/flush和原finally；create/claim另记setup。
外层wall、setup、root wall、export/archive、cleanup分别原始记录；CPU/RSS明确root进程与PG分列。
03-B overall包含create/claim及后验查询，不能替代R1 root wall；原root_arm wall接近R1范围，
但它无完整监督/等价证明。fixture准备/seed绝不能暗中并入root，或删掉root内部flush来降低分母。

**DECISION_REQUIRED**：原R1没给独立export/archive、两臂总上限、TERM/KILL分配及VM外部期限。
建议在不扩大180/180/30下定义控制/收尾子预算，外层pair/lease显式封顶；本轮不自填新秒数。
导出在清库前、root返回后，是否纳入原cleanup30或另列受限export需负责人批准合同修订；
未裁决时B只能设计离线接口，不能实现带猜测预算的真实执行入口。

## 7. BUSINESS_COMPARISON_MATRIX + IDENTITY_GRAPH

### 7.1 覆盖集合、类型与列级策略

以实际publication.MODELS的10表为发布输出全集，另核输入、Job、5种publication存储、dirty、
schedule/provider/service边界表及alembic_version。每个ORM列的名称、声明、可空、来源行和唯一策略
在附录B逐列展开；没有“全部ID忽略”或按列后缀自动排除。附录规则集是未来校验器合同，不是当前实现。
不存在于清单的新增表/列或schema fingerprint变化立即SCHEMA_DRIFT，不静默跳过。

| policy | 机械比较/验证 |
| --- | --- |
| X | 严格值和类型比较：字符串UTF-8不改写；int不接受bool/float；bool严格；日期YYYY-MM-DD精确；float按数据库返回binary64规范hex，null/NaN/+Inf/-Inf分开，未批准非有限数即拒绝；不容差 |
| J | typed JSON递归严格：object键排序、数组顺序保持、null/空串/0/false不混同；SQL NULL与JSON null分开；含嵌套原表行须按其schema比较，不把JSON数值全转float |
| U | 受限UUID双射，实体kind+自然键定位；同一UUID所有出现处统一映射，原件保留，不能多对一或跨kind；外部/预存UUID若不属本run则严格相等 |
| T | 仅明确列允许的生成事件时间映射：逐行自然键+列+事件类型绑定OFF/ON时间；UTC/精度/null性、复制关系、先后约束独立验证，原戳全部保留；业务/PIT日期永不映射 |
| N | 原始SERIAL/固定sector ID严格int相等并检查序列状态与自然键关系；本设计不授权SERIAL重编号，使顺序/分配缺陷可见 |
| R | 字段/JSON中的引用按U/N和对应实体表的自然键闭包递归核验；非FK声明的业务引用也核，悬挂/错owner失败 |
| M | Job元数据专用逐路径策略见§7.3；不得把整个JSON替为hash或排除 |
| E | 操作遥测逐字段校验/保留原值，身份/状态/计数按语义核对，耗时/PG PID等不要求双臂数值相等；仅用于明确遥测路径，不能用于金融值/原因码 |
| Z | 当前固定R1路径预期空/不变的表，仍按全部列导出并X/J验证；出现非预期写入立即OUT_OF_SCOPE_WRITE，不扩大试验 |

ORM该路径无Numeric/Decimal金额列，但规范保留Decimal为精确十进制字符串+scale，禁止退float；
未来新增Numeric列需schema修订，不能套用float规则。dtype在DB列层及计算DataFrame层分开：
先核ORM/DDL型、可空和实际导出tag；计算帧dtype要靠B获批的只读导出边界，不修改算法/Result消费。

输入/输出范围与排序：

| table / 来源 | 自然键=sort key（映射后）；scope | 特殊规则 |
| --- | --- | --- |
| stock_basic；market_data.py:27 | ts_code；输入/前后不变 | list_date/delist_date与退市状态X；updated_at只允许seed事件T |
| trade_calendar；:45 | cal_date；输入 | is_open/pretrade_date/exchange严格；不换真实日历 |
| stock_daily/stock_adj_factor/stock_daily_basic/index_daily；:54/77/89/114 | trade_date,ts_code；输入 | 所有行情字段X；stock_daily.source_updated_at绑定seed输入事件，不按0补缺 |
| stock_st_daily/stock_suspend_daily/stock_limit_daily；:133/148/162 | date,code；suspend另含suspend_type；输入/空表证明 | 原有created/updated事件T；其余X |
| sector/sector_member；:276/289 | sector(source,source_code)且sector_id101严格；member(sector_id,ts_code,valid_from)；输入 | member.id严格N；历史valid_to/PIT严格X |
| theme/theme_member_snapshot/theme_member_interval/theme_daily/theme_moneyflow_daily/theme_limit_daily；:525/543/559/579/605/627 | theme_code；snapshot_date,theme_code,ts_code；theme_code,ts_code,valid_from；各daily日期,theme_code | 原seed无题材行，作为输入空/不变证明；PIT成员不以当前集合替换；unexpected行失败 |
| stock_trade_status_daily/stock_factor_daily；:392/179 | trade_date,ts_code；全部public及本root候选 | calc_run_id U/R、calculated_at T；其余全部X/J |
| market_daily；:245 | trade_date；全部输出 | 同上；counts int与金融float不同型 |
| sector_factor_daily/theme_factor_daily；:304/646 | trade_date,sector_id/theme_code；全部输出/可能空 | 行业/题材ID与成员PIT闭包；source_strategy_config_hash严格X |
| stock_state_daily/stock_opportunity_daily；:421/699 | trade_date,ts_code,algo_version；全部输出 | 原状态/原因/排名/策略hash X/J；行业/题材引用不随机映射 |
| strategy_signal；:452 | trade_date,ts_code,signal_type,algo_version；输出 | id严格N；calc_run_id U；payload/reason_codes J，时间T |
| signal_forward_eval；:483 | signal_id,eval_version,entry_basis；边界表 | evaluate_signals=false预期无新行但发布有FK cascade路径，必须空/不变核验；id严格N，signal_id R/N |
| data_quality_daily；:345 | trade_date,dataset；原Raw质量输入+Derived输出分区 | id严格N、job_id U/R、checked_at按seed/运行事件T；issue_codes全部J |
| job_run；job.py:24 | 单root按(job_type,target_date,request_fingerprint,parent/dependency结构)匹配，再映射id；审全部行 | worker_id使用固定实验worker标签严格；execution_token U为本次执行域，metadata M |
| data_publication；data_publication.py:24 | job_id U；ledger | token必须等Job；identity J/X等queue_identity，state及row_counts精确 |
| data_publication_source；:42 | publication_id,source_job_id U；source | role X，validation.days严格有序日期；pending_dirty_ids精确引用 |
| data_publication_row；:59 | publication_id,table_name,row_key；候选/tombstone | row_key按KEYS；row_data/base_row按目标ORM全列重入；source_id闭包，删除/null约束 |
| data_publication_preimage；:87 | publication_id,table_name,row_key；首次原像 | 不重写；原像行按原表全列；旧来源严格身份，不能改成新root |
| data_publication_scope；:100 | publication_id,table_name,source_id,start_date,end_date；scope | id U；tuple重复按多重集保留，附组内ordinal双射；日期/范围严格，不将scope当行值 |
| data_dirty_range；market_data.py:371 | dataset,dirty_start_date,dirty_end_date,id；边界 | manual dirty_ranges=[]预期空/不变；任何写入先失败，不能静默转dirty_repair |
| data_schedule_intent/provider_api_log/service_heartbeat | 分别identity_key；provider/api/date/id；service/instance/id；边界 | 不启动Scheduler/Provider/常驻Worker，预期空/不变；字段策略附录B |
| alembic_version | version_num；元结构 | 精确单head与迁移图一致，当前未连库，无实测current |

其余Research/Portfolio/Agent/Paper等表不属此manual根执行路径，迁移后空基线由schema全表清单
逐表count/hash守卫；根前后任何变化OUT_OF_SCOPE_WRITE。对非空外部业务表一律拒绝目标库，
不能以忽略这些模块方式允许错误库执行。schema全清单来自迁移/ORM静态inventory，下轮A实库核验。

### 7.2 IDENTITY_GRAPH（实际关系，无虚构generation表）

```text
外部run/arm/lease ─> JobRun(root.id) ─[worker_id + execution_token]─> 本次执行归属
                         ├─> JobRun.parent_job_id / depends_on_job_id（本manual方案预期无子/依赖）
                         ├─> DataPublication.job_id/token/identity
                         │     ├─> Source(publication_id,source_job_id) ─> root或真实子Job
                         │     ├─> Row(publication_id,source_id,row_key,row_data/base_row)
                         │     ├─> Scope(publication_id,source_id,日期范围)
                         │     └─> Preimage(publication_id,row_key,row_data) ─> 原来源Job或原NULL
                         ├─> derived.calc_run_id / quality.job_id
                         └─> strategy_signal.id ─> signal_forward_eval.signal_id
```

本链没有独立generation UUID/owner用户表；execution_token对应一次claim执行，calc_run_id引用Job，
不是额外generation表FK。外部manifest可称execution generation但只能绑定现有root+token，
不能创建虚假的ORM实体或把request_fingerprint（稳定请求hash）映射成随机值。
W03的generic generation/owner设计概念在此落实为worker/token与实际Job引用，W03原字节不改。

UUID映射域：JobRun.id（root及若获批的子/依赖）、JobRun.execution_token、DataPublicationScope.id；
所有publication/source/row/metadata复制引用重用同一映射。worker_id固定受控标签不按hostname/PID猜映射。
没有外部历史Job却出现非NULL引用必须失败；真实历史null可保持null，不补造旧Job。
各域双射、kind不混、所有引用可达，父/依赖不能环、自指。Scope的实际ORM未声明自然tuple唯一，record_scope每次可追加；
相同(publication,table,source,start,end)按多重集精确比较次数，组内按原UUID排序编号，
以该ordinal建立UUID双射，不丢重复行。当前源码无scope.id对外FK；若新schema出现引用，
必须扩展闭包并另审，不能沿用任意组内配对。
候选row_key中signal_id等按真实KEYS重构，不能对JSON里所有UUID形状字符串做全局替换。
T时间映射按事件域/行自然键显式对应；每域保留双向表、重复/复制关系和null性。时间分辨率造成
域内一对多不能强行合并；判TIME_MAPPING_AMBIGUOUS而非忽略。交易日、snapshot_date、valid_from/to不映射。

### 7.3 M：Job及嵌套JSON的逐路径合同

规则先匹配已列路径，其余typed递归严格J；任何新动态路径导致差异/未注册时拒绝，绝不自动忽略。
公开日志不能输出自由error_message/SQL，比较器只在私有合成快照内精确比原值，导出固定码与摘要。

| JSON路径 | 类型/策略与闭包 |
| --- | --- |
| job_metadata.queue_identity | 完整dict逐键X：analysis/opportunity/algo/factor/raw_quality/data_quality/provider_limits/market/sector/theme/trend/opportunity_calc；等ledger.identity |
| job_metadata.calc_run_id | null或UUID字符串，映射Job；其余start/end/source/mode/evaluate_signals/版本/config/预热日期/chunk/progress/质量统计/dirty_range_ids严格J/X |
| job_metadata.publication | state/row_counts/parent_owned严格；identity UUID→root U，published_at T并等ledger复制事件 |
| job_metadata.calculation_execution | schema_version/flags/source/request/commit_status及scope标签严格；job_id/root_job_id U；source_diagnostics的源码hash/状态严格；elapsed_seconds及reads/driver_reads/sql/stages中的seconds归E，calls/rows/failures等与对称root计数核验，不宽泛忽略子树 |
| job_metadata.calculation_progress | name/kind/phase/batch_index/count/completed/total严格；started_at/operation_started_at/updated_at/advanced_at T；elapsed/operation_elapsed E；recent_events有序保留且每项结构/状态/计数核对，时间T |
| job_metadata.database_sessions | schema/status/process_exit_proven严格，root_job_id U；execution/owner_fingerprint必须由本臂已知token/worker重新派生验证，不跨臂直接hash相等；roles.first/latest的application_name按space2/role/root/token-fingerprint格式派生核验；其pid、backend_start、database_oid、postmaster_start、observed_at作为E并绑定本PG身份，非清理证明 |
| job_metadata.heartbeat_health | schema/state/phase/sqlstate/证明布尔字段按E独立安全约束核验；observed_at/last_confirmed_at T，execution_fingerprint派生验证；consecutive_failures/unconfirmed_seconds E，缺失不能当0；任何degraded/unconfirmed阻断单对接受 |
| job_metadata.execution_diagnostics | 若固定worker_diagnostics关闭须缺失；启用时schema/root/fingerprint/outcome核验，业务计数按明确role与scope核对、duration E；默认不把它作为新PERF trace替代物 |
| job_metadata.execution_unconfirmed/execution_error_code/policy_change | bool/固定原因及source hash严格J；出现unconfirmed/漂移就是失败，不靠相等放行 |
| data_publication_source.validation | days有序ISO日期X；pending_dirty_ids严格int引用dirty；未知键J并显式审阅，不能跳过 |
| data_publication_row.row_key/row_data/base_row；preimage.row_data | table_name只允许registry；按目标表自然键和附录列策略解码，base NULL与空对象分开；跨层ID/时间复制必须一致 |
| strategy_signal.payload/reason_codes；state/opportunity.reason_codes；quality.issue_codes | 整棵业务JSON严格J；不允许计时豁免，不以“是JSON”忽略任何值或数组顺序 |

注意遥测E不是业务全等：所有原件保留、分别验证，时间/心跳频次不纳入金融字段相等结论。
E若混入未知金融字段、未知session角色或未知结构必须UNMAPPED_JSON_PATH并NO_GO。
完整schema版本在B/C先用源码+固定人工golden定义；未实现/未实际验证，不授予运行许可。

### 7.4 seed/快照与摘要设计；UNMAPPED_COLUMNS

原seed420/weekday、请求2026-02-23～24、manual/evaluate_signals=false、250交易日/430自然日预热均不变。
静态行数：calendar420；basic2；4种股票日输入各600；sector/member各1；index=300×benchmark数；
stock_st/suspend_d原质量输入各300。以上不是实库读数，null/退市边界照原seed，不扩大成4股月窗。

**新发现的输入冻结裁决**：原seed使用服务器默认updated_at/source_updated_at/created_at/checked_at，
独立新库分别seed并不能保证输入原始字节相同。不能把这些时间全删后宣称同一输入。
候选最小方案：另批准备时仅用原seed生成一次基准合成snapshot，随后两新库加载同一带时间戳/ID/
序列状态的快照；不改业务seed公式。是否允许这种准备方式替代原“每臂重新seed”的实现解释，
必须负责人明确批准（DECISION_REQUIRED）；未批准则真实执行NO-GO，不能暗中冻结DB时钟或改原seed。
备选严格原seed每臂执行，保留每臂原始hash并只对附录明确seed时间列做输入T映射，
但不再声称raw-byte-identical；须另批语义等价定义，任何业务source hash差异仍拒绝，不能归一化已存hash。

摘要层次：raw artifact bytes SHA256；schema/type/null/FK fingerprint；source/seed/config/flags/依赖/
PG版本+ordered dataset canonical SHA256；输出业务canonical与操作E证据分别hash后由共同manifest绑定。
包含表名/列名/类型/行数、排序和长度边界，拒重复自然键/重复JSON key/nonfinite非法值。
将真实run root UUID映射只作用于列级副本，原件不改；04-B dataset hash与04-C状态输入hash不复用。

UNMAPPED_COLUMNS：附录B的当前静态ORM列全部分配明确策略，未用兜底IGNORE；未知JSON路径
只有严格J或拒绝，不擅自提升成时间/身份豁免。真实schema/current、运行时导出dtype、
完整JSON黄金集及域内T双射可行性未实测，故G09仍PARTIAL（implementation/physical verification missing）。
若下轮发现任一无法映射列，立即`G09=BLOCKED_BY_UNMAPPED_COLUMNS`并输出table/column/来源/值型，
停止B/C依赖部分、等待审阅；不得自动加忽略名单。本文静态设计不证明真实比较已通过。

### 7.5 COMPARISON_FAILURE_CODES 与失败合同

固定码候选：SCHEMA_DRIFT、UNMAPPED_COLUMN、UNMAPPED_JSON_PATH、DUPLICATE_NATURAL_KEY、
TYPE_MISMATCH、NULL_SEMANTICS_MISMATCH、VALUE_MISMATCH、ORDER_MISMATCH、IDENTITY_NOT_BIJECTIVE、
DANGLING_REFERENCE、WRONG_OWNER_TOKEN、PIT_OR_VERSION_MISMATCH、TIME_MAPPING_AMBIGUOUS、
SERIAL_OR_SEQUENCE_MISMATCH、CANDIDATE_BASE_MISMATCH、OUT_OF_SCOPE_WRITE、ROOT_NOT_PUBLISHED、
ACK_UNKNOWN、CLEANUP_UNCERTAIN、EVIDENCE_NOT_ATTESTED、COUNTER_SCOPE_MISMATCH。
错误仅输出code/table/column/row-key安全摘要，禁止原SQL/参数/自由文本泄漏。

| 独立后续验收场景 | 必须证明（不是本轮运行） |
| --- | --- |
| 正常 | root SUCCESS/PUBLISHED、全public值与候选对应、首原像保留、source/owner闭包、独立读者无候选泄漏 |
| 业务异常/质量失败/缺损 | 原首错/原因/质量证据保留，root FAILED或实际未确认状态；ledger ABORTED或实际未知，不以空结果当成功；旧public不变 |
| 取消 | CANCELLED/ABORTED及原cancel_requested/时间、无部分发布；未知取消ACK不能写成已取消 |
| ACK未知/原生退出/发布失败 | 保留实际RUNNING/PREPARING或已有terminal事实，区分未知与已失败；没有final保留prefix；不重发commit/root或解锁Writer |
| 重复/幂等 | 限离线注入/另批非性能安全验收；同活动fingerprint去重与append-only原像保持；不能靠真实单对补跑验证 |
| 候选删除/cascade | preimage只记首次，signal_forward_eval FK级联的旧行证据不丢；空seed下也要结构负例，不能只比较count |

SQL counters按主业务上下文、心跳、控制/独立核验、销毁分列；root freeze在完整execute返回后，
含finally，独立导出与清库不计根SQL。driver FETCH calls/batches/rows与partition嵌套分列，失败rows=null、
已知前缀另列；execute时间不是纯服务器时间。对称观测OFF/ON，不重放SQL、二次消费Result或把心跳差异归因性能。

## 8. G01_G12_READINESS_TABLE

每行按W03原状态保留；设计不是门禁实证。authorization均为后续NOT_AUTHORIZED；
current_state没有被本轮设计转绿。owner=项目负责人，operator=获批资源操作者，reviewer=ChatGPT独立审阅。

| gate_id | W03_reported_state | verified_evidence | missing_evidence | required_implementation / owning_component | independent_test | proposed_next_task / decision_owner | authorization | current_state |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| G01 | NOT_AUTHORIZED | 用户仅批本文；E01/E03 | 精确SHA/协议/机库/run/单对审批 | owner单次清单/持久消费 | 无批准/错SHA/重放拒绝 | D；owner/reviewer | NOT_AUTHORIZED | NOT_AUTHORIZED |
| G02 | MISSING | E08/E32历史runner | 新机全部§3属性 | ENVIRONMENT_SPEC / lease verifier | 缺属性/错租约拒绝 | A；owner/operator | NOT_AUTHORIZED | MISSING；host NOT_ASSESSED |
| G03 | PARTIAL | E09历史3.12.14安装 | 新机ABI/67包/二进制 | A安装身份核验 | 缺包/多包/错patch/坏hash | A；owner/operator | NOT_AUTHORIZED | PARTIAL |
| G04 | MISSING | E17物理核验源码 | 新实例control/server/owner证据 | owned PG broker / 身份绑定 | 假marker/错system/创建ACK未知拒绝 | A；owner/operator | NOT_AUTHORIZED | MISSING |
| G05 | MISSING | E18固定seed | 实际schema/输入snapshot/序列状态 | A准备recipe+C快照合同 | 值/null/时间/顺序/表缺失负例 | A/C；owner/reviewer | NOT_AUTHORIZED | MISSING |
| G06 | PARTIAL | E19～24真实入口 | 新adapter实现、完整阶段/ACK原语 | B固定root adapter | 错claim/root重复/业务异常拒绝 | B；owner/reviewer | NOT_AUTHORIZED | PARTIAL |
| G07 | NOT_PROVEN | E06/07残余风险 | 外层lease/硬阻塞处置与数值裁决 | B监督+A域/外部fencing设计 | 假spawn/监督阻塞/未知句柄注入及另批OS能力验证 | A/B/D；owner/operator | NOT_AUTHORIZED | NOT_PROVEN |
| G08 | PARTIAL | E04与§4/7设计 | 最终SHA/config/两臂资源输入同一性 | manifest+canonical dataset binding | source/flags/配置/fixture漂移拒绝 | A/B/C；owner/reviewer | NOT_AUTHORIZED | PARTIAL |
| G09 | PARTIAL | E25/26/30逐列与图 | 校验器/golden/真实schema及dtype证明 | C列级比较器 | 每列tamper、错ref/多对一/时间别名/空值负例 | C；owner/reviewer | NOT_AUTHORIZED | PARTIAL；发现未映射即BLOCKED_BY_UNMAPPED_COLUMNS |
| G10 | NOT_PROVEN | E06/07仅Mock回收 | 真实归属/持久独立确认/清理证明 | B证据封存+A资源确认+owner ledger | 回执自签/重算hash/丢ACK/残留域拒绝 | A/B/D；owner/operator/reviewer | NOT_AUTHORIZED | NOT_PROVEN |
| G11 | PARTIAL | E16/E32工程CI | 最终实现同SHA工程验收及R1独立人工批准流程 | D授权包；当前不要求新增Workflow | 旧CI/旧03-B/错run/skip不能放行 | D；owner/reviewer | NOT_AUTHORIZED | PARTIAL |
| G12 | PARTIAL | 原停止规则/§5 | 真实外部停止与收尾实证 | B状态机+A lease/fence | 首错粘性/晚到成功/清理未知停后续臂 | A/B/D；owner/operator | NOT_AUTHORIZED | PARTIAL；实际停止能力NOT_PROVEN |

## 9. MINIMAL_IMPLEMENTATION_SLICES + ALTERNATIVES

以下四个候选编号均NOT_AUTHORIZED，只提出任务而不创建其他任务文件或代码。

| slice | 最小交付/拟议文件与缺失函数 | 依赖与验收 | 回退/停止 |
| --- | --- | --- | --- |
| P0-LNX-W04-A | 非业务资源/依赖身份验证器与受限准备手册；候选r1_lab_identity.py、env/PG schema、离线契约测试；缺validate_environment/verify_owned_pg/register_resource | 本设计独立审阅、owner选机/成本/配额/安装与数据库准备许可；先纯离线负例，再另批新机安装/物理身份验证；不得运行root | 无权限只交付规格；未知ACK保留资源意图，不全局清理；停止使用未核验目标 |
| P0-LNX-W04-B | 新固定adapter+监督器+持久确认接口/故障合同；候选r1_single_pair_adapter.py、r1_single_pair_supervisor.py及对应离线测试；§4候选函数 | 入口/预算/外层风险裁决后才实现；可在A规格冻结后开发离线部分，不连PG；假句柄/协议/期限/首错/清理注入先RED→GREEN；真实OS能力验证另批 | 新入口默认拒绝real，无通用命令口；失败停止不无限追加Mock；只撤独立新增模块，不改业务与旧Mock |
| P0-LNX-W04-C | 标准库typed快照/比较器；候选r1_business_snapshot_contract.py及人工golden/离线负例，不连接业务库；缺validate_schema/canonicalize/compare_identity_closure | 附录列策略/JSON路径/seed时间裁决批准；可独立于A实机/B执行开发离线合同；每列策略穷尽、全FK/非FKref及时间/ID负例，旧文件不改 | 不知列立即拒绝，不加IGNORE；C通过只证明人工合同，真实导出/Golden另需获批准备 |
| P0-LNX-W04-D | 单次readiness裁决/一次性授权申请包与审阅报告，默认无root执行；实际试验须用户另批精确一次 | A资源/安装实证+B工程/OS故障合同+C比较/golden验收完成；最终SHA普通CI、残余风险接受、协议/机库/run范围与操作者签认 | 任一门禁不齐NO-GO；不dispatch/rerun，不把申请包当令牌；真实OFF1→ON1仍须明确运行指令 |

依赖：owner选机/预算/输入与风险裁决→A规格；A规格+预算/接口审阅→B离线；
静态schema+输入/映射审批→C离线（不需真实DB）；A实证+B/C验收→D裁决→独立单次执行授权。
离线开发与实机验证分开审批，不能因A获准安装就触发root；B/C无需重写或增加Mock actor功能。

ALTERNATIVES：可让B/C共用一份严格manifest/schema规范，减少重复字段解析；保留独立外部
owner确认与独立比较职责，不能由adapter自证相等。现03-B最多复用无副作用纯结构/摘要规则的设计，
不调用其Actions-only控制器，不删其授权检查。少于四切片仅能合并文档/发布包，不能合并权限门禁。

授权申请包仅文字示意，不输出正式令牌文件：schema=r1.single-pair.authorization-proposal.v1；
status=NOT_AUTHORIZED；target_sha/protocol_sha256=NOT_SELECTED；owner_approval=NOT_GRANTED；
run_id=NOT_ALLOCATED；host_identity/postgres_physical_identity=NOT_VERIFIED；dataset=NOT_CREATED；
arms=[OFF1,ON1]；root_attempts_per_arm=1；required_gates=G01～G12；
performance_accepted/production_read_authorized/capacity_ready=false。与03-B旧schema不互换。

## 10. DECISIONS_REQUIRED

| 决策 | 需要负责人确认的具体边界 | 未确认后果 |
| --- | --- | --- |
| D01机器/成本 | B专用x86_64 Linux、资源owner/预算/独占窗、运维权限；A作为备选是否另审 | 不创建/登录/安装，G02缺证 |
| D02物理PG与依赖 | 同专用PG17实例两随机库、物理身份/角色/网络；3.12.14与原67包锁 | 不连接/建库/迁移，不借历史安装通过 |
| D03固定数值 | R1原180/180/30不变；补齐export/archive、TERM/KILL/wait、pair/lease/fence外层预算、CPU/RSS/pids/IO配额 | 不实现猜测数值的真实调度器 |
| D04输入时间 | 是否批准一次原seed基准快照供两库加载；或另批seed时间语义映射，精确区分字节与语义相同 | G05/G08阻断，不能自动规范化source hash |
| D05持久信任与风险 | 独立operator确认/只追加账本机制、cgroup/lease/fence权限及D状态责任；明确接受哪些NOT_PROVEN尾部 | G07/G10/G12不放行，不宣称硬保证 |
| D06切片权限 | ChatGPT先独立审阅；A具体准备/安装、B/C离线实现、后续工程提交/CI与D裁决分别批准 | 本轮只报告；不把设计批准升级为Git或实验许可 |

## 11. ACCEPTANCE_CHECKLIST

这里AC05是本任务设计项；历史监督AC-05仍PARTIAL，两者不可混淆。
PASS表示静态设计材料齐全，不表示实机/业务全等/性能门禁通过。

| ID | 状态 | 证据/边界 |
| --- | --- | --- |
| AC01 | PASS | §1 Git三方一致，tracked不变，保留W03 |
| AC02 | PASS | W03原文件存在、完整读取、SHA匹配；交付再核 |
| AC03 | PASS | E01～E18治理/原计划/收尾/W01/W02/04-D/E/03-B及源码索引 |
| AC04 | PASS | §2/6三合同输入、预算、开关和资格分开 |
| AC05 | PASS | §2.1真实root调用链、§4未实现边界明确 |
| AC06 | PASS | §3.1每属性expected/method/artifact/NOT_ASSESSED/blocking齐备 |
| AC07 | PASS | 历史04-D与新机未验证并列，3.12.16不能替换 |
| AC08 | PASS | §3.2物理marker/control/server/owner、UUID及清理前复核 |
| AC09 | PASS | §3/7.4 schema/seed/行数/digest与输入时间裁决；零装载 |
| AC10 | PASS | §4 owner/supervisor/adapter能力分离，无任意命令/外部PID/Mock ticket |
| AC11 | PASS | §5 spawn/协作退出/原deadline/信号/reap/uncertain/fence流程；数值未决不运行 |
| AC12 | PASS | 四NOT_PROVEN与外部责任保留，不承诺D状态硬终止 |
| AC13 | PASS | §4.2 OFF完整/清理后才ON，无重试/补样 |
| AC14 | PASS | §7+附录B实际列/类型/null/策略全覆盖，未知schema/列/JSON拒绝；无忽略ID |
| AC15 | PASS | 实际root/job/token/publication/quality图、双射和引用闭包；无虚构generation |
| AC16 | PASS | §7.5原异常/取消/ACK未知/重复/发布/质量/append-only/PIT要求 |
| AC17 | PASS | §8十二门禁逐项证据/实施/责任/任务/授权，保持NO_GO |
| AC18 | PASS | §9四切片是提案，未创建资源/代码/Workflow或实验 |
| AC19 | PASS | 文档空白/标题/链接/逐列覆盖/白名单、git diff --check及W03 hash核验见交付检查 |
| AC20 | PASS | 零真实执行、无Git交付或Actions；R1与历史AC05保持PARTIAL |

## 12. DELIVERY_REPORT

本轮只读Git/文本/AST/文件hash和标准库静态解析；只新建本文。无需pytest、Ruff、安装或CI；
不把旧6331/18项成功标为W04新执行。没有环境探针、数据库连接、业务导入或业务命令。
附录静态自动展开仅写本文，未生成Python源文件、schema、fixture或回执令牌。
检查新增untracked文档的UTF-8/尾随空白、12章节、门禁/20AC、源码路径、附录列覆盖和秘密/绝对路径；
再核tracked diff为空、W03 hash不变、两份untracked恰为W03+W04。报告自身hash在聊天给出，避免自引用。

run_counts：pg_connections=0；worker_roots=0；off_on_pairs=0；capacity_runs=0；deployments=0；
actions_dispatches=0。commit=NOT_COMMITTED；push=NOT_PUSHED；new_ci_runs=NOT_TRIGGERED。
readiness_decision=W04_DESIGN_READY_FOR_REVIEW；experiment_decision=NO_GO。
待ChatGPT独立审阅和负责人D01～D06裁决后，才分别申请最小切片授权，不自动启动。

## 附录A：当前源码符号与原始Git blob身份

以下清单由标准库AST静态提取，符号范围绑定S；不执行这些模块。

| source_path | 原字节SHA256 | 实际顶层符号范围（含类方法在类范围内） |
| --- | --- | --- |
| [scripts/performance_diagnostics_overhead.py](../../scripts/performance_diagnostics_overhead.py) | 98dbd99f94f2c784ca862bbadce43228350d72aca4f36ac4eca9110c9e763693 | measure:13–37, main:40–49, root_arm:52–118 |
| [tests/integration/test_perf03_root_diagnostics.py](../../tests/integration/test_perf03_root_diagnostics.py) | 7f9a5a16e19d64e7215466e8593f9fad3e1ab630a23cd036d087fba81fb9683a | test_real_root_parity_and_local_reports:21–79 |
| [scripts/business_recalc_measure.py](../../scripts/business_recalc_measure.py) | edbd4b0d290fdf41ace88f2d8b15fb395c86eed2a7ae99daad5814975d114108 | main:23–499 |
| [scripts/biz_perf_03_b_once.py](../../scripts/biz_perf_03_b_once.py) | f9dc1970d5b9fa2176158131386a737b30945abc11c3c0bb4173ca10dcb42abb | Refused:53–54, arm_deadline:57–62, watchdog:66–91, require:94–96, digest:99–100, read_json:103–113, write_json:116–130, protocol:133–145, authorize:148–176, check_environment:179–215, clean_error:218–220, completion_status:223–235, number:238–240, metric_map:243–249, safe_plan:252–271, export_measurement:274–346, Channel:349–386, validate_single_mode:389–394, git:397–399, source_check:402–408, dependency_versions:411–418, api:421–427, Lab:430–706, phase_deadline:709–715, network_inode:718–719, validate_phase:722–743, process_rss:746–750, bounded_run:753–778, resource_check:781–788, check_resources:791–794, execute:797–842, prepare_export:845–918, validate_document:921–968, main:971–1008 |
| [scripts/v14_test_database.py](../../scripts/v14_test_database.py) | 5a7edc5707b5b21a97e711d043dbcff082739699376be88955f74c6c3625f1ca | verified_test_url:15–40, isolated_v14_database:44–79 |
| [scripts/perf03_lnx_offline_supervisor.py](../../scripts/perf03_lnx_offline_supervisor.py) | c6d71d7f923995af5bcf12acc48c71828ad6aaea2b2d206cfe33ad199c64edb5 | OwnedDirectory:23–143, fail:146–150, _supervise_registered:153–307, supervise:310–327, batch:330–343, main:346–356 |
| [scripts/perf03_lnx_hard_watchdog.py](../../scripts/perf03_lnx_hard_watchdog.py) | 02d8c6f939c694410c04fb7bc449f030e0e2c8708c1c801b08e5a2eba5940454 | Refused:38–39, require:42–44, canonical:47–48, request:51–55, validate_request:58–64, spec_hash:67–69, reserve:72–75, empty_receipt:78–91, fail:94–102, validate_receipt:105–156, Messages:159–240, _exited:243–245, _bound:248–252, _owned:255–257, _drain:260–268, _group_gone:271–276, _claims:279–300, _cleanup:303–348, _drive:351–408, run:411–457, _Parser:460–462, main:465–478 |
| [scripts/perf03_lnx_hard_mock_actor.py](../../scripts/perf03_lnx_hard_mock_actor.py) | e4c4a2cf9c5478cbd85c4f4fe17277c535e8eeba29427846b473e9065109d264 | emit:16–22, simulated_block:25–26, ChildLifecycle:30–131, same_group_child:134–166, main:168–220 |
| [tests/integration_offline/test_perf03_lnx_hard_watchdog_linux.py](../../tests/integration_offline/test_perf03_lnx_hard_watchdog_linux.py) | 3cfe5b4a0ee81e02f56c3692e494350964e524ce5ce2cf5d1997de0f1ae5e8d0 | invoke:20–51, test_linux_fixed_success_requires_exit_and_os_group_confirmation:54–58, test_linux_blocked_actor_deadline_is_independent_and_reaped:64–79, test_linux_same_group_child_is_reaped_by_actor_before_group_confirmation:82–88, test_linux_bad_or_missing_receipt_and_nonzero_never_pass:93–98, test_linux_fifo_reference_blocks_without_watchdog_and_owned_term_reaps:101–141, test_linux_race01_term_windows_never_claim_work_success_or_leave_child:146–156 |
| [tests/integration/test_business_recalc_performance.py](../../tests/integration/test_business_recalc_performance.py) | c6cc8cf4145d3dbefd259417e08c06ac7470a39adeca654ce9fe2f5483f2ba27 | isolated:22–24, seed:27–55, test_batched_raw_preflight_matches_every_field_and_reduces_queries:59–107, test_input_window_preserves_full_frame_dtypes_and_detects_source_change:110–137, test_input_window_status_overlay_tombstone_and_root_identity:140–179, test_input_window_memory_failure_closes_cursor_without_partial_frame:182–195, test_raw_preflight_rejects_unbounded_window:198–202, test_new_read_paths_are_off_by_default:205–212, test_final_source_verification_uses_original_publication_budget:215–230, test_cached_inputs_require_reverification_after_checkpoint_commit:233–245, test_opt_in_real_worker_financial_quality_and_atomic_terminal_state:249–305 |
| [backend/app/services/recalculation.py](../../backend/app/services/recalculation.py) | ac3d9625079277b0e4031f3b1b43a167905230458cf1958e3b1862564c76ae4c | run_recalculation:47–348, validate_recalculation_raw_prerequisites:351–399, _stop_if_cancelled:402–418, _factor_warmup_start:421–440, _month_chunks:443–454, create_recalculation_job:457–488 |
| [backend/app/services/job_worker.py](../../backend/app/services/job_worker.py) | 91069dd58733e442831977f58ee1c37616d1ef37a271d7845856421251d6e7da | worker_identity:120–121, claim_next_job:124–206, execute_claimed_job:210–505, _hold_unconfirmed_execution:508–528, _finish_data_cancellation:531–543, _run_heartbeat_loop:546–630, run_worker:633–640, _run_worker_with_source:643–656, _run_worker_loop:659–776, run_validate_data_job:779–847, _metadata_date:850–856, _load_dirty_ranges:859–865, _provider:868–869 |
| [backend/app/services/job_guard.py](../../backend/app/services/job_guard.py) | e9654107d525ca03bf412c3199f2add1ed0b376b648a9a20af5590b2cd80462b | QueueCapacityError:39–40, data_queue_identity:43–54, request_fingerprint:57–70, ResearchQueueConflictError:73–74, ActiveIngestionJobError:78–84, scheduler_setting:87–91, active_ingestion_jobs:94–106, recover_stale_ingestion_jobs:109–120, recover_stale_research_jobs:123–144, _recover_stale_jobs:147–204, research_can_run:207–213, production_can_run:216–222, find_active_ingestion_job:225–233, reject_if_active_ingestion_job:236–243, create_queued_ingestion_job:246–309, _acquire_ingestion_advisory_lock:312–324, _acquire_research_advisory_lock:327–330 |
| [backend/app/services/job_execution.py](../../backend/app/services/job_execution.py) | 5117d5634cfa43afbd0778c255e2258a6d84be9bf99a1e54a2e5b72f414a17bb | JobCancelled:14–15, JobOwnershipLost:18–19, JobExecutionUnconfirmed:22–23, uncertain_database_error:26–34, preserve_execution_on_disconnect:37–41, Execution:45–49, checkpoint:55–82 |
| [backend/app/repositories/job_run.py](../../backend/app/repositories/job_run.py) | 599f7275f5e58d96bc25c1a8a343389e96326fd976be48b45002f04ed6381624 | completed_data_source:12–18, start_job:21–60, update_job:63–96, _update_owned_data_job:99–180, touch_job_heartbeat:183–252, cancel_requested:255–258, finish_cancelled:261–268, log_provider_call:271–292 |
| [backend/app/services/data_publication.py](../../backend/app/services/data_publication.py) | 39d95b00afed3da308aa78a00917fad2308f9d19266cfa30268b145bd35e7e88 | _json:76–83, published_table:87–89, workspace:92–93, PublicationWorkspace:96–468, record_validation:471–481, defer_dirty_resolution:484–497, _finish_publication_dirty:500–538, route_upsert:541–558, _qualified_keys:561–566, _publishable_sql:569–576, _verify_candidate:579–747, finish_publication:751–943 |
| [backend/app/models/market_data.py](../../backend/app/models/market_data.py) | c0207d196fb9777bfd5c83284ca9d36f5b2cbf9ea5191ca149fbce9afcee9261 | StockBasic:27–42, TradeCalendar:45–51, StockDaily:54–74, StockAdjFactor:77–86, StockDailyBasic:89–111, IndexDaily:114–130, StockStDaily:133–145, StockSuspendDaily:148–159, StockLimitDaily:162–176, StockFactorDaily:179–242, MarketDaily:245–273, Sector:276–286, SectorMember:289–301, SectorFactorDaily:304–342, DataQualityDaily:345–368, DataDirtyRange:371–389, StockTradeStatusDaily:392–418, StockStateDaily:421–449, StrategySignal:452–480, SignalForwardEval:483–522, Theme:525–540, ThemeMemberSnapshot:543–556, ThemeMemberInterval:559–576, ThemeDaily:579–602, ThemeMoneyflowDaily:605–624, ThemeLimitDaily:627–643, ThemeFactorDaily:646–696, StockOpportunityDaily:699–743, _ResearchForwardFields:746–832, OpportunityForwardEval:835–900, ThemeForwardEval:903–962, ResearchTransitionEval:965–1023 |
| [backend/app/models/job.py](../../backend/app/models/job.py) | fc795d1d4fb92ff3b8a10d41e19898e392e236ca84c661e78dfa2b02519ecc11 | JobRun:24–62, ProviderApiLog:65–79, ServiceHeartbeat:82–96 |
| [backend/app/models/data_publication.py](../../backend/app/models/data_publication.py) | c9163a6e8386404d3b9faf9eaa1bf064d4a476b986e8fcc452ba9ce382aca63c | RowKeyJSON:15–21, DataPublication:24–39, DataPublicationSource:42–56, DataPublicationRow:59–84, DataPublicationPreimage:87–97, DataPublicationScope:100–111 |
| [backend/app/models/data_schedule.py](../../backend/app/models/data_schedule.py) | 1c02583b6d8b455be81a3fc7f34c7aa93c167a6e516395e6688c24939fdf48c2 | DataScheduleIntent:12–33 |
| [backend/app/services/calculation_policy.py](../../backend/app/services/calculation_policy.py) | 11801e7198f3cb41a008f38abc99f39cb66f178c70f1bff0a628a6574ba27ab0 | PolicyChangeReason:26–30, PolicyChanged:33–47, source_audit:50–60, calculation_source_identity:63–74, _source:77–83, runtime_source:86–132, flag_values:135–139, request_range:142–147, ExecutionPolicy:150–293, DriverFetchObserver:296–330, effective_flag:333–340, QueryObserver:343–401 |
| [backend/app/services/performance_diagnostics.py](../../backend/app/services/performance_diagnostics.py) | af36e0988732fcc2977713215afa80d906c9787c5dcfc73eddabb658819b09dc | stamp:27–28, resource_sample:31–41, Trace:44–134, span:138–165, terminal:168–172, observed:175–182, observe_worker:185–235, measured_interval:238–248, driver_fetch:251–263, bind_task:266–281 |
| [backend/app/services/performance_sql_diagnostics.py](../../backend/app/services/performance_sql_diagnostics.py) | 2cb9aaef19f83a8e7f0bdb0bf09295e6eb298c5f7b2493827bf28647f1e58bd0 | fingerprint:12–29, SQLObserver:32–119 |
| [backend/app/services/calculation_progress.py](../../backend/app/services/calculation_progress.py) | 0086476cf51480281701a4bd4c10e0327d41004ebb0d9849444fa7772d0fdc1a | CalculationProgress:23–67, ProgressStep:70–130, run_calculation:133–145 |
| [backend/app/services/worker_observation.py](../../backend/app/services/worker_observation.py) | d6cac9bca33c87a7d245c7c57feef5937ec90290fbbef05676e8d4eb0e2529e5 | fingerprint:20–21, SessionRegistry:24–43, bind_session:46–49, observe_session:52–71, HeartbeatHealth:74–107, persist_observation:110–172, heartbeat_health_payload:175–194, finish_worker_observation:197–218 |
| [backend/app/services/execution_diagnostics.py](../../backend/app/services/execution_diagnostics.py) | bc31d3e718122b024b142cbd4e2602d410a923e6b54d58899f66e097f48d80ff | ExecutionDiagnostics:28–92, record_duration:95–104, operation:108–119 |
| [backend/app/services/calc_metadata.py](../../backend/app/services/calc_metadata.py) | ee0932fd089ebb233bb62080cc03d0672c22412278e9b97123272e87bd55ee2c | config_hash:8–10, calculation_metadata:13–24 |
| [backend/app/services/trend/service.py](../../backend/app/services/trend/service.py) | c70c5541240268a23246905823cb4b7093767204915ea64426a7c02a0bd01b60 | TrendService:39–237, _clean_row:240–251, _ensure_unique_rows:254–267 |
| [backend/app/services/opportunity/service.py](../../backend/app/services/opportunity/service.py) | 62297dcf8aeca074214980eb67f848b6228e4e24575e8e8fa00f485b56ce25a3 | OpportunityService:39–165, _clean:168–179 |
| [backend/app/services/quality/daily_quality.py](../../backend/app/services/quality/daily_quality.py) | 60878cb538fd662ef51b8627eaa1553ae6a34898daf7fcbf98287a9a505a2be8 | CoverageResult:37–51, CrossTableQualityResult:55–63, CrossTableRangeResult:67–85, DataQualityError:88–89, expected_stock_daily_codes:92–111, check_daily_coverage:114–163, persist_coverage_result:166–222, record_cross_table_quality:225–370, validate_cross_table_range:374–402, cross_table_coverage_status:405–423, _persist_simple:426–487, _persist_sector_coverage:490–530, _count_date:533–548, _open_trade_dates:551–564, _daily_threshold:567–574, _cross_table_threshold:577–590 |
| [migrations/versions/20261018_0058_data_publication.py](../../migrations/versions/20261018_0058_data_publication.py) | b53c079ff98a589a6c85c333c9000c19f3517b0725755c2250f84379aef43376 | upgrade:13–169, downgrade:172–186 |
| [.github/workflows/ci.yml](../../.github/workflows/ci.yml) | 1c631a30a4fab3f04355675e45f6be8188eb025d12aa872b6f08d78ecea9ad95 | 全文静态合同 |
| [.github/workflows/biz-perf-03-b-once.yml](../../.github/workflows/biz-perf-03-b-once.yml) | cbb721247699730247d7902c540f8fb211afcb8ebed3fcabe4d1d1fa4c72429a | 全文静态合同 |
| [docs/acceptance/biz_perf_03_b_actions_once_protocol.json](../../docs/acceptance/biz_perf_03_b_actions_once_protocol.json) | 56e81fcbfe23071dde631d1eab9eb7b5d74e4011f0f27b6b98e2b8f845a92d17 | 全文静态合同 |
| [requirements-biz-perf-linux-py312-v1.lock](../../requirements-biz-perf-linux-py312-v1.lock) | 88549dce3164364430e20970fa10eb2125b60ff05f456d7bef4474876a98dcfc | 全文静态合同 |

## 附录B：机械列级合同（静态ORM，不是数据库探测）

每行必须唯一对应(table,column)，原始声明包括SQL型/FK/default。nullable依据显式nullable、
PK约束与Mapped Optional推导；最终DDL仍须A对真实隔离库核验。无继承动态schema的猜测。
策略X/J/U/T/N/R/M/E/Z含义见§7；表自然键/sort/scope见§7.1。边界表Z仍保留逐列策略，
一旦出现未批准行即失败。源码声明中的竖线用HTML实体表达以保持表格结构。

静态展开：37张ORM表、520个列，另加alembic_version.version_num；原始声明未执行。

| table.column | 声明SQL型/FK/default（精确源码） | nullable | policy | source:line |
| --- | --- | --- | --- | --- |
| stock_basic.ts_code | `mapped_column(String(16), primary_key=True)` | NO | X | backend/app/models/market_data.py:30 |
| stock_basic.symbol | `mapped_column(String(8))` | YES | X | backend/app/models/market_data.py:31 |
| stock_basic.name | `mapped_column(String(64))` | YES | X | backend/app/models/market_data.py:32 |
| stock_basic.market | `mapped_column(String(32))` | YES | X | backend/app/models/market_data.py:33 |
| stock_basic.exchange | `mapped_column(String(8))` | YES | X | backend/app/models/market_data.py:34 |
| stock_basic.industry | `mapped_column(String(64))` | YES | X | backend/app/models/market_data.py:35 |
| stock_basic.list_status | `mapped_column(String(4))` | YES | X | backend/app/models/market_data.py:36 |
| stock_basic.list_date | `mapped_column(Date)` | YES | X | backend/app/models/market_data.py:37 |
| stock_basic.delist_date | `mapped_column(Date)` | YES | X | backend/app/models/market_data.py:38 |
| stock_basic.is_hs | `mapped_column(String(4))` | YES | X | backend/app/models/market_data.py:39 |
| stock_basic.updated_at | `mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())` | NO | T | backend/app/models/market_data.py:40 |
| trade_calendar.cal_date | `mapped_column(Date, primary_key=True)` | NO | X | backend/app/models/market_data.py:48 |
| trade_calendar.is_open | `mapped_column(Boolean, nullable=False)` | NO | X | backend/app/models/market_data.py:49 |
| trade_calendar.pretrade_date | `mapped_column(Date)` | YES | X | backend/app/models/market_data.py:50 |
| trade_calendar.exchange | `mapped_column(String(8), nullable=False, default='SSE')` | NO | X | backend/app/models/market_data.py:51 |
| stock_daily.trade_date | `mapped_column(Date)` | NO | X | backend/app/models/market_data.py:61 |
| stock_daily.ts_code | `mapped_column(String(16))` | NO | X | backend/app/models/market_data.py:62 |
| stock_daily.open | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:63 |
| stock_daily.high | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:64 |
| stock_daily.low | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:65 |
| stock_daily.close | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:66 |
| stock_daily.pre_close | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:67 |
| stock_daily.change | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:68 |
| stock_daily.pct_chg | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:69 |
| stock_daily.vol | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:70 |
| stock_daily.amount | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:71 |
| stock_daily.source_updated_at | `mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())` | NO | T | backend/app/models/market_data.py:72 |
| stock_adj_factor.trade_date | `mapped_column(Date)` | NO | X | backend/app/models/market_data.py:84 |
| stock_adj_factor.ts_code | `mapped_column(String(16))` | NO | X | backend/app/models/market_data.py:85 |
| stock_adj_factor.adj_factor | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:86 |
| stock_daily_basic.trade_date | `mapped_column(Date)` | NO | X | backend/app/models/market_data.py:96 |
| stock_daily_basic.ts_code | `mapped_column(String(16))` | NO | X | backend/app/models/market_data.py:97 |
| stock_daily_basic.close | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:98 |
| stock_daily_basic.turnover_rate | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:99 |
| stock_daily_basic.turnover_rate_f | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:100 |
| stock_daily_basic.volume_ratio | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:101 |
| stock_daily_basic.pe | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:102 |
| stock_daily_basic.pe_ttm | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:103 |
| stock_daily_basic.pb | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:104 |
| stock_daily_basic.ps | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:105 |
| stock_daily_basic.ps_ttm | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:106 |
| stock_daily_basic.total_share | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:107 |
| stock_daily_basic.float_share | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:108 |
| stock_daily_basic.free_share | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:109 |
| stock_daily_basic.total_mv | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:110 |
| stock_daily_basic.circ_mv | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:111 |
| index_daily.trade_date | `mapped_column(Date)` | NO | X | backend/app/models/market_data.py:121 |
| index_daily.ts_code | `mapped_column(String(16))` | NO | X | backend/app/models/market_data.py:122 |
| index_daily.open | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:123 |
| index_daily.high | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:124 |
| index_daily.low | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:125 |
| index_daily.close | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:126 |
| index_daily.pre_close | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:127 |
| index_daily.pct_chg | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:128 |
| index_daily.vol | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:129 |
| index_daily.amount | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:130 |
| stock_st_daily.trade_date | `mapped_column(Date)` | NO | X | backend/app/models/market_data.py:137 |
| stock_st_daily.ts_code | `mapped_column(String(16))` | NO | X | backend/app/models/market_data.py:138 |
| stock_st_daily.name | `mapped_column(String(64))` | YES | X | backend/app/models/market_data.py:139 |
| stock_st_daily.st_type | `mapped_column(String(32))` | YES | X | backend/app/models/market_data.py:140 |
| stock_st_daily.st_type_name | `mapped_column(String(64))` | YES | X | backend/app/models/market_data.py:141 |
| stock_st_daily.created_at | `mapped_column(DateTime(timezone=True), server_default=func.now())` | NO | T | backend/app/models/market_data.py:142 |
| stock_st_daily.updated_at | `mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())` | NO | T | backend/app/models/market_data.py:143 |
| stock_suspend_daily.trade_date | `mapped_column(Date)` | NO | X | backend/app/models/market_data.py:152 |
| stock_suspend_daily.ts_code | `mapped_column(String(16))` | NO | X | backend/app/models/market_data.py:153 |
| stock_suspend_daily.suspend_type | `mapped_column(String(8))` | NO | X | backend/app/models/market_data.py:154 |
| stock_suspend_daily.suspend_timing | `mapped_column(Text, nullable=True)` | YES | X | backend/app/models/market_data.py:155 |
| stock_suspend_daily.created_at | `mapped_column(DateTime(timezone=True), server_default=func.now())` | NO | T | backend/app/models/market_data.py:156 |
| stock_suspend_daily.updated_at | `mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())` | NO | T | backend/app/models/market_data.py:157 |
| stock_limit_daily.trade_date | `mapped_column(Date)` | NO | X | backend/app/models/market_data.py:166 |
| stock_limit_daily.ts_code | `mapped_column(String(16))` | NO | X | backend/app/models/market_data.py:167 |
| stock_limit_daily.pre_close | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:168 |
| stock_limit_daily.up_limit | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:169 |
| stock_limit_daily.down_limit | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:170 |
| stock_limit_daily.asset_type | `mapped_column(String(16))` | YES | X | backend/app/models/market_data.py:171 |
| stock_limit_daily.exchange | `mapped_column(String(8))` | YES | X | backend/app/models/market_data.py:172 |
| stock_limit_daily.created_at | `mapped_column(DateTime(timezone=True), server_default=func.now())` | NO | T | backend/app/models/market_data.py:173 |
| stock_limit_daily.updated_at | `mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())` | NO | T | backend/app/models/market_data.py:174 |
| stock_factor_daily.trade_date | `mapped_column(Date)` | NO | X | backend/app/models/market_data.py:187 |
| stock_factor_daily.ts_code | `mapped_column(String(16))` | NO | X | backend/app/models/market_data.py:188 |
| stock_factor_daily.adj_open | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:189 |
| stock_factor_daily.adj_high | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:190 |
| stock_factor_daily.adj_low | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:191 |
| stock_factor_daily.adj_close | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:192 |
| stock_factor_daily.ma5 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:193 |
| stock_factor_daily.ma10 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:194 |
| stock_factor_daily.ma20 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:195 |
| stock_factor_daily.ma60 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:196 |
| stock_factor_daily.ma120 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:197 |
| stock_factor_daily.ma250 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:198 |
| stock_factor_daily.return1 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:199 |
| stock_factor_daily.return3 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:200 |
| stock_factor_daily.return5 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:201 |
| stock_factor_daily.return20 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:202 |
| stock_factor_daily.return60 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:203 |
| stock_factor_daily.return120 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:204 |
| stock_factor_daily.return250 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:205 |
| stock_factor_daily.ma20_slope5 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:206 |
| stock_factor_daily.ma60_slope10 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:207 |
| stock_factor_daily.atr20 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:208 |
| stock_factor_daily.atr20_pct | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:209 |
| stock_factor_daily.amount_ma20 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:210 |
| stock_factor_daily.amount_ratio20 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:211 |
| stock_factor_daily.prev_high20 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:212 |
| stock_factor_daily.prev_high60 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:213 |
| stock_factor_daily.prev_high120 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:214 |
| stock_factor_daily.low20 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:215 |
| stock_factor_daily.low60 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:216 |
| stock_factor_daily.breakout20 | `mapped_column(Boolean)` | YES | X | backend/app/models/market_data.py:217 |
| stock_factor_daily.breakout60 | `mapped_column(Boolean)` | YES | X | backend/app/models/market_data.py:218 |
| stock_factor_daily.cross_above_ma20 | `mapped_column(Boolean)` | YES | X | backend/app/models/market_data.py:219 |
| stock_factor_daily.cross_above_ma60 | `mapped_column(Boolean)` | YES | X | backend/app/models/market_data.py:220 |
| stock_factor_daily.higher_low | `mapped_column(Boolean)` | YES | X | backend/app/models/market_data.py:221 |
| stock_factor_daily.higher_low_pct | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:222 |
| stock_factor_daily.drawdown_high60 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:223 |
| stock_factor_daily.drawdown_high120 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:224 |
| stock_factor_daily.max_drawdown60 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:225 |
| stock_factor_daily.trend_efficiency20 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:226 |
| stock_factor_daily.rps20 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:227 |
| stock_factor_daily.rps60 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:228 |
| stock_factor_daily.rps120 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:229 |
| stock_factor_daily.rps250 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:230 |
| stock_factor_daily.rps20_delta5 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:231 |
| stock_factor_daily.rps60_delta5 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:232 |
| stock_factor_daily.relative_return20 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:233 |
| stock_factor_daily.relative_return60 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:234 |
| stock_factor_daily.eligible | `mapped_column(Boolean, nullable=False, default=False)` | NO | X | backend/app/models/market_data.py:235 |
| stock_factor_daily.exclusion_reason | `mapped_column(String(128))` | YES | X | backend/app/models/market_data.py:236 |
| stock_factor_daily.calc_version | `mapped_column(String(32))` | YES | X | backend/app/models/market_data.py:237 |
| stock_factor_daily.config_hash | `mapped_column(String(64))` | YES | X | backend/app/models/market_data.py:238 |
| stock_factor_daily.calc_run_id | `mapped_column(UUID(as_uuid=True), ForeignKey('job_run.id', ondelete='RESTRICT'), index=True)` | YES | U/R | backend/app/models/market_data.py:239 |
| stock_factor_daily.calculated_at | `mapped_column(DateTime(timezone=True))` | YES | T | backend/app/models/market_data.py:242 |
| market_daily.trade_date | `mapped_column(Date, primary_key=True)` | NO | X | backend/app/models/market_data.py:248 |
| market_daily.market_score | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:249 |
| market_daily.regime | `mapped_column(String(16))` | YES | X | backend/app/models/market_data.py:250 |
| market_daily.breadth20 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:251 |
| market_daily.breadth60 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:252 |
| market_daily.up_count | `mapped_column(Integer)` | YES | X | backend/app/models/market_data.py:253 |
| market_daily.down_count | `mapped_column(Integer)` | YES | X | backend/app/models/market_data.py:254 |
| market_daily.flat_count | `mapped_column(Integer)` | YES | X | backend/app/models/market_data.py:255 |
| market_daily.up_rate | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:256 |
| market_daily.new_high20_count | `mapped_column(Integer)` | YES | X | backend/app/models/market_data.py:257 |
| market_daily.new_low20_count | `mapped_column(Integer)` | YES | X | backend/app/models/market_data.py:258 |
| market_daily.new_high60_count | `mapped_column(Integer)` | YES | X | backend/app/models/market_data.py:259 |
| market_daily.new_low60_count | `mapped_column(Integer)` | YES | X | backend/app/models/market_data.py:260 |
| market_daily.total_amount | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:261 |
| market_daily.amount_ratio20 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:262 |
| market_daily.index_trend_score | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:263 |
| market_daily.breadth_score | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:264 |
| market_daily.ad_score | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:265 |
| market_daily.new_high_low_score | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:266 |
| market_daily.liquidity_score | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:267 |
| market_daily.calc_version | `mapped_column(String(32))` | YES | X | backend/app/models/market_data.py:268 |
| market_daily.config_hash | `mapped_column(String(64))` | YES | X | backend/app/models/market_data.py:269 |
| market_daily.calc_run_id | `mapped_column(UUID(as_uuid=True), ForeignKey('job_run.id', ondelete='RESTRICT'), index=True)` | YES | U/R | backend/app/models/market_data.py:270 |
| market_daily.calculated_at | `mapped_column(DateTime(timezone=True))` | YES | T | backend/app/models/market_data.py:273 |
| sector.sector_id | `mapped_column(Integer, primary_key=True, autoincrement=True)` | NO | N | backend/app/models/market_data.py:280 |
| sector.source | `mapped_column(String(16), nullable=False)` | NO | X | backend/app/models/market_data.py:281 |
| sector.source_code | `mapped_column(String(32), nullable=False)` | NO | X | backend/app/models/market_data.py:282 |
| sector.name | `mapped_column(String(128), nullable=False)` | NO | X | backend/app/models/market_data.py:283 |
| sector.level | `mapped_column(String(16))` | YES | X | backend/app/models/market_data.py:284 |
| sector.parent_code | `mapped_column(String(32))` | YES | X | backend/app/models/market_data.py:285 |
| sector.is_active | `mapped_column(Boolean, nullable=False, default=True)` | NO | X | backend/app/models/market_data.py:286 |
| sector_member.id | `mapped_column(Integer, primary_key=True, autoincrement=True)` | NO | N | backend/app/models/market_data.py:296 |
| sector_member.sector_id | `mapped_column(ForeignKey('sector.sector_id'), nullable=False)` | NO | N/R | backend/app/models/market_data.py:297 |
| sector_member.ts_code | `mapped_column(String(16), nullable=False)` | NO | X | backend/app/models/market_data.py:298 |
| sector_member.valid_from | `mapped_column(Date, nullable=False)` | NO | X | backend/app/models/market_data.py:299 |
| sector_member.valid_to | `mapped_column(Date)` | YES | X | backend/app/models/market_data.py:300 |
| sector_member.is_latest | `mapped_column(Boolean, nullable=False, default=True)` | NO | X | backend/app/models/market_data.py:301 |
| sector_factor_daily.trade_date | `mapped_column(Date)` | NO | X | backend/app/models/market_data.py:311 |
| sector_factor_daily.sector_id | `mapped_column(ForeignKey('sector.sector_id'))` | NO | N/R | backend/app/models/market_data.py:312 |
| sector_factor_daily.member_count | `mapped_column(Integer)` | YES | X | backend/app/models/market_data.py:313 |
| sector_factor_daily.eligible_member_count | `mapped_column(Integer)` | YES | X | backend/app/models/market_data.py:314 |
| sector_factor_daily.return1 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:315 |
| sector_factor_daily.return3 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:316 |
| sector_factor_daily.return5 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:317 |
| sector_factor_daily.return20 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:318 |
| sector_factor_daily.excess_return5 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:319 |
| sector_factor_daily.excess_return20 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:320 |
| sector_factor_daily.breadth20 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:321 |
| sector_factor_daily.breadth60 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:322 |
| sector_factor_daily.up_rate | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:323 |
| sector_factor_daily.new_high20_rate | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:324 |
| sector_factor_daily.rps60_median | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:325 |
| sector_factor_daily.rps60_top20_rate | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:326 |
| sector_factor_daily.amount | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:327 |
| sector_factor_daily.amount_ratio20 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:328 |
| sector_factor_daily.limit_up_density | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:329 |
| sector_factor_daily.moneyflow_score | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:330 |
| sector_factor_daily.heat_score | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:331 |
| sector_factor_daily.heat_momentum1 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:332 |
| sector_factor_daily.heat_momentum3 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:333 |
| sector_factor_daily.heat_rank | `mapped_column(Integer)` | YES | X | backend/app/models/market_data.py:334 |
| sector_factor_daily.rank_change | `mapped_column(Integer)` | YES | X | backend/app/models/market_data.py:335 |
| sector_factor_daily.lifecycle | `mapped_column(String(32))` | YES | X | backend/app/models/market_data.py:336 |
| sector_factor_daily.calc_version | `mapped_column(String(32))` | YES | X | backend/app/models/market_data.py:337 |
| sector_factor_daily.config_hash | `mapped_column(String(64))` | YES | X | backend/app/models/market_data.py:338 |
| sector_factor_daily.calc_run_id | `mapped_column(UUID(as_uuid=True), ForeignKey('job_run.id', ondelete='RESTRICT'), index=True)` | YES | U/R | backend/app/models/market_data.py:339 |
| sector_factor_daily.calculated_at | `mapped_column(DateTime(timezone=True))` | YES | T | backend/app/models/market_data.py:342 |
| data_quality_daily.id | `mapped_column(BigInteger, primary_key=True, autoincrement=True)` | NO | N | backend/app/models/market_data.py:352 |
| data_quality_daily.trade_date | `mapped_column(Date, nullable=False)` | NO | X | backend/app/models/market_data.py:353 |
| data_quality_daily.dataset | `mapped_column(String(64), nullable=False)` | NO | X | backend/app/models/market_data.py:354 |
| data_quality_daily.expected_rows | `mapped_column(Integer)` | YES | X | backend/app/models/market_data.py:355 |
| data_quality_daily.actual_rows | `mapped_column(Integer)` | YES | X | backend/app/models/market_data.py:356 |
| data_quality_daily.coverage_rate | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:357 |
| data_quality_daily.missing_count | `mapped_column(Integer)` | YES | X | backend/app/models/market_data.py:358 |
| data_quality_daily.duplicate_count | `mapped_column(Integer)` | YES | X | backend/app/models/market_data.py:359 |
| data_quality_daily.null_count | `mapped_column(Integer)` | YES | X | backend/app/models/market_data.py:360 |
| data_quality_daily.warning_count | `mapped_column(Integer)` | YES | X | backend/app/models/market_data.py:361 |
| data_quality_daily.error_count | `mapped_column(Integer)` | YES | X | backend/app/models/market_data.py:362 |
| data_quality_daily.status | `mapped_column(String(32), nullable=False)` | NO | X | backend/app/models/market_data.py:363 |
| data_quality_daily.issue_codes | `mapped_column(JSONB)` | YES | J | backend/app/models/market_data.py:364 |
| data_quality_daily.checked_at | `mapped_column(DateTime(timezone=True), server_default=func.now())` | NO | T | backend/app/models/market_data.py:365 |
| data_quality_daily.job_id | `mapped_column(UUID(as_uuid=True), ForeignKey('job_run.id', ondelete='RESTRICT'), index=True)` | YES | U/R | backend/app/models/market_data.py:366 |
| data_dirty_range.id | `mapped_column(BigInteger, primary_key=True, autoincrement=True)` | NO | N | backend/app/models/market_data.py:375 |
| data_dirty_range.dataset | `mapped_column(String(64), nullable=False)` | NO | X | backend/app/models/market_data.py:376 |
| data_dirty_range.dirty_start_date | `mapped_column(Date, nullable=False)` | NO | X | backend/app/models/market_data.py:377 |
| data_dirty_range.dirty_end_date | `mapped_column(Date, nullable=False)` | NO | X | backend/app/models/market_data.py:378 |
| data_dirty_range.reason | `mapped_column(String(256))` | YES | X | backend/app/models/market_data.py:379 |
| data_dirty_range.source_job_id | `mapped_column(UUID(as_uuid=True), ForeignKey('job_run.id', ondelete='RESTRICT'), index=True)` | YES | U/R | backend/app/models/market_data.py:380 |
| data_dirty_range.status | `mapped_column(String(16), nullable=False, default='OPEN')` | NO | X | backend/app/models/market_data.py:383 |
| data_dirty_range.retry_count | `mapped_column(Integer, nullable=False, default=0)` | NO | X | backend/app/models/market_data.py:384 |
| data_dirty_range.last_error | `mapped_column(Text)` | YES | X | backend/app/models/market_data.py:385 |
| data_dirty_range.last_failed_at | `mapped_column(DateTime(timezone=True))` | YES | T | backend/app/models/market_data.py:386 |
| data_dirty_range.processing_started_at | `mapped_column(DateTime(timezone=True))` | YES | T | backend/app/models/market_data.py:387 |
| data_dirty_range.created_at | `mapped_column(DateTime(timezone=True), server_default=func.now())` | NO | T | backend/app/models/market_data.py:388 |
| data_dirty_range.resolved_at | `mapped_column(DateTime(timezone=True))` | YES | T | backend/app/models/market_data.py:389 |
| stock_trade_status_daily.trade_date | `mapped_column(Date)` | NO | X | backend/app/models/market_data.py:400 |
| stock_trade_status_daily.ts_code | `mapped_column(String(16))` | NO | X | backend/app/models/market_data.py:401 |
| stock_trade_status_daily.is_active | `mapped_column(Boolean, nullable=False)` | NO | X | backend/app/models/market_data.py:402 |
| stock_trade_status_daily.is_suspended | `mapped_column(Boolean, nullable=False)` | NO | X | backend/app/models/market_data.py:403 |
| stock_trade_status_daily.is_st | `mapped_column(Boolean)` | YES | X | backend/app/models/market_data.py:404 |
| stock_trade_status_daily.st_status_unknown | `mapped_column(Boolean, nullable=False, default=False)` | NO | X | backend/app/models/market_data.py:405 |
| stock_trade_status_daily.up_limit | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:406 |
| stock_trade_status_daily.down_limit | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:407 |
| stock_trade_status_daily.is_limit_up_close | `mapped_column(Boolean)` | YES | X | backend/app/models/market_data.py:408 |
| stock_trade_status_daily.is_limit_down_close | `mapped_column(Boolean)` | YES | X | backend/app/models/market_data.py:409 |
| stock_trade_status_daily.tradable | `mapped_column(Boolean, nullable=False)` | NO | X | backend/app/models/market_data.py:410 |
| stock_trade_status_daily.strategy_eligible | `mapped_column(Boolean, nullable=False)` | NO | X | backend/app/models/market_data.py:411 |
| stock_trade_status_daily.status_reason | `mapped_column(String(256))` | YES | X | backend/app/models/market_data.py:412 |
| stock_trade_status_daily.calc_version | `mapped_column(String(32), nullable=False)` | NO | X | backend/app/models/market_data.py:413 |
| stock_trade_status_daily.config_hash | `mapped_column(String(64), nullable=False)` | NO | X | backend/app/models/market_data.py:414 |
| stock_trade_status_daily.calc_run_id | `mapped_column(UUID(as_uuid=True), ForeignKey('job_run.id', ondelete='RESTRICT'), index=True)` | YES | U/R | backend/app/models/market_data.py:415 |
| stock_trade_status_daily.calculated_at | `mapped_column(DateTime(timezone=True), nullable=False)` | NO | T | backend/app/models/market_data.py:418 |
| stock_state_daily.trade_date | `mapped_column(Date)` | NO | X | backend/app/models/market_data.py:429 |
| stock_state_daily.ts_code | `mapped_column(String(16))` | NO | X | backend/app/models/market_data.py:430 |
| stock_state_daily.algo_version | `mapped_column(String(32))` | NO | X | backend/app/models/market_data.py:431 |
| stock_state_daily.previous_state | `mapped_column(String(16))` | YES | X | backend/app/models/market_data.py:432 |
| stock_state_daily.state | `mapped_column(String(16), nullable=False)` | NO | X | backend/app/models/market_data.py:433 |
| stock_state_daily.state_day_count | `mapped_column(Integer)` | YES | X | backend/app/models/market_data.py:434 |
| stock_state_daily.is_new_state | `mapped_column(Boolean, nullable=False, default=False)` | NO | X | backend/app/models/market_data.py:435 |
| stock_state_daily.right_side_score | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:436 |
| stock_state_daily.trend_score | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:437 |
| stock_state_daily.opportunity_score | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:438 |
| stock_state_daily.primary_sector_id | `mapped_column(Integer)` | YES | X/R | backend/app/models/market_data.py:439 |
| stock_state_daily.sector_heat | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:440 |
| stock_state_daily.market_score | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:441 |
| stock_state_daily.fast_transition | `mapped_column(Boolean, nullable=False, default=False)` | NO | X | backend/app/models/market_data.py:442 |
| stock_state_daily.reason_codes | `mapped_column(JSONB)` | YES | J | backend/app/models/market_data.py:443 |
| stock_state_daily.calc_version | `mapped_column(String(32))` | YES | X | backend/app/models/market_data.py:444 |
| stock_state_daily.config_hash | `mapped_column(String(64))` | YES | X | backend/app/models/market_data.py:445 |
| stock_state_daily.calc_run_id | `mapped_column(UUID(as_uuid=True), ForeignKey('job_run.id', ondelete='RESTRICT'), index=True)` | YES | U/R | backend/app/models/market_data.py:446 |
| stock_state_daily.calculated_at | `mapped_column(DateTime(timezone=True))` | YES | T | backend/app/models/market_data.py:449 |
| strategy_signal.id | `mapped_column(BigInteger, primary_key=True, autoincrement=True)` | NO | N | backend/app/models/market_data.py:465 |
| strategy_signal.trade_date | `mapped_column(Date, nullable=False)` | NO | X | backend/app/models/market_data.py:466 |
| strategy_signal.ts_code | `mapped_column(String(16), nullable=False)` | NO | X | backend/app/models/market_data.py:467 |
| strategy_signal.signal_type | `mapped_column(String(32), nullable=False)` | NO | X | backend/app/models/market_data.py:468 |
| strategy_signal.score | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:469 |
| strategy_signal.opportunity_score | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:470 |
| strategy_signal.reason_codes | `mapped_column(JSONB)` | YES | J | backend/app/models/market_data.py:471 |
| strategy_signal.payload | `mapped_column(JSONB)` | YES | J | backend/app/models/market_data.py:472 |
| strategy_signal.algo_version | `mapped_column(String(32), nullable=False)` | NO | X | backend/app/models/market_data.py:473 |
| strategy_signal.calc_version | `mapped_column(String(32))` | YES | X | backend/app/models/market_data.py:474 |
| strategy_signal.config_hash | `mapped_column(String(64))` | YES | X | backend/app/models/market_data.py:475 |
| strategy_signal.calc_run_id | `mapped_column(UUID(as_uuid=True), ForeignKey('job_run.id', ondelete='RESTRICT'), index=True)` | YES | U/R | backend/app/models/market_data.py:476 |
| strategy_signal.calculated_at | `mapped_column(DateTime(timezone=True))` | YES | T | backend/app/models/market_data.py:479 |
| strategy_signal.created_at | `mapped_column(DateTime(timezone=True), server_default=func.now())` | NO | T | backend/app/models/market_data.py:480 |
| signal_forward_eval.id | `mapped_column(BigInteger, primary_key=True, autoincrement=True)` | NO | N | backend/app/models/market_data.py:495 |
| signal_forward_eval.signal_id | `mapped_column(ForeignKey('strategy_signal.id', ondelete='CASCADE'), nullable=False)` | NO | N/R | backend/app/models/market_data.py:496 |
| signal_forward_eval.trade_date | `mapped_column(Date, nullable=False)` | NO | X | backend/app/models/market_data.py:499 |
| signal_forward_eval.ts_code | `mapped_column(String(16), nullable=False)` | NO | X | backend/app/models/market_data.py:500 |
| signal_forward_eval.signal_type | `mapped_column(String(32), nullable=False)` | NO | X | backend/app/models/market_data.py:501 |
| signal_forward_eval.algo_version | `mapped_column(String(32), nullable=False)` | NO | X | backend/app/models/market_data.py:502 |
| signal_forward_eval.eval_version | `mapped_column(String(16), nullable=False, default='eval_v3')` | NO | X | backend/app/models/market_data.py:503 |
| signal_forward_eval.entry_basis | `mapped_column(String(16), nullable=False, default='NEXT_OPEN')` | NO | X | backend/app/models/market_data.py:504 |
| signal_forward_eval.horizon_basis | `mapped_column(String(32), nullable=False, default='MARKET_TRADING_DAY')` | NO | X | backend/app/models/market_data.py:505 |
| signal_forward_eval.entry_trade_date | `mapped_column(Date)` | YES | X | backend/app/models/market_data.py:508 |
| signal_forward_eval.entry_price | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:509 |
| signal_forward_eval.entry_executable | `mapped_column(Boolean)` | YES | X | backend/app/models/market_data.py:510 |
| signal_forward_eval.exit_executable | `mapped_column(Boolean)` | YES | X | backend/app/models/market_data.py:511 |
| signal_forward_eval.non_executable_reason | `mapped_column(String(128))` | YES | X | backend/app/models/market_data.py:512 |
| signal_forward_eval.ret5 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:513 |
| signal_forward_eval.ret10 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:514 |
| signal_forward_eval.ret20 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:515 |
| signal_forward_eval.ret60 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:516 |
| signal_forward_eval.mfe20 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:517 |
| signal_forward_eval.mae20 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:518 |
| signal_forward_eval.evaluated_until_date | `mapped_column(Date)` | YES | X | backend/app/models/market_data.py:519 |
| signal_forward_eval.updated_at | `mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())` | NO | T | backend/app/models/market_data.py:520 |
| theme.theme_code | `mapped_column(String(32), primary_key=True)` | NO | X | backend/app/models/market_data.py:528 |
| theme.source | `mapped_column(String(16), nullable=False)` | NO | X | backend/app/models/market_data.py:529 |
| theme.name | `mapped_column(String(128), nullable=False)` | NO | X | backend/app/models/market_data.py:530 |
| theme.theme_type | `mapped_column(String(16), nullable=False)` | NO | X | backend/app/models/market_data.py:531 |
| theme.exchange | `mapped_column(String(16))` | YES | X | backend/app/models/market_data.py:532 |
| theme.constituent_count | `mapped_column(Integer)` | YES | X | backend/app/models/market_data.py:533 |
| theme.list_date | `mapped_column(Date)` | YES | X | backend/app/models/market_data.py:534 |
| theme.is_active | `mapped_column(Boolean, nullable=False, default=True)` | NO | X | backend/app/models/market_data.py:535 |
| theme.first_seen_date | `mapped_column(Date)` | YES | X | backend/app/models/market_data.py:536 |
| theme.last_seen_date | `mapped_column(Date)` | YES | X | backend/app/models/market_data.py:537 |
| theme.updated_at | `mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())` | NO | T | backend/app/models/market_data.py:538 |
| theme_member_snapshot.snapshot_date | `mapped_column(Date)` | NO | X | backend/app/models/market_data.py:550 |
| theme_member_snapshot.theme_code | `mapped_column(ForeignKey('theme.theme_code'))` | NO | X | backend/app/models/market_data.py:551 |
| theme_member_snapshot.ts_code | `mapped_column(String(16))` | NO | X | backend/app/models/market_data.py:552 |
| theme_member_snapshot.stock_name | `mapped_column(String(64))` | YES | X | backend/app/models/market_data.py:553 |
| theme_member_snapshot.is_new | `mapped_column(Boolean)` | YES | X | backend/app/models/market_data.py:554 |
| theme_member_snapshot.source | `mapped_column(String(16), nullable=False)` | NO | X | backend/app/models/market_data.py:555 |
| theme_member_snapshot.created_at | `mapped_column(DateTime(timezone=True), server_default=func.now())` | NO | T | backend/app/models/market_data.py:556 |
| theme_member_interval.theme_code | `mapped_column(ForeignKey('theme.theme_code'))` | NO | X | backend/app/models/market_data.py:566 |
| theme_member_interval.ts_code | `mapped_column(String(16))` | NO | X | backend/app/models/market_data.py:567 |
| theme_member_interval.valid_from | `mapped_column(Date)` | NO | X | backend/app/models/market_data.py:568 |
| theme_member_interval.valid_to | `mapped_column(Date)` | YES | X | backend/app/models/market_data.py:569 |
| theme_member_interval.source | `mapped_column(String(16), nullable=False)` | NO | X | backend/app/models/market_data.py:570 |
| theme_member_interval.source_is_new | `mapped_column(Boolean)` | YES | X | backend/app/models/market_data.py:571 |
| theme_member_interval.quality_flag | `mapped_column(String(16), nullable=False)` | NO | X | backend/app/models/market_data.py:572 |
| theme_member_interval.created_at | `mapped_column(DateTime(timezone=True), server_default=func.now())` | NO | T | backend/app/models/market_data.py:573 |
| theme_member_interval.updated_at | `mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())` | NO | T | backend/app/models/market_data.py:574 |
| theme_daily.trade_date | `mapped_column(Date)` | NO | X | backend/app/models/market_data.py:586 |
| theme_daily.theme_code | `mapped_column(ForeignKey('theme.theme_code'))` | NO | X | backend/app/models/market_data.py:587 |
| theme_daily.open | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:588 |
| theme_daily.high | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:589 |
| theme_daily.low | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:590 |
| theme_daily.close | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:591 |
| theme_daily.pre_close | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:592 |
| theme_daily.avg_price | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:593 |
| theme_daily.change | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:594 |
| theme_daily.pct_change | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:595 |
| theme_daily.vol | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:596 |
| theme_daily.turnover_rate | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:597 |
| theme_daily.total_mv | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:598 |
| theme_daily.created_at | `mapped_column(DateTime(timezone=True), server_default=func.now())` | NO | T | backend/app/models/market_data.py:599 |
| theme_daily.updated_at | `mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())` | NO | T | backend/app/models/market_data.py:600 |
| theme_moneyflow_daily.trade_date | `mapped_column(Date)` | NO | X | backend/app/models/market_data.py:609 |
| theme_moneyflow_daily.theme_code | `mapped_column(ForeignKey('theme.theme_code'))` | NO | X | backend/app/models/market_data.py:610 |
| theme_moneyflow_daily.name | `mapped_column(String(128))` | YES | X | backend/app/models/market_data.py:611 |
| theme_moneyflow_daily.lead_stock | `mapped_column(String(64))` | YES | X | backend/app/models/market_data.py:612 |
| theme_moneyflow_daily.close_price | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:613 |
| theme_moneyflow_daily.pct_change | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:614 |
| theme_moneyflow_daily.theme_index | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:615 |
| theme_moneyflow_daily.company_num | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:616 |
| theme_moneyflow_daily.lead_stock_pct_change | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:617 |
| theme_moneyflow_daily.net_buy_amount | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:618 |
| theme_moneyflow_daily.net_sell_amount | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:619 |
| theme_moneyflow_daily.net_amount | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:620 |
| theme_moneyflow_daily.created_at | `mapped_column(DateTime(timezone=True), server_default=func.now())` | NO | T | backend/app/models/market_data.py:621 |
| theme_moneyflow_daily.updated_at | `mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())` | NO | T | backend/app/models/market_data.py:622 |
| theme_limit_daily.trade_date | `mapped_column(Date)` | NO | X | backend/app/models/market_data.py:631 |
| theme_limit_daily.theme_code | `mapped_column(ForeignKey('theme.theme_code'))` | NO | X | backend/app/models/market_data.py:632 |
| theme_limit_daily.name | `mapped_column(String(128))` | YES | X | backend/app/models/market_data.py:633 |
| theme_limit_daily.days | `mapped_column(Integer)` | YES | X | backend/app/models/market_data.py:634 |
| theme_limit_daily.up_stat | `mapped_column(String(64))` | YES | X | backend/app/models/market_data.py:635 |
| theme_limit_daily.cons_nums | `mapped_column(Integer)` | YES | X | backend/app/models/market_data.py:636 |
| theme_limit_daily.up_nums | `mapped_column(Integer)` | YES | X | backend/app/models/market_data.py:637 |
| theme_limit_daily.pct_chg | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:638 |
| theme_limit_daily.hot_rank | `mapped_column(Integer)` | YES | X | backend/app/models/market_data.py:639 |
| theme_limit_daily.created_at | `mapped_column(DateTime(timezone=True), server_default=func.now())` | NO | T | backend/app/models/market_data.py:640 |
| theme_limit_daily.updated_at | `mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())` | NO | T | backend/app/models/market_data.py:641 |
| theme_factor_daily.trade_date | `mapped_column(Date)` | NO | X | backend/app/models/market_data.py:653 |
| theme_factor_daily.theme_code | `mapped_column(ForeignKey('theme.theme_code'))` | NO | X | backend/app/models/market_data.py:654 |
| theme_factor_daily.member_snapshot_date | `mapped_column(Date)` | YES | X | backend/app/models/market_data.py:655 |
| theme_factor_daily.member_count | `mapped_column(Integer)` | YES | X | backend/app/models/market_data.py:656 |
| theme_factor_daily.eligible_member_count | `mapped_column(Integer)` | YES | X | backend/app/models/market_data.py:657 |
| theme_factor_daily.return1 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:658 |
| theme_factor_daily.return3 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:659 |
| theme_factor_daily.return5 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:660 |
| theme_factor_daily.return20 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:661 |
| theme_factor_daily.excess_return5 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:662 |
| theme_factor_daily.excess_return20 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:663 |
| theme_factor_daily.breadth20 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:664 |
| theme_factor_daily.breadth60 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:665 |
| theme_factor_daily.up_rate | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:666 |
| theme_factor_daily.new_high20_rate | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:667 |
| theme_factor_daily.rps60_median | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:668 |
| theme_factor_daily.turnover_rate | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:669 |
| theme_factor_daily.turnover_ratio20 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:670 |
| theme_factor_daily.net_amount | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:671 |
| theme_factor_daily.net_amount_3d | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:672 |
| theme_factor_daily.net_amount_per_member | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:673 |
| theme_factor_daily.moneyflow_score | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:674 |
| theme_factor_daily.limit_up_count | `mapped_column(Integer)` | YES | X | backend/app/models/market_data.py:675 |
| theme_factor_daily.limit_up_density | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:676 |
| theme_factor_daily.continuous_limit_count | `mapped_column(Integer)` | YES | X | backend/app/models/market_data.py:677 |
| theme_factor_daily.continuous_limit_density | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:678 |
| theme_factor_daily.hot_list_days | `mapped_column(Integer)` | YES | X | backend/app/models/market_data.py:679 |
| theme_factor_daily.hot_rank | `mapped_column(Integer)` | YES | X | backend/app/models/market_data.py:680 |
| theme_factor_daily.limit_strength_score | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:681 |
| theme_factor_daily.heat_score | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:682 |
| theme_factor_daily.heat_rank | `mapped_column(Integer)` | YES | X | backend/app/models/market_data.py:683 |
| theme_factor_daily.heat_momentum1 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:684 |
| theme_factor_daily.heat_momentum3 | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:685 |
| theme_factor_daily.rank_change | `mapped_column(Integer)` | YES | X | backend/app/models/market_data.py:686 |
| theme_factor_daily.lifecycle | `mapped_column(String(32))` | YES | X | backend/app/models/market_data.py:687 |
| theme_factor_daily.source_coverage | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:688 |
| theme_factor_daily.data_coverage | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:689 |
| theme_factor_daily.calc_version | `mapped_column(String(32), nullable=False)` | NO | X | backend/app/models/market_data.py:690 |
| theme_factor_daily.config_hash | `mapped_column(String(64), nullable=False)` | NO | X | backend/app/models/market_data.py:691 |
| theme_factor_daily.source_strategy_config_hash | `mapped_column(String(64), nullable=False)` | NO | X | backend/app/models/market_data.py:692 |
| theme_factor_daily.calc_run_id | `mapped_column(UUID(as_uuid=True), ForeignKey('job_run.id', ondelete='RESTRICT'), index=True)` | YES | U/R | backend/app/models/market_data.py:693 |
| theme_factor_daily.calculated_at | `mapped_column(DateTime(timezone=True), nullable=False)` | NO | T | backend/app/models/market_data.py:696 |
| stock_opportunity_daily.trade_date | `mapped_column(Date)` | NO | X | backend/app/models/market_data.py:711 |
| stock_opportunity_daily.ts_code | `mapped_column(String(16))` | NO | X | backend/app/models/market_data.py:712 |
| stock_opportunity_daily.algo_version | `mapped_column(String(32))` | NO | X | backend/app/models/market_data.py:713 |
| stock_opportunity_daily.state | `mapped_column(String(16), nullable=False)` | NO | X | backend/app/models/market_data.py:714 |
| stock_opportunity_daily.previous_state | `mapped_column(String(16))` | YES | X | backend/app/models/market_data.py:715 |
| stock_opportunity_daily.state_day_count | `mapped_column(Integer)` | YES | X | backend/app/models/market_data.py:716 |
| stock_opportunity_daily.left_reversal_score | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:717 |
| stock_opportunity_daily.left_reversal_new | `mapped_column(Boolean, nullable=False, default=False)` | NO | X | backend/app/models/market_data.py:718 |
| stock_opportunity_daily.right_side_score | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:719 |
| stock_opportunity_daily.trend_score | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:720 |
| stock_opportunity_daily.trend_rank_score | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:721 |
| stock_opportunity_daily.position_score | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:722 |
| stock_opportunity_daily.extension_risk | `mapped_column(String(16))` | YES | X | backend/app/models/market_data.py:723 |
| stock_opportunity_daily.market_score | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:724 |
| stock_opportunity_daily.industry_sector_id | `mapped_column(Integer)` | YES | X/R | backend/app/models/market_data.py:725 |
| stock_opportunity_daily.industry_heat | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:726 |
| stock_opportunity_daily.industry_lifecycle | `mapped_column(String(32))` | YES | X | backend/app/models/market_data.py:727 |
| stock_opportunity_daily.primary_theme_code | `mapped_column(String(32))` | YES | X/R | backend/app/models/market_data.py:728 |
| stock_opportunity_daily.primary_theme_name | `mapped_column(String(128))` | YES | X | backend/app/models/market_data.py:729 |
| stock_opportunity_daily.primary_theme_heat | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:730 |
| stock_opportunity_daily.primary_theme_lifecycle | `mapped_column(String(32))` | YES | X | backend/app/models/market_data.py:731 |
| stock_opportunity_daily.hot_theme_count | `mapped_column(Integer)` | YES | X | backend/app/models/market_data.py:732 |
| stock_opportunity_daily.context_score | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:733 |
| stock_opportunity_daily.opportunity_stage | `mapped_column(String(32), nullable=False)` | NO | X | backend/app/models/market_data.py:734 |
| stock_opportunity_daily.opportunity_score | `mapped_column(Float)` | YES | X | backend/app/models/market_data.py:735 |
| stock_opportunity_daily.reason_codes | `mapped_column(JSONB)` | YES | J | backend/app/models/market_data.py:736 |
| stock_opportunity_daily.calc_version | `mapped_column(String(32), nullable=False)` | NO | X | backend/app/models/market_data.py:737 |
| stock_opportunity_daily.config_hash | `mapped_column(String(64), nullable=False)` | NO | X | backend/app/models/market_data.py:738 |
| stock_opportunity_daily.source_strategy_config_hash | `mapped_column(String(64), nullable=False)` | NO | X | backend/app/models/market_data.py:739 |
| stock_opportunity_daily.calc_run_id | `mapped_column(UUID(as_uuid=True), ForeignKey('job_run.id', ondelete='RESTRICT'), index=True)` | YES | U/R | backend/app/models/market_data.py:740 |
| stock_opportunity_daily.calculated_at | `mapped_column(DateTime(timezone=True), nullable=False)` | NO | T | backend/app/models/market_data.py:743 |
| job_run.id | `mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)` | NO | U/R | backend/app/models/job.py:39 |
| job_run.job_type | `mapped_column(String(64), nullable=False)` | NO | X | backend/app/models/job.py:40 |
| job_run.target_trade_date | `mapped_column(Date)` | YES | X | backend/app/models/job.py:41 |
| job_run.started_at | `mapped_column(DateTime(timezone=True), server_default=func.now())` | NO | T | backend/app/models/job.py:42 |
| job_run.heartbeat_at | `mapped_column(DateTime(timezone=True))` | YES | T | backend/app/models/job.py:43 |
| job_run.worker_id | `mapped_column(String(128))` | YES | X | backend/app/models/job.py:44 |
| job_run.finished_at | `mapped_column(DateTime(timezone=True))` | YES | T | backend/app/models/job.py:45 |
| job_run.status | `mapped_column(String(16), nullable=False, default='RUNNING')` | NO | X | backend/app/models/job.py:46 |
| job_run.step | `mapped_column(String(64))` | YES | X | backend/app/models/job.py:47 |
| job_run.row_count | `mapped_column(Integer, nullable=False, default=0)` | NO | X | backend/app/models/job.py:48 |
| job_run.error_message | `mapped_column(String(2048))` | YES | X | backend/app/models/job.py:49 |
| job_run.cancel_requested | `mapped_column(Boolean, nullable=False, default=False)` | NO | X | backend/app/models/job.py:50 |
| job_run.execution_started_at | `mapped_column(DateTime(timezone=True))` | YES | T | backend/app/models/job.py:51 |
| job_run.cancel_requested_at | `mapped_column(DateTime(timezone=True))` | YES | T | backend/app/models/job.py:52 |
| job_run.last_progress_at | `mapped_column(DateTime(timezone=True))` | YES | T | backend/app/models/job.py:53 |
| job_run.execution_token | `mapped_column(UUID(as_uuid=True))` | YES | U/R | backend/app/models/job.py:54 |
| job_run.request_fingerprint | `mapped_column(String(128))` | YES | X | backend/app/models/job.py:55 |
| job_run.depends_on_job_id | `mapped_column(UUID(as_uuid=True), ForeignKey('job_run.id', ondelete='RESTRICT'))` | YES | U/R | backend/app/models/job.py:56 |
| job_run.parent_job_id | `mapped_column(UUID(as_uuid=True), ForeignKey('job_run.id', ondelete='RESTRICT'))` | YES | U/R | backend/app/models/job.py:59 |
| job_run.job_metadata | `mapped_column(JSONB, nullable=False, default=dict)` | NO | M | backend/app/models/job.py:62 |
| provider_api_log.id | `mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)` | NO | U/R | backend/app/models/job.py:71 |
| provider_api_log.provider | `mapped_column(String(32), nullable=False)` | NO | X | backend/app/models/job.py:72 |
| provider_api_log.api_name | `mapped_column(String(64), nullable=False)` | NO | X | backend/app/models/job.py:73 |
| provider_api_log.trade_date | `mapped_column(Date)` | YES | X | backend/app/models/job.py:74 |
| provider_api_log.elapsed_ms | `mapped_column(Integer)` | YES | X | backend/app/models/job.py:75 |
| provider_api_log.row_count | `mapped_column(Integer)` | YES | X | backend/app/models/job.py:76 |
| provider_api_log.status | `mapped_column(String(16), nullable=False)` | NO | X | backend/app/models/job.py:77 |
| provider_api_log.error_type | `mapped_column(String(128))` | YES | X | backend/app/models/job.py:78 |
| provider_api_log.created_at | `mapped_column(DateTime(timezone=True), server_default=func.now())` | NO | T | backend/app/models/job.py:79 |
| service_heartbeat.id | `mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)` | NO | U/R | backend/app/models/job.py:89 |
| service_heartbeat.service_name | `mapped_column(String(32), nullable=False)` | NO | X | backend/app/models/job.py:90 |
| service_heartbeat.instance_id | `mapped_column(String(160), nullable=False)` | NO | X | backend/app/models/job.py:91 |
| service_heartbeat.started_at | `mapped_column(DateTime(timezone=True), nullable=False)` | NO | T | backend/app/models/job.py:92 |
| service_heartbeat.heartbeat_at | `mapped_column(DateTime(timezone=True), nullable=False)` | NO | T | backend/app/models/job.py:93 |
| service_heartbeat.version | `mapped_column(String(32), nullable=False)` | NO | X | backend/app/models/job.py:94 |
| service_heartbeat.status | `mapped_column(String(16), nullable=False, default='UP')` | NO | X | backend/app/models/job.py:95 |
| service_heartbeat.service_metadata | `mapped_column(JSONB, nullable=False, default=dict)` | NO | J | backend/app/models/job.py:96 |
| data_publication.job_id | `mapped_column(UUID(as_uuid=True), ForeignKey('job_run.id', ondelete='RESTRICT'), primary_key=True)` | NO | U/R | backend/app/models/data_publication.py:30 |
| data_publication.execution_token | `mapped_column(UUID(as_uuid=True), nullable=False)` | NO | U/R | backend/app/models/data_publication.py:33 |
| data_publication.state | `mapped_column(String(16), nullable=False, default='PREPARING')` | NO | X | backend/app/models/data_publication.py:34 |
| data_publication.identity | `mapped_column(JSONB, nullable=False)` | NO | J | backend/app/models/data_publication.py:35 |
| data_publication.created_at | `mapped_column(DateTime(timezone=True), server_default=func.now())` | NO | T | backend/app/models/data_publication.py:36 |
| data_publication.publish_started_at | `mapped_column(DateTime(timezone=True))` | YES | T | backend/app/models/data_publication.py:37 |
| data_publication.published_at | `mapped_column(DateTime(timezone=True))` | YES | T | backend/app/models/data_publication.py:38 |
| data_publication.row_counts | `mapped_column(JSONB, nullable=False, default=dict)` | NO | J | backend/app/models/data_publication.py:39 |
| data_publication_source.publication_id | `mapped_column(UUID(as_uuid=True), ForeignKey('data_publication.job_id', ondelete='RESTRICT'), primary_key=True)` | NO | U/R | backend/app/models/data_publication.py:46 |
| data_publication_source.source_job_id | `mapped_column(UUID(as_uuid=True), ForeignKey('job_run.id', ondelete='RESTRICT'), primary_key=True)` | NO | U/R | backend/app/models/data_publication.py:51 |
| data_publication_source.role | `mapped_column(String(16), nullable=False)` | NO | X | backend/app/models/data_publication.py:54 |
| data_publication_source.validated_at | `mapped_column(DateTime(timezone=True))` | YES | T | backend/app/models/data_publication.py:55 |
| data_publication_source.validation | `mapped_column(JSONB)` | YES | J/R | backend/app/models/data_publication.py:56 |
| data_publication_row.publication_id | `mapped_column(UUID(as_uuid=True), ForeignKey('data_publication.job_id', ondelete='RESTRICT'), primary_key=True)` | NO | U/R | backend/app/models/data_publication.py:72 |
| data_publication_row.table_name | `mapped_column(String(64), primary_key=True)` | NO | X | backend/app/models/data_publication.py:77 |
| data_publication_row.row_key | `mapped_column(RowKeyJSON(), primary_key=True)` | NO | J/R | backend/app/models/data_publication.py:78 |
| data_publication_row.row_data | `mapped_column(JSONB(none_as_null=True))` | YES | J/R | backend/app/models/data_publication.py:79 |
| data_publication_row.base_row | `mapped_column(JSONB(none_as_null=True))` | YES | J/R | backend/app/models/data_publication.py:80 |
| data_publication_row.source_id | `mapped_column(UUID(as_uuid=True), nullable=False)` | NO | U/R | backend/app/models/data_publication.py:81 |
| data_publication_row.is_deleted | `mapped_column(Boolean, nullable=False)` | NO | X | backend/app/models/data_publication.py:82 |
| data_publication_row.trade_date | `mapped_column(Date)` | YES | X | backend/app/models/data_publication.py:83 |
| data_publication_row.entity_key | `mapped_column(String(64))` | YES | X | backend/app/models/data_publication.py:84 |
| data_publication_preimage.publication_id | `mapped_column(UUID(as_uuid=True), ForeignKey('data_publication.job_id', ondelete='RESTRICT'), primary_key=True)` | NO | U/R | backend/app/models/data_publication.py:90 |
| data_publication_preimage.table_name | `mapped_column(String(64), primary_key=True)` | NO | X | backend/app/models/data_publication.py:95 |
| data_publication_preimage.row_key | `mapped_column(RowKeyJSON(), primary_key=True)` | NO | J/R | backend/app/models/data_publication.py:96 |
| data_publication_preimage.row_data | `mapped_column(JSONB, nullable=False)` | NO | J/R | backend/app/models/data_publication.py:97 |
| data_publication_scope.id | `mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)` | NO | U/R | backend/app/models/data_publication.py:104 |
| data_publication_scope.publication_id | `mapped_column(UUID(as_uuid=True), ForeignKey('data_publication.job_id', ondelete='RESTRICT'))` | NO | U/R | backend/app/models/data_publication.py:105 |
| data_publication_scope.table_name | `mapped_column(String(64), nullable=False)` | NO | X | backend/app/models/data_publication.py:108 |
| data_publication_scope.source_id | `mapped_column(UUID(as_uuid=True), nullable=False)` | NO | U/R | backend/app/models/data_publication.py:109 |
| data_publication_scope.start_date | `mapped_column(Date)` | YES | X | backend/app/models/data_publication.py:110 |
| data_publication_scope.end_date | `mapped_column(Date)` | YES | X | backend/app/models/data_publication.py:111 |
| data_schedule_intent.identity_key | `mapped_column(String(64), primary_key=True)` | NO | X | backend/app/models/data_schedule.py:20 |
| data_schedule_intent.kind | `mapped_column(String(32), nullable=False)` | NO | X | backend/app/models/data_schedule.py:21 |
| data_schedule_intent.target_date | `mapped_column(Date, nullable=False)` | NO | X | backend/app/models/data_schedule.py:22 |
| data_schedule_intent.identity | `mapped_column(JSONB, nullable=False)` | NO | J | backend/app/models/data_schedule.py:23 |
| data_schedule_intent.state | `mapped_column(String(32), nullable=False)` | NO | X | backend/app/models/data_schedule.py:24 |
| data_schedule_intent.job_id | `mapped_column(PGUUID(as_uuid=True), ForeignKey('job_run.id', ondelete='RESTRICT'))` | YES | U/R | backend/app/models/data_schedule.py:25 |
| data_schedule_intent.attempts | `mapped_column(Integer, nullable=False, default=0)` | NO | X | backend/app/models/data_schedule.py:28 |
| data_schedule_intent.error_code | `mapped_column(String(80))` | YES | X | backend/app/models/data_schedule.py:29 |
| data_schedule_intent.queue_count | `mapped_column(Integer)` | YES | X | backend/app/models/data_schedule.py:30 |
| data_schedule_intent.next_attempt_at | `mapped_column(DateTime(timezone=True), nullable=False)` | NO | T | backend/app/models/data_schedule.py:31 |
| data_schedule_intent.created_at | `mapped_column(DateTime(timezone=True), server_default=func.now())` | NO | T | backend/app/models/data_schedule.py:32 |
| data_schedule_intent.updated_at | `mapped_column(DateTime(timezone=True), server_default=func.now())` | NO | T | backend/app/models/data_schedule.py:33 |
| alembic_version.version_num | migration revision string | NO | X | Alembic metadata（非业务ORM类） |
