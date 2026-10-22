# A4-2.3.1 归因协议 v1（P0提交时冻结；只诊断，不是性能验收）

## 唯一问题与干预

基线 `3bdfc3713fea595eaf913bbc347e76510d340b60`。
H1–H5见[a4231_hypotheses.md](a4231_hypotheses.md)。没有预设可修复候选。
只干预一个因素：原Telemetry的每样本完整生命周期启用(full) / 不创建Telemetry(minimal)。
两模式均使用同一个未修改的lab.workload/lookup、Proxy/Rows/JSON计时；C0/C1对称。
最小模式不是生产实现，不移除/扣减自然GC或Python转换；不比较它与历史正式P95的“增益”。
本轮未批准任何observer修复、生产差异或正式5/100性能试验。

## 身份与fixture

协议文件必须先进入Commit1，测量代码在后续Commit2验证父提交中该文件字节相同、其SHA256等于代码内固定值。
实际测量HEAD/run/attempt、协议hash、脚本hash、C0/C1 SQL模板hash及物理marker/system ID写入原始收据。
CI只对Commit2的唯一标记`[a4231-attribution-once]`、master push、attempt1启用独立Job。
普通后续提交/PR/重复attempt不自动重跑；没有失败重试或改次数入口。

沿用现有a421-pg capacity资源类：CPU/memory未设置容器限额时明确记录，不伪称受限；不改资源设置。
只允许CI自建、marker+system identifier双验证的PG17，先验证后DDL，绝不读取业务.env。
正式Alembic、原seed(5000,20)，public603040行；原seed_candidates，B503020行。
快表stock_trade_status_daily 2000固定键（第9/19天各1000股票），输入SHA256：
`f7a11ade5c21e70867378f342946f570fb914ffdbd73b385adaea91846e51ed3`。
as_seeded完成后只对原四张表ANALYZE，再测analyzed；两状态独立报告。
保存模型/index/settings/关系统计前后摘要；若设置、索引或数据身份漂移，标INCOMPLETE，不重跑。
每状态父进程导出同一只读RR快照给该状态所有子进程；数据准备提交后无实验业务写入。
不受控缓存，只声明固定预热后的诊断，不主张受控冷缓存。

## 固定样本与顺序（128次，不是旧100×5矩阵）

每状态2个全新Python子进程；每子进程8轮×4条件=32个完整2000键lookup，共64次/状态、128次总计。
每个条件每状态16个样本，分别来自2个独立进程，各8次；不见结果后追加。
条件A=(C0,full)、B=(C1,full)、C=(C0,minimal)、D=(C1,minimal)。
子进程0按以下四行Williams顺序循环两次：ABDC、BCAD、CDBA、DACB。
子进程1按每行逆序执行：CDBA、DACB、ABDC、BCAD；不根据耗时排序。
每子进程先运行两个固定未计入的2000键预热：block0 C0→C1，block1 C1→C0；无Telemetry，无GC干预。
预热和初始化记录在工件，不能以追加预热筛选有利数据。
慢表仅各取B存在/A-only的5键正确性哨兵，C0/C1等价；不测其完整2000键成本。

## 计时与观测

版本标签`A4231_ATTRIBUTION_V1_TELEMETRY_ONLY_INTERVENTION`，与旧正式协议不可跨口径混算。
wall包住完整workload（4×500），包括所有真实SQL、JSON、行转换/映射与自然GC；CPU同时计量。
Telemetry构造/入退、资源前后采样、GC/分配状态摘要、逐样本原子落盘均在wall外。
full模式Telemetry后台采样可能与wall重叠，这是唯一被干预因素的一部分。
两模式保留完全相同的原execute计时（含驱动传输/缓冲）、next(rows)计时和JSON计时，不改旧包装器。
对自然GC记录generation、start/stop、collected/uncollectable、最多6层纯函数名标签、当前分配块计数。
记录phase=observer_enter/lookup_wall/observer_exit及wall实际起止；GC与row/CPU嵌套，绝不相加或从wall扣除。
每样本最多256次GC事件；溢出明确INCOMPLETE并保留计数，不静默截断为成功。
使用gc.get_count/get_stats、sys.getallocatedblocks及tracemalloc一层跟踪；不做全堆对象枚举。
tracemalloc只在每个新子进程开始启用一次，两模式同样启用；进程峰值不冒充逐查询峰值。
仅在整个子进程结束保存受限分配来源摘要，不输出字符串内容/完整路径或任何bind。
PG记录查询id统计差量、buffers/temp/WAL、backend CPU/RSS、前后wait；full另保存原Telemetry结果。
无法获得的独占I/O/对象归属填NOT_AVAILABLE；错误保留，不伪装零成本。
每样本与相同只读快照的C0 Golden完全一致；提交/DF不适用，不填造时间。

## 预算、中断与一次性

父进程20分钟软预算，独立CI Job30分钟硬限；每个子进程至多300秒。
单SQL仍300秒，发布/270分钟容量预算完全不动；本轮不执行正式发布或L2。
原子进度标DIAGNOSTIC_ONLY，异常/取消/缺任一样本输出INCOMPLETE；子进程退出后先清理连接再清理自有UUID测试库。
父进程中断只终止自己创建的子进程，不能波及业务；不自动补样本或重复attempt。

## 事先规定的判读，不事后挑赢家

每个regime/block/variant分别报告full/minimal的P50/P90/P95/P99、全部样本、GC分代及CPU/PG计数。
只有四个独立block（2状态×2进程）中两个SQL变体的full/minimal方向一致，
且full在各block均有自然generation2长GC(≥0.05s)落在lookup wall、对应full尾部增量≥0.04s，
minimal中的长GC负担确实较小，并有分配/阶段机制印证，才可考虑支持Telemetry整体因素。
即使满足，也必须逐条审阅非GC反例、顺序/资源漂移与分配干扰，不能自动证明某条生产代码有错。
不满足时如实CORRELATED_NOT_CAUSAL/MIXED/INSUFFICIENT_EVIDENCE；事件过少不是“无问题”。
全样本分布仅诊断，不应用旧P95门槛宣布生产合格，不生成performance_eligible=true。
所有capacity_ready/production_read_authorized恒false，P2/P3 NOT_AUTHORIZED。
只有因果证据充分才提交至多一个P2设计/试验申请；用户再次审阅批准前不实施修复。

## 官方观测接口依据

GC回调提供分代、回收对象数等事件信息；get_stats是进程累计统计，非独占分配者证据。
依据[Python3.12 GC文档](https://docs.python.org/3.12/library/gc.html)。
tracemalloc跟踪Python分配，快照/跟踪本身有开销，故两模式一致且不用于生产性能宣称。
依据[tracemalloc文档](https://docs.python.org/3.12/library/tracemalloc.html)。
