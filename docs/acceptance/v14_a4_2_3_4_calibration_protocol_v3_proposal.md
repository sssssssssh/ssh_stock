# A42341 校准协议v3修订提案（只模拟，不运行）

**PROPOSED / USER_APPROVAL_PENDING / NOT_RUN_NOT_AUTHORIZED**。
基线f5c0fe4d08f37c01714a3085d49f30da4bc4f1d4；旧v2及有效总8次确认保持原字节/阻塞状态。
本提案不替换旧协议、不批准16次预热、缩小试跑或128点真实校准。execution_enabled恒false。
清单a42341_preparation_manifest.json SHA256：
4cca8088909821371f99d8cd9dba450d2fa6ada4c6dbc462ccd8ec64498a163e。
任何修改提案须在批准前重新冻结SHA；测后不得调整。本轮绝不接触真实测量。

## 1. 固定输入、顺序和身份

seed4233；旧input字节918104253d18ad21629323befc4d2d2c198ca71a56629ca577b4ca1a9cb58e9a，
语义f7a11ade5c21e70867378f342946f570fb914ffdbd73b385adaea91846e51ed3。
2000键/500batch，原stock_trade_status_daily模型/索引及C0/C1源模板、model tree/依赖不变，均在清单冻结。
四串行独立进程，block0/2先C0后C1，block1/3先C1后C0；每variant8对，每对(pair+block)%2交错OFF/ON。
共64对128点，position0..127；每variant32个OFF、32个ON。复用原纯顺序函数，不执行lab.workload。
调度SHA256（canonical JSON、sort_keys、无空白）：
3917cd75902cc0821b900c40d247a0d5f9bb427ae9fd7b778e53fbc6b44f858c。
每点绑定独立expected_identity：40位HEAD/run/attempt、提案/清单/驱动源码/旧v2/source、模型/输入/依赖、
模拟实例/快照/索引/四表统计与fresh/cached计划指纹。源SHA不能从未信任工件自证。

## 2. 方案A：16次候选只是LOWER_BOUND_ONLY

每block4次无Observer候选预热：偶数block C0,C1,C0,C1；奇数block C1,C0,C1,C0。
每variant lookup_number1/2；每候选lookup四条同模板/同OID向量/同真实连接SQL，总16次，均不混入128点。
候选定义键block/position/variant/mode=OFF/lookup_number；SHA256：
e7d8ec5ddbc10398bb4733a52285c07b40f605b9839060987fdefd63938c2a63。
它们发生于各block PRE_WARMUP探针之后、BLOCK_START探针之前，只生成模拟记录，不做真实调用。

每block一个新连接/进程，不跨block共享，C0/C1各有独立缓存键；键包含连接归属、driver实际SQL字节与参数OID。
锁定psycopg3.3.4，prepare_threshold5、prepared_max100，不强制prepare、不改planner/GC。
理论每条件4次SQL不足，第6次才prepare；两次lookup的8次SQL仅越过必要计数，
不证明server statement存在、未被驱逐、连接未重建、SQL/类型没有分裂或计划可比。
mock使用声明的模拟连接/参数类型/模板摘要，不冒称实证真实driver字节/OID；真实静态proof为NOT_PROVEN。
将来必须独立批准后在同一受验证连接只读核验，禁止计数达到就设置PREPARED_STABLE=true。
若需要大于16次，本提案只建议**另审32次固定候选**，不实现自动阶梯/补采/动态增量；
未来必须在测量前另冻确定预算、上限与失败规则，不得看慢点后加预热或重启刷绿。

## 3. 方案B与默认C

坚持8次时承认first-pair含cold→prepared过渡；估计目标须改为“包含冷启动转换的端到端观察成本”，
至少按block/variant/执行位置/实测prepared阶段分层，原128原始点全部保留。
只有能够独立证明阶段分布与OFF/ON方向对称、明示顺序效应和有限样本局限、重新预注册接受条件后才能讨论；
当前交叉方向本身不能证明冷态等价，不沿用方案A的同prepared稳态或原P95解释。
这些证明/接受门槛尚未确定，B仍研究草案，不用于本轮模拟接受函数，也不作为无额外批准的回退。
A/B均未批准时默认C：真实执行BLOCKED_NEEDS_USER_PROTOCOL_DECISION。

## 4. 边界探针设计（均未运行）

每block仅PRE_WARMUP、BLOCK_START、BLOCK_END各一次，共12次非计时边界探针；同一主连接用于prepare身份。
允许系统视图pg_prepared_statements只读投影name、prepare_time、parameter_types(OID)、from_sql、
generic_plans/custom_plans；名称只在内存绑定并导出摘要，禁止导出statement原文/参数/用户名/地址。
探针不执行/prepare被测SQL，不用EXPLAIN EXECUTE；计数应仅随已记录预热/lookup的同缓存键执行而增长，
主会话被pool重新checkout、驱逐、重建、名字/类型/模板变化、计数回退/意外增长均停止。
投影查询自身亦有解析/缓存/分配/CPU成本，不能宣称零扰动；次数固定，未来成本单列，且只在明确授权后调用。
PRE_WARMUP可合法未prepared；BLOCK_START/BLOCK_END必须有受信同会话观测；只有模拟证据时仍REAL_NOT_PROVEN。

PostgreSQL17未提供本提案已验证的“零执行读取cached plan结构”方法；只读prepared计数不等于cached plan结构。
fresh plan独立探针与主连接cached结构的绑定/无扰动证明本轮未实现；缺任一项ENVIRONMENT_NOT_VERIFIED，
不能用旧EXPLAIN EXECUTE或pg_stat_clear_snapshot暗中补齐，也不授予新数据库权限。
四表为data_publication_row/signal_forward_eval/stock_opportunity_daily/stock_trade_status_daily；
受信合成harness提供统计投影/索引/SQL/fresh/cached结构指纹，MVCC摘要不代替统计稳定。
generic/custom累计计数必须按已记录SQL次数增长；CUSTOM_ONLY或GENERIC_ONLY模式及结构稳定，任何切换/异常增量为DRIFT。
mock可构造CUSTOM_ONLY完整一致反例/正例，不证明真实数据库具有相同模式。

## 5. 模拟生命周期、计时与资源

新schema=a42341.mock.v1；evidence_kind/data_source显式MOCK_CONTRACT_ONLY；所有资格false、unique_repair_candidate=null。
只准内建数据型MockWorkload/MockObserver/MockClock/MockResources，拒绝真实连接、通用callback或其替代子类。
四个**逻辑**独立block用不同模拟进程/连接摘要及串行窗口表示，不spawn真实子进程；128点均为内存合成。
完整lookup wall包含四批SQL、driver缓冲、JSON/行物化和自然GC，嵌套段单列、不相加、不从wall扣GC/observer。
GC只记录模拟原始事件/代次/时间区间/计数，enabled=true、thresholds[700,10,10]前后不变；不调用GC API。
OFF状态OBSERVER_OFF、空ticks；CPU/GC/RSS与ON相同粒度。ON使用独立mock-window.v1，不冒充旧v2真实bridge；
每点三tick合成窗口，planned_ticks3(仍在2..8内)、250ms周期、每视图SQL≤100ms、每tick总wall≤25ms；
必须有完成的前边界与后边界tick、零overflow/partial、最终join。长lookup不能被包围就BRACKET_UNCOVERED。
旧v1/v2解析与限制不变；128点长期真实bridge未实现且须独立版本化审阅，不能从mock直接复用v2为真采样器。

模拟默认OFF wall50ms、ON51ms，仅为测试数据；三个tick位于窗口0/250/500ms、各1ms，
lookup起点2ms，外窗口503ms（OFF同长但不生成假tick）。边界等待、setup/stop、序列化/写盘成本分列；
它们不扣lookup，也不以这些人为数字宣称真实Observer开销。记录进程CPU、worker整线程CPU、worker elapsed，
CPU比例仅用整worker CPU/进程elapsed；RSS是进程生命周期高水位，不是Observer独占。
backend CPU须同容器/PID/backend_start/proc starttime/clockticks及USER_PLUS_SYSTEM前后差，
缺失/零分母/生命周期变动为METRIC_UNAVAILABLE，不填0，不以SQL wall替代，不提权或挂host /proc。

## 6. 判定、异常与预算

候选阈值仅PROPOSED_THRESHOLD：positive lookup p50≤0.05、inclusive p95≤0.10，tick≤25ms，
worker CPU/进程elapsed≤0.05，ON−OFF RSS≤33554432bytes，backend CPU positive中位数≤0.05。
signed=(ON−OFF)/OFF、OFF>0，absolute=abs(signed)、positive=max(signed,0)，全部原始负值与异常保留。
inclusive排序h=(n−1)p、i=floor(h)、Q=x[i]+(h−i)(x[min(i+1,n−1)]−x[i])；Decimal精确插值，等于门槛允许。
全体、C0/C1、block×variant分别报n、原始配对点、signed/absolute/positive及分位/max，不能仅全局投票。
collection_status、calibration_decision、prepared_evidence_status、environment_stability_status、authorization_status分离。
mock内部仅SIMULATED_ACCEPT/REJECT；外层NOT_RUN_NOT_AUTHORIZED，真实prepared/环境仍NOT_PROVEN。
任一关键身份/资源/统计/计划/后台活动/清理缺证为INCOMPLETE/UNDETERMINED，禁止四项绿色抵消一项未知。
NOT_OBSERVED不是无维护证明；其他活动、未知关系、PID复用、跨视图矛盾、partial、超时或未join均拒绝。

lookup/批SQL≤300000ms、block≤300000ms、parent≤1200000ms、future workflow≤1800000ms、
stop/join≤2000ms、单项输出≤2000ms，均为未来未授权预算，mock仅验证其静态边界，绝不延长或补跑。
首发异常sticky，cleanup码单列；完整前缀点和末不完整点保留，取消/信号/SQL/写盘错误不续采。
samples.json、review.json、独立failure.json与最后manifest.json原子新写、不覆盖；缺文件/坏hash/路径穿越/
symlink/重复JSON key/NaN/Inf/超尺寸/错schema或未知字段均离线拒绝，错误只输出固定码，无原始异常文本。
预算内无法证明写盘成功为INCOMPLETE，不生成成功manifest；磁盘全坏时只能保留固定stdout错误，不伪称已落盘。

## 7. 两道人审与来源

第一关未批准协议/预算，当前BLOCKED_NEEDS_USER_PROTOCOL_DECISION；工具代码绿色只可TOOLCHAIN_CONTRACT_READY_FOR_REVIEW。
第二关还须独立批准真实exact SHA/profile/未消费token/资源/新fixture权限能力/Environment真实审核。
两关都未落实，所有execute/approve/force/repeat/预算覆盖/旧token/dispatch无条件A42341_EXECUTION_NOT_AUTHORIZED。
当前不注册profile、不改Environment，不连接业务或合成数据库、不执行真实预热/lookup；到工具合同交付即停止。

参考：只读/同会话视图定义见[PostgreSQL17 pg_prepared_statements](https://www.postgresql.org/docs/17/view-pg-prepared-statements.html)；
该视图的计数不是计划结构证明。计划模式与重规划条件见[PostgreSQL17 PREPARE](https://www.postgresql.org/docs/17/sql-prepare.html)。
psycopg公开机制参考[prepared statements](https://www.psycopg.org/psycopg3/docs/advanced/prepare.html)，
但本轮第6次的精确断言以已锁定3.3.4本地纯PrepareManager测试为准，不用滚动文档版本代替锁定源码。
