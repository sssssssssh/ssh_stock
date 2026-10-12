# M16.4 不可变研究报告收尾记录

## 交付边界

M16.4 把已经通过 M16.3 证据编译并持久化的 assistant message 转换为不可变研究报告。它不调用 LLM、不重跑九个只读工具，也不触发数据同步、Research、回测、Experiment 或 Walk-forward 计算。`llm_enabled=false` 只禁止新聊天，不影响报告生成、查看、比较、导出与归档。

允许的来源必须同时满足：当前登录 owner、assistant 角色、message 与 turn 均为 `COMPLETED`、规范化回答不是 `INSUFFICIENT_EVIDENCE`，并且至少一个 verified Claim 的所有 Evidence ID 都能在该消息已归档 Citations 中解析。`PARTIAL_VERIFIED` 会保留通过的 Claims，并显示脱敏 rejected Claim 原因。

## 冻结契约与限制

- 报告版本：`m16.4-v1`。
- 快照级别：`CLAIM_SNAPSHOT_ONLY`。
- 报告类型：`market_review`、`opportunity_review`、`strategy_review`、`oos_review`。
- 默认上限：快照 256 KiB、50 Claims、100 Citations、12 Sections、8 Charts、单图 300 点、比较 100 个事实；配置位于 `config/agent.yaml` 的 `agent.reports`。
- 图表类型只允许 `line`、`bar`、`table`。当前 message 未保存完整工具 payload/日序列，因此初版以事实表和合法同日柱状图为主，并固定提示 `SOURCE_PAYLOAD_NOT_ARCHIVED`、`REPLAY_UNAVAILABLE`、`SERIES_NOT_AVAILABLE`。
- Canonical JSON 对对象 key 排序，日期/时间、UUID、Decimal 和有限 float 使用稳定字符串语义后计算 SHA-256。金融差值使用 Decimal，不直接使用 float 运算。

## 数据库与幂等

迁移 `0050_m16_4_reports` 新增：

- `agent_research_report`：owner/source/parent/request identity、类型/版本、标题/截止日、source answer status、冻结 snapshot/source contract/hash、独立 `archived_at`。
- `agent_research_report_comparison`：owner、左右报告、request identity、policy version、三态与原因码、冻结结果、双方 snapshot hash 与 comparison hash。

数据库复合外键约束 source message/chat 和 report/owner 关系。报告触发器只允许归档时间变化；比较触发器拒绝更新。同 owner 的 `(owner_user_id, request_id)` 唯一：相同 body 返回原 ID，不同 body 返回 HTTP 409 `IDEMPOTENCY_CONFLICT`。跨 owner 的详情、导出、归档和比较统一返回 404。

## API

- `POST /api/v1/agent/reports`
- `GET /api/v1/agent/reports`
- `GET /api/v1/agent/reports/{report_id}`
- `GET /api/v1/agent/reports/{report_id}/export?format=markdown|html`
- `POST /api/v1/agent/reports/{report_id}/archive`
- `POST /api/v1/agent/report-comparisons`
- `GET /api/v1/agent/report-comparisons/{comparison_id}`

导出完全来自冻结快照。HTML 对全部内容转义，不包含脚本或外部 CSS；响应带 `Content-Disposition`、`X-Content-Type-Options: nosniff` 和限制性 CSP。

## 比较语义

比较只读取左右 snapshot，不读取当前业务表，也不重跑策略。状态为：

- `COMPARABLE`：同类报告、共同指标且未发现上下文/不兼容标记，可输出 Decimal 绝对差值。
- `CONTEXT_REQUIRED`：例如截止日期不同、来源 Claim 要求上下文或 TRAIN/OOS 样本窗口不同；只并列事实与原因码。
- `INCOMPATIBLE`：报告类型不同、没有共同指标或来源 Claim 已判定不可比；不输出差值或排名。

历史 assistant metadata 没有归档 `performance.summary` 的完整 M14 Bundle/Run 执行与会计假设；这类报告固定携带 `EXACT_M14_BUNDLE_NOT_ARCHIVED`，报告间比较返回 `INCOMPATIBLE / EXACT_M14_BUNDLE_REQUIRED`，不会隐式查询 latest Artifact 来制造可比结果。只有快照中已冻结完整口径的后续契约才可进入 M14 Decimal delta；完整 Evidence Bundle Archive 属于 M16.5 候选。

## 验证与上线

实现阶段在独立 PostgreSQL 17 测试库执行空库全迁移、`0050 -> 0049 -> 0050`、`alembic current` 与 `alembic heads`，并验证 owner 隔离、请求幂等、归档幂等、冻结比较及数据库触发器拒绝正文更新。前端覆盖生成入口、Evidence 展示、三态比较和无 delta 的上下文状态。

上线顺序：备份数据库，部署代码，执行 `python -m alembic upgrade head`，确认 current/heads 均为 `0050_m16_4_reports`，再部署前端。无需开启 LLM。

运行时回滚优先隐藏/停止使用报告入口并回退应用版本，保留新表。迁移 downgrade 仅在两张 M16.4 表均为空时允许；只要存在报告或比较数据就拒绝降级，避免静默丢失用户快照。删除报告数据属于破坏性操作，必须另行获得明确授权。
