# V1.4 阶段 A 审阅记录（未批准生产）

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
