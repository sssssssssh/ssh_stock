# M16.6 路径映射与设计决策

基线：`07e288c3826618192b4022e8b63d0df06db679ec`。本文件记录实现前核对，不改变既有冻结口径。

| 职责 | 当前代码路径 | 本阶段接入点 |
|---|---|---|
| M14 精确 Bundle | `services/agent/adapters/research.py::performance_summary`、`services/performance/analytics_bundle.py` | 工具选中 Performance/Risk/Trade/Period 后，在同一 `agent_db_session` 捕获 |
| M14 交易日 | `models/performance.py::PortfolioPerformanceDaily.trade_date` | 按精确 `performance_id`、`trade_date` 升序读取，核对 `trade_days` 与起止日，不选 latest |
| M15 窗口 | `ResearchAgentAdapter.walk_forward_window_lineage`、`models/walk_forward.py` | 复用已联接的 Study/Validation/Window/Trial/Evaluation/Train/OOS 精确 ID；分别冻结每条返回记录 |
| 工具私有通道 | `chat/application.py::_execute_tool`、`chat/orchestrator.py::ToolResultContext` | 在工具只读事务内捕获；不加入模型可见 payload 或九工具公开 Schema |
| 原子归档 | `chat/application.py::_complete_turn`、`repositories/agent_archive.py::insert_draft` | 与 Assistant、Turn、原 Archive 同一写事务插入独立合同和子 Manifest |
| 报告读取/比较 | `services/agent/report/{application,integrity,comparison}.py` | 新版本分派；旧 v1/v2/v3 JSON、Hash 和比较审计值不回写 |

## 0052 存储约束

新合同以 `(tool_result_archive_id, owner_user_id, turn_id)` 复合外键引用原 ToolArchive；子 Manifest 以 `(base_manifest_id, owner_user_id, turn_id)` 引用原 Manifest，并由唯一 Turn、Chat/Turn/Owner 复合外键锁定归属。原 Manifest 暂无该复合唯一键，因此 0052 只为其增加非改数据的唯一约束。新表拒绝 UPDATE；有合同或子 Manifest 时拒绝降级。父归档删除继续被 RESTRICT 拒绝，0051 内容与 SHA 不变。

合同 JSON 使用显式版本、类型、subject、role、来源 ID、日期集、假设、报告身份、字段事实和 Gap；关键 owner/turn/tool/base Manifest 关系单独强类型存列。canonical 规则继承已发布的 JSON 排序/Decimal 字符串/ISO 日期形式，但新函数与版本独立，不修改 Evidence v2 或原 Archive 算法。单件、单 Turn 字节和交易日数量均有硬上限，超限拒绝而非截断。

## 权限与兼容

冻结只能证明当次已选来源的合同，不证明原算法重跑。没有 Period、精确交易日或关键假设时记录 Gap，不授予严格比较。Study stitched OOS 只标为 Aggregate；只有精确 Window 与双端 M14 Bundle 可参与窗口退化。旧 Report/Comparison 始终按其原版本解释，即使后来出现合同也不升级。新捕获默认关闭，且依赖既有 `agent.archive.enabled`。

## 与任务书建议字段的偏差

`PortfolioPerformanceDaily` 的日期归属以实际 `performance_id` 为准；`PortfolioWalkForwardWindow` 已直接保存 Train/Test 有序日期与各自日期 Hash。WindowValidation 已具有联接 Trial、Train/OOS 报告的复合外键，捕获时仍需逐字段核验，不能仅把 FK 存在等同于合同可比。当前用户未提供独立本地测试库；数据库写入型测试只能在 CI 隔离 PostgreSQL 17 中执行，不连接业务库。
