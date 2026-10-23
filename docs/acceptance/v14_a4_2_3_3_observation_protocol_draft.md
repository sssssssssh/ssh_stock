# A4233 下一轮观测协议草案

**DRAFT / NOT APPROVED / NO PERFORMANCE MEASUREMENT EXECUTED**

仅批准本轮微型 observer 自检，不批准校准或归因。草案 SHA 绑定自检收据只是内容身份，
不表示运行授权。旧 a4231/a4232 one-shot 已消费，不得复用 profile/token/hash。
下述全部是候选预注册参数；新 workflow、policy profile、实验 SHA/授权/执行均须新任务书。

## 1. 三个独立阶段

1. 本轮合同自检：正式迁移的四张**空**目标表，受限角色，最多 3 ticks/用例；
   无 lookup、seed、计时对照、样本分位数，也不是 observer 开销校准。
2. 未来开销校准：单独审阅/冻结协议和 SHA，以同一双身份隔离 PG17、同一模型/索引/
   合成输入与 prepared 条件比较 off/on；新工件目录，与本轮及旧 a4232 均分开。
3. 未来因果归因：只有校准合格且另行批准，才冻结独立协议/SHA/顺序/资源后运行；
   校准绿色不自动授权归因，归因不自动授权正式 P95/L2/生产。

## 2. 观测预算候选（尚未获准用于性能实验）

250ms 固定周期；每条白名单 SQL 100ms 服务端硬上限/客户端 wall 检查；
start-to-start >500ms、低于200ms的追赶密集采样、缺tick、时钟后退/UTC漂移>50ms、
DB时钟落在主机tick±50ms外即失败。单tick wall≤250ms；最多1024ticks，不覆盖、
不删除慢点；stop+join≤2秒。单视图最多128行，超限停止，不截断。
独立 AUTOCOMMIT/只读/UTC 连接，无共享 RR 累计统计缓存，无刷新统计/维护/授权语句。
候选权限仅 pg_read_all_stats 与预置 pg_control_system EXECUTE，无超级、业务表或维护权限。
进度视图非跨视图原子一致；PID+backend_start+datid+relid 关联，冲突 AMBIGUOUS_EVENT。
四表及其目录映射的 INDEX/TOAST/TOAST_INDEX 批准，其他关系/数据库未知并停止。

每tick原始 SQL wall、总wall、observer线程CPU、进程RSS分开；artifact序列化与
原子写入wall另记manifest，后者含重序列化，不能相加或解释成纯CPU/物理I/O。
CPU为线程CPU，RSS为整个观测进程当前RSS，不是监控的独占增量或query峰值。
禁止修改GC enabled/threshold、强制回收、去掉尖峰、扣监控或GC时间。

## 3. 未来 off/on 校准的确定候选设计

只提出方案、不执行。固定 seed=4233 作为输入生成身份；交错顺序不抽签/不测后调整。
四个新进程按 block0/1/2/3 串行，各比较两个 SQL（C0/C1），每 SQL 八对 off/on：
4×2×8×2=128 个完整 lookup，每方案/模式32点；这个数字**不是本轮授权的新128归因批次**。
block0/2 每对先C0后C1，block1/3先C1后C0；每方案配对方向按(pair+block)%2固定，
偶数 off→on，奇数 on→off。准备固定8次无observer交替预热，禁止追加。
正式输入候选沿用2000键/500批次，只在下一轮批准后才可装载原5000×20合成库。
off也用相同进程隔离、资源采集、自然GC/行物化边界；off缺少后台活动可见性须披露，
不得把off/on差值当成维护的因果效应。不要与旧1100或受tracemalloc影响的128耗时直接比提速。

候选开销门槛：零缺tick/丢事件/队列溢出；每tick总wall≤25ms（周期10%）；
on/off完整wall的配对相对差中位数≤5%、inclusive P95≤10%；每进程observer线程CPU
占elapsed≤5%，on/off进程RSS峰值差≤32MiB；DB backend CPU配对中位增量≤5%。
后端CPU零分母、无独占I/O/资源计数不可用则 NOT_AVAILABLE/不合格，不能把缺失当0。
这些阈值只是提交审阅的提案，不得测后放宽；原正式C1 P95门槛、SQL300s/L2预算保持不变。
失败保存整批与异常末点、停止OBSERVER_OVERHEAD_UNQUALIFIED，不补样或自动重跑。

## 4. 后续归因必须重新冻结的维度

模型/索引/输入/source/协议/hash、marker+system ID摘要、四表统计摘要、fresh/cached计划
签名、generic/custom计数分别保存；数据RR不证明统计/计划稳定，不强制prepare mode。
原 lookup wall 包含 execute、driver缓冲、Python JSON/row物化与全部自然GC；
SQL wall不能叫纯PG CPU/FETCH/I/O，嵌套分段不相加或扣除。保留所有异常、未完成末点。
预热、探针、full/minimal Telemetry生命周期边界保持对称，新增干预必须可证伪且单因素。
仅有活动重合/关系映射/GC栈不能证明唯一代码修复；无反例检验则INSUFFICIENT_EVIDENCE。

未知目标、跨视图矛盾、仅worker活动、累计统计变动但无进度、前后统计/计划漂移、
权限/时钟/tick/写盘/清理失败立即停止，不筛除污染样本继续。query_start仅active候选，
不等于真实维护起点；累计统计滞后只能POSSIBLE_IN_BRACKET；NOT_OBSERVED不证明无维护。

GitHub Environment人工审阅是必要但不充分条件；须另行任务书批准未消费的新profile、
exact SHA、protocol hash、顺序和校准预算。当前不新增任何性能dispatch或自动入口。
所有本轮输出DIAGNOSTIC_ONLY，performance_eligible/capacity_ready/production_read_authorized
恒false，unique_repair_candidate=null。停止本阶段等待代码审阅。
