# A4-2.3.2 统计稳定性 v2：运行前冻结协议

## 身份、范围和历史

审阅基线29ee84548a4254c646b30305ed620ae0fdd2f49c，master，开工工作树干净，fetch后origin/master相同。
本协议必须先单独提交，再实现/执行测量；测量入口固定本文件SHA256和预注册提交，验证Git中的原字节。
只授权P0/P1诊断；P2/P3、生产SQL、正式5/100与L2、A4-3/B/C未授权。
[历史基线](evidence/a4232_historical_baseline.json)将旧1100与128样本均标HISTORICAL_DIAGNOSTIC，
保持旧文件字节。旧C1 analyzed P95=0.191595/C0=0.088756，约2.159倍失败不变。
七异常中的六大GC相关点与repeat81非大GC反例、上次H3仅2/8和统计漂移不因本轮结果消失。

仅CI自建postgres:17容器（现有a421-pg capacity资源类），不读取业务dotenv、连接云库或操作用户服务。
先验证marker与pg_control_system().system_identifier及自有容器标签，再由正式隔离库工具创建随机UUID子库。
任何ANALYZE/ALTER TABLE前重复双身份校验，核对连接是本上下文新建的那个UUID子库；外部库名无CLI入口。
正式Alembic+原seed(5000,20)：public603040行、诊断B503020行；十表及B分表计数在预检固定，不能只比总数。
四张关键表：stock_opportunity_daily、signal_forward_eval、stock_trade_status_daily、data_publication_row。
不修改模型/索引/公式/配置，模型hash=f8bb5cf42d3f38757eda46ff149239789638f3aabe14434cda6ed7fe9daee20f。
快表固定2000键hash=f7a11ade5c21e70867378f342946f570fb914ffdbd73b385adaea91846e51ed3。
C0源码hash=7708d91c831a64093f18aa4f8515789492762f464ccfe202ee0219b756f32976；
C1候选源码hash=5409c99ed43ca4d306e441a12736fb866c9f920e38e4b81d9d465a242eb18964。
原lab与a4231采集器保持字节冻结，复用原lab.workload/lookup及a4231的完整wall计时边界。
新入口仅在wall外增加部分初始化/退出异常的自有observer清理，首发与终态错误分别保留；两模式对称套用。
Python固定3.12.15，依赖requirements.lock（psycopg3.3.4），记录实际版本与全部源码hash。

## 统计稳态：先默认路径，至多一次测量前fallback

只运行一个analyzed稳态；不运行自然as_seeded观察组，不和旧两状态合并比较收益。
fixture装载/候选提交/pg_stat_statements准备完成后，默认路径手动ANALYZE四张关键表各一次，
强制下一次统计刷新并提交。用独立AUTOCOMMIT观察连接获取新目录/统计快照，不使用RR缓存来掩盖漂移。
预检固定四次观测，间隔2秒（t0/2/4/6），每次先pg_stat_clear_snapshot；等待不在wall内。
检查四表last_analyze非空、统计条目存在、无本子库活动autovacuum、四次统计指纹均相同。
默认预检有漂移或活动autovacuum时，仅在尚无计时样本时允许一次明确fallback：
重复双身份/自有UUID库核验，仅对这四张新合成表SET(autovacuum_enabled=false)，再手动ANALYZE各一次，
重复同样固定四次观测；仍不稳定则INCOMPLETE，停止。缺字段/权限/物理身份/索引/计数错误不进入fallback。
禁止全局/数据库GUC、ALTER SYSTEM、生产表或现存fixture控制；不设置TOAST独立参数、不取消后台进程。
表级选项对相关TOAST的继承作用如实记录；反回卷autovacuum仍可能运行，不能用false选项替代观测。
若fallback实际使用，环境标签必须为CONTROLLED_SYNTHETIC_TABLE_AUTOVACUUM_OFF，不能冒充默认生产PG。
如果默认路径通过，保持默认表级选项；采样后漂移不得再fallback或从头重来。

统计指纹独立包含：四表reltuples/relpages/last_analyze/last_autoanalyze/reloptions、
完整pg_statistic条目的服务端SHA256和条数（包含数值槽、直方图等内容但只返回摘要），
索引定义SHA256、固定planner settings及SQL300s/plan_cache_mode、公共/B分表实际计数。
不导出stavalues/histogram/MCV、真实或合成自然键、SQL或bind值。
n_live_tup是估计/累积信息，不当作实际行数或稳定判据；查询所有目录时明确绕开累计统计缓存。
同一父RR只读导出数据快照供四子进程导入，记录snapshot hash；它不等同于目录统计或计划缓存被冻结。

## 计划签名与prepared维度

两方案只用旧C0与固定C1，每批500。捕获原lookup生成的SQL/参数仅驻内存，原Proxy/JSON/Rows不改。
初始检查C0/C1模板SHA256分别为1b19ae3a8b492895c0b15c0f05adcff034b673a8fb4407bc4b4cdbec7635559a、
b792c8641cc98c1cba20dc9537ee5db911d804511787be7fe19cdeb042562ecc。
固定代表计划使用相同首500键。保存两种维度的EXPLAIN(FORMAT JSON)结构摘要：
独立非prepared probe（prepare=False仅用于EXPLAIN），以及实际lookup连接已有prepared语句的EXPLAIN EXECUTE。
后者由pg_prepared_statements的SQLhash精确匹配原SQL的参数化形式；参数顺序/类型核验，
EXECUTE参数仅用驱动Literal/Identifier安全适配、驻内存，不导出SQL/参数、驱动异常原文或原日志。
测量连接保持默认prepare_threshold=5、prepared_max=100、plan_cache_mode=auto，不force generic/custom或关闭prepare。
记录每个prepared语句hash、匿名名字hash、generic/custom累计计数；计数按调用自然增长不是漂移。
EXPLAIN EXECUTE前后计数差须明确此次用generic或custom；该mode与计划结构在块内必须稳定。
非prepared计划与cached计划分别冻结，不假定两者相同，也不将EXPLAIN探针冒充每次真实执行计划。

结构白名单：Node Type、Strategy、Partial Mode、Parallel Aware、Join Type、Scan Direction、
Relation Name、Index Name、Alias、Parent Relationship、Subplan Name、CTE Name、Function Name及递归Plans。
不存Filter/Index Cond/Output/Sort Key等表达式、Query Text、成本/估计行数/执行时间或参数；
原始计划仅驻内存，白名单结构及SHA256落盘。缺Plan/Node Type或无效节点立即失败。
每个子进程固定预热后、每轮四条件前后、结束时校验两类计划、统计与索引/settings；
任一意外差异ENVIRONMENT_DRIFT，保留差异块/字段/时间和已有样本，立即停止，不挑样本继续。
每个样本附所属轮前/后计划签名和观测时间，标BRACKETED_NOT_EVERY_EXECUTION_PLAN。

## 唯一批次：128样本与固定准备

版本A4232_STATS_STABLE_V2_TELEMETRY_INTERVENTION，四个新Python子进程，block0/1/2/3顺序执行。
每进程8轮×4条件=32个完整2000键lookup，总128；每block每条件8次，汇总每条件32次。
条件A=C0/full，B=C1/full，C=C0/minimal，D=C1/minimal。
block0/2：ABDC、BCAD、CDBA、DACB循环两次；block1/3：每行逆序CDBA、DACB、ABDC、BCAD循环两次。
每子进程固定8个未计入的2000键预热：block偶数(C0,C1)重复4次，奇数(C1,C0)重复4次，无Telemetry。
这是为在测量前观测已存在prepared语句而预注册的固定准备，不根据快慢/尾部追加预热；
预热后prepared身份/mode/计划未稳定，预检即失败，不改prepare策略再试。
每块同一RR快照的C0 Golden比较所有C1及full/minimal返回，含public原像/now；
慢表仅各5键B存在与A-only正确性哨兵，不运行其完整2000键成本。
预检另运行既有typed/null/tombstone/cross-root与取消/回滚/未知提交安全用例，不替代正式L2。

复用原execute/JSON/next计时及Telemetry完整生命周期；full/minimal唯一干预仍为是否创建原Telemetry。
完整wall含全部四批SQL、Python转换和自然GC；构造/入退、资源采样、计划/统计检查、落盘在wall外。
tracemalloc每新子进程启用一次、一层跟踪，两端一致；不reset peak或全堆枚举。
自然GC回调保留gen0/1/2、起止、duration、phase、collected/uncollectable、分配块、最多6纯函数名。
每样本最多256事件，overflow/配对错误/回调失败均INCOMPLETE，释放回调并保留失败样本，不静默截断。
被动回调沿用原NaturalGC事件字段，额外捕获回调异常为失效标记，不让Python忽略回调异常后伪装采集成功。
保留client CPU、Python内存及分配摘要、backend CPU/RSS、queryid/calls/buffers/temp/WAL、前后wait，
full额外保留原Telemetry采样；独占I/O/FETCH或分配者不可用就写NOT_AVAILABLE/明确非独占口径。
GC与JSON/next/CPU嵌套，不相加或扣除；driver execute不能叫纯PG CPU或磁盘时间。
计划检查/预热的新分配节奏使本版本只作受控诊断，不能与旧1100/128绝对耗时比增益。

## 因果判读、停止与资源

H1自然GC：支持事件本身及时间重合；触发栈不是回收对象的分配者。无长GC或旧非GC例未解释就不能唯一归因。
H2行物化/Proxy：保持两端不变，计时/分配只能观察；没有单独干预不批准生产重构。
H3Telemetry：4独立block×2SQL共8个检查必须全部满足：full P95-minimal P95≥0.04秒，
full有wall内gen2≥0.05秒，full wall内gen2总负担>minimal，full入场分配块中位数增量>minimal。
还必须逐点排除位置/计划/资源反例；单组漂亮结果或仅分配增加不够，不自动CAUSAL/PASS。
H4顺序/共享历史：按固定round/position/PID保存全部事件；若长GC随位置而非模式、两独立块方向反转，
就是反例；本轮不改顺序追因、不追加轮次。H5后端：分别审阅execute/PG counters/CPU及未知I/O；
旧repeat81未解释时明确UNKNOWN，不把六GC例等同于解释全部七例。
四条件P50/P90/P95/P99按inclusive原样全样本复算；不剔除尖峰、不扣GC、不应用旧P95门槛宣称新性能达标。
统计稳定能支持“旧漂移是混杂因素被控制”，不能证明其造成旧全部尾延迟，更不能直接比较速度。
缺唯一可修复机制时INSUFFICIENT_EVIDENCE，unique_repair_candidate=null，STOP/OPEN等待审阅。
即使8条件满足，仍需机制/反例审阅；本轮不自动创建P2补丁，不开始正式性能复核。

父进程20分钟软预算、Job30分钟、每子进程300秒，SQL仍300秒；不改变发布300秒/行预算1000万/batch500/L2 270min。
专用workflow先轻量unit/PG17预检；它成功才允许唯一标记[a4232-statstable-once]的master push、attempt1测量Job。
P1a先无标记提交并通过预检，P1b单独激活；普通push/重复attempt/失败均不自动重跑实验。
无对外行数/轮次/状态/seed覆盖开关；父子全部绑定同HEAD/run/attempt/模型/协议/实例与clean tree。
进度原子写，初始预检不通过不采样；中断/漂移/缺计划/部分样本INCOMPLETE，保留第一异常和终态清理异常。
只清理本次子进程、新UUID库、自有容器，不取消其他CI/业务任务；不擅自采购或借用Runner。
所有证据DIAGNOSTIC_ONLY，production_matches_candidate/performance_eligible/capacity_ready恒false，P2/P3 NOT_AUTHORIZED。
原release/Core/audit/A4-1/A4-2合同及正式L2触发不改；新Job没有release准入边。

## 官方接口依据

表级autovacuum_enabled影响该表自动VACUUM/ANALYZE，反回卷是例外；本协议只对新合成表条件式控制。
见[PG17表存储参数](https://www.postgresql.org/docs/17/sql-createtable.html#SQL-CREATETABLE-STORAGE-PARAMETERS)。
累计统计可有刷新滞后及事务缓存，需独立新快照检查；见[PG17统计系统](https://www.postgresql.org/docs/17/monitoring-stats.html)。
pg_statistic含潜在敏感数据，只导出服务端摘要；见[PG17系统目录](https://www.postgresql.org/docs/17/catalog-pg-statistic.html)。
prepared的generic/custom选择与统计更新分别影响计划，见[PG17 PREPARE](https://www.postgresql.org/docs/17/sql-prepare.html)
与[psycopg prepared说明](https://www.psycopg.org/psycopg3/docs/advanced/prepare.html)。
