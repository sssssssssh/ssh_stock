# A4235 W05 观测可行性与停止条件

范围是独立 v3 MOCK 长窗合同，不修改 a4233 v1/v2 三 tick 适配器、旧协议或 Reviewer。
既有三 tick 微型合同仅验证旧生命周期，不说明未来128点可测或 Observer 开销合格。

## 相互独立的证明

四表固定为 data_publication_row、signal_forward_eval、stock_opportunity_daily、stock_trade_status_daily。
每表各有 relation OID、统计投影、索引定义、列定义摘要；数据快照、MVCC 快照、schema/实例、
PG设置、模型/SQL、fresh plan、cached plan、generic/custom 模式和 backend 生命周期分别核对。
同构实例/schema 是必要条件，不是可互换 PID/clock 的许可证。统计摘要不能由 MVCC 替代；
fresh plan 结构不能由主连接计数替代，cached 结构当前 NOT_VERIFIED，因而整体仍阻塞。

ANALYZE/VACUUM、unknown relation、ambiguous/POSSIBLE_IN_BRACKET、PID churn、OID/统计/索引/
列/设置/计划/模式漂移或 autovacuum 不确定均停止。NOT_OBSERVED 只保留“未观测到”，不证明不存在。
不调用 EXPLAIN EXECUTE、pg_stat_clear_snapshot、reset stats、planner 参数、自动维护或强制 prepare。

## 长窗合同（尚未部署）

未来需在观测前固定2–8 planned_ticks，250ms tick起点间隔；单SQL≤100ms、整tick≤25ms、
stop+join≤2s，off/on 保持相同资源口径。所有tick序号/时间必须构成连续稳定前缀，
只有最后一点可以是未完成快照；不得超过预定 tick 数。STOP_TIMEOUT 必须 joined=false、
worker finish/整线程 CPU 未知、cleanup=false；joined=true 需要完整生命周期和真实终点。
首发错误 sticky，后续 cleanup codes 独立、有界4项及遗漏计数，不删除异常末点。

完整 ON 要有：读窗前完成tick、读窗内完成tick、读窗后tick，且都在 worker 生命周期内。
在250ms调度下，只有2点不可能同时提供三类完整证据，或 lookup 过短无窗内tick时，
必然 BRACKET_UNCOVERED；不靠偷偷加第三点、延长 lookup、减慢业务或从 wall 扣观察开销解决。
预窗口/后窗口可以作为下一次独立协议提案，但需要固定总预算和开始/停止语义，当前不启用。
合同不采用真实 sleep，不生成真实 GC、CPU、RSS 或任何 SQL 测量。

## 下一次审阅必须解决

G1 受信小型 UUID fixture、非提权可得的元数据列/最小角色、helper PID/clock 双向映射，
同 session 无扰动 prepared 计数可见性、cached plan 结构可信方法，以及短窗 bracket 的可行预算。
若任何方法需 root/hostPID/共享业务库/放宽预算，停止并重新请求范围批准；不自动 fallback。
