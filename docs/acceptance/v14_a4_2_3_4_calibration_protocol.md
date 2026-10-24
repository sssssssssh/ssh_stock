# A4234 校准候选协议 v2（已确认8次总预热，阻塞）

**DRAFT / NOT APPROVED / NOT_RUN_NOT_AUTHORIZED**。
状态：**BLOCKED_NEEDS_SPEC_OR_CAPABILITY**。基线5215145152ae732fdba2cc5104c022eb0bed2618。
用户在本轮明确确认“全批共8次，能力不足则标阻塞”。不增加预热，不改变driver/planner/GC设置。
本轮不执行128次真实lookup、缩小版试跑或正式数据集装载，不连接业务.env/数据库。
原v1（提交fb10b2e及6b92c8f）为未执行的32次候选；本次确认后由v2取代，旧提交不改写。
只有本v2字节SHA可供当前guard引用；协议SHA不是运行授权。

## 1. 冻结定义与精确输入

定义清单：docs/acceptance/a4234_preparation_manifest.json，schema a4234.preparation-manifest.v2；
字节SHA256 4ceb7149357ac7a91a48eda1407d0d621b7ca24f256f417e8e4e8ba35052947d。
清单固定源/模型/迁移/配置树、requirements.lock、C0/C1 SQL模板与预算。
输入文件a4234_input_keys.json只含键定义，不是已装载的实验数据库：
先2026-01-11再2026-01-21，各S000001.SZ至S001000.SZ，精确字典序共2000键，无洗牌。
文件SHA256 918104253d18ad21629323befc4d2d2c198ca71a56629ca577b4ca1a9cb58e9a；
列表json.dumps(sort_keys=True)默认分隔符、无换行的语义SHA256
f7a11ade5c21e70867378f342946f570fb914ffdbd73b385adaea91846e51ed3。seed4233仅为定义身份。
控制表stock_trade_status_daily；同模型/索引/快照，500 batch、2000键完整lookup含4条批查询。
模板C0=1b19ae3a8b492895c0b15c0f05adcff034b673a8fb4407bc4b4cdbec7635559a；
C1=b792c8641cc98c1cba20dc9537ee5db911d804511787be7fe19cdeb042562ecc。
生产SQL、A/B覆盖/遮蔽/血缘/原子发布/取消/未知提交、开关/金融口径全部不改。

## 2. 候选128点的顺序（不采集）

4个独立新子进程block0..3严格串行，无共享连接/Python堆。
block0/2先C0的8对后C1的8对；block1/3相反；每对偶数(pair+block)先OFF后ON，奇数相反。
position=0..127，键(block,variant,pair,mode)唯一；64对，每variant32对/32 OFF/32 ON。
canonical JSON sort_keys=True、separators=(',',':')的序列SHA256
3917cd75902cc0821b900c40d247a0d5f9bb427ae9fd7b778e53fbc6b44f858c。
不删异常、不补采、不重排、不反复重跑，不跨旧Telemetry协议比较提速。

## 3. 用户确认的8次预热及阻塞证明

全批严格8次、不计入128点。每block仅2次，无Observer，在该新进程/driver连接内，
按本block顺序各C0/C1一次，初检后且BLOCK_START探针前；只定义顺序，不执行。
预热序列SHA256 ce3552ec5615884d8095f89d351ad00a7e8e54c1df270d83adcfd36a95305323。
每个进程/variant仅1次完整lookup×4批查询=4次SQL。现有prepare_threshold=5、prepared_max=100不改；
psycopg在执行次数超过threshold后才创建prepared statement，所以4次不足以准备。
8个独立进程/variant条件，至少各2次完整预热才能越过5次阈值，最低16次总预热；
16只是创建prepared statement的算术下界，**不保证**generic/custom计划稳态。
全批8次无法满足这一必要条件，重新分配8次亦至少有一个条件不足，不能靠共享连接规避独立进程要求。

因此当前guard必须在真实数据集/连接/预热/采样之前拒绝：
A4234_PREPARED_WARMUP_BUDGET_INSUFFICIENT。
不能把第一个正式OFF/ON点充作额外预热、强制prepare、改threshold、提前执行同模板探针、
复用旧连接或增加隐藏SQL。EXPLAIN EXECUTE不能被当作免费只读准备；无预热授权的提前查询也拒绝。
本轮在此停止W03–W05实现与任何实验，保留离线顺序/数学证明及拒绝guard，等待用户重新裁决。
预热8次要求与保持独立driver prepared稳态的条件同时保持，**不自行选择牺牲任何一项**。

## 4. 未来适配/漂移检查的冻结要求（未实现，非可执行承诺）

如果未来解除阻塞，仍须新版本实现并单独批准：

- 完整lookup wall含全部4批execute、driver缓冲、Python JSON/行物化与自然GC；嵌套段不相加/扣除。
- OFF同资源/GC口径且OBSERVER_OFF，无线程/假tick。ON仅封存v2快照；前有完成tick、后有有效tick，
  不覆盖就BRACKET_UNCOVERED停止。旧v1/v2解析、2..8 planned_ticks、SQL白名单/列/角色保持原样。
- 250ms周期、100ms SQL硬限、原时钟与200..500ms start间隔约束不变；候选另限每tick总wall≤25ms。
- 进程CPU、observer整个worker线程CPU/进程elapsed、worker elapsed、RSS峰值各自记录，
  不把sum(tick CPU)或SQL wall当整worker/backend CPU。start/stop/序列化/写盘成本另列，不扣lookup。
- 复用backend_snapshot纯解析口径前，须证明容器摘要/PID/pg backend_start/proc starttime/clock ticks
  前后一致；CPU为主backend累计user+system差，RSS高水位是进程生命周期口径，不是Observer独占。
  不加privileged、host proc挂载或数据库高权限；缺CPU/零分母为NOT_AVAILABLE，不填0。
- 自然GC事件、代次、区间、计数、原始安全标签及阈值前后全留；不disable/collect/set_threshold。
- 未来probe只允许PRE_WARMUP/BLOCK_START/BLOCK_END每block各一次，共12次、均非计时。
  精确SQL与prepared计数增量尚不能在本8次预热协议下形成有效稳态合同，需下一版本另审。
- 数据MVCC摘要不证明统计稳定；四表统计投影、索引、SQL模板、fresh/cached结构、generic/custom计数
  分开比对。旧statistics_snapshot会pg_stat_clear_snapshot，旧plan_snapshot会EXPLAIN EXECUTE推进计数，
  都不能直接作为无副作用入口。不得调用ANALYZE/VACUUM/reset/SET planner/自动授权助手。
- correlate所有事件和完整ticks保留；NOT_OBSERVED不证明无维护。其他事件、未知关系、进程churn、
  PID复用、跨视图冲突、partial tick、身份/计划/统计漂移或未join一律停止。
- 取消、超时、SQL/写盘/清理失败保留首发、最多4个cleanup码/遗漏数和异常末点；不续采或回填历史。

## 5. 候选预算（未授权）

lookup/批SQL300秒；Observer SQL100ms；每block总300秒，parent全批1200秒，未来workflow1800秒；
stop/join2000ms、每原子输出2000ms。父预算是含准备/子进程/探针/清理的嵌套上限，不累加或动态延长。
预热总8、每block2；无32次替代执行。未来无资源保持RESOURCE_DEFERRED，不缩规模/采购/借用业务机器。
当前没有spawn、DB connect、seed、lookup或高成本workflow入口；所有执行调用无条件拒绝。

## 6. 候选统计定义（只冻结，reviewer未实现）

signed=(ON-OFF)/OFF，OFF>0；同时保留absolute=abs(signed)、positive=max(signed,0)。
负值原始点与signed/absolute完整保留，不删除；候选gate用保守positive增量。
inclusive：排序x，h=(n-1)p，i=floor(h)，Q=x[i]+(h-i)(x[min(i+1,n-1)]-x[i])；
十进制精确插值，p50=0.5、p95=0.95，等于门槛允许。按全体、variant及block/variant分别保存原值/配对/n/分位数/max。

| 候选项 | 尚未应用的阈值 |
|---|---|
| 完整性 | 64对128点，8预热；零缺tick/溢出/隐藏样本 |
| tick总wall | ≤25ms，原SQL100ms与250ms周期同时保留 |
| positive lookup差 | p50≤5%、inclusive p95≤10%，分组披露并同门槛检验 |
| observer整worker CPU / 进程elapsed | 每ON点≤5%，两种CPU/elapsed不混用 |
| ON−OFF进程RSS峰值 | 每对≤32MiB，signed/absolute均保留 |
| backend CPU positive差 | p50≤5%；缺失/零分母NOT_AVAILABLE，不合格 |
| 环境/cleanup/输出 | 任一异常INCOMPLETE/UNDETERMINED，无任何资格 |

未来collection_status与calibration_decision分开；模拟数字不能当实际校准或C1性能/因果/容量证据。
当前不实现可产生PASS_CANDIDATE的reviewer，不生成伪造的128点完整成功工件。

## 7. 身份、安全与人工停止点

离线guard核验40位HEAD=origin/master=target、clean tree、协议/manifest/input/source/model/依赖版本；
角色/物理证明的typed模拟检查仍不代表当前真实fixture存在。loopback UUID新库、可信harness归属、
marker/system双身份、Observer非super/无DML/DDL/MAINTAIN/信号他人权限等条件在未来执行前必须重证。
当前guard即使全部模拟身份正确仍因8次预热不足返回BLOCKED，不接受execute/approve/force/repeat/
预算覆盖/普通push、PR或旧consumed profile作为真实许可，不注册profile或修改Environment。
所有输出DIAGNOSTIC_ONLY，execution_enabled/performance_eligible/capacity_ready/
production_read_authorized/attribution_authorized恒false，unique_repair_candidate=null。
本轮W00验收收尾、W01协议和W02阻塞拒绝可交付；W03–W05及其完整AT02–AT18校准覆盖不能冒称完成。
最终状态BLOCKED_NEEDS_SPEC_OR_CAPABILITY；下一请求需明确如何在**总8次预热**约束下处理prepared条件，
或单独修订相冲突的条件/预算。当前不会自行改任一要求，也不会把此请求当128次测量批准。
