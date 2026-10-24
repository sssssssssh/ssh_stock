# A4234 校准候选协议 v1（准备，不执行）

**DRAFT / NOT APPROVED / NOT_RUN_NOT_AUTHORIZED**。
基线5215145152ae732fdba2cc5104c022eb0bed2618。execution_enabled=false为不可覆盖的代码常量；
本协议的SHA只证明内容，不是授权。旧A4231/A4232 profile/token已消费，不能复用。
本轮只生成模拟收据、离线统计与静态拒绝；不得创建正式数据集、连接业务.env/数据库或运行lookup。
批准本协议也不使当前runner可执行，真实入口需要下一版本、独立profile/一次性注册与Environment审核。

## 1. 身份与精确输入（W01）

定义清单：`docs/acceptance/a4234_preparation_manifest.json`，字节SHA256
`baf6fc9b476555eb51eaeecf779d699ffb7df83686ff4a3347a037a2939b7698`。
驱动将校验协议自身字节SHA与清单SHA，不接受预算/seed/keys/模式的运行时覆盖。
清单记录现有C0/C1源码、SQL模板、模型/迁移/配置树、固定requirements.lock、旧观测器/探针源码摘要。
新驱动/reviewer/适配器源码从可信目标Git提交重新取blob摘要，不相信待审工件自述的expected身份。
最终HEAD/远端SHA/run/attempt、Python3.12、PG17、固定依赖、fixture定义与实例摘要全部绑定。
同批Python patch/依赖版本与镜像ID必须一致；本轮本机与CI功能测试不冒充同资源性能环境。

完整2000键列表：`a4234_input_keys.json`，先2026-01-11再2026-01-21，各S000001.SZ至S001000.SZ，
按trade_date/ts_code字典序；不洗牌。仅键定义，**不是**5000×20业务行装载或已准备好的数据库。
文件字节SHA256 `918104253d18ad21629323befc4d2d2c198ca71a56629ca577b4ca1a9cb58e9a`；
对列表json.dumps(sort_keys=True)（默认分隔符、无末换行）的语义SHA256
`f7a11ade5c21e70867378f342946f570fb914ffdbd73b385adaea91846e51ed3`，与旧控制表输入一致。
seed4233作为fixture定义身份保留；无新增随机排序。未来数据仍需独立新建并双验证PG17后才可装载。

控制表stock_trade_status_daily，固定2000键/500 batch，即每个完整lookup含4个连续批次。
C0/C1 SQL模板SHA分别为1b19ae3a8b492895c0b15c0f05adcff034b673a8fb4407bc4b4cdbec7635559a
和b792c8641cc98c1cba20dc9537ee5db911d804511787be7fe19cdeb042562ecc。
只冻结旧实验实现，不编辑/执行生产SQL；生产C0、A/B覆盖/遮蔽/血缘/发布/取消语义不变。

## 2. 确定顺序与预热候选

4个新子进程block0..3严格串行，不共享driver连接或Python堆。
block0/2先完成C0的8对，再C1的8对；block1/3相反。
每对方向仅由(pair+block)%2决定：偶数OFF→ON，奇数ON→OFF。
position严格0..127；键(block,variant,pair,mode)唯一。全批64对/128点；每variant32对、各32 OFF/ON。
序列按json.dumps(sort_keys=True,separators=(',',':'))摘要：
`3917cd75902cc0821b900c40d247a0d5f9bb427ae9fd7b778e53fbc6b44f858c`。
不补采、不删慢点/失败点、不重排、不自动重试，不跨旧Telemetry协议比较提速。

**待用户确认的预热解释**：候选为每个独立子进程8次无Observer交替预热（每variant4次），
共32次，均独立于128个分析点；顺序随block的variant顺序交替4轮。
理由：每次2000键lookup为4次500键SQL，driver默认prepare_threshold=5；每进程仅2次预热
（全批8次）会使每variant仅4次SQL，不能在正式配对前建立同一prepared稳态。
该数量解释已单独提请用户确认，**不是**追加真实运行授权；确认其他口径须先新协议SHA及重新审阅。
候选warmup序列SHA256 `bfb974ac22c73eaf4afed77a53c29d66592058e737331b98affb8ebbcef9816b`。
预热在各子进程内、数据/权限初检后、block起始探针前完成；无Observer，保留原始成本但不混入分析。
prepare_threshold=5/prepared_max=100沿用旧定义，不改prepare mode/planner/GC设置以求稳态。
若预热后计划/模式不能稳定，停止并报告，不增加预热或隐藏漂移。

## 3. 时钟、边界与资源口径

lookup_wall从第一个批次执行前，到第4批全部映射/JSON/行物化完成后；包含全部自然GC与driver缓冲。
SQL execute、driver/Python物化、GC为嵌套段，不能相加、扣除或冒充PG CPU/FETCH/I/O。
Golden核对在计时外，两模式相同，缺失或结果不同立即失败；模拟数据不构成真实Golden证明。
OFF/ON使用同一host monotonic时钟、资源/GC schema与输入版本。
OFF必须OBSERVER_OFF、无observer对象/后台线程/伪tick；ON只接受封存的Observer v2快照。
新桥接协议`a4234.observer-bridge.v1`不改旧v1/v2解析、SQL列、权限、2..8 planned_ticks界限或生命周期。
lookup前有已完成的有效前tick、结束后有后tick；全部tick保留，不能只取快tick或跨缺口。
无法完整包围即BRACKET_UNCOVERED停止，不将微型接口偷扩为1024 tick真实采样器。
250ms固定周期，原100ms SQL上限及原时钟/200..500ms start间隔检查保留；校准候选另要求每tick≤25ms。
stop/join≤2秒；未join、partial tick、缓冲超限、信号/SQL异常、首发或清理错误均停止。

CPU记录进程CPU、observer整段worker线程CPU、各自elapsed；sum(tick CPU)不等于整段worker CPU。
桥接包装仅在worker自身用thread_time测入口至finally，保留旧worker负责close/join，不跨线程close。
进程RSS峰值是整个采样进程窗口的高水位，非Observer独占；两模式相同采样口径，记录RSS采样间隔。
backend CPU采用既有backend_snapshot的主backend user+system CPU累计差，保留旧scope说明；
新增容器摘要、PID、pg backend_start、/proc starttime、clock ticks前后对应，任一变化停止。
仅容器内特定自有PID的stat/status；不用privileged/宿主proc挂载/pg_signal_backend或新高权限。
不把容器总CPU、host CPU或SQL wall替代主backend CPU。不可用写NOT_AVAILABLE/null，不填0。
backend CPU零分母亦METRIC_UNAVAILABLE；进程及observer CPU非负，elapsed正且来源明确。
采样/observer start/stop/序列化/原子写盘各自记wall，允许嵌套，不与lookup相减。
GC仅被动记录自然事件、代次、区间、计数、原始函数标签与阈值前后，绝不disable/collect/set_threshold。

## 4. 只读环境投影与非计时探针

MVCC数据摘要、四表规划器统计、索引定义、SQL模板、fresh/cached plan结构与prepared计数分别记录。
数据相同不证明统计稳定。统计投影使用旧A4232定义字段，但不调用会pg_stat_clear_snapshot的
statistics_snapshot入口，也不调用stabilize/ANALYZE/VACUUM/reset/SET planner等助手。
只接受四表精确投影及服务端statistic_sha256，不外发pg_statistic原始值、SQL、参数、用户名/IP/DSN。
权限只由未来独立harness预置；缺权限停止，不自动GRANT。

每block恰好3个非计时探针：PRE_WARMUP、BLOCK_START、BLOCK_END，共12个；无每样本探针。
每探针独立资源/成本收据；发生慢点也不追加EXPLAIN或改变prepared状态。
独立probe连接采fresh EXPLAIN FORMAT JSON（无ANALYZE，prepare=False），不执行lookup。
PRE_WARMUP允许cached状态NOT_YET_PREPARED；BLOCK_START/END需同一已观测cached模式/结构。
若获未来批准，固定每variant一次非计时EXPLAIN EXECUTE读取cached结构；其固有prepared计数增量
必须显式记录为1，不能假称“零扰动”。旧plan_snapshot的副作用不由本轮工具自动执行。
BLOCK_START→END间每variant16个完整lookup×4SQL=64次prepared执行；先读END计数时应增加64，
固定END探针后再增加1。generic/custom分别核对，非选中mode增量0，不忽略计数或以单MVCC证明稳定。
实际driver若不能满足此可观测计数规则则INCOMPLETE_ENVIRONMENT_DRIFT，不调整prepare策略来通过。
模型、数据、索引、统计、SQL/计划/模式或未预注册计数漂移均INCOMPLETE_ENVIRONMENT_DRIFT。

ON复用A4233 correlate并独立重算；所有tick的事件原样保存。
NOT_OBSERVED仅为未捕获，不证明无维护；其他所有事件（含ENVIRONMENT_ACTIVITY_ONLY/POSSIBLE/
UNKNOWN/AMBIGUOUS、进度、PID复用或进程churn）均停止，不在污染样本后继续收集。

## 5. 固定预算（候选，未授权执行）

每lookup/批SQL沿用300秒硬限；Observer SQL仍100ms；非计时probe单SQL30秒。
每子进程总300秒、父进程全批1200秒、未来workflow1800秒；父预算含准备/全部子进程/探针/清理，
是嵌套上限而非可相加额度，不动态延长。中断/stop/join2000ms、每独立原子输出2000ms。
新输出路径、固定最多128样本/32warmup/12probes、每tick128行、GC256事件/样本；不覆盖历史文件。
本版本没有真实启动/子进程/数据装载/数据库连接实现；mock仅检查预算与顺序，不消耗实验授权。
未来若预算不足，保留INCOMPLETE/RESOURCE_DEFERRED，不借业务机器、不采购资源、不缩规模重跑。

## 6. 候选统计口径（离线模拟测试，不认证真实校准）

每对定义signed=(ON-OFF)/OFF，OFF>0；同时保留signed、absolute=abs(signed)、positive=max(signed,0)。
负值原始点和signed/absolute完整保留；候选gate用保守positive增量，不裁剪原数据、不删除异常。
inclusive分位数：排序x，h=(n-1)p，i=floor(h)，Q=x[i]+(h-i)(x[min(i+1,n-1)]-x[i])。
用十进制精确插值，p50中位数、p95=0.95；等于门槛允许，严格大于不合格。
全64对、每variant32对及每block/variant8对分别保存原值、pair delta、n/p50/p95/max；
候选门槛应用于全体、各variant及各block/variant，避免全局平均掩盖顺序效应。

| 候选项 | 判定 |
|---|---|
| 完整性 | 128点/64对，32warmup/12probes，精确顺序、身份与配对，零缺tick/溢出 |
| 每tick总wall | ≤25ms，同时保持100ms SQL与250ms周期原合同 |
| positive lookup相对差 | 每组p50≤0.05、inclusive p95≤0.10 |
| observer整worker CPU / 对应进程资源elapsed | 每ON点≤0.05；worker elapsed和进程CPU另存，不互相替代 |
| ON−OFF进程RSS峰值 | 每对≤33554432字节，signed与absolute差同时披露 |
| backend CPU positive相对增量 | 每组p50≤0.05；缺指标或OFF CPU=0为NOT_AVAILABLE，不合格 |
| 环境/输出/cleanup | 任一异常不完整/未定，不可形成任何资格 |

任何非有限、负耗时、零lookup或超预算极大点先失败；真实失败末点保留，不能扣GC或重测。
超过统计阈值的完整模拟可标simulated_threshold_decision=UNQUALIFIED；缺资源为UNDETERMINED。
collection_status为COMPLETE/INCOMPLETE，与阈值判定分开。当前calibration_decision恒NOT_RUN
（模拟）或NOT_AUTHORIZED（真实输入拒绝），单列simulated_threshold_decision用于检验公式。
PASS_CANDIDATE仅模拟候选门槛结果，不可冒称真实开销通过；本版本永不产生真实PASS_CANDIDATE凭据。

## 7. Guard、工件与停止

guard可离线验证可信expected与待审身份；真实执行函数无条件拒绝，不检查env/token后转为可运行。
CLI不接受execute/approve/force/repeat/预算/规模覆盖，不自动注册profile或修改Environment。
HEAD=origin/master=40位target SHA、clean tree、source/model/input/dependency/protocol字节与新建
UUID loopback PG17 marker/system双证据必须分别验证；模拟expected不能用于实际数据库授权。
当前模拟proof标SYNTHETIC_RECEIPT_ONLY，不声称已创建真实fixture或已审批Environment。
离线文件strict extra-forbid、有限数、重复JSON key拒绝、唯一原子路径、manifest逐文件hash/大小与可信身份复核。
失败写独立incomplete收据，保留首发、最多4个清理码/遗漏数、异常末点；写盘失败不能报成功。
所有输出固定DIAGNOSTIC_ONLY、execution_enabled=false、performance_eligible=false、capacity_ready=false、
production_read_authorized=false、attribution_authorized=false、unique_repair_candidate=null。
完成开发与同SHA普通CI后停在READY_FOR_USER_PROTOCOL_REVIEW；真实128次lookup/64对未运行。
下一请求必须审阅本协议（含预热解释）、CPU/权限/环境可行性，并另批新profile/准确SHA/独立一次性预算。
