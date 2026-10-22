# V1.4 A4-2.2：P0 基线与实验计划（验收 OPEN）

## 冻结与已有证据

已快进拉取 master `4a095883bff09e0e5da6fe5fcf308f8206651f35`，初始工作树干净，保持 master。
[完整脱敏基线](evidence/v14_a4_2_2_baseline.json) 记录 run/attempt/job、物理 ID、正式失败与逐表原始计数。
本次不连接阿里云、不读取业务 .env，不启动业务服务或修改在途任务。

| 工作流 | run / attempt | 当前结果 |
|---|---|---|
| 主 CI | 39732005829 / 1 | failure；Core npm audit 失败、L2 RESOURCE_DEFERRED、release 拒绝 |
| A4-2 | 39732005730 / 1 | success；不能代替新 SHA |
| A4-1 | 39732005757 / 1 | success |
| Publication V1.3 | 39732005753 / 1 | success |

L2 ZIP 12419701750 的 SHA256：
`bec6a0603b34f703890d9548be2f56a4176304cfa77c97fa287296a63d9130fa`；
发布失败 ZIP 12419068893：
`6b8f990ff1fd93818a17121805acf0b8f35450e34ff87fd2245ea449bdf4c83a`。
已下载核对；两者 head/run/attempt 匹配。L2 的计时器真实触发，正式状态 INCOMPLETE、results=[]；
first_failure 在 signal_forward_eval 的 _lookup_batch SQL，terminal_failure 为清理 OperationalError。
PG17.11，容量容器 CPU/memory limit=0（未设置），Runner logical_cpus=4；不能冒充阿里云测量。

| 表 | 目标行 | 完成行 | 实测 batch / day commit | payload 秒 | WITH execute 秒 | upsert 秒 | 行/秒 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| stock_trade_status_daily | 100000 | 100000 | 200 / 20 | 7.284 | 2.062 | 15.038 | 4171.07 |
| stock_factor_daily | 100000 | 100000 | 200 / 20 | 7.457 | 2623.416 | 2646.512 | 37.63 |
| market_daily | 20 | 20 | 20 / 20 | 0.004 | 0.565 | 0.651 | 25.72 |
| sector_factor_daily | 1000 | 1000 | 20 / 20 | 0.084 | 31.638 | 31.872 | 30.85 |
| theme_factor_daily | 2000 | 2000 | 20 / 20 | 0.162 | 0.084 | 0.571 | 1653.23 |
| stock_state_daily | 100000 | 100000 | 200 / 20 | 7.230 | 2637.554 | 2651.770 | 37.54 |
| stock_opportunity_daily | 100000 | 100000 | 200 / 20 | 7.570 | 5662.600 | 5681.167 | 17.57 |
| strategy_signal | 100000 | 100000 | 200 / 20 | 6.737 | 28.034 | 41.005 | 2057.95 |
| signal_forward_eval | 100000 | 50000 | 100 / 10 | 0.070 | 5007.370 | 5057.718 | 9.87 |
| data_quality_daily | 20 | NOT_AVAILABLE | NOT_AVAILABLE | NOT_AVAILABLE | NOT_AVAILABLE | NOT_AVAILABLE | NOT_AVAILABLE |

SFE 完成行不含第 101 次未返回 upsert；该次 payload_count=50500，不是完成行数。
最后完整表 strategy_signal 累计 503020 行；SFE 另返回 50000 行、10 次日提交。
全局 workspace.upsert=16126.304 秒；逐表已返回 WITH execute 合计
15993.320 秒。
它们互相嵌套，不相加。表计时/SQL 是客户端墙钟，不等于数据库 CPU 或纯 I/O。
旧 sidecar 没有逐表开始/结束 UTC、独占 RSS、具体计划、pg_stat_statements 或宿主 I/O 采样：
这些保持 NOT_AVAILABLE；不能按相邻日志差伪造原始阶段时间。

Core 在 npm audit 约 90 秒后只打印 Audit command failed，后续前端 coverage/build/browser 未执行；
日志没有保留 error.code/signal，不能断言是 DNS、TLS 或特定 registry 故障。
缺少后续浏览器工件是后果，不是原始根因。

## 分阶段最小实验

1. P1：只在 CI 新建、双重身份验证的 PG17 合成实例上诊断，不改生产查询。
   复用正式 Alembic、capacity.seed(5000,20) 的十表 public 数据与真实模型/索引。
   使用单独的合成候选快照（503020 + SFE 50000），明确只作查询夹具，不作发布/容量成功收据。
2. 三个代表表：stock_opportunity_daily、signal_forward_eval、stock_trade_status_daily。
   对固定完整 2000 键代表工作负载比较 C0 原实现、C1 显式等值、C2 集合关联；
   C3 用相同完整键集合比较 100/500/1000，不改变生产默认 500。
   五轮交替，每轮覆盖全部代表键，记录 batch 与整个代表工作负载 median/P95。
   这不是完整 100000 行表或正式 L2，通过与否不能填充正式容量收据。
3. 当前 SQL 从冻结 4a095883 的真实 _lookup_batch 捕获，C1/C2 只改变受控关联片段。
   保留原生 typed composite、全部返回列、候选优先、tombstone 与公开原像。
   先做类型/NULL/重复键/跨根/表隔离等价，再采集
   EXPLAIN (ANALYZE, BUFFERS, VERBOSE, SETTINGS, FORMAT JSON)，不保存 binds。
4. 同一物理实例/快照/资源/索引；原统计与显式 ANALYZE 后分开测量，不伪称受控冷缓存。
   记录实际容器/主机、settings、统计时间、关系大小、PG counters、CPU/RSS/采样等待；
   无权限指标标 NOT_AVAILABLE。
5. 生产改动必须同时达到慢表 lookup median 至少 30% 与完整代表工作负载至少 20%，
   不回归其他表/资源/正确性；否则仅交付诊断。
   已有 A4-1/A4-2 逐字节冻结会拒绝生产文件任何变化；用户已允许仅对经验证的
   _lookup_batch() 差异设置严格例外，其余源码/模型/历史证据继续冻结。
6. npm audit 独立提交：有界网络重试、受控脱敏诊断、完整 lockfile 校验；
   INCOMPLETE 独立文件且非零退出，不生成虚假风险清单。独立审计 Job 不阻断本地前端测试调度，
   但 release 必须验证同 SHA/attempt 的有效审计。
7. 完整 L2 只在候选与实际生产路径一致、证据达到门槛后执行，规模、发布/回滚/读者、
   SQL 300 秒、1000 万行预算不变。诊断阶段不就绪必须失败关闭，不能当作验收通过。

## 决策状态

根因目前 INSUFFICIENT_EVIDENCE：已定位查询调用路径，尚无实际计划来区分 SQL、统计、资源或客户端。
生产 SQL 未改，AB_MERGE_READ_ENABLED=false；不进入 A4-3/B/C。
正式 L2 / 全部新 SHA 工件 / Release Gate 尚 OPEN，不用历史或诊断代替。

## 实施记录

- P1 `6e486a8dfd0de63c516e50e14af267302d8ee589` 已推送。
  CI 39774476378 / attempt 1 的新候选查找安全测试通过，诊断尚在运行；
  主 Core job 119809850998 在隔离容器就绪阶段失败：日志先报告 Unix socket
  accepting connections，随后读取 pg_control_system 时出现 database system is shutting down。
  这是测试容器初始化临时 socket 服务的就绪竞争，不是业务数据库证据。
- 后续改用容器内 TCP 就绪与身份读取，保留双身份、PG17、loopback 与正式迁移检查。
  不放宽原有 release assertions；测试精确限制启动脚本仅作这一替换。
- npm audit 与 Core frontend coverage/build 分为独立 Job；仍要求同 SHA/run/attempt、
  Node22、lock SHA、合法完整 all/production 报告；发布门禁重新调用同一 Node 校验器。
  每次明确网络失败最多三次、每次 90 秒、1/2 秒退避；证书/格式/模式错误快速失败。
  stdout/stderr 只输出有界结构摘要与字节数，不转储任意 registry 响应。
  失败产生独立 INCOMPLETE 诊断、非零退出，不输出部分风险清单或伪造零漏洞。
- 诊断先保存所有代表表 actual plans，再执行较长重复实验；在截止情况下保留已取得计划。
  每样本保存 UTC、整个代表表 lookup wall、batch、rows/sec、JSON 与 buffered-row 计时。
  execute 含驱动传输/缓冲，不冒充纯数据库执行；无 DataFrame / commit 的阶段标不适用。
  整个三表代表负载按每轮实际墙钟求和后计算 median/P95，不把“各表 median 之和”冒充结果。
  pg_stat_database 为可能延迟至事务末尾的累积计数，不能作独占逐查询 I/O。
- Node22.23.4 上 audit 单元测试 24/24 通过；相关 Python 单元测试 65/65、ruff 通过。
  一次全 unit 运行因外部 LLM_ENABLED=false 覆盖合成 dotenv 用例失败；移除该测试环境覆盖重跑，
  不改业务测试断言。完整 PG17、前端及容量结论以新 SHA CI 工件为准。

## 首轮实测与跟进（历史 P1，不作后续 SHA 验收）

P1 主 CI 39774476378 / attempt 1 的 lookup Job 成功，工件 12424881949：
ZIP SHA256 `d014d56160b76279c2fcd9962929ab16d49ff36ec0e16b9b32e2b70d61580074`。
同实例 150 次样本、30 份 actual EXPLAIN，全部样本 golden 一致。

| 原统计、2000 键 median 秒 | C0 | C1 | C2 | C3/100 | C3/1000 |
|---|---:|---:|---:|---:|---:|
| stock_opportunity_daily | 0.131781 | 0.114662 | 0.536879 | 0.130041 | 0.111767 |
| signal_forward_eval | 75.953502 | 0.080825 | 0.080810 | 0.090320 | 0.079798 |
| stock_trade_status_daily | 0.108841 | 0.082479 | 0.083214 | 0.092449 | 0.081977 |

显式 ANALYZE 后 opportunity C0/C1 为 0.131918/0.115423 秒（仅改善 12.5%）；
SFE 为 76.921047/0.084642 秒。严格门槛没有全部达到，生产 SQL 未改。
P1 的三表总耗时计算仅为表 median 之和，不能代替逐轮完整工作负载；后续脚本已修正。

重要反证：SFE 前两个 B 覆盖批次约 0.02 秒，后两个 B 缺失批次约 38 秒；
首批 EXPLAIN 却仅约 11ms，说明首批计划不能解释真正慢批次。
该样本 wall=75.387 秒、execute=75.352 秒、client CPU=0.245 秒、JSON=0.00243 秒；
PG cgroup CPU 增量约 75.575 秒，采样 blockers=0，物理读取字节无增长、temp=0。
支持数据库端 CPU 执行而非 Python/锁/磁盘读是该样本主成本，但尚不能推断具体慢节点。
根因仍标 INSUFFICIENT_EVIDENCE，不能把首批快计划当作慢计划，也不归因阿里云配置。

后续严格补强：机会表也必须覆盖 A-only 首次写入，所以将两个慢表候选均固定为前十天。
public 仍是原 5000×20、603040 行；诊断 B 共 503020 行，固定同一快照下比较全部方案。
这与 P1 的 553020 行 B 快照不同，不能把跨轮绝对时间作为优化增益；不修改正式 L2。
全部代表表、全部方案在同一新实例比较 B 覆盖与晚期键实际 EXPLAIN（60 份），并在计时外
追加同连接 auto_explain 实际执行计划（36 份）和 generic/custom prepared counters。
auto_explain 只在计时外开启，参数日志关闭，不改 planner/plan_cache_mode；原始 server logs 不导出。
依据 [PG17 auto_explain 文档](https://www.postgresql.org/docs/17/auto-explain.html)，
log_parameter_max_length=0 禁止参数日志；LOAD/配置/JSON 解析先做低成本自检，再装载大夹具。

P2 `9de0a75f2a1d93f3b47664c6bd4dac2a6666fbdc` 的 CI 39776238585 / attempt 1：
独立审计成功，工件 12424317609，ZIP SHA256
`d9edc98844b11125d70dc58f3390aacf7ad28d56e005327a8700b874e0911460`。
Node22.23.3/npm10.9.9，lock SHA256
`379b41703367d8c450005543ee3baed30334ebb0e6343bbc441cf9d32caa8b19`。
all=11（moderate4/high3/critical4）；production=4（moderate2/high2/critical0）。
两份报告均合法 exit1，未伪报零漏洞，未升级依赖；该结果不能填充后续 SHA 的审计。
