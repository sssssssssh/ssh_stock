# V1.4-A4-1：性能基线与问题定位

## 范围与状态

仅 W00/W01。没有修改生产 SQL、索引、锁、指纹、候选校验、计算公式、版本、
事务或发布预算；没有进入 A4-2 SQL 方案改造或阶段 B/C。
`AB_MERGE_READ_ENABLED=false` 保持不变。未连接阿里云数据库，未操作业务服务/任务。

`READ_PERFORMANCE_OPEN`。本报告是诊断基线，不是性能优化关闭或上线许可。
主 CI、专用诊断 CI 的最终 exact-HEAD 结果未同时 SUCCESS 前，代码验收也为 OPEN。

## 冻结与可复现性

- 审阅/生产读链路：`4b158c10f22119374c2e0891308ba935ff91d4ca`。
- Q0 TEMP VIEW 定义：`c9f3b1a977c56698436d0ec4b29b6b154ed0fe55`；
  冻结源 SHA256：`99db843a6840df5210cfffccd032727a4337539efe6ca44118f240b1134d4657`。
- `scripts/ab_read_profile_v14_a4.py` 在业务配置导入前验证显式测试 URL、PG17 实例标记和
  物理 system identifier；随后才创建 UUID 数据库并执行正式 Alembic。
- 启动时将七份生产源码与审阅提交逐字节比较；不同即拒绝。哈希保存在每份原始 JSON。
  诊断前后生产读链路无修改；测试态 monkeypatch 在 finally 恢复，不进入应用入口。
- Python 3.12、SQLAlchemy/psycopg/pandas 实际版本、Git HEAD/dirty、脚本 SHA256、索引、
  ANALYZE 时间、参数、表/索引大小、数据分组均保存于原始 JSON。
- 本地主表诊断脚本 SHA256 为
  `b5d209d7adf847f315dc88448f8ed96d236f5e1563b4e1dda9fe1b5ebc5f1d0b`。
  本地读链路固定于审阅 SHA，诊断文件尚未提交时 `dirty=true` 如实保留；
  不能冒充最终提交的 exact-HEAD CI。提交后的 CI 独立生成含最终 HEAD 的三规模原始收据。
- 本机 8 核、8 GiB；新建物理隔离 PostgreSQL 17.11，独占容器限额 2 CPU / 3 GiB，
  loopback TCP，不是 Windows→云端链路。业务容器仍停止。
- 不清 OS/PG 缓存：`cache_control=UNCONTROLLED`、`cold_cache=UNPROVEN`。
  不能把第一轮称为受控冷缓存，也不能把后续轮称为完全受控热缓存。

每个规模的三轮顺序为 Q0/Q1/Q2 → Q1/Q2/Q0 → Q2/Q0/Q1，串行执行，
没有并发完整 pytest、其他压测或负载生成器。独立逻辑读试验从空的 root-local 读集开始；
T7 专项保留跨月读集。只重置测试进程的内存证据，不修改持久候选或尝试发布。

### 测量口径

1. Q0 精确保留旧 benchmark 的路径，包括没有逐批 checkpoint、不做最终全局排序的事实。
   另测 `q0_service_control`，沿用真实 `read_calculation_frame()` 的逐批任务检查，
   不把它偷偷替换为原 26.191 秒的对照。
2. `seconds` 为完整读取直到 DataFrame 就绪：Q1/Q2 的准备、锁、指纹、候选验证、日历、
   所有命名游标 FETCH、checkpoint、DataFrame 和最终排序均在内。
3. `final_verify_seconds` 单列 T8；`read_plus_final_verify_seconds` 为读取与 T8 函数之和，
   不含额外提交/取得锁的往返。汇总另从原始 offset 计算
   `read_to_final_verify_trace_span_seconds`，覆盖读取起点至复核返回的完整诊断跨度。
   Golden 归一化/摘要、EXPLAIN、独立锁试验不计入读取时间，不冒充性能收益。
4. T3/T8、prepare/其内部 SQL 等是嵌套计时，禁止全部相加。独占可观测分项另存
   `read_wall_components_seconds`；Python/SQLAlchemy/progress/观测器剩余项不是纯网络。
5. 真正 psycopg ServerCursor 保存 DECLARE 模板、游标名、每次 FETCH 请求/返回行数与耗时、
   关闭状态。SQLAlchemy 首次 FETCH 1 行，再取 4999 行组成首批，随后 5000 行；
   不能把逻辑 5000 行批次谎称每个线协议 FETCH 都是 5000 行。
6. 普通 SELECT 的 `EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON)` 与 `EXPLAIN DECLARE` 分开保存。
   新增独立 untimed auto_explain 完整游标探针：节点计时关闭，保留实际 rows/loops/buffers；
   timed trials 不加载该观测。SELECT 计划不能冒充真正游标执行计划。
7. 驱动 FETCH 包含 PG 执行、传输、解码；无法精确拆开，网络/PG/解码分别为 UNPROVEN。
   cgroup CPU 包括隔离 PG 的 WAL/checkpointer，不是某一 backend 的纯 CPU。
   pg_stat_statements、temp、buffer/WAL 原始计数保留，不把嵌套 SQL 执行时间相加。
   PG buffer read 也不是物理磁盘读取字节；后台 autovacuum 未禁用，主表收据记录维护状态。
8. RSS 同时给出进程累计高水位和 0.5 秒采样下界；累计高水位不是某次读取的独立峰值。
   `frame_deep_bytes`/跨月累计帧字节不是线协议传输字节；线协议字节仍 UNPROVEN。

`T2_lock_acquire` 是取得锁的完整往返时间（含等待），不是已剥离网络的纯等待。
读后 commit 是诊断边界，测得的持锁时长仅为实际 FactorService 事务的**读阶段下界**；
真实业务还会计算和暂存后才 commit，本报告不伪造其完整持锁上界。
hold 计时止于客户端提交请求，未独立剥离 COMMIT 往返；T8 跨度也不是完整原子发布耗时。
观测口径参考 [PG17 auto_explain](https://www.postgresql.org/docs/17/auto-explain.html)、
[EXPLAIN](https://www.postgresql.org/docs/17/using-explain.html) 和
[累计统计](https://www.postgresql.org/docs/17/monitoring-stats.html)：
计划探针会增加开销，因此与 timed FETCH 隔离；统计快照及后台维护也不能当作纯磁盘根因。

### 合成数据

与旧样本对齐：百万级交易状态 A=2,570,000，当前 B=1,350,000，其他 root B=2,800,000。
保留 stock-major、257 个 2024 合成工作日、NULL、错版本 B、1% tombstone、部分覆盖/新键。
其他 B 不再全是状态行：使用 Factor 全字段、原生 double precision 和明确的合成 NULL 分布，
不是向 status_reason 填随机长字符串来伪造通用表体积。NULL 分布仅用于行宽校准，
不声称是指标引擎输出或线上采样，也不改变当前 root 的 A/B/删除/错版本分布。
先完成的压力样本保留 140 万条真实 Factor 首次原像；校准主表的其他 root 为新 Factor 键，
首次原像为 NULL，当前 root 仍保留 642,500 条实际状态 A 原像。
辅助 Factor 公开 A 单列统计，不与 257 万交易状态 A 混算。
其他 root 只是私有候选多表负载，不尝试发布，也不以它替代真实十表发布链路的 Golden。

主表实际候选表本体（含 TOAST）为 **5,984,976,896 bytes**，索引另为 **1,054,900,224 bytes**，
合计 **7,039,877,120 bytes**。这里“约 6 GB 表”绝不表示“含索引总共 6 GB”。
压力样本本体 8,056,160,256、索引 995,876,864，合计 9,052,037,120 bytes；
两种样本不能跨表直接比较时间来宣称提速。

为复现旧小样本，1 万行仍采用冻结 helper 的 1/4 code 偏移；10 万/百万采用 3/4 偏移。
因此规模斜率只对覆盖比例一致的 10 万→百万做有限差分，不用三点强行拟合因果关系。
合成日历不是中国真实节假日日历；相关边界由现有集成回归覆盖。

## 实测结果

以下为同一诊断脚本、同一生产读链路、三轮交替的真实测量，单位秒。
p95 为 n=3 的 inclusive 分位数，仅描述样本，不宣称统计显著或受控冷/热缓存。

| A 输入规模 / 输出行数 | Q0 p50 / p95 | Q1 p50 / p95 | Q2 p50 / p95 |
|---|---:|---:|---:|
| 10,000 / 9,471 | 0.082 / 0.084 | 0.175 / 0.187 | 0.712 / 0.723 |
| 100,000 / 120,592 | 0.741 / 0.830 | 1.776 / 3.133 | 2.187 / 2.192 |
| 2,570,000 / 3,104,443 | 35.777 / 51.643 | 64.406 / 67.709 | 65.983 / 70.100 |

百万级原始读取样本，未剔除第一轮慢值：

- Q0：53.405665500、35.777468625、35.227016542。
- Q1：68.076343083、62.975951042、64.406095250。
- Q2：70.557396250、63.840527375、65.982762708。

Q1/Q2 相对本轮 Q0 中位数分别增加 **28.629 / 30.205 秒**；不存在已完成的优化收益。
包含跨事务最终复核的诊断跨度 p50/p95：Q1 **89.536 / 90.141**，
Q2 **86.346 / 93.246**。Q0 没有新增 T3/T4/T8 保护，不能把其 35.777 秒解释为
安全等价实现的全部成本。另测真实逐批 checkpoint 的 Q0 service control 为 **36.406 秒**，
只有一次控制样本，不当作三轮中位数。

所有百万级独立读和三个月重放均为 3,104,443 行，六列及 dtype/NULL 摘要一致：
`38c31457a657816e1cde97dfbab281b8d6bdee69b6951519785bdaa54d096f02`。
现有集成测试另外保持逐字段严格断言及真实十表发布链路，不用摘要替代这些断言。

### 时间消耗在哪里

下表为百万级每次**读取内部互斥分项**的 p50 / p95；T8 另列，不与总 T3 重复相加。
各分项的中位数之和不必等于整段中位数；原始逐次值、嵌套计时、FETCH 分布均在证据 JSON。

| 分项 | Q0 | Q1 | Q2 |
|---|---:|---:|---:|
| T1 日历和窗口生成 | 不适用 | 不适用 | 0.011 / 0.019 |
| T2 读取期锁获取往返 | 无新增锁 | 1.011 / 1.012 | 0.001 / 0.905 |
| T3 首次公开 A 指纹 | 无 | 25.841 / 26.280 | 20.925 / 21.189 |
| T4 当前 root 全 B 校验 SQL | 无 | 5.901 / 6.834 | 5.547 / 5.552 |
| T5 DECLARE 合计 | 0.007 / 0.009 | 0.012 / 0.013 | 0.186 / 0.188 |
| T5 原生驱动全部 FETCH | 25.318 / 40.945 | 22.260 / 23.704 | 25.922 / 30.758 |
| T6 DataFrame 构造 | 4.730 / 5.269 | 4.457 / 4.654 | 5.391 / 5.394 |
| T6 Python 最终排序 | 无 | 0.361 / 0.363 | 0.439 / 0.446 |
| checkpoint | 原基准无 | 1.337 / 1.367 | 1.501 / 1.564 |
| Python/SQLAlchemy/观测等剩余项 | 5.944 / 6.109 | 4.037 / 4.290 | 5.323 / 5.498 |
| T8 最终复核（读取外） | 无 | 22.113 / 24.816 | 21.416 / 23.234 |

reset_index 每次不足 0.0001 秒，原始值仍保存。锁获取约 1 秒的样本存在，但没有足够证据
将这 1 秒全部归为锁冲突；该计时包含往返及服务端执行，不能伪造纯等待数字。

**结论（依据本轮证据的推断）：** 额外首次全 A 指纹和全 B 校验是本轮 Q1/Q2
端到端倒退的主要新增项；DataFrame 排序不是主要瓶颈。最终复核还需要第二次全 A 指纹。
窗口化没有消除这些准备成本，也没有保证 SQL/FETCH 更快。不能简单删掉这些安全保护。
旧探索样本 26.191/80.008/127.610 来自非最终源码与不同负载/行宽/缓存状态，
没有完整 T1–T8 收据；**无法追溯分摊旧样本的约 54/101 秒**，本轮不能伪称精确重现其每一秒。

10 万→百万同覆盖比例下，每新增 100 万条当前 B 的有限差分（秒）：

| 分项 | Q0 | Q1 | Q2 |
|---|---:|---:|---:|
| 完整读取 | 27.003 | 48.271 | 49.169 |
| T1 日历/窗口 | 0 | 0 | 0.003 |
| T2 读取期锁获取往返 | 0 | 0.778 | −0.000（近零噪声） |
| 首次指纹 | 0 | 19.329 | 15.577 |
| 候选校验 SQL | 0 | 4.447 | 4.204 |
| DECLARE 合计 | 0.003 | 0.008 | 0.091 |
| 全 FETCH | 19.220 | 16.858 | 19.562 |
| 构帧 | 3.533 | 3.319 | 4.025 |
| Python 排序 | 0 | 0.268 | 0.327 |
| reset_index | 0 | <0.001 | <0.001 |
| checkpoint | 0 | 0.987 | 1.002 |
| Python/SQLAlchemy/观测等剩余项 | 4.417 | 2.949 | 3.809 |
| 最终复核 | 0 | 16.475 | 15.938 |
| T7 三块读取总和 | 61.616 | 139.172 | 160.990 |

分母是 (1,350,000−52,529)/1,000,000；A、其他 root B、总表体积同时增大，
因此这是**联合规模变化的观测斜率**，不是单独增加 B 的因果导数或复杂度证明。
逐项可由同一 JSON 的 `read_wall_components_seconds` 按相同公式复算。
T7 是三个输入块的成本总和，不能再加到独立全年读或 T1–T6 上。

### 实际 SQL 计划与 FETCH

所有计划探针在计时试验结束后单独执行；以下 cursor 指真正 DECLARE 后全量 FETCH 的
auto_explain 实际 rows/loops/buffers，非普通 SELECT 的替代值。

- Q0：Append + Hash Anti Join；B 输出走日期索引，遮蔽键走主键 Index Only Scan，
  1,350,000 条遮蔽键、Heap Fetches=16。顶层 shared read=1,333,943 blocks，
  temp read/write=21,159 blocks。公共 A Seq Scan 的当前身份输出 2,434,736 行。
- Q1：实际游标为 **Sort + Append + Hash Anti Join**，external sort，磁盘排序空间
  97,016 KiB；顶层 shared read=2,539,608，temp written=57,575 blocks。
  遮蔽侧改走日期 Index Scan，实际 1,350,000 行；该节点 shared read=1,227,992，
  与 Q0 的主键 index-only 路径不同。普通 SELECT 则为 Gather Merge，执行 10.697 秒；
  **不能用这个 SELECT 数字宣称游标只耗时 10.697 秒**。
- Q2：每次独立读 53 个窗口，52 个非空；代表性首窗/中窗输出 60,397/60,395 行，
  quicksort 3,896 KiB 内存排序、Hash Anti Join、公共 A Bitmap Heap Scan；
  候选输出和遮蔽侧各走日期 Index Scan。顶层 shared read=60,226/60,930 blocks。
  最后一窗为空；只采首/中/末三个实际计划，不冒称全部 53 窗计划都已分析。
- T3：公开 A 主键 Index Scan 实际读 2,570,000 行，聚合为 257 个逐日指纹；
  普通 SELECT ANALYZE 约 19.943/20.128 秒，支持全范围序列化/哈希成本显著这一判断，
  不能把其节点时间差全部归为某一 CPU 函数。
- T4：`SELECT EXISTS` 在没有坏行时仍过滤当前 root 全部 1,350,000 条 B；
  实际约 5.094/5.018 秒，不能因 EXISTS 的估计成本小而当作 O(1)。

Q0/Q1 每次真实 FETCH 623 次，Q2 为 774 次；均完整取回 3,104,443 行且关闭游标。
每轮原生 FETCH p95：Q0 0.266933/0.063692/0.061212 秒；
Q1 0.008949/0.009339/0.009388 秒；Q2 0.450819/0.422557/0.411133 秒。
Q1 的首行等待为 21.057/19.284/17.841 秒，首 5000 行为 21.082/19.296/17.848 秒，
均以游标创建为起点，**未包含此前 T3/T4**。Q2 非空窗首行 p50 为
0.520/0.446/0.437 秒，不能只看单窗首行快就忽略全部窗口总成本。

据此后续 A4-2 应同时实验查询形态/规划、窗口和安全核验重复成本；
本阶段没有选择 S1–S6 最终方案，没有设置 planner hint、移除锁/指纹或新增索引。

### 锁、跨月重复及资源

两次事务的持锁总和 p50/p95：Q1 89.501/90.076 秒、Q2 86.317/93.217 秒；第一段读事务持锁约
Q1 62.964–68.026 秒、Q2 63.829–70.547 秒。它们是前述读阶段下界。
独立双连接锁试验在公开表和通用 B 表均得到：SHARE 持有时零行 UPDATE 在约
0.215/0.208 秒以 55P03 失败；DML 持有时 SHARE 获取约 0.213/0.213 秒以 55P03 失败。
RR 公共读者 SELECT 成功，约 0.014/0.003 秒。这是受控小型锁试验，不是生产读者延迟 SLA。
新增回归另外验证读后 commit、旁路更改 A、最终 T8 必须失败关闭，不返回成功发布。

T7 重放 2025-01/02/03，输入从各月首日向前 430 自然日开始，分别为
2023-10-29、2023-11-29、2023-12-27。每月再次读相同 2024 历史：

| 变体 | 三个月读取总秒数 | 各月读取 p50/p95 秒 | 输出逻辑总字节 | 采样最大客户端 RSS |
|---|---:|---:|---:|---:|
| Q0 | 82.230 | 26.646 / 28.845 | 1,267,329,525 | 1,389,740,032 |
| Q1 | 185.769 | 61.912 / 62.366 | 1,267,329,525 | 1,579,188,224 |
| Q2 | 216.488 | 73.156 / 76.914 | 1,267,329,525 | 1,652,867,072 |

此处月度分位数描述三个不同输入块，并非同一月份的三次独立重复试验。

Q1 每月一个窗，Q2 每月 66 窗。保留 root-local 读证据后，指纹范围累积自
2023-10-29 至各月月底；每月重新扫描同样 257 万 A，重新校验 135 万当前 B。
额外每月 T8 只是本诊断的独立采样；生产的最终复核次数不可据此乘三。
以上 RSS 是进程分配复用和 0.5 秒采样共同影响的下界，不是三份 DataFrame 同时驻留。

独立全年读取每帧 422,443,175 逻辑字节；客户端读阶段 CPU p50：
Q0 12.179、Q1 10.387、Q2 13.129 秒。隔离数据库**整个容器**在读取+T8间的
CPU delta p50：22.582、72.668、71.744 秒（Q0 无 T8）；口径不同，不做纯 backend 对比。
逐次 RSS、PG buffer/temp、维护快照保存在摘要，逐语句 WAL、原始 cgroup I/O
保存在原始 JSON。Q1 数据库 temp delta 三次为 283,475,696 / 283,479,424 /
1,741,876,444 bytes，慢/大样本没有删除；统计时滞和后台活动使这些计数不能直接等同于
该 FETCH 的纯落盘字节。Q2 对应约 6.5 MB，说明少 temp **不代表完整读取更快**。

压力补充样本（9.052 GB，较早观测器）三轮中位数 Q0/Q1/Q2 为
46.257/65.673/76.701 秒；其摘要单独保留，不能与校准主表跨 fixture 宣称改进。
一份调试中的百万级 fixture 在任何读取前由本测试进程中断，保存 KeyboardInterrupt
失败收据且 runs=0；不纳入有效性能样本，也不当作成功或删除失败事实。

### 收据索引

主表三规模使用相同脚本 SHA256（见上），提交以下可直接审阅的去冗余证据；
保留所有逐次时长、摘要、dtype、FETCH 分布、阶段、范围、关键计划和原始文件 SHA256。
完整 DECLARE/FETCH 逐次记录、SQL、资源快照在本地 `.codex_tmp` 及 CI 上传的原始 JSON；
索引是投影，不冒充完整原始收据。

| 摘要 | 原始 JSON SHA256 |
|---|---|
| [1 万](evidence/v14_a4_primary_10k.json) | `e4c6c63a886a245360e56b3e196ad36e0239088ada060e6cf15f72e155fe61fc` |
| [10 万](evidence/v14_a4_primary_100k.json) | `005c21d38d539ede42510f5004111eb8e07747d0c899ba11ad59980699af2ace` |
| [百万](evidence/v14_a4_primary_million.json) | `d6bab930b042c0d45e55164140c773d8f9146228841df41ec09f0e4cddf5ba52` |
| [9 GB 压力补充](evidence/v14_a4_stress_local.json) | `5866f3718e0c2555d675caa491303cb8d8e60ddf1ae0f1b9a7c7f0fe701b689c` |

## T1–T8 证据索引

| 分段 | 诊断原始字段 / 验证 |
|---|---|
| T1 | calendar_inclusive、calendar_sql、每窗指标 |
| T2 | lock_acquire、事务 lock_hold、独立 SHARE/DML/RR 锁试验 |
| T3 | fingerprint_inclusive、lo/hi、实际 A 逐日行数、指纹 SQL 的扫描计划 |
| T4 | candidate_validation_sql、当前 root 全 B 数量/计划；prepare 包含其上层成本 |
| T5 | DECLARE/FETCH、首行/首 5000/每窗全量、普通 SELECT/游标估计/独立实际游标计划 |
| T6 | frame/sort/reset_index、client CPU、驱动 FETCH、映射/进度等剩余项 |
| T7 | 实际 `_month_chunks()`、每月输入 start−430 自然日、重复范围/次数/字节/RSS |
| T8 | verify_inclusive、第二次公开指纹、跨 commit 旁路写的失败关闭回归 |

T4 验证的是冗余键/载荷身份，不等于最终发布所有来源证书验证；
`finish_publication()` 的其余来源/质量/身份/CAS/原子发布流程没有被跳过或改写。
T7 只重放真实输入边界的读阶段，不运行指标引擎、不暂存或发布；
诊断额外单列逐块 T8 采样，不能当作实际完整任务的耗时。

## 复现

先创建**独立** PG17，设置随机 `v14.test_instance`、记录其 `pg_control_system()` ID，
预加载 pg_stat_statements 并打开 track_io_timing；只能指向合成 `_test` 父库。
设置 `TEST_DATABASE_URL`、`V14_TEST_INSTANCE`、`V14_TEST_SYSTEM_IDENTIFIER`，
禁止读取/复用业务 `.env` 目标。完整流程见 `.github/workflows/ab-read-a4-baseline.yml`。

```bash
python scripts/ab_read_profile_v14_a4.py --multitable --service-control --monthly \
  --output .codex_tmp/v14-a4-10k.json
python scripts/ab_read_profile_v14_a4.py --public-rows 100000 \
  --candidate-rows 52529 --other-rows 108949 --multitable --service-control --monthly \
  --output .codex_tmp/v14-a4-100k.json
python scripts/ab_read_profile_v14_a4.py --public-rows 2570000 \
  --candidate-rows 1350000 --other-rows 2800000 --multitable --service-control --monthly \
  --output .codex_tmp/v14-a4-million.json
```

`--container` 仅可指定标有 `purpose=ssh-stock-a4-physical-test` 且实例标记相同的测试容器，
用于读取 cgroup 计数；省略则资源归因为 UNPROVEN。不得将业务容器作为该参数。

## 验证、CI 与未解决项

本阶段修改文件仅包括：

- 两个 `scripts/ab_read_profile*_v14_a4.py`：隔离观测及可复现摘要。
- 新增单元/真实 PG17 集成测试，以及既有 workflow 工件边界测试的新增参数。
- `.github/workflows/ab-read-a4-baseline.yml`：独立三规模诊断；
  主 `ci.yml` 只为其专用测试 PG 增加统计预加载，不删除或放宽任何已有门禁。
- 本报告、四份证据索引、README、PROJECT_RULES、PRD、系统设计。

`backend/`、`migrations/`、`config/`、`frontend/` 的 diff 均为空。
没有生产模型、迁移、依赖、Compose 或业务 UI 变更，因此本地未重跑前端构建、
浏览器操作或 Compose 镜像构建；原主 CI 的这些门禁仍保留。

| 验证 | 本地结果 / 证据 |
|---|---|
| 定向单元与 PG17 集成回归 | 70 passed，0 skipped，147.338 秒；`.codex_tmp/v14-a4-targeted.xml` |
| 完整 pytest | 2,250 passed，0 skipped，492 warnings，1876.30 秒；`.codex_tmp/v14-a4-full-final.xml` |
| Ruff（backend/tests/migrations/scripts） | PASS |
| git diff --check | PASS |
| 隔离父库 Alembic upgrade/current/heads | PASS；current=head=`0058_data_publication` |
| 生产源码冻结 | 七份源码与审阅 SHA 逐字节一致 |
| 三规模诊断 | 每规模 9 次独立读、9 次跨月读；完整 FETCH/Golden/游标关闭 PASS |
| exact-HEAD 主 CI / 专用诊断 CI | 提交前尚未执行本提交的运行；均成功前代码验收 OPEN |

前一审阅 SHA 的主 CI 仍在既有 `Cold start L1 L2 L3 isolated publication capacity` 步骤，
不是新 A4-1 诊断结果；不取消、不跳过、不缩小该已有门禁。
提交后的具体 run URL / conclusion 在交付消息中核对，不能借旧 SHA 的绿色结果放行。

首轮完整回归为 2,247 passed / 3 failed（`.codex_tmp/v14-a4-full.xml`），未覆盖失败收据：
两项发现摘要工具对缺少时间字段的不完整游标收据先抛 KeyError；已将游标完整性检查
移至跨度计算之前，仍严格抛 `A4_INCOMPLETE_OR_UNCLOSED_CURSOR`，不修改或放宽断言。
另一项是本地命令的全局 `LLM_ENABLED=false` 遮蔽原有 dotenv 测试的临时 true；
最终重跑移除该全局覆盖，确认实际默认仍为 `tools_only` / llm_enabled=false，2,250 项全部通过。
上述相关 17 项重验 PASS（`.codex_tmp/v14-a4-recheck.xml`）；业务配置和既有 LLM 测试未改。
修复仅涉及摘要整理顺序，计时器脚本 b5d209d7… 和所有性能原始收据均未改变。

- 原样保留 READ_PERFORMANCE_OPEN、默认开关关闭、300 秒/1000 万行保护。
- 未获得受控冷缓存、Windows→云端 RTT/资源、阿里云真实故障复现或生产验证。
- A4-2 方案实验与 ADR、A4-3 实现、A4-4 全专项关闭、A4-5 最终回退手册尚未开展。
  本阶段等待审阅，不以诊断代替后续优化交付。
