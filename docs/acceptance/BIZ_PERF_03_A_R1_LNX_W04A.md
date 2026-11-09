# P0-LNX-W04-A-01 隔离 Linux 与确定性 Seed 离线合同交付

2026-11-09，Asia/Shanghai。仅四文件离线实现，无真实资源操作。
**实现已交付待审；验证状态 W04A_BLOCKED（pytest 启动环境缺 pluggy）**。
标准库替代测试20项全部通过、Ruff及py_compile通过；pytest没有收集或执行测试，不能宣称其完整验收通过。
任务书允许无pytest时执行纯Python合同自测；本轮遵守禁止安装依赖的边界，不修用户Python环境。
EXPERIMENT_NO_GO；G01 NOT_AUTHORIZED；R1与历史AC-05 PARTIAL；Windows原生根因UNKNOWN。

## 1. 基线、范围及来源等级

HEAD/origin/master/实时远端master均为
`b6ffb7bf8ec7d26f771d9b89923e4f7e926edbed`，master。开始tracked diff为空，
已有untracked只有W03/W04；结束只增加本轮四文件，未git add/commit/push或触发CI。
两报告完整内容已在同一会话读取，当前再次核对字节及全部列目录/门禁；不当作Git基线材料或独立批准。

| 来源 | 等级 | 核查事实 / 不证明什么 |
| --- | --- | --- |
| AGENTS及五份治理、PRD/系统设计/规则/README相关边界 | GIT_SOURCE | 当前仍有旧G0/CI-OPT/04-E执行指针；本轮明确批准只限四文件，未改治理以制造授权 |
| W03本地报告 | LOCAL_UNTRACKED_SELF_REPORTED | SHA256 `21e9f0acc048d1724be985b13667a2cd71572992096abea9d8fbd57699455c9d`匹配；保持原字节/untracked，不表示GitHub已审 |
| W04本地报告 | LOCAL_UNTRACKED_SELF_REPORTED | SHA256 `09ac6d54828cdc085e134c5a54f91e3a1efa8933d42dea1e9bc7ae3967370f0d`匹配；37表520列逐个由AST复核一致；不表示真实schema或结果比较通过 |
| 原seed、ORM、Root集成测试、03-B另一套seed、config/锁 | GIT_SOURCE | 9份固定材料的Git blob SHA和原字节SHA256如下；无业务导入 |
| 04-D Run42156106471与04-E归档 | HISTORY_VERIFIED | 前轮已重核原安装工件；历史3.12.14/67包VERIFIED、E完整性VALID；不自动继承新目标资源资格 |
| W02及其Linux专项、S的6331/18项工程CI | HISTORY_VERIFIED | 固定Mock工程；本轮未重跑/重取CI，不是本轮20项测试或真实Root资格 |
| 本合同的资源档位、冻结注入点与候选值 | DESIGN_INFERENCE | 只定义未来审批的方案，未创建/安装/装载/探测；影响仍NOT_VERIFIED |
| 目标VM、PG身份、Seed实体快照、真实OFF/ON、Root结果 | UNVERIFIED | 全部NOT_VERIFIED/NOT_RUN；不补造IP、marker、system_identifier、实验run_id或成功回执 |

| 固定材料 / 行段（1-based） | Git blob SHA | Git原字节 SHA256 |
| --- | --- | --- |
| `backend/app/models/market_data.py`；StockBasic:27–42, TradeCalendar:45–51, StockDaily:54–74, StockAdjFactor:77–86, StockDailyBasic:89–111, IndexDaily:114–130, StockStDaily:133–145, StockSuspendDaily:148–159, StockLimitDaily:162–176, StockFactorDaily:179–242, MarketDaily:245–273, Sector:276–286, SectorMember:289–301, SectorFactorDaily:304–342, DataQualityDaily:345–368, DataDirtyRange:371–389, StockTradeStatusDaily:392–418, StockStateDaily:421–449, StrategySignal:452–480, SignalForwardEval:483–522, Theme:525–540, ThemeMemberSnapshot:543–556, ThemeMemberInterval:559–576, ThemeDaily:579–602, ThemeMoneyflowDaily:605–624, ThemeLimitDaily:627–643, ThemeFactorDaily:646–696, StockOpportunityDaily:699–743, _ResearchForwardFields:746–832, OpportunityForwardEval:835–900, ThemeForwardEval:903–962, ResearchTransitionEval:965–1023 | `56ea835f28e289dc165717639b20bcecf3015e61` | `c0207d196fb9777bfd5c83284ca9d36f5b2cbf9ea5191ca149fbce9afcee9261` |
| `backend/app/models/job.py`；JobRun:24–62, ProviderApiLog:65–79, ServiceHeartbeat:82–96 | `36918fcb92d34d430dcc2a7f359c2fbdb49ebf7e` | `fc795d1d4fb92ff3b8a10d41e19898e392e236ca84c661e78dfa2b02519ecc11` |
| `backend/app/models/data_publication.py`；RowKeyJSON:15–21, DataPublication:24–39, DataPublicationSource:42–56, DataPublicationRow:59–84, DataPublicationPreimage:87–97, DataPublicationScope:100–111 | `36eca6f02b6173ec136487554b69a88235db73a9` | `c9163a6e8386404d3b9faf9eaa1bf064d4a476b986e8fcc452ba9ce382aca63c` |
| `backend/app/models/data_schedule.py`；DataScheduleIntent:12–33 | `6722f487ec11726673706837ffa5c7216e1a7bf9` | `1c02583b6d8b455be81a3fc7f34c7aa93c167a6e516395e6688c24939fdf48c2` |
| `tests/integration/test_business_recalc_performance.py`；isolated:22–24, seed:27–55, test_batched_raw_preflight_matches_every_field_and_reduces_queries:59–107, test_input_window_preserves_full_frame_dtypes_and_detects_source_change:110–137, test_input_window_status_overlay_tombstone_and_root_identity:140–179, test_input_window_memory_failure_closes_cursor_without_partial_frame:182–195, test_raw_preflight_rejects_unbounded_window:198–202, test_new_read_paths_are_off_by_default:205–212, test_final_source_verification_uses_original_publication_budget:215–230, test_cached_inputs_require_reverification_after_checkpoint_commit:233–245, test_opt_in_real_worker_financial_quality_and_atomic_terminal_state:249–305 | `3e6be63279a8f944f075fac0637a50c953c86632` | `c6cc8cf4145d3dbefd259417e08c06ac7470a39adeca654ce9fe2f5483f2ba27` |
| `tests/integration/test_perf03_root_diagnostics.py`；test_real_root_parity_and_local_reports:21–79 | `1bedec6bf9974b00c47bf63b2ee5733e8ac8231a` | `7f9a5a16e19d64e7215466e8593f9fad3e1ab630a23cd036d087fba81fb9683a` |
| `scripts/business_recalc_measure.py`；main:23–499 | `782e45ba53c8de8df0d12ffa84c219855316cfda` | `edbd4b0d290fdf41ace88f2d8b15fb395c86eed2a7ae99daad5814975d114108` |
| `config/strategy.yaml`；1–83 | `2d4fe1ea25feb05a508161ff87409e70e48a3817` | `2ac50c63f3b522ae84e97dad2c9eb2eabd2206c224cea25f83d8d049e7d2864b` |
| `requirements-biz-perf-linux-py312-v1.lock`；1–70 | `121cb63ee81bdbb61ffb1070ef627dcfbce4562c` | `88549dce3164364430e20970fa10eb2125b60ff05f456d7bef4474876a98dcfc` |

Git blob仅代表观察基线的原件身份。Windows checkout若有CRLF，不将原字节不符改写为通过；
material_digest逐字节拒绝，测试仅在自己的临时目录物化LF合成副本，没有改旧文件或全局Git设置。
校验器不会运行Git，也不声称仅凭40/64位字符串已经核实工作树/提交；返回REFERENCE_ONLY_NOT_VERIFIED。

## 2. 四文件与接口

| 文件 | 范围 |
| --- | --- |
| [合同JSON](biz_perf_03_a_r1_lnx_w04a_contract.json) | 固定环境/PG/输入/49时间列/历史/12门禁/零运行状态，schema `perf03-lnx.w04a.offline-readiness.v1` |
| [标准库校验器](../../scripts/perf03_lnx_w04a_offline_contract.py) | 无环境变量、网络、业务包或子进程读取/调用；只读固定合同/固定文本材料及纯内存比较 |
| [测试](../../tests/unit/test_perf03_lnx_w04a_offline_contract.py) | unittest.TestCase，pytest可收集；纯合成内存/临时目录/静态源文件，不触及PG |
| 本报告 | 来源、Seed列分类、实际结果、风险、后续授权；自身SHA在聊天交付，避免自引用循环 |

接口：parse_json / validate_contract / material_digest / plan_fingerprint / compare_plans /
synthetic_snapshot_fingerprint / compare_synthetic_snapshots。函数均不写文件、不探测目标、不执行其他命令。
CLI只接受无参数或--check，固定读合同路径，未知参数仅输出W04A_CLI_REFUSED；不能传自由命令或PID。
API read_safe接收调用方明确可信root与相对文本路径；material_digest另限制为9个固定材料。
拒绝..、绝对/越界/反斜线/别名路径、symlink/junction、目录/特殊文件、超限与打开前后身份变化。
路径保护是可信静态checkout下的本地边界，不宣称恶意同UID持续替换祖先路径的内核级隔离。
Windows link/特殊文件负例通过确定性属性注入覆盖，不冒充Linux真实FIFO或symlink实测。

## 3. 环境和PG17合同

只定义候选B专用Linux VM/ECS。小档候选4 vCPU/16GiB/80GiB SSD数据盘；大档候选8/32/160。
这些值不是运行预算或性能保证，系统盘、IOPS/带宽、CPU型号/governor、swap、NUMA、内核/
发行版、时钟源、cgroup/pids/native线程、owner租约与独占窗口、噪声、安全组/出口、
日志盘/备份/销毁/外部fencing及租期费用均NOT_VERIFIED或PENDING_OWNER_DECISION。
不报价、不选账号、不创建/登录/部署资源，不宣称当前hosted runner适合实验。

目标固定CPython3.12.14、x86_64、glibc>=2.28，原67包hash锁；具体版本/文件摘要见固定锁和
04-D的dependency-verification.json。历史原件glibc2.39/pip25.0.1只是旧runner事实。
新机须另批干净安装、wheel/ABI/完整67包集合与工具链核验；不以本地3.12.0测试或Main3.12.16代替。
04-E历史bundle完整性不产生TARGET_VERIFIED/EXPERIMENT_AUTHORIZED。

PG17预期流程：核owner/lease→离线control ID→在线major17/随机marker/system_identifier双核
→记录创建意图→创建UUID合成库并确认ACK→迁移/seed前重核→导出前核绑定→销毁前再核。
独立非生产角色/受限创建broker，禁止与业务实例共用可误写凭据；不能自动连接已有stock_db、
不能读.env或回退默认DATABASE_URL，网络仅同机loopback或获批隔离VPC。
control读取/建库需要的特权由owner分离批准，业务进程不获生产管理员能力；核不齐直接拒绝。
记录精确PG版本/镜像digest或包hash、扩展、locale/collation/timezone/work_mem/shared_buffers/
storage/cache策略；不承诺OS物理冷缓存。没有任何实际数据库身份写入新合同。
销毁需owner/对象标签/创建确认/再核物理身份，绝不靠名称前缀删除；未知ACK或归属缺证为
CLEANUP_UNCERTAIN/NO_GO，不自动重试CREATE/DROP，不全局清理。

## 4. Seed的三层身份与冻结设计

1. 计划：原seed入口、观察SHA/源文件/config/锁hash、两证券、420日、原日历/指数集、日期/manual/
   evaluate_signals=false、逐列冻结策略均固定；离线只得到PLAN_EQUAL。
2. 输入实体：未来真实两库Root开始前按所有输入表/列/类型/主键排序/行数/规范值与摘要复核，
   外部owner确认。目前实体快照NOT_RUN；本轮只比较小型人工快照。
3. Root结果：未来W04-C独立全列/身份闭包/失败语义比较；不能用输出相同倒推输入相同。

原R1入口`tests.integration.test_business_recalc_performance.seed(factory,include_closed=False,history_days=420)`；
日历2025-01-01～2026-02-24，请求2026-02-23～24，证券000001.SZ/000002.SZ，benchmark指数
000300.SH/000001.SH；manual/evaluate_signals=false。list_date/delist_date、业务trade_date/valid_from
等保持原值，不能冻结为同一天或取消原退市边界。原250交易日预热/430自然日回看不改。
03-B的900日/4证券/2025-01、constant-price-frozen-audit-v2及2026-10-27统一时间是另一套生成器，
本轮不复用其seed_rows、flags或Root测量协议。

### 4.1 每个Seed触及表及时间列

| 输入表 | PK | 全列数 | Seed时间戳策略 |
| --- | --- | --- | --- |
| stock_basic | ts_code | 11 | updated_at: FROZEN_SEED_VALUE |
| trade_calendar | cal_date | 4 | 无DateTime；原业务Date保持 |
| stock_daily | trade_date, ts_code | 12 | source_updated_at: FROZEN_SEED_VALUE |
| stock_adj_factor | trade_date, ts_code | 3 | 无DateTime；原业务Date保持 |
| stock_daily_basic | trade_date, ts_code | 16 | 无DateTime；原业务Date保持 |
| index_daily | trade_date, ts_code | 10 | 无DateTime；原业务Date保持 |
| stock_st_daily | trade_date, ts_code | 7 | created_at: NOT_IN_INPUT；updated_at: NOT_IN_INPUT |
| stock_suspend_daily | trade_date, ts_code, suspend_type | 6 | created_at: NOT_IN_INPUT；updated_at: NOT_IN_INPUT |
| stock_limit_daily | trade_date, ts_code | 9 | created_at: FROZEN_SEED_VALUE；updated_at: FROZEN_SEED_VALUE |
| sector | sector_id | 7 | 无DateTime；原业务Date保持 |
| sector_member | id | 6 | 无DateTime；原业务Date保持 |
| data_quality_daily | id | 15 | checked_at: FROZEN_SEED_VALUE |

W04逐列目录独立复核：全部ORM列的 `(table,column,path,line)` 与原W04的520行目录全等；只读AST，未导入模型或连接数据库。

| W04表 / ORM起始列行 | 静态列数 | 本轮映射 |
| --- | --- | --- |
| stock_basic；backend/app/models/market_data.py:30 | 11 | INPUT_SCHEMA全列 |
| trade_calendar；backend/app/models/market_data.py:48 | 4 | INPUT_SCHEMA全列 |
| stock_daily；backend/app/models/market_data.py:61 | 12 | INPUT_SCHEMA全列 |
| stock_adj_factor；backend/app/models/market_data.py:84 | 3 | INPUT_SCHEMA全列 |
| stock_daily_basic；backend/app/models/market_data.py:96 | 16 | INPUT_SCHEMA全列 |
| index_daily；backend/app/models/market_data.py:121 | 10 | INPUT_SCHEMA全列 |
| stock_st_daily；backend/app/models/market_data.py:137 | 7 | INPUT_SCHEMA全列 |
| stock_suspend_daily；backend/app/models/market_data.py:152 | 6 | INPUT_SCHEMA全列 |
| stock_limit_daily；backend/app/models/market_data.py:166 | 9 | INPUT_SCHEMA全列 |
| stock_factor_daily；backend/app/models/market_data.py:187 | 54 | 非本轮Seed输入；Root/其他结果仍待W04-C |
| market_daily；backend/app/models/market_data.py:248 | 24 | 非本轮Seed输入；Root/其他结果仍待W04-C |
| sector；backend/app/models/market_data.py:280 | 7 | INPUT_SCHEMA全列 |
| sector_member；backend/app/models/market_data.py:296 | 6 | INPUT_SCHEMA全列 |
| sector_factor_daily；backend/app/models/market_data.py:311 | 30 | 非本轮Seed输入；Root/其他结果仍待W04-C |
| data_quality_daily；backend/app/models/market_data.py:352 | 15 | INPUT_SCHEMA全列 |
| data_dirty_range；backend/app/models/market_data.py:375 | 13 | 非本轮Seed输入；Root/其他结果仍待W04-C |
| stock_trade_status_daily；backend/app/models/market_data.py:400 | 17 | 非本轮Seed输入；Root/其他结果仍待W04-C |
| stock_state_daily；backend/app/models/market_data.py:429 | 19 | 非本轮Seed输入；Root/其他结果仍待W04-C |
| strategy_signal；backend/app/models/market_data.py:465 | 14 | 非本轮Seed输入；Root/其他结果仍待W04-C |
| signal_forward_eval；backend/app/models/market_data.py:495 | 22 | 非本轮Seed输入；Root/其他结果仍待W04-C |
| theme；backend/app/models/market_data.py:528 | 11 | 非本轮Seed输入；Root/其他结果仍待W04-C |
| theme_member_snapshot；backend/app/models/market_data.py:550 | 7 | 非本轮Seed输入；Root/其他结果仍待W04-C |
| theme_member_interval；backend/app/models/market_data.py:566 | 9 | 非本轮Seed输入；Root/其他结果仍待W04-C |
| theme_daily；backend/app/models/market_data.py:586 | 15 | 非本轮Seed输入；Root/其他结果仍待W04-C |
| theme_moneyflow_daily；backend/app/models/market_data.py:609 | 14 | 非本轮Seed输入；Root/其他结果仍待W04-C |
| theme_limit_daily；backend/app/models/market_data.py:631 | 11 | 非本轮Seed输入；Root/其他结果仍待W04-C |
| theme_factor_daily；backend/app/models/market_data.py:653 | 42 | 非本轮Seed输入；Root/其他结果仍待W04-C |
| stock_opportunity_daily；backend/app/models/market_data.py:711 | 31 | 非本轮Seed输入；Root/其他结果仍待W04-C |
| job_run；backend/app/models/job.py:39 | 20 | 非本轮Seed输入；Root/其他结果仍待W04-C |
| provider_api_log；backend/app/models/job.py:71 | 9 | 非本轮Seed输入；Root/其他结果仍待W04-C |
| service_heartbeat；backend/app/models/job.py:89 | 8 | 非本轮Seed输入；Root/其他结果仍待W04-C |
| data_publication；backend/app/models/data_publication.py:30 | 8 | 非本轮Seed输入；Root/其他结果仍待W04-C |
| data_publication_source；backend/app/models/data_publication.py:46 | 5 | 非本轮Seed输入；Root/其他结果仍待W04-C |
| data_publication_row；backend/app/models/data_publication.py:72 | 9 | 非本轮Seed输入；Root/其他结果仍待W04-C |
| data_publication_preimage；backend/app/models/data_publication.py:90 | 4 | 非本轮Seed输入；Root/其他结果仍待W04-C |
| data_publication_scope；backend/app/models/data_publication.py:104 | 6 | 非本轮Seed输入；Root/其他结果仍待W04-C |
| data_schedule_intent；backend/app/models/data_schedule.py:20 | 12 | 非本轮Seed输入；Root/其他结果仍待W04-C |

`alembic_version.version_num`是W04另列的迁移哨兵，不计入37/520；未来目标迁移状态NOT_VERIFIED。

5个实际Seed默认时间列为stock_basic.updated_at、stock_daily.source_updated_at、
stock_limit_daily.created_at/updated_at、data_quality_daily.checked_at。
合同将其**未来计划**分类为FROZEN_SEED_VALUE，列清各自UTC微秒候选值与原ORM声明。
未来注入位置候选是新受限fixture构造中显式为这些列赋值、在INSERT之前替换对应默认值，
并对源事实/修订时间/新鲜度/质量判断逐项验收；本轮既未修改原seed，也未批准该业务影响。
不是把全部DateTime写同一常数：候选值按列独立，created_at不晚于updated_at；所有行值必须
在将来的显式生成策略中审阅。当前behavior_impact全为NOT_VERIFIED_REQUIRES_APPROVAL。
原server_default/onupdate的数据库实际触发、额外trigger与目标DDL均未实测，未来schema/trigger
审计缺失时继续拒绝，不能只靠ORM目录推断没有数据库触发器。

12表/106个输入列由当前ORM静态展开；另有synthetic_type_probe（9列）只为decimal/bytes等类型负例，
不是业务表、不是数据库fixture、不扩大真实数据集。原种子中不产生ST/停牌Raw行，也必须保留空表证据。
37表/520列是W04审计的静态全集，**不是**本轮106输入列比较器已经覆盖全部Root结果。

### 4.2 时间戳分类目录

49个时间列均已静态识别：FROZEN_SEED_VALUE=5、DYNAMIC_ROOT_VALUE=19、NOT_IN_INPUT=25、UNRESOLVED=0。
这里resolved指分类和源码位置可证明，不是冻结代码已实现/业务影响已验证/目标机已验收。
data_quality_daily.checked_at分Raw输入Seed冻结与Root Derived质量动态时间两阶段；绝不冻结Root后写入。
Job.started/heartbeat/finished/execution/cancel/progress、Derived.calculated_at、publication发布时间等
必须保留自然生命周期，留给W04-C逐列映射。错误/取消时间不能伪装成Seed；null仍独立。
将任一目录项改UNRESOLVED可以解析，但G05明确SEED_FIELD_UNRESOLVED/NO_GO；缺项/重复项/错分类拒绝。

| table.column / ORM位置 | Seed分类 | Root策略 | 拟议UTC值 |
| --- | --- | --- | --- |
| stock_basic.updated_at；backend/app/models/market_data.py:40 | FROZEN_SEED_VALUE | NOT_IN_INPUT | 2025-01-01T00:00:00.000000Z |
| stock_daily.source_updated_at；backend/app/models/market_data.py:72 | FROZEN_SEED_VALUE | NOT_IN_INPUT | 2025-01-01T00:00:00.000001Z |
| stock_st_daily.created_at；backend/app/models/market_data.py:142 | NOT_IN_INPUT | NOT_IN_INPUT | 无冻结 |
| stock_st_daily.updated_at；backend/app/models/market_data.py:143 | NOT_IN_INPUT | NOT_IN_INPUT | 无冻结 |
| stock_suspend_daily.created_at；backend/app/models/market_data.py:156 | NOT_IN_INPUT | NOT_IN_INPUT | 无冻结 |
| stock_suspend_daily.updated_at；backend/app/models/market_data.py:157 | NOT_IN_INPUT | NOT_IN_INPUT | 无冻结 |
| stock_limit_daily.created_at；backend/app/models/market_data.py:173 | FROZEN_SEED_VALUE | NOT_IN_INPUT | 2025-01-01T00:00:00.000002Z |
| stock_limit_daily.updated_at；backend/app/models/market_data.py:174 | FROZEN_SEED_VALUE | NOT_IN_INPUT | 2025-01-01T00:00:00.000003Z |
| stock_factor_daily.calculated_at；backend/app/models/market_data.py:242 | DYNAMIC_ROOT_VALUE | DYNAMIC_ROOT_VALUE | 无冻结 |
| market_daily.calculated_at；backend/app/models/market_data.py:273 | DYNAMIC_ROOT_VALUE | DYNAMIC_ROOT_VALUE | 无冻结 |
| sector_factor_daily.calculated_at；backend/app/models/market_data.py:342 | DYNAMIC_ROOT_VALUE | DYNAMIC_ROOT_VALUE | 无冻结 |
| data_quality_daily.checked_at；backend/app/models/market_data.py:365 | FROZEN_SEED_VALUE | DYNAMIC_ROOT_VALUE | 2025-01-01T00:00:00.000004Z |
| data_dirty_range.last_failed_at；backend/app/models/market_data.py:386 | NOT_IN_INPUT | NOT_IN_INPUT | 无冻结 |
| data_dirty_range.processing_started_at；backend/app/models/market_data.py:387 | NOT_IN_INPUT | NOT_IN_INPUT | 无冻结 |
| data_dirty_range.created_at；backend/app/models/market_data.py:388 | NOT_IN_INPUT | NOT_IN_INPUT | 无冻结 |
| data_dirty_range.resolved_at；backend/app/models/market_data.py:389 | NOT_IN_INPUT | NOT_IN_INPUT | 无冻结 |
| stock_trade_status_daily.calculated_at；backend/app/models/market_data.py:418 | DYNAMIC_ROOT_VALUE | DYNAMIC_ROOT_VALUE | 无冻结 |
| stock_state_daily.calculated_at；backend/app/models/market_data.py:449 | DYNAMIC_ROOT_VALUE | DYNAMIC_ROOT_VALUE | 无冻结 |
| strategy_signal.calculated_at；backend/app/models/market_data.py:479 | DYNAMIC_ROOT_VALUE | DYNAMIC_ROOT_VALUE | 无冻结 |
| strategy_signal.created_at；backend/app/models/market_data.py:480 | DYNAMIC_ROOT_VALUE | DYNAMIC_ROOT_VALUE | 无冻结 |
| signal_forward_eval.updated_at；backend/app/models/market_data.py:520 | NOT_IN_INPUT | NOT_IN_INPUT | 无冻结 |
| theme.updated_at；backend/app/models/market_data.py:538 | NOT_IN_INPUT | NOT_IN_INPUT | 无冻结 |
| theme_member_snapshot.created_at；backend/app/models/market_data.py:556 | NOT_IN_INPUT | NOT_IN_INPUT | 无冻结 |
| theme_member_interval.created_at；backend/app/models/market_data.py:573 | NOT_IN_INPUT | NOT_IN_INPUT | 无冻结 |
| theme_member_interval.updated_at；backend/app/models/market_data.py:574 | NOT_IN_INPUT | NOT_IN_INPUT | 无冻结 |
| theme_daily.created_at；backend/app/models/market_data.py:599 | NOT_IN_INPUT | NOT_IN_INPUT | 无冻结 |
| theme_daily.updated_at；backend/app/models/market_data.py:600 | NOT_IN_INPUT | NOT_IN_INPUT | 无冻结 |
| theme_moneyflow_daily.created_at；backend/app/models/market_data.py:621 | NOT_IN_INPUT | NOT_IN_INPUT | 无冻结 |
| theme_moneyflow_daily.updated_at；backend/app/models/market_data.py:622 | NOT_IN_INPUT | NOT_IN_INPUT | 无冻结 |
| theme_limit_daily.created_at；backend/app/models/market_data.py:640 | NOT_IN_INPUT | NOT_IN_INPUT | 无冻结 |
| theme_limit_daily.updated_at；backend/app/models/market_data.py:641 | NOT_IN_INPUT | NOT_IN_INPUT | 无冻结 |
| theme_factor_daily.calculated_at；backend/app/models/market_data.py:696 | DYNAMIC_ROOT_VALUE | DYNAMIC_ROOT_VALUE | 无冻结 |
| stock_opportunity_daily.calculated_at；backend/app/models/market_data.py:743 | DYNAMIC_ROOT_VALUE | DYNAMIC_ROOT_VALUE | 无冻结 |
| job_run.started_at；backend/app/models/job.py:42 | DYNAMIC_ROOT_VALUE | DYNAMIC_ROOT_VALUE | 无冻结 |
| job_run.heartbeat_at；backend/app/models/job.py:43 | DYNAMIC_ROOT_VALUE | DYNAMIC_ROOT_VALUE | 无冻结 |
| job_run.finished_at；backend/app/models/job.py:45 | DYNAMIC_ROOT_VALUE | DYNAMIC_ROOT_VALUE | 无冻结 |
| job_run.execution_started_at；backend/app/models/job.py:51 | DYNAMIC_ROOT_VALUE | DYNAMIC_ROOT_VALUE | 无冻结 |
| job_run.cancel_requested_at；backend/app/models/job.py:52 | DYNAMIC_ROOT_VALUE | DYNAMIC_ROOT_VALUE | 无冻结 |
| job_run.last_progress_at；backend/app/models/job.py:53 | DYNAMIC_ROOT_VALUE | DYNAMIC_ROOT_VALUE | 无冻结 |
| provider_api_log.created_at；backend/app/models/job.py:79 | NOT_IN_INPUT | NOT_IN_INPUT | 无冻结 |
| service_heartbeat.started_at；backend/app/models/job.py:92 | NOT_IN_INPUT | NOT_IN_INPUT | 无冻结 |
| service_heartbeat.heartbeat_at；backend/app/models/job.py:93 | NOT_IN_INPUT | NOT_IN_INPUT | 无冻结 |
| data_publication.created_at；backend/app/models/data_publication.py:36 | DYNAMIC_ROOT_VALUE | DYNAMIC_ROOT_VALUE | 无冻结 |
| data_publication.publish_started_at；backend/app/models/data_publication.py:37 | DYNAMIC_ROOT_VALUE | DYNAMIC_ROOT_VALUE | 无冻结 |
| data_publication.published_at；backend/app/models/data_publication.py:38 | DYNAMIC_ROOT_VALUE | DYNAMIC_ROOT_VALUE | 无冻结 |
| data_publication_source.validated_at；backend/app/models/data_publication.py:55 | DYNAMIC_ROOT_VALUE | DYNAMIC_ROOT_VALUE | 无冻结 |
| data_schedule_intent.next_attempt_at；backend/app/models/data_schedule.py:31 | NOT_IN_INPUT | NOT_IN_INPUT | 无冻结 |
| data_schedule_intent.created_at；backend/app/models/data_schedule.py:32 | NOT_IN_INPUT | NOT_IN_INPUT | 无冻结 |
| data_schedule_intent.updated_at；backend/app/models/data_schedule.py:33 | NOT_IN_INPUT | NOT_IN_INPUT | 无冻结 |

每行的原声明、理由、源文件SHA、freeze_point及影响未知枚举均保存在JSON的seed_timestamp_policy中；不以表中分类省略来源。

## 5. JSON、计划与合成快照规则

所有dict严格字段集合、类型和固定值；未知嵌套字段、额外权限、环境VERIFIED、非零执行次数、
ready_to_run/performance_pass/production_authorized等伪造声明都拒绝。bool不等于int，420.0不等于420。
JSON必须UTF-8、单文件<=262144 bytes、最大深度32；重复key、BOM/坏编码、NaN/Infinity/1e999拒绝。
错误只输出W04A固定码，不附私密原文/DSN/路径。源SHA40、artifact SHA256为64位小写hex且绑定固定参考值。
固定材料摘要只表示TEXT_BYTES_MATCH_ONLY_NOT_GIT_IDENTITY，不查询Git或目标资源。

plan_fingerprint采用ASCII规范JSON：sort_keys=True、separators=(',',':')、ensure_ascii=True、allow_nan=False。
整合同参与摘要，包括source/config/hash、风险与逐列拟议值；schema变更必须独立版本，不与旧结果混用。
合同中允许变动仅为明确UNRESOLVED分类和5个格式有效的UTC微秒拟议值，仍不授予执行许可。
本轮实际计划摘要：`8e524dd68b684e2428533ccdea4072a930d04c650ef5d1a3d40ec6f294ca4524`。

合成快照schema `perf03-lnx.w04a.synthetic-input.v1`：严格schema/evidence_kind/plan_sha256/tables；
plan_sha256须匹配已验证计划，不能同数据配另一个计划。13个固定表名（12业务输入+人工probe），
每行字段集合等于静态schema，丢列/未知列/重复PK拒绝，总行数<=1000，仍受JSON字节/深度预算。
表名按canonical object键序，行按声明PK的类型标记canonical bytes排序；这是版本化稳定顺序，
不宣称与PostgreSQL本地collation或数字ORDER BY相同。输入行/列/表呈现顺序可变，但数组业务值顺序不变。

单元格为type/value严格二字段：null（真正None）、bool（bool）、int（非bool整数）、
decimal（精确十进制字符串含scale）、float（规范binary64 hex或显式NaN/+Infinity/-Infinity标记）、
date（严格ISO日期）、datetime（UTC的YYYY-MM-DDTHH:MM:SS.ffffffZ）、text（UTF-8）、bytes（小写hex）。
输入业务JSON列另以json标签递归校验；SQL NULL标签与JSON内部null不混同。禁止default=str、str(row)、
epsilon比较或无序集合替代原值。显式float特殊值仅合成类型证据，不允许JSON裸NaN/Infinity。
datetime的naive、非UTC offset、缺微秒或非法日期拒绝，微秒改值导致不相等；decimal 1.0与1.00分开。

完整的小型人工格式样例（可由离线接口接受）：

```json
{
  "schema": "perf03-lnx.w04a.synthetic-input.v1",
  "evidence_kind": "SYNTHETIC_ONLY",
  "plan_sha256": "8e524dd68b684e2428533ccdea4072a930d04c650ef5d1a3d40ec6f294ca4524",
  "tables": {
    "stock_basic": [],
    "trade_calendar": [],
    "stock_daily": [],
    "stock_adj_factor": [],
    "stock_daily_basic": [],
    "index_daily": [],
    "stock_st_daily": [],
    "stock_suspend_daily": [],
    "stock_limit_daily": [],
    "sector": [],
    "sector_member": [],
    "data_quality_daily": [],
    "synthetic_type_probe": [
      {
        "id": {
          "type": "int",
          "value": 1
        },
        "bool": {
          "type": "bool",
          "value": false
        },
        "int": {
          "type": "int",
          "value": 0
        },
        "decimal": {
          "type": "decimal",
          "value": "1.00"
        },
        "float": {
          "type": "float",
          "value": "0x1.0000000000000p+0"
        },
        "date": {
          "type": "date",
          "value": "2026-02-23"
        },
        "datetime": {
          "type": "datetime",
          "value": "2025-01-01T00:00:00.000001Z"
        },
        "text": {
          "type": "text",
          "value": "SYNTHETIC"
        },
        "bytes": {
          "type": "bytes",
          "value": "00ff"
        }
      }
    ]
  }
}
```

该人工样例摘要为 `b7f5dd4e4073d306d9b9c291f1060b63d1e1172854a4ddb3fec267a68bc5d73e`，
只对应测试snapshot()的SYNTHETIC_ONLY内容（12业务输入表为空，probe一行），不是真实Seed装载摘要。
合法输出只有PLAN_EQUAL或SYNTHETIC_SNAPSHOT_EQUAL，始终real_input_equality=NOT_VERIFIED、decision=NO_GO。
比较器只做输入型值与PK合同，不实现真实ORM连接/FK全图/Root输出/可信owner消费；后续不得拿它替代W04-C。

## 6. 实际测试、失败保留与工具边界

执行平台Windows win32，CPython3.12.0（本地验证解释器，非目标3.12.14），Ruff0.12.7。
默认python3.13.7没有pytest/Ruff；另一本机现成3.12.0有pytest模块但启动import失败：
ModuleNotFoundError: pluggy。没有安装依赖、改变用户site-packages或禁用项目插件刷过。
pytest没有进入收集：NOT_RUN/STARTUP_BLOCKED；项目source_contract_pytest插件也未被执行。
W01/W02相邻pytest子集同样NOT_RUN，原因相同，不将它们标skip或通过；未扩大至全量/集成测试。

采用任务书允许的标准库离线测试，测试类同时支持将来pytest正常收集：

```text
python -B -m unittest discover -s tests/unit -p test_perf03_lnx_w04a_offline_contract.py -v
python -m ruff check scripts/perf03_lnx_w04a_offline_contract.py tests/unit/test_perf03_lnx_w04a_offline_contract.py
python -B -m scripts.perf03_lnx_w04a_offline_contract --check
```

上述python表示本机已核验的现成3.12.0，不在文档写本机绝对解释器路径。
最终同源码20 tests、20 OK、0 failures/errors/skipped，2.745秒，exit0。
首次标准库合跑亦20 OK/0.423秒；后续仅因新增计划摘要与合成快照绑定负例而重验，不累计为40项。
Ruff最后exit0；两份新Python分别py_compile到项目外TemporaryDirectory，PASS，未在仓库新增pyc。
初次Ruff报告40项行长/闭包绑定问题，已仅在两新Python中拆长字符串/绑定lambda默认参数，
没有改变lint规则/降低断言；后续format/check通过。补丁一次因上下文不匹配被工具拒绝，文件未改，
核对实际行后补入计划绑定；不是测试失败、Root执行或无限重试。

公共节点前缀：`tests/unit/test_perf03_lnx_w04a_offline_contract.py::W04AContracts::`。

| AC | 真实测试函数名（接上述前缀） | 本轮unittest | pytest |
| --- | --- | --- | --- |
| A01 | `test_A01_no_authority_or_real_execution` | PASS，exit0，无skip | NOT_RUN，启动缺pluggy |
| A02 | `test_A02_schema_fields_versions_and_strict_scalar_types` | PASS，exit0，无skip | NOT_RUN，启动缺pluggy |
| A03 | `test_A03_json_duplicate_nonfinite_utf8_size_and_depth` | PASS，exit0，无skip | NOT_RUN，启动缺pluggy |
| A04 | `test_A04_private_input_never_echoed` | PASS，exit0，无skip | NOT_RUN，启动缺pluggy |
| A05 | `test_A05_stdlib_ast_and_fresh_import_without_business_or_environment` | PASS，exit0，无skip | NOT_RUN，启动缺pluggy |
| A06 | `test_A06_hash_references_not_git_identity_and_wrong_values_refused` | PASS，exit0，无skip | NOT_RUN，启动缺pluggy |
| A07 | `test_A07_path_links_traversal_outside_and_file_types` | PASS，exit0，无skip | NOT_RUN，启动缺pluggy |
| A08 | `test_A08_canonical_plan_digest_order_and_content` | PASS，exit0，无skip | NOT_RUN，启动缺pluggy |
| A09 | `test_A09_plan_equal_is_not_input_equal` | PASS，exit0，无skip | NOT_RUN，启动缺pluggy |
| A10 | `test_A10_r1_fixed_input_values` | PASS，exit0，无skip | NOT_RUN，启动缺pluggy |
| A11 | `test_A11_other_seed_and_protocol_refused` | PASS，exit0，无skip | NOT_RUN，启动缺pluggy |
| A12 | `test_A12_timestamp_inventory_and_unresolved_never_ready` | PASS，exit0，无skip | NOT_RUN，启动缺pluggy |
| A13 | `test_A13_utc_microseconds_and_timestamp_differences` | PASS，exit0，无skip | NOT_RUN，启动缺pluggy |
| A14 | `test_A14_typed_values_never_collapse` | PASS，exit0，无skip | NOT_RUN，启动缺pluggy |
| A15 | `test_A15_pk_duplicates_and_canonical_row_column_table_order` | PASS，exit0，无skip | NOT_RUN，启动缺pluggy |
| A16 | `test_A16_every_declared_column_is_required_and_hashed` | PASS，exit0，无skip | NOT_RUN，启动缺pluggy |
| A17 | `test_A17_root_lifecycle_error_cancel_not_seed` | PASS，exit0，无skip | NOT_RUN，启动缺pluggy |
| A18 | `test_A18_historical_verification_cannot_upgrade_target` | PASS，exit0，无skip | NOT_RUN，启动缺pluggy |
| A19 | `test_A19_all_twelve_gates_cannot_authorize` | PASS，exit0，无skip | NOT_RUN，启动缺pluggy |
| A20 | `test_A20_four_files_original_reports_and_sources_unchanged_no_writes` | PASS，exit0，无skip | NOT_RUN，启动缺pluggy |

20个方法含多组subTest，数量不重复累计；A16逐106输入列做缺失与改值检查。
测试A20保护两个旧报告和16份明确旧文件字节；全仓tracked/四文件范围另由交付Git检查核实。
本轮没有编写Root/数据库变更，因此不运行完整后端pytest或全仓Ruff；当前限定离线范围遵从用户任务书。

## 7. G01～G12与残余风险

| gate | 当前状态 | 新增设计证据 / 仍缺 |
| --- | --- | --- |
| G01 | NOT_AUTHORIZED | 本轮离线开发不是单次真实Root许可 |
| G02 | MISSING | ENVIRONMENT_SPEC_DEFINED；VM/CPU/内存/IO/owner租约未实证 |
| G03 | PARTIAL | 原67包历史参考保留；新目标3.12.14/ABI/完整安装NOT_VERIFIED |
| G04 | MISSING | PG17物理身份/权限/清理合同定义；无实库核验 |
| G05 | MISSING | 时间列分类与PLAN_EQUAL/人工快照比较就绪；原seed未改、实体快照与影响NOT_VERIFIED |
| G06 | PARTIAL | 真实Root Adapter仍未实现，本轮不包装Mock |
| G07 | NOT_PROVEN | 首次spawn、watchdog自身syscall、D状态未证明，配额/外部截止待裁决 |
| G08 | PARTIAL | 计划/输入格式严格绑定，真实两臂资源与值同一性无证据 |
| G09 | PARTIAL | 本轮106输入列不是Root全列/identity闭包校验，W04-C待单独开发 |
| G10 | NOT_PROVEN | 真实OS回收与独立持久确认无实现/验收，不能消费Mock ticket |
| G11 | PARTIAL | 旧工程CI不代替本轮pytest或未来真实运行批准 |
| G12 | PARTIAL | 外部停止/已归属资源销毁原则明确，实机回收仍NOT_PROVEN |

DESIGN_DEFINED→SOURCE_REVIEWED→TARGET_VERIFIED→EXPERIMENT_AUTHORIZED是四类独立证据，
不是自动递进状态机；本模块不能签发后两种。UNRESOLVED与已识别但影响未验证都保留NO_GO。

## 8. 后续最小授权顺序与交付摘要

1. 负责人裁决候选机器/预算/owner/独占租约和安全边界；另批创建资源，当前vm_created=0。
2. 另批目标PG17物理身份/最小权限及3.12.14/67包真实安装核验，拒绝借用历史runner资格。
3. 独立批准原R1 seed逐列最小冻结方案与业务影响验收，真实输入表schema/trigger/值/序列快照及外部owner确认；
   本轮候选常数或W04基准快照方案均不是已批准实现。
4. 另批受限真实Root Adapter/外部监督的接口与离线故障合同，保留不可抢占尾部风险和fencing责任。
5. 另批W04-C真实全列/身份闭包比较器与golden，包括错误/取消/未知ACK，不用本输入比较器冒充结果比较。
6. readiness重新逐门禁审阅；仅实证齐备及残余风险被负责人明确接受后，申请一次OFF1→ON1许可，禁止自动继续六臂。

| 新文件 | SHA256 |
| --- | --- |
| `docs/acceptance/biz_perf_03_a_r1_lnx_w04a_contract.json` | `0f464a6acc4efc651fdea798fac1b0b4b3b61069147515115afa5b9f2d91d2f8` |
| `scripts/perf03_lnx_w04a_offline_contract.py` | `b11a4a2b8e6da6224ab8c503130073bef5ace9ec701dbf43649e116c0be6c5a0` |
| `tests/unit/test_perf03_lnx_w04a_offline_contract.py` | `f3232a88f0be68ca710ffba337e8dcfae9fa096d54a681ee8dc2eb760efce2ef` |

本报告自身SHA256在最终P0_LNX_W04_A_01_DELIVERY_REPORT给出，不能把自hash嵌入原字节形成循环。
最终静态检查覆盖四文件UTF-8/尾随空白/普通文件/白名单、引用路径与JSON定义一致性、
tracked/staged diff为空、原W03/W04摘要不变；不把空git diff --check当成untracked文件已受检。
本地pytest缺依赖是明确未执行项；20项标准库通过不升级为完整pytest验收。
commit=NOT_COMMITTED；push=NOT_PUSHED；new_ci=NOT_TRIGGERED。
pg_connections=0；workers=0；off_on_pairs=0；capacity=0；vm_created=0；containers_created=0；
actions_dispatches=0；deployments=0。结束等待ChatGPT独立审阅，不自动补装环境或申请真实执行。

## 9. 固定回执字段

```text
baseline_sha = head = origin_master = remote_master = b6ffb7bf8ec7d26f771d9b89923e4f7e926edbed
tracked_diff = EMPTY; staged_diff = EMPTY
untracked_inventory_before = [W03_PREFLIGHT.md, W04_READINESS.md]
untracked_inventory_after = [以上两份原件, 本报告, contract.json, offline_contract.py, test_offline_contract.py]
source_review_count = 9 pinned source artifacts; ORM inventory = 37 tables / 520 columns
seed_timestamp_columns_resolved_unresolved = 49 / 0 (classification only; not behavior verified)
schema_version = perf03-lnx.w04a.offline-readiness.v1
implementation_paths = 本报告第2节四个精确路径
AC01_to_AC20 = 本报告第6节20个真实节点，每项unittest PASS，pytest NOT_RUN
pytest = NOT_RUN / STARTUP_BLOCKED (missing pluggy, exit1)
ruff = RUN / PASS (exit0)
py_compile = RUN / PASS
experiment_decision = NO_GO; R1 = PARTIAL; AC05 = PARTIAL
blockers = pytest runner; target resources/PG/dependencies; seed behavior and physical input; real adapter/supervision; W04-C result closure; explicit experiment authorization
next_authorization_needed = 本报告第8节六个切片，逐一独立授权
```

untracked缩写仅用于摘要；四个精确新增路径在第2节，两个原件精确路径及SHA在第1节。
交付状态W04A_BLOCKED来自pytest启动缺口；不将20项替代测试写为pytest通过。
