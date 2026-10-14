# M16.6 路径映射与设计决策

## PR-E 验收通过

- 提交 `878ba1cae5609bf369e5cbd290928aaff0143874`，CI https://github.com/sssssssssh/ssh_stock/actions/runs/38373484728 成功；真实独立 PG17：1277 passed，后端覆盖率 87%，前端 100 passed，迁移/容器/构建通过。
- 本机隔离 Node 22.23.3 + Playwright 1.64.0/Edge，1440px/390px 浏览器与截图验证：合同分页、键盘、错误恢复、XSS、窗口专用公式、无许可隐藏差值、旧报告无修复入口均通过。截图使用明确标注的合成 API 数据；不冒充金融源端到端，源端到端由 PG 集成测试覆盖。

## PR-F 验收通过

- 基础验收提交 `974d07b6cd1e2525c5c2d5760fce780b869beffb`，[CI](https://github.com/sssssssssh/ssh_stock/actions/runs/38376180481) success：1285 passed、Ruff、0052 current/heads、Docker、前端与 Linux 浏览器均通过。1/36 实际窗口捕获均 14 SELECT，0.0255/0.1782 秒；最大档超 count/byte 默认上限，必须分页，不扩大硬限。
- 审查补充：相同 Evidence + kind/subject/role 的不同合同，在写前与离线读时均拒绝 `CONTRACT_EVIDENCE_CONFLICT`；不同 TRAIN/OOS 角色允许共享窗口 Evidence，缓存相同内容正常。合同和子 Manifest flush 后人为失败必须共同回滚；已通过全量 CI。

- 同 Evidence/写后回滚补丁 `5d88006f904c22005fe30af2d8d14d0c4fb3bf3d`，[CI](https://github.com/sssssssssh/ssh_stock/actions/runs/38377760959) success：1289 passed、Ruff、0052、Docker、前端和双视口浏览器通过。
- 最后补充共享 deadline（v4 原 Archive 与合同复核不重新计时）、窗口 percent 差值明确为百分点，以及导出与 UI 同等全局/逐项/公式门禁。本机 1077 单元、100 前端测试/81.45% 行覆盖率、build/Ruff 通过；功能提交 `4f5f2d453704e73fac8c29c084baf10ffa27082a` 的 [最终 CI](https://github.com/sssssssssh/ssh_stock/actions/runs/38379683263) 全部成功，1298 pytest、87% 后端覆盖率、0052/Docker/前端/双视口 Chromium 通过。

- 增加 1/36 最大窗口真实批量捕获的 SELECT 次数/耗时/字节测量、100 合同默认上限的写前拒绝、离线预检及超时测试；已通过隔离 CI。最终实测均 14 SELECT，0.0304/0.2204 秒；最大档必须分页，不扩大硬限。
- CI 增加 Alembic current/heads 输出和 Playwright Linux Chromium 浏览器验收/截图产物；Playwright 在 runner 临时目录安装，不改变应用依赖锁文件。
- A–F 已验收封版，最终矩阵、P2 依赖风险和上线回滚说明见 `M16_6_closeout.md`。捕获仍默认关闭，上线前核对备份、迁移和双开关；本轮未迁移业务库。

- 双锚点绑定：`contracts/report_binding.py`；读取同时核验原 Manifest 与子 Manifest，旧 v1/v2/v3 的序列化及 AUTO 请求哈希不变。
- `report/application.py` 新增 v4 分派、提交前完整复核、冻结政策重检、分页安全投影和比较导出；不查询最新业务表。
- API 新增 `/reports/{id}/contracts`、`/contracts/{contract_id}`、`/verify-contracts`，以及 `/report-comparisons/{id}/export`；相同 Cookie/owner 404 与严格 DTO。
- Vue 复核状态独立、分页/错误恢复/请求取消、专用窗口退化表，全局和逐项许可双门禁；只消费 `display_result`。
- E 初始本机单元 1058 passed，Ruff passed，前端 100 passed、覆盖率 80.83%、构建 passed；后续追加测试后的最终结果见上文。实际 PG 工具捕获→归档→Report API→Comparison API 已由隔离 CI 执行，浏览器使用合成安全投影单独验证 UI，不冒充源数据核验。

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

## 阶段验收记录

- PR-A：`0a11b49` 建立 0052；`d625edc` 释放旧迁移测试的读取锁后再执行 DDL。[CI](https://github.com/sssssssssh/ssh_stock/actions/runs/38340339216) Success；本地 unit 1004 passed、ruff、diff check、Alembic heads 通过。0052 不回填历史；新合同拒绝 UPDATE/DELETE，非空时拒绝降级。
- PR-B：精确 M14 ID 只 SELECT，复用原比较契约构建器；合同走私有 ToolResultContext，归档仅引用已选 ToolArchive。合同/子 Manifest 与完成回答共用一次 commit。缺 Period/日期/假设仅冻结 Gap。默认关闭。新增独立临时 PG17 数据库中的真实工具/Chat、回滚和幂等用例；结果以本阶段 CI 为准。
- PR-B 验收：`c048b84` 的 [CI](https://github.com/sssssssssh/ssh_stock/actions/runs/38356151219) Success，真实捕获、请求幂等与失败共同回滚已通过。新增测试复用了固定 7 日的交易夹具，精确查询输入只传 report_id。
- PR-C：窗口工具按精确窗口批量捕获双端 M14 及 Window 合同，Manifest 绑定合同依赖 ID/Hash。复用 M15 原选择/OOS 校验及退化公式；摘要只冻结 Aggregate Gap。新增真实 M15 两窗口乱序/错误参数测试，本阶段结果以 CI 为准。
- PR-C 验收：`ec49593` 的 [CI](https://github.com/sssssssssh/ssh_stock/actions/runs/38358271783) Success；本地 unit 1007 passed，Ruff 通过。新合同增加明确的报告关系及白名单执行/会计快照，并验证假设 Hash。
- PR-D：离线校验合同集合、Tool/Evidence/Window 绑定、源报告关系、精确日期集、假设与选择参数。提交前运行同一核验；新 v4 政策为独立纯函数，严格同样本才授权逐指标 Decimal 差值；敏感性只展示上下文；单窗口退化复用 M15。原 v3 比较函数保持原行为，接入新报告/API 属 PR-E。阶段结果以 CI 为准。
