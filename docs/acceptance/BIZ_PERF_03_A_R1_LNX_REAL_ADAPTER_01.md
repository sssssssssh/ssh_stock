# P0_LNX_REAL_ADAPTER_01_DELIVERY_REPORT

2026-11-09，Asia/Shanghai。P0-LNX-REAL-ADAPTER-01 V1.0，W00～W06离线源码交付。
**OFFLINE_ADAPTER_AND_COMPARATOR_IMPLEMENTED / LOCAL_TESTS_PASS / CODE_REVIEW_PENDING**。
真实实验 **NO_GO**；R1与历史AC05保持PARTIAL，Windows原生根因UNKNOWN。

## 1. 基线、原件和授权

baseline_master_sha / local_head / origin_master / remote_master均为
`b6ffb7bf8ec7d26f771d9b89923e4f7e926edbed`，master；实时远端原始核对见仓库外git-remote.log。
开始tracked/staged为空，仅六个历史untracked；结束tracked/staged仍为空，只新增白名单12文件，合计18个untracked。
全部既存tracked文件与开始时保存的原字节摘要一致。无分支切换、覆盖拉取、reset、clean、git add、commit或push。
治理旧G0/04-E/CI-OPT执行指针保留历史语境，以本轮明确授权为范围，不改治理制造放行。
六份旧原件摘要前后相同，详见附录；没有覆盖、重排、清理或提交它们。

| 来源等级 | 核查及适用边界 |
| --- | --- |
| GIT_SOURCE_REVIEWED | AGENTS、五治理及相关PRD/设计/规则/README；R1 plan/closeout、W01/W02、04-D/E、BIZ-PERF-01/02边界；18个固定实现来源见附录 |
| LOCAL_UNTRACKED_SELF_REPORTED | W03/W04/W04-A六原件，不冒充已提交Git源或独立批准 |
| HISTORY_VERIFIED | 04-D历史3.12.14/67包、04-E完整性和W02工程事实，不继承未来新目标资格；本轮未重跑 |
| OFFLINE_CONTRACT_TESTED | 本轮新模块的fake调用、状态机、类型比较与配方验证 |
| UNVERIFIED | 真实Linux、PG身份、Root、持久ACK、真实回收及性能/容量 |

BIZ-PERF-01小样本32.8%/31.3%/21.8%不等于百万行验收；优化开关仍false。
BIZ-PERF-02的一月整链退化5.34%及候选撤回不变。Windows原R1 OFF 0xC0000005根因UNKNOWN；
旧三对+5.6501%不合格，当前版本无有效三对，≤3%仍NOT_VERIFIED。工程CI不替代这些结论。

## 2. 实际源码实现

| 文件/接口 | 实际行为 |
| --- | --- |
| r1_real_root_protocol.py | 固定R1请求、来源摘要集合、外部ref、flags、预算、严格JSON/字段/错误码；OwnerAuthority接口及有限状态迁移 |
| r1_real_root_adapter.py::execute_one_r1_root | 验证→owner一次reservation→fake freeze/session→create→claim→refresh核worker/token/data_claim→execute→expire/observe；不commit/重试，保留首错与原终态 |
| r1_real_root_supervisor.py::Supervisor | start_once/tick父算法，意图先于spawn；句柄、host/PG/domain/PID/PGID/SID/creation与独立owner事实绑定；绝对期限、TERM/KILL、分离的退出/冻结/回收/ACK检查及单对下一臂限制 |
| r1_business_snapshot_contract.py::compare_snapshots | 37表全列、强类型、排序/主键/多重集、UUID/事件双射、FK/JSON/候选/public/Scope闭包；分层摘要和有界脱敏错误 |
| r1_seed_snapshot_recipe.py | 原Seed确定性取值、49时间源、完整类型行/空边界表、序列/无随机调用状态、两种配方及独立加载消费者验证 |
| r1_business_compare_schema_v1.json | 恰好37表520列，源位置/声明/类型/可空、PK/自然键/FK/语义引用、逐列政策、JSON有限路径/观测角色/版本/预算 |

已核实际签名：create_recalculation_job(db,*,start,end,evaluate_signals,mode,dirty_ranges=None,job_id=None)；
claim_next_job(db,worker_id)；execute_claimed_job(db,job_id,*,expected_worker=None,expected_token=None)。
create_queued_ingestion_job的新建/去重分别设置_queue_deduplicated=false/true，Adapter拒绝旧根。
claim提交worker/token并写Session.info.data_claim，Adapter refresh后核验；不虚构数据库方法。
_update_owned_data_job保持原worker/token/状态CAS及finish_publication同事务提交；Adapter不写Job、
不接管心跳/ContextVar/PublicationWorkspace、不伪造发布、不补跑未知事务。MODELS十表和KEYS三项自然键覆写已承接。

root_adapter_calls_real_api_in_source=YES，仅指BusinessFacade中三个真实签名的晚导入及调用；
root_adapter_executed_on_real_db=NO。每个BusinessFacade方法首先执行无条件拒绝的real_execution_bridge。
生产freeze/Session/Settings/worker_source/导出器尚未接线，不能通过authorized:true、hash或ref打开。
CLI总是先拒绝，无自由命令、DSN、模块、PID入口；fake接口不是不可信Python代码的沙箱。
Adapter向注入recorder交付阶段事件；监督阶段的单调时刻保存在StateMachine.events，无真实阶段耗时或文件持久化记录器。

### 2.1 期限及不可证明项

外层t0为Supervisor构造的fake单调时刻。setup=t0+180；ROOT_STARTED时root=min(root_start+180,t0+360)；
首次cleanup_request时cleanup=min(cleanup_start+30,t0+390)。390是180+180+30包络，
不是03-B的420/60秒，也没有额外归档预算。heartbeat、日志、失败或阶段切换不续期。
poll/退出/回执返回迟到时重新采钟；TERM后5秒才能KILL，仍在原30秒内。

只存在fake Process/Clock/Owner/Receipt接线，固定spawn模板shell=false、新session、最小环境，real_spawn=DISABLED。
新模块没有subprocess、信号、扫描或真实PG实现；缺句柄不表示确定未创建，保守SPAWN_UNCERTAIN。
owner/归属/清理未知为CLEANUP_UNCERTAIN/FENCING_PENDING；不生成下一臂、无自动重试。
summary.complete恒false，仅offline_model_complete可在完整假证据下true。
FIRST_SPAWN、WATCHDOG_SYSCALLS、UNINTERRUPTIBLE_D_STATE、DURABLE_TRUST、REAL_RECLAMATION均NOT_PROVEN。
返回迟到的故障模型不证明能抢占永久阻塞系统调用；真实OS/持久确认仍须另批。

### 2.2 比较范围和算法

37/520与W04附录的(table,column,path,line)逐项一致，排除三个继承Research模型，不随意凑全仓40表。
alembic_version.version_num是另列迁移哨兵，不计520。每列有唯一政策和原声明，未使用全局忽略政策。
None/bool/int/Decimal及scale/有限float的hex/date/UTC-aware datetime/UUID/bytes/Unicode/JSON/tuple保留类型；
NaN/Inf/naive/非UTC偏移拒绝，不用default=str或epsilon。候选JSONB的UUID/date字符串须由未来受审导出器按列恢复原生类型。

有序流逐行摘要，无序批次≤10000行/表，按行检查字节预算后才缓冲并排序；排序是类型规范字节，
不宣称等同PG collation。每表stream最多2000000行；单行规范包≤262144B；每臂原始+规范编码累计64MiB；
身份/引用及public摘要索引20000项，关键ledger/scope10000行。超限INCOMPLETE，无外部spill实现，
不声称百万行/容量或峰值RSS已测；64MiB是逻辑编码字节预算，不是OS RSS硬上限。

Job/token/Scope分域双射；当前手动R1只接受一个root、无parent/dependency，所有Job复制引用闭合到该root。
不虚构generation实体、不忽略serial ID。Scope tuple未声明唯一，按tuple分组、原UUID顺序对应ordinal，
双射须与排序一致并精确保留重复次数；不在原件中映射ID。动态时间只对schema逐列批准项映射；
目前采用保持跨列复制等值与次序的全局事件双射，比独立逐列映射更保守。真实时间分辨率一对多时拒绝，
需另审事件导出；业务日期/PIT/版本/hash始终精确。Raw质量job_id=null时间精确，Root质量进入输出分区。

候选row_data按目标全列重入、row_key按真实KEYS；成功候选须与public摘要/删除状态一致且有Scope覆盖。
FK、source、原像字段和NULL保持；只有SUCCESS/PUBLISHED、FAILED/ABORTED、CANCELLED/ABORTED关系可合法离线匹配，
UNKNOWN_ACK拒绝。metadata仅有限路径；queue_identity与ledger一致，复制UUID复用原映射。
calculation_execution核来源/flags/请求/计数角色；只对明确seconds等观测值另行摘要，不豁免金融字段。
session指纹/application_name从本臂root/token/固定worker重算，并核显式合成PG资源绑定；
heartbeat必须通信确认、无失败，证明布尔不可自升true。未知JSON/角色、degraded或来源漂移拒绝。
错误最多一项：固定码、schema内table/column、16位角色键摘要；流的自由异常文本不回显。

Golden是37表各一行的人工schema练习，覆盖全部列，**不是原R1 Seed或真实合法业务库状态**。
另有独立的420日/weekday/两证券/退市边界完整输入配方测试；不以人工Golden冒充实库结果。
输入/输出/观测摘要和原始类型行摘要分开保存，比较不修改输入；这些不是原始PG dump或真实输入证明。

### 2.3 Seed

原两股、420日、2026-02-23～24/manual/false信号、250交易日预热、430自然日回看及退市边界固定。
原Seed的12个输入表及六个题材空边界表显式保留。五个Seed默认时间列保留UTC微秒向量和原始hash；
49时间源区别SEED_INPUT/ROOT_RUNTIME/EVIDENCE，不覆盖now()或修改原seed。
共同快照方案比较两份独立loader ref的全部manifest/行数/类型/原始hash/序列；
逐列方案保留两臂原始表hash和时间向量，非时间hash、类型与序列不变，实际向量须满足双射。
Sector显式插入101不表示序列已推进101；ID/序列不丢弃。原seed没有随机函数调用，状态显式登记。
owner_selection=NOT_SELECTED，decision=DECISION_REQUIRED，G05=MISSING/G08=PARTIAL；没有装载、SQL或真实输入资格。

## 3. RED→GREEN和最终检查

复用仓库外隔离venv：Windows win32、CPython3.12.0、pytest9.1.1、pluggy1.7.0、pytest-cov7.1.0、Ruff0.16.4，
user-site=false。本轮未安装依赖。原pyproject默认source_contract_pytest和pytest_cov均由trace-config确认加载，
无-p no、覆盖addopts、skip/xfail、降低断言/容差。完整argv、真实解释器路径、cwd、起止UTC、退出码及日志摘要
保存在仓库外命令JSON；本文件用<isolated-venv>缩写，避免把本机绝对路径写入仓库。

| 证据 | 实际结果 |
| --- | --- |
| 初轮RED | 56顶层节点；终端8 failed、51 passed、1245 subtests passed，100.67s/exit1；失败数包含三个生命周期subtest，不能相加当唯一节点数。原像误用candidate source、SQL count漏列、AST误将类文档字符串当函数 |
| 去重RED | first_error意外None；1 failed、1 passed、4 subtests passed/exit1，同一顶层节点含subtest，不算两个独立AC |
| 缓冲RED | 预算耗尽前消费10行，断言只应[0]；1 failed/exit1 |
| 修复 | 只改新增模块/测试：区分原像、承接实际SQL计数、AST只审函数、拒绝去重旧根、预算检查前移；保留负例及全部旧断言 |
| 定位子集 | 36 passed、2 deselected、40 subtests passed，12.04s；不是完整验收 |
| 最终完整pytest | **62 passed、1249 subtests passed，156.99s，exit0；0失败/错误/跳过** |
| 新unittest | **42 tests OK，149.027s，exit0** |
| 原W04-A unittest | **20 tests OK，2.501s，exit0** |
| Ruff / py_compile | 10个新Python文件全部通过，exit0；pyc定向仓库外 |

62顶层中新增42/1081 subtests，旧W04-A仍20/168 subtests；520列各missing与wrong_type两负例共1040子断言。
动态身份也做类型破坏，另有合法错值/错域/孤儿/复制/候选/public/Scope/session专项。
Golden正例、三种终态与负例在同一最终套件通过，不依赖提前错误刷绿。历次61/62通过、pytest/unittest、
顶层/subtest均不累加为规模。最终前仅加强一次性Owner跨臂/跨pair负例，原子集和旧原件未改。
开发Ruff发现16项，7项安全自动修复，9项显式修复，无配置变更。一次patch上下文不符未写入，核对后重施。
报告生成脚本曾有引号嵌套SyntaxError，未写文件，也不是业务/测试失败；改用直接文档写入，未影响GREEN源码。

最终命令逻辑（完整实路径argv见仓库外JSON）：

```text
<isolated-venv>/python -X utf8 -B -m pytest <五份新test_r1文件> tests/unit/test_perf03_lnx_w04a_offline_contract.py -v --tb=long --trace-config --junitxml=<external> --basetemp=<external> -o cache_dir=<external>
<isolated-venv>/python -X utf8 -B -m unittest discover -s tests/unit -p test_r1_*.py -v
<isolated-venv>/python -X utf8 -B -m unittest discover -s tests/unit -p test_perf03_lnx_w04a_offline_contract.py -v
<isolated-venv>/python -m ruff check <五份新模块及五份新test_r1文件>
<isolated-venv>/python -B -c <py_compile各新文件，cfile指定external/compiled>
git diff --check
```

缓存均在仓库外；没有全量后端/集成pytest、迁移或Main CI，不冒充完整工程回归。
测试runner启动Python验证命令，不表示被测模块启动业务子进程；Process/Session/Owner全部为fake。

## 4. 门禁、未完成项及后续授权

| Gate | 状态 | 剩余项 |
| --- | --- | --- |
| G01 | NOT_AUTHORIZED | 真实单对许可 |
| G02 | MISSING | 独占Linux资源/owner租约实证 |
| G03 | PARTIAL | 目标3.12.14/67包/ABI实证，不能借历史安装 |
| G04 | MISSING | PG17物理身份、权限、创建/回收ACK |
| G05 | MISSING | Seed方案负责人裁决、真实实体输入 |
| G06 | PARTIAL | 离线编排实现，生产Facade/可信桥接仍关闭 |
| G07 | NOT_PROVEN | 首次spawn、监督自身阻塞、D状态和fencing |
| G08 | PARTIAL | 真实OFF/ON输入及资源身份 |
| G09 | PARTIAL | 37/520离线通过，真实导出/完整运行时JSON及结果未验 |
| G10 | NOT_PROVEN | 独立持久确认、真实回收 |
| G11 | PARTIAL | 无本轮最终提交同SHA普通CI |
| G12 | PARTIAL | 实机销毁/租约/异常收尾 |

当前无未修复的新测试失败、UNMAPPED_COLUMNS或源码漂移。生产授权桥接、记录器、只读导出接线和真实物理验证
仍未实现/未执行；严格未知JSON、事件歧义和索引超限仍可能拒绝真实数据，不能临场扩白名单或补样。
保守全局时间双射的真实可行性、OS硬期限、持久信任、百万行容量均未证明；这些限制不被42个假对象测试关闭。

下一步仅为ChatGPT独立源码审阅。后续至少另批：VM/预算/配额/责任人；目标Linux及3.12.14/67包；
PG17 marker/system_identifier/最小权限/创建与销毁归属；Seed冻结方案和业务影响；真实两臂实体输入hash；
持久owner桥接与外层fencing残余风险；生产Facade/记录器/类型导出接线和比较器审阅；最终代码同SHA普通CI；
然后负责人单独明确批准恰好一次OFF1→ON1。缺一项仍NO_GO，不自动扩三对、容量、优化或部署。
回滚方式仅指未来获批后删除本轮明确新增12文件；本轮不自行删除或回退，旧原件和其他用户文件保留。

## 5. 固定回执字段

```text
baseline_master_sha = local_head = origin_master = remote_master = b6ffb7bf8ec7d26f771d9b89923e4f7e926edbed
worktree_before = tracked/staged EMPTY; original six untracked
worktree_after = tracked/staged EMPTY; original six + task twelve untracked
original_six_sha256_before_after = 附录；全部相同
new_files_and_sha256 = 附录十一文件 + 最终聊天/外部完整十二文件清单（报告自身避免自引用）
source_review_count = 18 pinned artifacts; runtime source digest binds 379 Git texts
root_adapter_calls_real_api_in_source = YES (static sealed binding)
root_adapter_executed_on_real_db = NO
fake_root_positive_negative_cases = AC04/07/08/09/10/11/30
process_supervisor_real_os_test = NO
supervisor_offline_fault_cases = AC12–17 + late poll/receipt
compare_schema_tables / columns = 37 / 520
column_policy_coverage / tamper_coverage = 520/520; 1040 missing/type subassertions
identity_closure_negative_cases = AC23/24/25 + candidate/public/scope/session/fingerprint/unknown JSON
seed_recipe_selected_by_owner = NOT_SELECTED
W04A_previous_20_pytest_and_168_subtests_status = PASS; original six unchanged
new_pytest = 42/1081 PASS; combined with old = 62/1249 PASS
unit_tests = new42 PASS + old20 PASS (separate runs)
ruff / py_compile / diff = PASS / PASS / PASS; exit_codes = 0
pg_connections=0 / real_worker_roots=0 / off_on_pairs=0 / capacity=0
vm_created=0 / containers_created=0 / actions_dispatches=0 / deploys=0
commit=NOT_COMMITTED / push=NOT_PUSHED / new_ci=NOT_TRIGGERED
G01_G12_status = 第4节，未升级真实GO
R1=PARTIAL / AC05=PARTIAL / experiment=NO_GO
remaining_blockers = 真实环境/PG/Seed裁决/可信监督ACK/生产接线/导出/同SHA CI/单对许可
recommended_next_action = ChatGPT independent source review
```

## 附录：可复核索引、每列覆盖及摘要

以下索引由实际文件/最终JUnit生成；仓库外完整命令、RED/GREEN日志、JUnit及column_coverage.json保留。
new-files.diff为白名单12文件对空文件的完整新增内容，不能以空git diff代替。
报告自身SHA在最终聊天和外部new-files-sha256.json给出，避免自引用循环。

### A. 六原件前后摘要

| 原件 | before = after SHA256 |
| --- | --- |
| `docs/acceptance/BIZ_PERF_03_A_R1_LNX_W03_PREFLIGHT.md` | `21e9f0acc048d1724be985b13667a2cd71572992096abea9d8fbd57699455c9d` |
| `docs/acceptance/BIZ_PERF_03_A_R1_LNX_W04_READINESS.md` | `09ac6d54828cdc085e134c5a54f91e3a1efa8933d42dea1e9bc7ae3967370f0d` |
| `docs/acceptance/biz_perf_03_a_r1_lnx_w04a_contract.json` | `0f464a6acc4efc651fdea798fac1b0b4b3b61069147515115afa5b9f2d91d2f8` |
| `scripts/perf03_lnx_w04a_offline_contract.py` | `b11a4a2b8e6da6224ab8c503130073bef5ace9ec701dbf43649e116c0be6c5a0` |
| `tests/unit/test_perf03_lnx_w04a_offline_contract.py` | `f3232a88f0be68ca710ffba337e8dcfae9fa096d54a681ee8dc2eb760efce2ef` |
| `docs/acceptance/BIZ_PERF_03_A_R1_LNX_W04A.md` | `25bffe509c2f78473221bbb39c61bac95eec6db5e0930828205072ea46e66b20` |

### B. 固定源码证据

全部精确函数签名/起止行段见schema.sources.functions与外部source-index.json。

| 文件 | Git blob SHA | Git原件SHA256 |
| --- | --- | --- |
| `backend/app/models/market_data.py` | `56ea835f28e289dc165717639b20bcecf3015e61` | `c0207d196fb9777bfd5c83284ca9d36f5b2cbf9ea5191ca149fbce9afcee9261` |
| `backend/app/models/job.py` | `36918fcb92d34d430dcc2a7f359c2fbdb49ebf7e` | `fc795d1d4fb92ff3b8a10d41e19898e392e236ca84c661e78dfa2b02519ecc11` |
| `backend/app/models/data_publication.py` | `36eca6f02b6173ec136487554b69a88235db73a9` | `c9163a6e8386404d3b9faf9eaa1bf064d4a476b986e8fcc452ba9ce382aca63c` |
| `backend/app/models/data_schedule.py` | `6722f487ec11726673706837ffa5c7216e1a7bf9` | `1c02583b6d8b455be81a3fc7f34c7aa93c167a6e516395e6688c24939fdf48c2` |
| `backend/app/services/recalculation.py` | `ed7d51e0e63a26e461fa59fab42c555c3c081c82` | `ac3d9625079277b0e4031f3b1b43a167905230458cf1958e3b1862564c76ae4c` |
| `backend/app/services/job_worker.py` | `48e6706d1178d566eeb7a9a05317005d018e9390` | `91069dd58733e442831977f58ee1c37616d1ef37a271d7845856421251d6e7da` |
| `backend/app/repositories/job_run.py` | `c28ff517b8876397ecb62cc63b5ab39f295aa14e` | `599f7275f5e58d96bc25c1a8a343389e96326fd976be48b45002f04ed6381624` |
| `backend/app/services/data_publication.py` | `fcad174573ce76d957a9ad239f85b9a990d30fa0` | `39d95b00afed3da308aa78a00917fad2308f9d19266cfa30268b145bd35e7e88` |
| `scripts/v14_test_database.py` | `3abec2e278a62a8f1fc98e79c53d496625b09967` | `5a7edc5707b5b21a97e711d043dbcff082739699376be88955f74c6c3625f1ca` |
| `scripts/performance_diagnostics_overhead.py` | `4fa0cd55810dd851a5a8942d3625a748a18c6262` | `98dbd99f94f2c784ca862bbadce43228350d72aca4f36ac4eca9110c9e763693` |
| `tests/integration/test_business_recalc_performance.py` | `3e6be63279a8f944f075fac0637a50c953c86632` | `c6cc8cf4145d3dbefd259417e08c06ac7470a39adeca654ce9fe2f5483f2ba27` |
| `backend/app/services/calculation_policy.py` | `73b666d675c3a739a68c7848d89da1b5cdc2d732` | `11801e7198f3cb41a008f38abc99f39cb66f178c70f1bff0a628a6574ba27ab0` |
| `backend/app/core/config.py` | `a109faf8dbca88bf4213ccb1af453b70902bfda5` | `e182f18f8e1f00fac17c25b836210a459b0cd66083c747d82a59fbcc7fc6fcf7` |
| `config/strategy.yaml` | `2d4fe1ea25feb05a508161ff87409e70e48a3817` | `2ac50c63f3b522ae84e97dad2c9eb2eabd2206c224cea25f83d8d049e7d2864b` |
| `requirements-biz-perf-linux-py312-v1.lock` | `121cb63ee81bdbb61ffb1070ef627dcfbce4562c` | `88549dce3164364430e20970fa10eb2125b60ff05f456d7bef4474876a98dcfc` |
| `backend/app/services/worker_observation.py` | `e8464b2f27ba219011df978d5d76e332f9336823` | `d6cac9bca33c87a7d245c7c57feef5937ec90290fbbef05676e8d4eb0e2529e5` |
| `backend/app/services/calculation_progress.py` | `c20ff14a57e49d2ec50625923099f864ba977a71` | `0086476cf51480281701a4bd4c10e0327d41004ebb0d9849444fa7772d0fdc1a` |
| `backend/app/services/job_guard.py` | `3fa6c02ab9965bf20968989d93be7166419e2d8a` | `e9654107d525ca03bf412c3199f2add1ed0b376b648a9a20af5590b2cd80462b` |

### C. 全部测试节点

各test_ACnn对应任务书AC01～AC32；其余为补充边界。默认插件未绕过。

| 实际pytest节点 | 最终结果 |
| --- | --- |
| `tests/unit/test_r1_real_root_protocol.py::ProtocolTests::test_AC01_original_six_and_baseline_preserved` | PASS |
| `tests/unit/test_r1_real_root_protocol.py::ProtocolTests::test_AC02_fixed_request_and_flags` | PASS |
| `tests/unit/test_r1_real_root_protocol.py::ProtocolTests::test_AC03_json_strict_types_and_private_errors` | PASS |
| `tests/unit/test_r1_real_root_protocol.py::ProtocolTests::test_AC05_hashes_and_refs_never_authorize` | PASS |
| `tests/unit/test_r1_real_root_protocol.py::ProtocolTests::test_AC06_finite_state_transitions_and_sticky_error` | PASS |
| `tests/unit/test_r1_real_root_protocol.py::ProtocolTests::test_AC28_cli_sealed_and_static_capabilities` | PASS |
| `tests/unit/test_r1_real_root_protocol.py::ProtocolTests::test_AC31_source_sha_and_every_new_utf8_file` | PASS |
| `tests/unit/test_r1_real_root_protocol.py::ProtocolTests::test_AC32_no_offline_state_upgrades_admission` | PASS |
| `tests/unit/test_r1_real_root_adapter.py::AdapterTests::test_AC04_no_owner_no_session_or_business_binding` | PASS |
| `tests/unit/test_r1_real_root_adapter.py::AdapterTests::test_AC07_real_orchestration_create_claim_execute_exactly_once` | PASS |
| `tests/unit/test_r1_real_root_adapter.py::AdapterTests::test_AC08_wrong_claim_token_worker_and_repeated_execute_refused` | PASS |
| `tests/unit/test_r1_real_root_adapter.py::AdapterTests::test_AC09_cancel_error_ack_and_residual_heartbeat_preserved` | PASS |
| `tests/unit/test_r1_real_root_adapter.py::AdapterTests::test_AC10_diagnostics_only_switch_changes` | PASS |
| `tests/unit/test_r1_real_root_adapter.py::AdapterTests::test_AC11_adapter_never_commits_or_calls_worker_provider_scheduler` | PASS |
| `tests/unit/test_r1_real_root_adapter.py::AdapterTests::test_AC30_failure_no_retry_or_private_exception_echo` | PASS |
| `tests/unit/test_r1_real_root_supervisor.py::SupervisorTests::test_AC12_absolute_budgets_and_no_heartbeat_extension` | PASS |
| `tests/unit/test_r1_real_root_supervisor.py::SupervisorTests::test_AC13_intent_before_spawn_and_unknown_handle` | PASS |
| `tests/unit/test_r1_real_root_supervisor.py::SupervisorTests::test_AC14_unowned_reused_pid_pgid_sid_no_signal` | PASS |
| `tests/unit/test_r1_real_root_supervisor.py::SupervisorTests::test_AC15_term_kill_late_done_and_missing_os_exit` | PASS |
| `tests/unit/test_r1_real_root_supervisor.py::SupervisorTests::test_AC16_syscall_lease_and_cleanup_uncertainty_fail_closed` | PASS |
| `tests/unit/test_r1_real_root_supervisor.py::SupervisorTests::test_AC17_off_incomplete_never_generates_on_and_success_only_simulated` | PASS |
| `tests/unit/test_r1_real_root_supervisor.py::SupervisorTests::test_late_returning_poll_and_receipt_never_extend_deadline` | PASS |
| `tests/unit/test_r1_business_snapshot_contract.py::SnapshotTests::test_AC18_exact_orm_inventory_types_keys_foreign_keys` | PASS |
| `tests/unit/test_r1_business_snapshot_contract.py::SnapshotTests::test_AC19_policies_total_no_blanket_exemptions` | PASS |
| `tests/unit/test_r1_business_snapshot_contract.py::SnapshotTests::test_AC20_all_520_columns_type_mutation_and_missing_detected` | PASS |
| `tests/unit/test_r1_business_snapshot_contract.py::SnapshotTests::test_AC21_lossless_types_nonfinite_null_timezone` | PASS |
| `tests/unit/test_r1_business_snapshot_contract.py::SnapshotTests::test_AC22_scope_multiset_ordinal_and_unordered_rows` | PASS |
| `tests/unit/test_r1_business_snapshot_contract.py::SnapshotTests::test_AC23_full_identity_fk_json_candidate_and_orphan_closure` | PASS |
| `tests/unit/test_r1_business_snapshot_contract.py::SnapshotTests::test_AC24_wrong_root_worker_token_parent_and_dependency` | PASS |
| `tests/unit/test_r1_business_snapshot_contract.py::SnapshotTests::test_AC25_three_lifecycles_and_unknown_ack_never_equal` | PASS |
| `tests/unit/test_r1_business_snapshot_contract.py::SnapshotTests::test_AC26_input_output_evidence_and_originals_separate` | PASS |
| `tests/unit/test_r1_business_snapshot_contract.py::SnapshotTests::test_byte_budget_checked_before_unordered_buffer_grows` | PASS |
| `tests/unit/test_r1_business_snapshot_contract.py::SnapshotTests::test_candidate_public_scope_and_stream_exception_are_fail_closed` | PASS |
| `tests/unit/test_r1_business_snapshot_contract.py::SnapshotTests::test_full_execution_policy_and_consistently_wrong_nested_identities` | PASS |
| `tests/unit/test_r1_business_snapshot_contract.py::SnapshotTests::test_session_heartbeat_and_progress_copies_validate_before_observable_mapping` | PASS |
| `tests/unit/test_r1_business_snapshot_contract.py::SnapshotTests::test_stream_order_count_limits_and_bounded_errors` | PASS |
| `tests/unit/test_r1_business_snapshot_contract.py::SnapshotTests::test_unknown_json_time_bijection_delist_and_issue_code_tamper` | PASS |
| `tests/unit/test_r1_seed_snapshot_recipe.py::SeedTests::test_AC27_two_recipes_no_owner_no_gate_upgrade` | PASS |
| `tests/unit/test_r1_seed_snapshot_recipe.py::SeedTests::test_AC29_environment_tools_and_w04a_suite_not_modified` | PASS |
| `tests/unit/test_r1_seed_snapshot_recipe.py::SeedTests::test_full_typed_original_input_snapshot_and_independent_consumers` | PASS |
| `tests/unit/test_r1_seed_snapshot_recipe.py::SeedTests::test_seed_dates_quality_boundaries_and_all_49_sources` | PASS |
| `tests/unit/test_r1_seed_snapshot_recipe.py::SeedTests::test_sequence_schema_rows_and_hash_tamper_refused` | PASS |
| `tests/unit/test_perf03_lnx_w04a_offline_contract.py::W04AContracts::test_A01_no_authority_or_real_execution` | PASS |
| `tests/unit/test_perf03_lnx_w04a_offline_contract.py::W04AContracts::test_A02_schema_fields_versions_and_strict_scalar_types` | PASS |
| `tests/unit/test_perf03_lnx_w04a_offline_contract.py::W04AContracts::test_A03_json_duplicate_nonfinite_utf8_size_and_depth` | PASS |
| `tests/unit/test_perf03_lnx_w04a_offline_contract.py::W04AContracts::test_A04_private_input_never_echoed` | PASS |
| `tests/unit/test_perf03_lnx_w04a_offline_contract.py::W04AContracts::test_A05_stdlib_ast_and_fresh_import_without_business_or_environment` | PASS |
| `tests/unit/test_perf03_lnx_w04a_offline_contract.py::W04AContracts::test_A06_hash_references_not_git_identity_and_wrong_values_refused` | PASS |
| `tests/unit/test_perf03_lnx_w04a_offline_contract.py::W04AContracts::test_A07_path_links_traversal_outside_and_file_types` | PASS |
| `tests/unit/test_perf03_lnx_w04a_offline_contract.py::W04AContracts::test_A08_canonical_plan_digest_order_and_content` | PASS |
| `tests/unit/test_perf03_lnx_w04a_offline_contract.py::W04AContracts::test_A09_plan_equal_is_not_input_equal` | PASS |
| `tests/unit/test_perf03_lnx_w04a_offline_contract.py::W04AContracts::test_A10_r1_fixed_input_values` | PASS |
| `tests/unit/test_perf03_lnx_w04a_offline_contract.py::W04AContracts::test_A11_other_seed_and_protocol_refused` | PASS |
| `tests/unit/test_perf03_lnx_w04a_offline_contract.py::W04AContracts::test_A12_timestamp_inventory_and_unresolved_never_ready` | PASS |
| `tests/unit/test_perf03_lnx_w04a_offline_contract.py::W04AContracts::test_A13_utc_microseconds_and_timestamp_differences` | PASS |
| `tests/unit/test_perf03_lnx_w04a_offline_contract.py::W04AContracts::test_A14_typed_values_never_collapse` | PASS |
| `tests/unit/test_perf03_lnx_w04a_offline_contract.py::W04AContracts::test_A15_pk_duplicates_and_canonical_row_column_table_order` | PASS |
| `tests/unit/test_perf03_lnx_w04a_offline_contract.py::W04AContracts::test_A16_every_declared_column_is_required_and_hashed` | PASS |
| `tests/unit/test_perf03_lnx_w04a_offline_contract.py::W04AContracts::test_A17_root_lifecycle_error_cancel_not_seed` | PASS |
| `tests/unit/test_perf03_lnx_w04a_offline_contract.py::W04AContracts::test_A18_historical_verification_cannot_upgrade_target` | PASS |
| `tests/unit/test_perf03_lnx_w04a_offline_contract.py::W04AContracts::test_A19_all_twelve_gates_cannot_authorize` | PASS |
| `tests/unit/test_perf03_lnx_w04a_offline_contract.py::W04AContracts::test_A20_four_files_original_reports_and_sources_unchanged_no_writes` | PASS |

### D. 37表/520列覆盖

逐列机器可读测试映射见外部column_coverage.json；每列两负例均为最终套件PASS，不新增/忽略任何列。

| 表 | 列数 | PK | 自然比较键 | FK数 | 政策计数 |
| --- | --- | --- | --- | --- | --- |
| stock_basic | 11 | ts_code | ts_code | 0 | {'EXACT_TYPED_VALUE': 11} |
| trade_calendar | 4 | cal_date | cal_date | 0 | {'EXACT_TYPED_VALUE': 4} |
| stock_daily | 12 | trade_date,ts_code | trade_date,ts_code | 0 | {'EXACT_TYPED_VALUE': 12} |
| stock_adj_factor | 3 | trade_date,ts_code | trade_date,ts_code | 0 | {'EXACT_TYPED_VALUE': 3} |
| stock_daily_basic | 16 | trade_date,ts_code | trade_date,ts_code | 0 | {'EXACT_TYPED_VALUE': 16} |
| index_daily | 10 | trade_date,ts_code | trade_date,ts_code | 0 | {'EXACT_TYPED_VALUE': 10} |
| stock_st_daily | 7 | trade_date,ts_code | trade_date,ts_code | 0 | {'EXACT_TYPED_VALUE': 7} |
| stock_suspend_daily | 6 | trade_date,ts_code,suspend_type | trade_date,ts_code,suspend_type | 0 | {'EXACT_TYPED_VALUE': 6} |
| stock_limit_daily | 9 | trade_date,ts_code | trade_date,ts_code | 0 | {'EXACT_TYPED_VALUE': 9} |
| stock_factor_daily | 54 | trade_date,ts_code | trade_date,ts_code | 1 | {'EXACT_TYPED_VALUE': 52, 'UUID_BIJECTION': 1, 'TIMESTAMP_EVENT_MAPPING': 1} |
| market_daily | 24 | trade_date | trade_date | 1 | {'EXACT_TYPED_VALUE': 22, 'UUID_BIJECTION': 1, 'TIMESTAMP_EVENT_MAPPING': 1} |
| sector | 7 | sector_id | source,source_code | 0 | {'EXACT_TYPED_VALUE': 7} |
| sector_member | 6 | id | sector_id,ts_code,valid_from | 1 | {'EXACT_TYPED_VALUE': 6} |
| sector_factor_daily | 30 | trade_date,sector_id | trade_date,sector_id | 2 | {'EXACT_TYPED_VALUE': 28, 'UUID_BIJECTION': 1, 'TIMESTAMP_EVENT_MAPPING': 1} |
| data_quality_daily | 15 | id | trade_date,dataset | 1 | {'EXACT_TYPED_VALUE': 13, 'STRICT_JSON_SUBPATHS': 1, 'UUID_BIJECTION': 1} |
| data_dirty_range | 13 | id | id | 1 | {'EXACT_TYPED_VALUE': 12, 'UUID_BIJECTION': 1} |
| stock_trade_status_daily | 17 | trade_date,ts_code | trade_date,ts_code | 1 | {'EXACT_TYPED_VALUE': 15, 'UUID_BIJECTION': 1, 'TIMESTAMP_EVENT_MAPPING': 1} |
| stock_state_daily | 19 | trade_date,ts_code,algo_version | trade_date,ts_code,algo_version | 1 | {'EXACT_TYPED_VALUE': 16, 'STRICT_JSON_SUBPATHS': 1, 'UUID_BIJECTION': 1, 'TIMESTAMP_EVENT_MAPPING': 1} |
| strategy_signal | 14 | id | trade_date,ts_code,signal_type,algo_version | 1 | {'EXACT_TYPED_VALUE': 9, 'STRICT_JSON_SUBPATHS': 2, 'UUID_BIJECTION': 1, 'TIMESTAMP_EVENT_MAPPING': 2} |
| signal_forward_eval | 22 | id | signal_id,eval_version,entry_basis | 1 | {'EXACT_TYPED_VALUE': 22} |
| theme | 11 | theme_code | theme_code | 0 | {'EXACT_TYPED_VALUE': 11} |
| theme_member_snapshot | 7 | snapshot_date,theme_code,ts_code | snapshot_date,theme_code,ts_code | 1 | {'EXACT_TYPED_VALUE': 7} |
| theme_member_interval | 9 | theme_code,ts_code,valid_from | theme_code,ts_code,valid_from | 1 | {'EXACT_TYPED_VALUE': 9} |
| theme_daily | 15 | trade_date,theme_code | trade_date,theme_code | 1 | {'EXACT_TYPED_VALUE': 15} |
| theme_moneyflow_daily | 14 | trade_date,theme_code | trade_date,theme_code | 1 | {'EXACT_TYPED_VALUE': 14} |
| theme_limit_daily | 11 | trade_date,theme_code | trade_date,theme_code | 1 | {'EXACT_TYPED_VALUE': 11} |
| theme_factor_daily | 42 | trade_date,theme_code | trade_date,theme_code | 2 | {'EXACT_TYPED_VALUE': 40, 'UUID_BIJECTION': 1, 'TIMESTAMP_EVENT_MAPPING': 1} |
| stock_opportunity_daily | 31 | trade_date,ts_code,algo_version | trade_date,ts_code,algo_version | 1 | {'EXACT_TYPED_VALUE': 28, 'STRICT_JSON_SUBPATHS': 1, 'UUID_BIJECTION': 1, 'TIMESTAMP_EVENT_MAPPING': 1} |
| job_run | 20 | id | id | 2 | {'UUID_BIJECTION': 4, 'EXACT_TYPED_VALUE': 9, 'TIMESTAMP_EVENT_MAPPING': 6, 'STRICT_JSON_SUBPATHS': 1} |
| provider_api_log | 9 | id | id | 0 | {'EXACT_TYPED_VALUE': 9} |
| service_heartbeat | 8 | id | service_name,instance_id | 0 | {'EXACT_TYPED_VALUE': 7, 'STRICT_JSON_SUBPATHS': 1} |
| data_publication | 8 | job_id | job_id | 1 | {'UUID_BIJECTION': 2, 'EXACT_TYPED_VALUE': 1, 'STRICT_JSON_SUBPATHS': 2, 'TIMESTAMP_EVENT_MAPPING': 3} |
| data_publication_source | 5 | publication_id,source_job_id | publication_id,source_job_id | 2 | {'UUID_BIJECTION': 2, 'EXACT_TYPED_VALUE': 1, 'TIMESTAMP_EVENT_MAPPING': 1, 'STRICT_JSON_SUBPATHS': 1} |
| data_publication_row | 9 | publication_id,table_name,row_key | publication_id,table_name,row_key | 1 | {'UUID_BIJECTION': 2, 'EXACT_TYPED_VALUE': 4, 'STRICT_JSON_SUBPATHS': 3} |
| data_publication_preimage | 4 | publication_id,table_name,row_key | publication_id,table_name,row_key | 1 | {'UUID_BIJECTION': 1, 'EXACT_TYPED_VALUE': 1, 'STRICT_JSON_SUBPATHS': 2} |
| data_publication_scope | 6 | id | publication_id,table_name,source_id,start_date,end_date | 1 | {'UUID_BIJECTION': 3, 'EXACT_TYPED_VALUE': 3} |
| data_schedule_intent | 12 | identity_key | identity_key | 1 | {'EXACT_TYPED_VALUE': 10, 'STRICT_JSON_SUBPATHS': 1, 'UUID_BIJECTION': 1} |

### E. 新文件SHA256

| 新增文件 | SHA256 |
| --- | --- |
| `scripts/r1_real_root_protocol.py` | `7e3f40d4452a9dc4a7b373b089c5f11ae9b213b163ac0c00fb2b3312cf0d997e` |
| `scripts/r1_real_root_adapter.py` | `cf2de69c6e5acb2e39334e80eb6c5de3971794fd5d6c86510c406fcf4d3752e3` |
| `scripts/r1_real_root_supervisor.py` | `812a5c980f7fdc91c2dbde211d1b30e6d403f719061bc3baa787e57e7cb98892` |
| `scripts/r1_business_snapshot_contract.py` | `7219c0ffb405f01c3f9af973bf8b38665f1a02afd32361aab30cf67ab132d74a` |
| `scripts/r1_seed_snapshot_recipe.py` | `06d7a34b2a99139e1f7e66a593ccd03c9195098cd1252defb057242058a02f4c` |
| `docs/acceptance/r1_business_compare_schema_v1.json` | `f6be0a5de1ce46e30758039a3ab345a308ff96cb36f6ee86ec3ccdc39759f297` |
| `tests/unit/test_r1_real_root_protocol.py` | `eca291b0f915706ef7fb3245cf119d5b277554e373ea880b214c5e66b109ab18` |
| `tests/unit/test_r1_real_root_adapter.py` | `06d011d40f68299c926d02a70c763dfb17655a287c03a50447f59bb6970ae6a2` |
| `tests/unit/test_r1_real_root_supervisor.py` | `bf7116510b80f6560a2eb0cd4d44bdd2fc749956e868bf486dc4d401edf9a3df` |
| `tests/unit/test_r1_business_snapshot_contract.py` | `5f9f0e6d19b2c2db8fda50d17fa0fd8f20ab0a8504ff8e89653cdf9a7548ac1e` |
| `tests/unit/test_r1_seed_snapshot_recipe.py` | `3d6770f615a1a4a23460c42768792f476dad78838c5f3af699cd3aecb9300662` |
| 本验收报告 | 最终聊天及外部new-files-sha256.json，避免自引用 |
