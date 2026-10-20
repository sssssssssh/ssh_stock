# V1.4 阶段 A 审阅记录（未批准生产）

## 交付边界

| 工作包 | 当前状态 |
| --- | --- |
| A0 / W00-W01 | 基线冻结、专用物理 PG17、交易日守卫已实现并有本地回归 |
| A1-A2 / W02-W03 | 专用读取及窗口已实现，本地严格 Golden 通过，开关关闭 |
| A3 / W04 | 安全/游标/并发回归已补，性能与完整重负载矩阵未关闭 |
| B0-B3 | 未开始；须先通过阶段 A 验收并获得用户确认 |
| C | 可选项，未落地；不得自动创建原生临时缓存 |

本报告不是整份 V1.4 任务完成证明，`READ_PERFORMANCE_OPEN`，不批准生产启用。
本地回归不能替代最终 exact-SHA CI；完整核对及未执行项见末尾。

## A1：专用完整键读取

开始：A0 `60bfc33`。仅 FactorService._read_trade_status 可选择新仓储；
`AB_MERGE_READ_ENABLED=false` 默认关闭，性能门禁通过并经审阅后才显式启用。
无 workspace 使用公开表，不创建候选；有 workspace 必须沿用 ready 的 pinned connection，
根 ID 来自 workspace，不接受客户端 SQL/标识符/root 参数。没有新迁移。

Q1 双侧日期约束，候选输出排除 tombstone，A 遮蔽查询包含任何同完整键 B，
合并后才过滤版本/hash。全 root 检查 redundant date / row_key / live entity / payload 日期
与身份存在性；旧合法 tombstone.entity_key=NULL 由完整 row_key 证明，不能误拒绝。
取消检查和原游标读取保留；不直接写 A，不改首次 base_row，不改公式/版本或预热。

单次读事务 SHARE 锁防止多 SELECT 被旁路写者切换；不锁 root row，不阻止取消或普通 RR 读者。
跨阶段在 workspace 维护已读公开行全字段逐日 SHA256（含来源/NULL/空日），再次读及最终
发布前重新校验；旁路 A 修订明确失败。该证据只属于当前 root 的临时读集，不是阶段 B 的历史可信凭据。
共享锁/核验成本计入总耗时，不能只报最终 SELECT 速度。

隔离 PG17.11 定向测试：17 passed，JUnit `.codex_tmp/v14-a1-junit.xml`。
冻结 Q0 view 与新 Q1 对六个因子列及交易状态全部业务/来源列严格 DataFrame 对照，含
A-only、覆盖、新键、删除重建、NULL、版本/hash 不匹配、空结果、其他 root；
另测 key/date/entity/payload/缺身份污染、无 workspace、跨 checkpoint 旁路 A 改变。
六列 NULL/布尔/date dtype 保持；UUID/浮点价格/时间戳等全列也严格一致。

小样本 2000/1350/2800 只是正确性 smoke，Q0/Q1 输出均为 1893 行且摘要相同。
已记录普通 SELECT/DECLARE CURSOR 估算和 SELECT ANALYZE BUFFERS 原始计划，
实际 FETCH 与 EXPLAIN 内部执行不混同。大规模、最终 CI、Windows/跨网、读者 p95 尚 OPEN。
本记录不批准历史复用、临时候选缓存、云端迁移/重跑或旧任务处理。

## A2：SQL 窗口，不是指标分批

开始：A1 `5a2c3ca`。可信完整 TradeCalendar 按 1/3/5/10/20 个开市日划窗，
保留窗口间所有日历日期（即使存在历史休市日行，也须与 Q0 完整键集合一致）。
每窗 named cursor / FETCH 5000，最后一次构造 DataFrame 和 ts_code/trade_date 排序，
不按窗推断 dtype、不按窗调用引擎；失败不返回局部帧、不跳过/重试。
当前候选预检证明日期键一致后，遮蔽分支也增加显式窗口条件，避免每窗再读全部 root B。
每窗/每 FETCH 保留 checkpoint；窗口数、首行/首 5000、最长 FETCH、全窗耗时脱敏记录。
query_elapsed 是客户端复合耗时，不伪装成纯网络/PG 执行；PG wait 由隔离实验旁路采集。

隔离 PG17 全字段/六列黄金与窗口回归合计 22 passed，JUnit `.codex_tmp/v14-a2-junit.xml`。
五种窗宽覆盖月末/年末/休市/全空值前窗/非空后窗、跨股票日期排序和删除掩码。
原输入引擎不改，默认开关仍关闭；5 日只是待规模测量的实验起点，不声称最佳。
小样本 Q2 1893 行摘要与 Q0 一致，但约 0.365–0.379 秒，慢于 Q0；这不能作为性能通过证据。
百万规模与真实网络验收尚 OPEN，未进入阶段 B。

## A3：安全回归与性能审阅（READ_PERFORMANCE_OPEN）

开始：A2 `4bbcc4f`。新增实际 Worker 取消、PG 57014、断线、所有权失效、
最终发布前预热 A 旁路改变检查；已知失败保 A/ABORT，未知执行仍保留槽并报未确认。
真实旧/新引擎链路逐字段比较因子、质量及十表原子发布结果；仅独立时钟和 UUID 角色
按明确规则归一，不改变业务数值、NULL 或容差。普通 RR 公开读者不见 B，旧直写者
在单次多窗读锁期间收到 lock timeout，取消端点不受 root row lock 阻塞。
10002 行真实命名游标观测批次为 5000/5000/2，非 holdable，读取后关闭。
首行指标以实际 fetchone 收到一行为准，再将首行放回同一 5000 行客户端批次；
不把 DECLARE 完成或收到整批误报为首行到达，SQLAlchemy 的游标缓冲仍为 5000。

跨调用来源核验和新窗口捕获合并为一次全字段聚合，避免重叠范围重复扫描两次；
仍保留最终发布前核验，不移除来源保护来换取速度。无 workspace 的多窗同样锁定 A，
不建立 ledger。基准收据对行数、摘要和 dtype 强校验，不允许部分读取制造 PASS。

### 百万级探索结果，不是最终 SHA 验收

输入：A=2,570,000，当前 B=1,350,000，其他 root B=2,800,000，总 B=4,150,000。
全部九次完整 FETCH 均为 3,104,443 行，六列摘要相同：
`38c31457a657816e1cde97dfbab281b8d6bdee69b6951519785bdaa54d096f02`。

| 路径 | 全 FETCH 秒（三次） | 中位秒 |
| --- | --- | --- |
| 冻结 Q0 | 27.185 / 24.849 / 26.191 | 26.191 |
| 日期有界 Q1（含保护） | 58.778 / 80.008 / 80.159 | 80.008 |
| 5 开市日 Q2（含保护） | 147.901 / 127.610 / 110.323 | 127.610 |

结论：新路径更慢，建议降耗 50% 目标未达到，不启用、不声称解决业务云库超时。
客户端峰值 RSS 是进程累计峰值而非每次独立峰值；传输/解码和主机 CPU 归因 UNPROVEN。
实际 A table/index=679362560/159416320 bytes；B=2787500032/1022885888 bytes，
候选约 3.81GB（十进制），不足任务书约 6GB 的行宽条件。
cursor_tuple_fraction=0.1，work_mem=4MB，shared_buffers=128MB，effective_cache_size=4GB，
装载后 ANALYZE。Q2 第一窗的游标估算使用日期 bitmap 与 hash anti join；
这不是云端失败计划重现，也不能将估算成本当作实际逐次扫描/网络耗时。

原始 JSON/计划 `.codex_tmp/v14-million.json`，stdout `.codex_tmp/v14-million.log`。
实验在 dirty A2 上开始，早于最后合并来源扫描及补充新键字段的修改，不能冒称最终代码性能。
布局是按股票连续日期写入，与真实逐日写入可能不同；缓存未控制，曾并行运行测试，
没有大样本并发读者，其他 B 仍是交易状态而非真实多表行宽分布。
以上限制全部保留，禁止选择性删掉慢结果。
当前脚本另记录精确行数、行宽样本、索引 DDL/大小、脚本摘要，并允许仅在隔离库
对照 cursor_tuple_fraction=0.1/1.0；这两套最终大样本矩阵尚未完成。
`--window-days 1|3|5|10|20` / `--tombstone-percent 0|1|10` 为隔离矩阵入口，
不修改生产参数。要覆盖任务书矩阵应在专用测试资源逐组合运行，不能只跑默认 5/1。

独立复测入口（先按 A0 核对显式测试 URL、物理标记和 ID；绝不可替换为业务连接）：

```bash
python scripts/ab_read_benchmark_v14.py --public-rows 2570000 --candidate-rows 1350000 \
  --other-rows 2800000 --variant all --repeats 3 --readers 2 \
  --window-days 5 --tombstone-percent 1 --cursor-fraction 0.1 \
  --output .codex_tmp/v14-read-review.json
```

该命令仍只是当前行宽模型的探索入口；先完善真实多表/约 6GB 行宽与索引分布，再进行
正式重负载门禁。PG IO/temp bytes、pg_stat_statements、受控缓存和独立 PG CPU 归因
尚无完整同条件对照，不能从客户端总时间或估算计划补造这些指标。

### 门禁与下一步

本地专项初次 50 passed；修复测试环境变量泄漏、补首批指标后最终专项及已有 LLM
配置回归 55 passed（`.codex_tmp/v14-final-targeted.xml`）。完整回归
及最终 exact-SHA CI 收据以本报告末尾为准。修复环境隔离不改变既有配置测试断言。
前端 162 测试/23 文件通过，行覆盖率 87.27%，构建通过；已有 npm audit 11 项
（4 moderate / 3 high / 4 critical）及 chunk 警告未顺带修改依赖。
隔离 PG17 的正式 Alembic upgrade/current/heads 一致为 0058，无新迁移。
L1 发布 smoke 164 行，公开读者 15 样本、p95 25.854ms、最大 RUNNING=1、无等待者/读错误，
行预算和发布中 SQL 超时探针均保 A；只是结构性能 smoke，不代替 L2/L3 或真实金融计算。
另实际尝试 `data_publication_capacity_v12.py --confirm-synthetic --levels all`：L1 完成，
L2 在共享本机资源下写入过慢，未完成后续因子表，主动 SIGINT 结束，exit 130；
L3 未进入。采样时 B 的交易状态为 100000 行、因子为 5000 行，观察到既有
input_keys 候选写前查键 SQL；该实验不调用新 A/B 读仓储，不能据此归因新读代码或
推断扫描/耗时占比。统计已有 autoanalyze，没有修改规划器、SQL、测试阈值来制造通过。
原始 `.codex_tmp/v14-capacity-all.log` / `.json` 仅含已完成 L1 与中断证据；
L2/L3 仍 DEFERRED，需单独资源窗口按原脚本完成，不视为本轮通过。
夹具清理自己创建的合成临时库，不处理业务数据。
`docker compose --env-file .env.example config --quiet` / `build` 均通过（只构建，不启动业务服务）。
真实镜像的单 Worker / 双 Worker 队列各完成 6 个合成任务，双 Worker 原子发布场景
完成 6 个新任务加 1 个既有种子；最大顶层 RUNNING 均为 1，无跨表混合来源。
收据 `.codex_tmp/data-queue-containers.json` 带镜像源码摘要，执行时 A2 dirty，非最终 CI。
本地两档 cursor_tuple_fraction 的三路径三次 smoke 完整键/dtype/摘要一致，均不达性能目标；
这些小样本不代替最终大样本两档矩阵。

CI 新增独立物理标记 PG17、目标身份检查、专项 JUnit、Q0/Q1/Q2 smoke 和原始工件上传；
保留全部旧回归、迁移往返、容器双 Worker、发布容量、Research/PAPER 与前端门禁。
小样本读者场景不能证实大型并发 p95（Q0/Q1 可零样本），不标 CLOSED。
未关闭：最终约 6GB/行宽、受控冷暖缓存、窗宽五档规模、规划器两档、百万并发读者、
Windows/真实跨网、性能目标与最终 SHA 的全部 CI。资源不足项为 DEFERRED，不准生产。

阶段 B/C 未开始：历史预热仍为原 L0，不承诺避免百万预热候选。
先审阅阶段 A 未达标项并确认下一步，未经用户确认不进入 B。
运维前提与回退见 [试运行边界](../runbooks/v14_read_reuse_rollout.md)。

## 最终本地回执

冻结最终实现后完整执行：`python -m pytest -q --durations=20`，
**2231 passed**，489 项既有兼容/弃用警告，1365.17 秒；
JUnit `.codex_tmp/v14-full-green.xml`，stdout `.codex_tmp/v14-full-green.log`。
此前全量中旧 Raw-gate 单测的 SimpleNamespace 缺少日历查询，已补足已验证开市日夹具，
保留原 Raw 错误/交易状态不执行/事务断言；全部 1575 单测另行通过，再跑完整回归成功。
状态全列与窗口 Golden 显式 `check_exact=True`，不采用浮点默认容差。
最终专项 55 passed（57.25 秒），实际游标仍保持 5000/5000/2 批次及关闭检查。

最终 `ruff check backend tests migrations scripts`、`git diff --check` 通过；
前端 162 测试和构建、Compose config/build、源码摘要匹配的最终镜像单/双 Worker
与原子发布验收均通过。对应原始容器回执 `.codex_tmp/data-queue-containers.json`，
stdout `.codex_tmp/v14-final-container-acceptance.log`，三个场景均最多 1 个顶层 RUNNING。
全部本地实现测试发生在 A2 HEAD + dirty A3；提交后仍需最终 exact-SHA CI 及工件核对，
这里不虚构已完成的远端绿灯，不将本地 JUnit 冒充同 SHA CI。

无新迁移；PG17.11 / Alembic current=head=0058。没有连接业务云库，没有重提补算、
启停业务进程或改变业务任务终态。测试工件不提交，独立测试实例结束后停止。
最终结论仍是阶段 A 代码/本地回归通过、读性能与完整容量验收 OPEN，阶段 B/C 未开始。

## 推送后的 CI 工件上传修复

A3 `df281f2` 已推送，本地/远端一致且工作区干净。对应
[CI 39433747959](https://github.com/sssssssssh/ssh_stock/actions/runs/39433747959)
的 V1.4 物理标记 PG17、日历/合并读取专项、三路径游标 smoke 全部成功；
随后上传 `.codex_tmp/v14-*` 报 No files found，中断后续主 CI。
GitHub 官方 upload-artifact 默认排除点目录内文件，须显式 include-hidden-files；
见 [官方迁移说明](https://github.com/actions/upload-artifact/blob/main/docs/MIGRATION.md#hidden-files)。
不是数据库或新读路径测试失败，也不能将后续未执行步骤写成成功。

修复仅在主 CI 和既有 V1.3 的显式 `.codex_tmp` 合成证据白名单上传处开启隐藏文件，
不扩大为仓库上传、不上传 `.env`、不降低 if-no-files-found 门禁、不添加 continue-on-error。
新增工作流回归先复现两份配置失败，再验证修复；应用代码、迁移及全部测试阈值不变。
此前本地 2231 完整回归对应的应用实现未变，补充工作流测试独立记录；最终提交仍需重跑 CI。
