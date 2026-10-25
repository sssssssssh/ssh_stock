# A4235 W01 未批准的预热与统计目标决策包

本文件是候选设计，不改变旧 v2 或 v3。G1/G2/G3 是三个独立决定，均无运行许可。
当前 effective_warmups_total=8；128 点、64 对顺序原样冻结，真实运行 NOT_RUN。

| 方案 | 候选预算与估计目标 | 状态 |
|---|---|---|
| A 推荐提案 | 四独立连接/进程、C0/C1 八条件；总 16 或总 32 为两个互斥固定候选预算 | PROPOSED_NOT_APPROVED |
| B 研究备选 | 坚持总 8，估计包含 cold→prepared 转换的端到端开销，需重做分层/位置效应设计 | RESEARCH_ONLY_NOT_APPROVED |
| C 默认 | 总 8 与禁止真实执行保持，停止等待 | BLOCKED |

A 的 16 仅越过 driver prepare_threshold=5 的必要理论下界，不是充分准备或计划稳态证明。
一次完整 lookup 四批 SQL；八条件各一次只有四次同 key 执行，无法达到第六次 prepare。
16/32 不能动态升档；不得先16再看结果自动32、补慢点、重排、自动 retry 或 rerun 求 PASS。
未来必须在观测前冻结单个总次数、SQL/参数类型、缓存键、顺序、接受阈值与失败停止规则；
本轮不设置新的统计接受阈值，也不降低原 P95 或 CPU/RSS 门槛。
B 尚缺 OFF/ON 阶段分层、位置效应、可比性和预注册阈值，不能直接沿用稳态校准解释。

driver 阈值达到 ≠ 同 session 的 server prepared 可见 ≠ generic/custom 稳定 ≠ cached plan 结构可信绑定。
pg_prepared_statements 计数不能证明 cached plan 结构，fresh EXPLAIN 不能替代主连接缓存结构。
不使用 EXPLAIN EXECUTE、clear snapshot、planner 旋钮或强制 prepare 来伪称无扰动。

G1：未来独立 capability-only 探针手动审批，仅自有极小 synthetic PG17 元数据/通用 prepare SQL。
G2：请用户明确选择 A（另选固定16或32并补齐充分证据标准）、B（先重设计）或 C（继续停止）。
目前等待该明确裁决，不能把本任务开发/提交/push/CI 绿灯解释为 G2 批准。
G3：工具和可信环境完成后，另批 exact SHA/新 profile/未消费 one-shot/Environment/固定预算。
G1 通过也不升级 G2/G3；本轮 G1=NOT_APPROVED、G2=PENDING、G3=NOT_AUTHORIZED。
