# A4235 能力矩阵（无真实校准）

当前总体 BLOCKED_WITH_EVIDENCE，代码状态 CAPABILITY_IMPLEMENTED_NOT_YET_PROVEN。
MOCK 合同通过只说明检测器能拒绝指定矛盾，不说明物理事实或权限已成立。

| 能力 | 实现/来源 | 状态 | 本轮真实性及阻塞 |
|---|---|---|---|
| baseline/旧源码/协议 | 本地 Git 原文、远端引用、固定 SHA、独立 ZIP/hash | SUPPORTED | REAL 文件/日志核对；不是实时 PG |
| 静态 source/run/schema | Git 与文件 SHA、strict 模型，禁短 SHA/脏树/未知参数 | SUPPORTED | STATIC_ONLY；非授权 |
| UUID/nonce/marker/system/container/PG17 | 两份独立模拟上下文逐字段比较 | NOT_PROVEN | MOCK_ONLY；未接入真正受信 harness |
| 最低权限 | false-only 角色合同、100ms/8行上限 | NOT_PROVEN | MOCK_ONLY；真实角色未创建/查询；不默认授 pg_read_all_stats |
| G1 签名/过期/消费 | 模拟 grant 精确匹配、时间/nonce/profile/预算反例 | NOT_PROVEN | 无真实签名校验器或持久消费库；永不运行 |
| driver 第六次 prepare | 锁定 psycopg 3.3.4 PrepareManager，无连接 | SUPPORTED | DRIVER_MODEL_ONLY；4/8理论下界不是稳态 |
| 同 session prepared 投影 | 固定假 cursor、PID/start/generation/SQL/OID/cache-key、计数 | NOT_PROVEN | 通用 synthetic 模型，不证明 C0/C1 |
| cached plan 结构 | 与 prepared counters/fresh plan 分开 | UNSUPPORTED | CACHED_PLAN_STRUCTURE_NOT_VERIFIED；不调用 EXPLAIN EXECUTE |
| backend user+system CPU | namespace/container/startticks/clock 双向身份模拟桥 | NOT_PROVEN | METRIC_UNAVAILABLE；未读 /proc，不填零/用 SQL wall 替代 |
| 进程 CPU/整线程 CPU/elapsed/RSS/自然GC | 明确 scope/source/unit/interval/identity | SUPPORTED | 只验证 MOCK 口径；非真实资源可用证明 |
| 四表统计/索引/列/OID/设置/计划 | 独立摘要全等、维护事件保守阻断 | NOT_PROVEN | MVCC 不证明统计稳定；NOT_OBSERVED 不证明无事件 |
| 新版长窗口 bridge | v3 MOCK、2–8 tick/250ms/100ms SQL/25ms tick/2s join | NOT_PROVEN | 未部署、无线程；短 lookup 可能 BRACKET_UNCOVERED |
| 安全工件 | strict typed 四 JSON、哈希、独立 expected、路径/有限文件/独占新建 | SUPPORTED | 离线合同；READY 状态输入仍被拒绝 |
| 原 Observer 三 tick | 历史 CI 319 项/微型工件 | SUPPORTED | 既有微型边界，不证明新的长窗口或开销 |
| 真实128点/归因/P95/L2/生产 | 无入口/全部硬拒绝 | UNSUPPORTED | NOT_RUN，G3 未授权；unique_repair_candidate=null |

## 信任链不能由 JSON 自述补齐

未来 G1 必须由经审阅的新手动路径与受信 Environment 签发绑定 exact SHA/run/attempt、单次
capability-only profile、fixture nonce/marker/system/container、有效期、SQL allowlist/固定资源预算的
授权，并在独立受信存储原子消费。当前 Grant.signature_status 固定 MOCK_NOT_A_SIGNATURE，
两份模拟 grant 即使一致也只返回 signature_verified=false / persistent_consumption_verified=false。
CLI/env/token/普通 push/PR 不能注册、批准或消费该未来授权。本轮没有受信 live adapter，
即使伪造全绿 fixture 或显式 approved=True，RealAdapter.probe_synthetic 仍无条件拒绝。

未来 helper 设计仅限受控 PG 合成容器内最小权限、无端口、双向 PID/starttime 绑定的只读协议；
目前只实现数据合同，不部署。不增加 root/privileged/hostPID/host /proc mount 或系统 capability。
客户端与数据库 namespace/时钟不同时，不能假设客户端 /proc 可读，必须继续 unavailable。
G1 候选 grant 的 16 条短 SQL/2000ms 只是未来待批小探针上限，不是 16 次预热，更不许可完整 lookup。

## 三个独立状态

capability_probe_status=NOT_RUN_NOT_AUTHORIZED；protocol_decision_status=PENDING；
formal_calibration_authorization=NOT_AUTHORIZED。任何一项不得自动提升其他两项。
execution_enabled/performance_eligible/capacity_ready/production_read_authorized/attribution_authorized
全部 false，unique_repair_candidate=null。旧 Reviewer 未关闭问题仍须另行审阅，不由本轮绿灯消除。
