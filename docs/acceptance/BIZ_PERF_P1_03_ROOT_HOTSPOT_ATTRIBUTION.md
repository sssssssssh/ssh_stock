# BIZ-PERF-P1-03 重算整链热点归因

**决策为 `ROOT_HOTSPOT_NOT_PROVEN`。当前根任务热点为 `NONE_PROVEN`，下一改造点为 `PROVISIONAL`。** 优先核查 `backend/app/services/factors/engine.py::calculate_stock_factors` 的合并、分组滚动和排名。当前交付只有历史证据归因，现有开关维持默认。按下文提议补齐单根观测后再决定是否选定一个函数。

## W01 当前源码调用链与计量边界

| 阶段 | 冻结源码入口与调用链 | 计量范围 |
|---|---|---|
| Worker 编排 | `job_worker.execute_claimed_job → run_recalculation`。先校验交易日，`_factor_warmup_start` 从起点向前保留 250 个交易日，`_month_chunks` 将分析区间切成自然月。每段检查取消、更新进度、调用 `FactorService.recalc`，写候选并提交检查点。 | 请求月数和实际因子段数分别记录。Worker 包装器的根 wall 自 wrapper 建立 trace 至生成报告时，涵盖执行及清理。合成测量器的 `overall` 自 create/claim 前到终态 Job/ledger 读取后，排除 Seed、随后独立摘要核验和实例销毁。两者边界不同。 |
| Raw 前置 | `validate_recalculation_raw_prerequisites` 先一次有序读取开市日。默认每个开市日调用一次 `check_raw_completeness(persist=False)`；可选 `check_raw_range` 每自然月构造一个 `RawRangeFacts`，持 SHARE 锁、按批读，仍逐开市日做相同判定。 | 应分别记录开市日数、月批数、前置阶段 wall、SQL 调用及读行。当前版本和规模实测值 `UNKNOWN`；历史该阶段的 progress delivered=0 表示旧进度计数，不能代替驱动返回行数。 |
| 因子输入 | `FactorService.recalc` 每段从起点回看 430 日历日，依次读 stock_daily、stock_adj_factor、stock_basic、stock_trade_status_daily、index_daily；stock_basic 无日期谓词。默认经 `read_calculation_frame` 每批 5,000，完整输入只组一次帧，两个有序查询保留原代码/日期顺序。 | `operation(name,"query")` 计 `db.execute`；`fetch` 计批返回前间隔，含传输和驱动物化，间隔还可能包含相邻循环开销。单独的 psycopg FETCH 包装计调用至返回及实际行数；二者口径有交叠。默认路径 `frame` 单独包住 `pd.DataFrame(rows)`。 |
| 滚动复用（默认 OFF） | `FactorInputWindow.prepare/verify` 原事务持 SHARE 锁，对五类公开输入和当前根任务候选做摘要。绑定 Owner、连接、事务和来源；后续裁剪历史块并只读新尾段，`blocks_to_frame` 还原全列并保留类型，缓存上限 1 GiB，发布前复核。 | 摘要 SQL、锁和快照验证是必要正确性成本。已有进度阶段 `factors.input_verify/input_frame`；实际独占摘要、锁等待、解码成本和净收益 `UNKNOWN`。默认路径上复用阶段应标 `NOT_INSTRUMENTED`。 |
| 因子计算 | `run_calculation("factors.compute", calculate_stock_factors)` 内执行日线/复权/上市/交易状态合并、代码/日期排序、按股 MA/ATR 和回撤等 rolling、eligible、按交易日全市场 RPS 排名及指数基准合并。 | `factor.compute` span 包住函数，`factors.compute` 为进度计时。退出函数后的 `to_dict("records")`、清洗及 metadata 属于输出转换，不能归给引擎；如无安全独立观测则标 `NOT_INSTRUMENTED`。 |
| 候选、质量及发布 | `replace_slice_rows → PublicationWorkspace.upsert → _lookup_batch/_store_batch`，每 500 条；保持当前候选优先、tombstone、首次 public 原像。后续校验质量与候选归属，`finish_publication` 校验身份、预算及来源，在既有事务边界原子发布并保留未知 ACK 保护。 | `lookup_candidate` 含 A/B 批查，`store` 与候选序列化、发布核验和 commit 有各自边界。发布 `publish_inclusive` 含子步骤；其耗时不能再与子项相加。保持 300 秒发布预算。 |

`execution_diagnostics` 按命名阶段记录 wall、次数、行数和错误计数，标注 `NESTED_PHASES_DO_NOT_SUM`。缺测和被限额丢弃的字段分别按 `NOT_INSTRUMENTED` 或 `UNKNOWN` 处理。SQLAlchemy 执行监听从 before_cursor_execute 到 after/error，可能包含驱动缓冲、网络及服务端等待，不能当成 PostgreSQL CPU。驱动 FETCH 是传输与物化，计行与业务唯一键行数、网络字节均不同。CPU 是进程 `process_time` 的区间差；RSS 是当前或进程累计峰值，不能作为各阶段独占 RSS。历史测量器的 `recent_stage` 标签可能把同阶段的检查点 SQL 也计入。时间项可能嵌套或口径不同；未求和或相减构造所谓独占耗时。

## W02 证据矩阵

### 历史样本的身份与复算

[历史总表](biz_perf_01/end_to_end.json)的 `samples[0].runs[0]` 和[原始试次](biz_perf_01/raw/1m-0-old.json.gz)的 `runs[0]` 一致，数据集、实现摘要和窗口一致。[baseline](biz_perf_01/baseline.json) 与 [after](biz_perf_01/after.json) 各 9 条，[总表](biz_perf_01/end_to_end.json) 与 [query_counts](biz_perf_01/query_counts.json) 各 18 条。逐条校验身份、请求月数、开关、状态与归档 SQL 计数/耗时/返回行字段。总表省略 dirty 属性，原始与 baseline/after 记录均为 dirty。该矩阵为旧版本的合成样本。[validation](biz_perf_01/validation.json) 保持 `PERFORMANCE_OPEN`。

下面三行共享同一身份。历史 SHA 为 `1e510532bd140110e29b10b6e4eed30fbd573159`，本地试次无 GitHub run/attempt。Windows 10 build 19045，8 逻辑 CPU，PG17.11 loopback，dirty tree，8 股、请求 1 月（250 交易日预热使因子实际分 13 段）。原记录的 `optimized=false`；各子开关实际值未在样本中独立登记。根任务 `SUCCESS/PUBLISHED`，历史 harness `overall=24.422 s`，进程区间 CPU `20.09375 s`，进程累计 RSS 峰值 `225,607,680 B`；阶段独占 CPU/RSS 为 `UNKNOWN`。

| 证据等级 | stage_name | stage wall（s） | 同条 wall/root 筛选比 | SQLAlchemy 标签次数 / driver execute（s） | psycopg 标签 FETCH 次数 / 行数 |
|---|---|---:|---:|---|---|
| HISTORICAL_SYNTHETIC | factors.compute | 10.657 | 43.64% | 26 / 0.032 | UNKNOWN / UNKNOWN |
| HISTORICAL_SYNTHETIC | recalculation.raw_prerequisites | 2.984 | 12.22% | 4,376 / 1.376 | 4,373 / 13,380 |
| HISTORICAL_SYNTHETIC | candidate_lookup_batch | 2.128 | 8.71% | 164 / 1.767 | 7,584 / 7,420 |

比值仅供筛选，标签内 SQL 或 FETCH 可能包括检查点，不归为引擎本身的数据库调用。完整脱敏矩阵另保存五类读、发布核验以及独立的驱动 FETCH 时间；同一记录的五类读阶段 wall 约 0.015–0.405 s/类，无法分摊 SQL/FETCH/组帧的独占成本。这里的历史 raw preflight 信号不能替代当前按日读取成本，也不能外推 150、752、2,165 股或当前 SHA。

### 其他证据与排除理由

| 来源 / 身份 | 等级、可用信号和限制 |
|---|---|
| [03-A 观测工件](biz_perf_03_a/) | 示例只有 schema/覆盖定义；offline overhead 为 `OFFLINE_FAKE` 的 CPU 计时，不是根证据。历史 PG17 Worker overhead 来自 `fe94bddc` dirty candidate，小型合成，归入 `HISTORICAL_SYNTHETIC`；它测试观测开销，未给当前根任务阶段分布。 |
| [R1 localization](biz_perf_03_a_r1/localization.json) 与 [verification](biz_perf_03_a_r1/verification.json) | 旧 SHA `32cf8f43…`，Windows 有界合成定位。OFF 以 `0xC0000005` 退出且无 receipt；ON 为 SUCCESS/PUBLISHED。该不完整历史记录排除出热点排名与对照；R1 三对开销和业务全等验收仍缺。 |
| [04-A](BIZ_PERF_04_A.md) | Run 41991816127 attempt 1，旧 SHA `057dfe86…`。历史终态 measurement 相比 last_phase 多 SELECT 8、UPDATE 3；逐条归属 `UNKNOWN`，不能归给心跳。该处只修复 SQLAlchemy 尝试计数冻结边界；控制连接与隐式事务不合计。 |
| [V1.3](v13_candidate_write.md) 与 [V1.4](v14_ab_read_closeout.md) | V1.3 历史 10 万行候选 SQL 840→420，批量实现已存在；不是逐行查询。V1.4 dirty A2 探索中同 3,104,443 行完整 FETCH 的 Q0/Q1/Q2 中位数约 26.191/80.008/127.610 s，条件和版本受限，不能作为当前结论。 |
| [P1-01](BIZ_PERF_P1_01_CANDIDATE_PREPARE_CLOSEOUT.md) | `OFFLINE_FAKE`。5,000 行候选准备段 P95 恶化约 37.3%，源码已撤回，结论 `NO_MEASURABLE_GAIN`。未测 PG/Worker 整链。 |
| [P1-02](BIZ_PERF_P1_02_FACTOR_MONTHLY_READ_CLOSEOUT.md) 与仓库外 `local_attribution.json` | `OFFLINE_FAKE`。Windows fake Session，旧 P1-02 基线 `1fbb98c5…`，S0 复用 OFF、S1 复用 ON，其他开关固定 OFF；50,000 行基档、6 月场景，四类带日期输入每类 6→6 次 fake 读、299,997→66,413 行，stock_basic 6→1 次、912→152 行。根状态/发布均未运行，root wall、真实 SQL/FETCH、阶段独占 CPU/RSS 均 `UNKNOWN`。候选 GREEN 只证明离线候选验证；5,000 行档 15 对未落盘，其余未运行，`INCONCLUSIVE`，源码已撤回。 |

`CURRENT_ISOLATED_ROOT=NOT_AVAILABLE`，`PRODUCTION=NOT_AVAILABLE`。当前根任务可核实热点栏为 `NONE_PROVEN`。

## W03 历史优先级与唯一补证方案

| 历史调查顺位 | 方向与等级 | 规模、原子安全与现有可测性 |
|---|---|---|
| 1 | **因子计算**，`factors.compute`，HISTORICAL_SYNTHETIC | 10.657 s 为同条最强阶段信号。每月全输入合并与滚动随行数和标的数扩张，RPS 保持全市场和 PIT。已有计算 span 可把引擎与读/写分开，函数内 merge 与 rolling 的独占分布仍未知。 |
| 2 | **Raw 前置与输入读取**，`recalculation.raw_prerequisites`，HISTORICAL_SYNTHETIC，辅以 OFFLINE_FAKE | 2.984 s 及 4,376 个旧 SQLAlchemy 标签调用；另有 430 日历日的重复窗工作量。应分开验证交易日质检、SQL、FETCH 与 DataFrame。不能只凭返回行数开启复用、减少预热或改 PIT。 |
| 3 | **候选查找、来源核验与发布**，`candidate_lookup_batch`，HISTORICAL_SYNTHETIC | 2.128 s，批处理已实施；候选量增加仍可能放大处理。当前 `FactorInputWindow.verify` 和发布预算下的锁/摘要独占成本未测。批查与发布有既有观测，安全风险最高；保留原像、候选遮蔽、质量、来源及原子边界。 |

**唯一拟议实验**为隔离 Linux 上 **8 股、1 个月请求、1 个确定性合成根任务、一次运行**。沿用 250 交易日预热和 430 日历日回看。固定审核过的干净 SHA、依赖、输入摘要、策略、资源与 Seed。冻结四个业务优化开关为 OFF，独立登记实际观测开关。只复用现有 `scripts/business_recalc_measure.py` 的单次本地合成测量路径及现有 root/SQL/FETCH/阶段记录，不使用历史一次性 Actions 控制模式、不加 profiler 或第二次对照。若现有观测无法提供安全可区分的阶段证据，保留缺项并停止。

- **准入与授权**。由负责人另批固定 SHA、合成 Seed、单根执行、专用 Linux 与 PG17 资源、执行者、只写合成 UUID 库、终止及清理权限。相关 owner 门禁未签前保持 NO-GO。实例须独占、与业务库网络隔离，使用非生产账户和独立 PGDATA。首次写前及清理前校验 PG17 major、实例随机 marker、离线 control 与在线 system identifier、卷/进程域和 Owner 归属。禁止沿用旧实例或默认连接。
- **拟议预算**。从实验启动到清理最多 20 分钟，预留最后 5 分钟用于回收。保留既有 300 秒发布预算和业务内存守卫。提请核准 Worker 独立 cgroup 3 GiB、PG 独立 cgroup 4 GiB、独占卷含日志和证据最大 10 GiB。任一身份、时间、空间、进程域或内存边界异常即停，保留已落盘失败前缀；清理前再次验归属，未知创建 ACK 不盲删。
- **验收证据**。记录同一 root identity 的开始/结束边界、Job SUCCESS / ledger PUBLISHED、发布质量与原子终态、表级计数和可复核摘要、root wall、各阶段/SQL execute/FETCH 行数与时间、CPU/RSS、观测缺失和退出状态。记录逐阶段语义，不能合计嵌套 wall。没有完整身份、终态、计时或业务验真则继续 `NONE_PROVEN`，不补跑。一次合成根观测仅用于定位当前受控规模，不能推导提速、正式 R1、生产或容量。
- **后续单热点与回退**。若完整根证据支持优先 A，再以相同输入核查 `calculate_stock_factors` 内哪一处有独立可复测成本，并为单一函数另行申请变更。必须保留精确输出列/类型/标量、窗口及 RPS 横截面语义、资格、排序、取消与发布边界；基准先逐样本持久化，再汇总；不等价或证据不足即撤回唯一候选补丁。当前不指定具体改法，也不扩大观测平台。

不采用新增日志套件、D04 扩建、默认开关调整、放宽门槛、直接改因子或 SQL、重跑旧失败实验或用生产库试读。当前结论为 `NEXT_HOTSPOT=PROVISIONAL`。
