# A4236 能力矩阵：离线合同不是实机能力

本轮代码阶段判定 **PARTIAL / BLOCKED**。已实现可独立审阅的模型与默认拒绝骨架，
没有可由签名直接启用的真实执行器，不能称 `G1_IMPLEMENTATION_READY_FOR_INDEPENDENT_REVIEW`。
模型中出现的 UUID、marker、PID、namespace、issuer 和销毁收据全部 `MOCK_ONLY`、
`UNTRUSTED_TEST_ONLY`、`G1_SYNTHETIC_CAPABILITY_ONLY`，不是现实资源或签名。

| 能力 | 已实现 | 实际证明/下一关口 |
|---|---|---|
| 独立签发与验签 | 精确绑定、TTL/撤销反例，独立接口硬拒绝 | ISSUER_NOT_CONFIGURED；信任根/轮换/服务未部署 |
| 持久 once-only 消费 | 无回退 CAS 交错/快照恢复模型 | PERSISTENT_CONSUMER_UNAVAILABLE；Fake 不是存储 |
| 新建 PG17/角色/双域归属 | 数据合同、只读权限及漂移拒绝 | HARNESS_NOT_CONFIGURED / PHYSICAL_NOT_PROVEN |
| 独立销毁/absent | 顺序/归属/独立审计反例 | NOT_APPLICABLE_NO_FIXTURE；没有物理资源 |
| SQL 预算 | 封闭 FakeConnection：≤16 含投影，100ms/2s/8行 | 实际 SQL=0；外围硬终止 MODEL_ONLY_NOT_PROVEN |
| driver prepare | 锁定3.3.4 PrepareManager纯模型，第六次 SHOULD | DRIVER_MODEL_ONLY，不是 libpq/PG 执行 |
| 同会话 prepared | PID/start/generation/OID/bytes/cache-key/counters 合同 | NOT_RUN，server 可见性未实证 |
| cached plan | 永久限制输出 | CACHED_PLAN_STRUCTURE_NOT_VERIFIED；不是 C0/C1 稳态 |
| backend CPU | 双向映射/生命周期/user+system区间差合同 | METRIC_UNAVAILABLE；无 /proc 采集或提权 |
| 资源/GC | 整线程、elapsed、进程CPU、RSS生命周期、自然GC的口径合同 | 未采集，不填0，不改GC，不扣减 wall |
| 统计/计划/维护 | 四关系描述漂移判定 | METHOD_UNVERIFIED；NOT_OBSERVED≠无维护 |
| Observer 长窗 | 2–8 tick/250ms/25ms/100ms/2s模型 | NOT_RUN；短查询 BRACKET_UNCOVERED |
| 工件 | 双身份、独占 owner-only、安全JSON、首错/清理分离 | 只证明离线完整性，不建立物理信任 |

G1=NOT_APPROVED / G1_NOT_RUN_NOT_AUTHORIZED；G2=PENDING，有效总预热8；
16/32候选未批准。G3=NOT_AUTHORIZED，真实128点未运行。
全部 execution/performance/capacity/production/attribution 权限 false，唯一修复候选为空。
生产 C1/P95/L2/因果结论 INSUFFICIENT_EVIDENCE。本轮不包含任何性能对照或容量复测。

## SQL 与时间预算的解释

I4/I8 是通用合成 SELECT，PROJECTION 只读取当前会话 prepared 元数据，原 SQL/参数不入工件。
驱动 bytes 与协议 bytes 分开摘要，参数 OID23/20；不调用强制 prepare、PREPARE、EXPLAIN EXECUTE、
planner 开关或业务查询。allowlist 摘要由冻结代码生成，未来真实 harness 仍须独立认可。
16条是 SQL 总数，不是预热；六I4+六I8+四投影已占满预算，不能保证计划模式全部可观测。
sql_window 从第一条 reserve 到最后 finish，间隙和 overhead 都计入；失败不退预算、不重试。
授权1000ms、初始化/cleanup/写盘/最终终止各2000ms只是未批准的上限草案。
FakeClock/FakeReply 不是现实硬超时实现；真实执行器与最终回收均未证明。

Worker CPU 分母是整个进程 elapsed；unjoined 时整线程 CPU/elapsed 必须未知。
短 query 没有窗内 tick 时不得补睡眠、延长查询、换频率或沿用旧协议重采样。
新的长窗方法只能以 NEEDS_NEW_PROTOCOL_REVIEW 候选单独审阅。
