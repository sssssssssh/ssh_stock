# M16.4.1 报告比较正确性与快照完整性验收

日期：2026-10-13。开发基线：`8e652d995db1568dcec0cf55b2e36a25d7dc5d4d`。
交付分支：`master`。本轮仅整改报告比较、读取与展示，不开展 Evidence Payload Archive。

## 提交与 CI

- 本轮代码提交和 GitHub Actions Run 在首次推送验证后补记到此处。
- 基线 CI 已确认成功：[M16.4 基线 CI](https://github.com/sssssssssh/ssh_stock/actions/runs/38258873503)。这不是本轮整改的 CI 结果。

## T01–T05 对照

| 任务 | 生产代码 / 关键函数 | 实现与验收证据 |
|---|---|---|
| T01 | `services/agent/report/metric_identity.py`：`metric_semantics/collect_facts/pairing_key`；`comparison.py` | 完整受控 path、工具实体类别、实体、角色、单位与粒度；先分组检查重复，再唯一配对。Citation 必须逐事实唯一绑定。保存 Claim/Evidence/来源及未匹配、歧义项；反序不影响结果签名。 |
| T02 | `report/comparison_policy.py`：`ReportComparisonPolicy`；`application.create_comparison` | 独立政策 `m16.4.1-report-comparison-v2`，五种 intent；逐项 pair_status 和全局双门；Decimal `right-left`。运行 UUID 保留为来源，跨 Run 可以语义配对，但缺完整 M14/M15 时明确拒绝。 |
| T03 | `report/integrity.py`：`verify_report/verify_source_contract/verify_comparison`；Application 所有实体返回路径 | 重算原 canonical Hash、元数据及左右关联；详情/导出/创建比较/归档/幂等回放拒绝损坏。新快照 JSON 内绑定来源契约 Hash；旧数据不回填。 |
| T04 | `ReportSnapshotChart.vue`、`reportSnapshotChart.ts`、`AgentResearchReports.vue` | ECharts SVG bar 只取冻结事实；单位/日期/角色/指标/来源逐点验证，原数值保留表格。异常退回表格，禁止拼线图。旧比较风险提示及独立展示门禁；实例和监听释放。 |
| T05 | `test_m16_4_1_metric_identity.py`、`test_m16_4_1_integrity.py`、既有报告 API/PG 测试、前端测试、浏览器脚本 | 全量回归、PG17 约束/Trigger/owner/幂等/只读查询、前端覆盖率/构建及桌面/390px 浏览器验收。0050 原文与历史数据保持不变。 |

上述后端路径均位于 `backend/app/`，单元测试位于 `tests/unit/`，PG 测试位于 `tests/integration/`。

## 比较政策示例

以下均为合成事实，不代表真实行情或投资建议。

| 输入 | 输出 | 理由 / 数值权限 |
|---|---|---|
| 同日同配置同来源、LIVE 股票 A score：左 10、右 12 | COMPARABLE | 唯一实体和完整指标配对，pair_status 同为 COMPARABLE，Decimal delta=`2`，语义 right-minus-left、score 单位。 |
| 左 A=10/B=20；右 B=21/A=12，数组反序 | COMPARABLE | A 对 A 得 2；B 对 B 得 1。不会用右 B 减左 A；仅改变数组排列不改变结果 Hash。 |
| 左只有股票 A=10；右只有股票 B=12 | INCOMPATIBLE | `NO_COMPARABLE_FACTS`、`UNMATCHED_METRICS`；左右事实单列，无差值、无排名。 |
| 同股票 A，不同交易日，source hash 从 b 变化为 c | CONTEXT_REQUIRED | `AS_OF_DATE_MISMATCH`、`SOURCE_HASH_CHANGED`；明确显示双方日期和来源，无 delta。日期/source 不必全等，也不得忽略变化。 |
| 相同配置但缺 source_hash，存在 Evidence v2 content_hash 且内容改变 | CONTEXT_REQUIRED | `SOURCE_CONTENT_HASH_CHANGED`。只能证明返回内容身份，不宣称完整 Raw Payload 或原查询可重放。 |
| 两个不同 Run 的 performance.annualized_return | INCOMPATIBLE | Run UUID 不阻断语义配对，但 `EXACT_M14_BUNDLE_REQUIRED` 关闭差值；不查最新业务数据补洞。 |
| TRAIN/OOS 角色或 train_metrics/oos_metrics | INCOMPATIBLE | 路径和角色保持分离；未冻结真实 Window lineage 时 `FROZEN_M15_WINDOW_LINEAGE_REQUIRED`，不接受自报同源关系。 |
| 一个键重复但数值/来源冲突，同时另一个键合法 | INCOMPATIBLE | `DUPLICATE_METRIC_AMBIGUOUS` 保留诊断；合法事实可并列，但全局关闭 delta。 |

`CROSS_ENTITY_SAME_DATE` 仅允许安全并列：当前 API 未提供对象 pair mapping，不计算跨实体变化量或优劣排行。AUTO 分类不唯一时不授予额外权限。单位不做隐式小数/百分比转换。

## 完整性与历史兼容

- `canonical.py` 未修改。对数据库原始 JSON 重算 Hash，不先反序列化并补默认字段再 Hash，以保持历史摘要兼容。
- 合法 v1/v2 报告和旧/新比较均可读取；归档仍只更新 archived_at。轻量列表不扫描全部快照。
- 新快照 schema 为 `m16.4.1-report-snapshot-v2`，report_version 仍为 `m16.4-v1`；增加可选 `source_contract_hash`，该字段被已有 snapshot_hash 覆盖，不需要新增数据库列。
- 旧快照没有独立来源契约摘要。只检查引用集合、Citation 对应的全部归档来源身份、工具/证据版本/限制/政策与快照一致；不能宣称旧 source_contract_json 被 snapshot_hash 直接覆盖。比较结果另外冻结所使用的排序稳定契约签名。
- Report Snapshot Hash、类型、标题、日期、chat/message/turn 指针或 source_answer_status 不一致：`REPORT_SNAPSHOT_INTEGRITY_ERROR`（409）。导出前拒绝，无部分正文泄漏。
- 比较 result_json 数值改变、Hash 不符、左右指针/快照摘要错配、state/reasons/policy 不一致或新契约签名不符：`REPORT_COMPARISON_INTEGRITY_ERROR`（409）。不重算旧政策、不删除或修复历史。
- PG 故障测试用 `set_committed_value()` 在 Session 内模拟损坏读取，再 refresh 核对真实数据未变；不关闭 Trigger，也不向生产写脏数据。实际 UPDATE snapshot/result 被原 0050 Trigger 拒绝。
- API 原 `result` 保留冻结审计内容，`comparison_hash` 对应它；新增 `display_result/display_safety` 是运行时安全展示投影，不冒充冻结摘要。旧政策投影删除 delta，并提示重新创建比较，旧请求 AUTO Hash 保持原规则，历史同 request ID 幂等回放不重算。
- 原 API 路径与旧请求 JSON 继续有效；新增 intent 可选。旧响应无新增展示字段仍可由 DTO 反序列化。跨 owner 404、冲突 409 不变。

## 12 类负向场景定位

| 任务书场景 | 测试函数（缩略） |
|---|---|
| 1. 两股票反序 | `test_reverse_stock_order_aligns_by_entity_and_permutations_are_stable` |
| 2. 重复事实值冲突 | `test_duplicate_conflict_cannot_hide_behind_another_legal_pair` |
| 3. 同字符串不同实体类别 | `test_different_entity_kind_role_full_path_or_unit_never_match` 参数化 |
| 4. 同股票 TRAIN/OOS | 上述参数化及 `test_same_entity_both_train_and_oos_are_distinct_candidates` |
| 5. 同末级不同完整路径/单位/日月粒度 | 参数化、`test_daily_and_monthly_counts_never_share_a_metric_identity`、窗口 train/oos 路径测试 |
| 6. 同主体历史日期 | `test_historical_dates_and_source_changes_are_context_not_blanket_mismatch` |
| 7. 同配置来源 Hash 改变 | 上述历史测试和 `test_source_contract_per_pair_gate` |
| 8. M14 Bundle 缺口 | `test_cross_run_pairs_keep_distinct_runs_but_require_frozen_m14_bundle` |
| 9. 未归档 M15 Window 血缘 | `test_train_oos_paths_and_roles_require_real_archived_window_lineage` |
| 10. 快照单值篡改 | `test_report_tamper_blocks_every_application_read_boundary_before_writing`；PG 内存注入 |
| 11. 比较 delta 篡改 | `test_comparison_hash_metadata_and_frozen_report_bindings`；幂等重放及 PG 注入 |
| 12. 旧比较不 UPDATE、接口兼容 | `test_legacy_display_gate_hides_delta_without_changing_frozen_result`；PG 旧行读回/同请求复用 |

另有多 Citation 无法唯一绑定、未知字段路径、来源版本/配置缺口、输出裁剪、HTML 安全 409、渲染失败、精度不同但 Number 相等、点数超限及图表清理回归。

## 验证命令与结果

所有数据库测试使用一次性 PostgreSQL **17** 容器与独立测试库，不读取本机 .env 的用户数据库。后端在 Python **3.12** 测试镜像运行，`PYTHONPATH=backend`；前端用项目锁文件安装。

```bash
python -m alembic upgrade head
python -m pytest tests/unit/test_m16_4_report_foundation.py \
  tests/unit/test_m16_4_1_metric_identity.py tests/unit/test_m16_4_1_integrity.py \
  tests/unit/test_m16_4_report_api.py tests/integration/test_m16_4_research_reports.py -q
python -m pytest --cov=backend/app --cov-report=term --cov-fail-under=70 -q
python -m ruff check backend tests migrations scripts
python -m alembic current
python -m alembic heads
```

```bash
cd frontend
npm ci
npm run test:coverage
npm run build
```

```bash
# 使用已安装的 Playwright；可通过 PLAYWRIGHT_MODULE_PATH 指定其入口。
# 先在 frontend 启动仅绑定 127.0.0.1 的 Vite 服务，再于仓库根目录执行：
PLAYWRIGHT_BROWSER_CHANNEL=chrome node scripts/verify_m16_4_1_reports.mjs
```

- 全量后端：**1126 passed**，覆盖率 **86.55%**，7 个已有依赖弃用提示，无失败。
- 专项测试：**59 passed**；包含新增日/月粒度、双样本角色及固定三条只读查询断言。
- Ruff：通过；没有降低断言或跳过验收。
- 前端：82 passed，覆盖率 80.13%；新图表组件和事实验证模块行覆盖均为 100%。Build 通过，保留已有 >700 KiB bundle 提示。
- PostgreSQL：空库升到 `0050_m16_4_reports`；current 与 heads 一致。验证 owner composite FK、request unique、state CHECK、不可变 Trigger、归档、并发幂等与历史保护。没有修改模型或 0050，无需降级测试。
- 比较详情只执行 3 条 SELECT：Comparison、Left Report、Right Report；不随事实数量追加 SQL、不查询当前上游指标、不写 Job。
- Browser：1440px 桌面和 390px 手机、键盘 Enter 打开、冻结 bar、缺序列禁 line、非法数据降表、旧/不可比差值屏蔽、切换清理均通过，水平溢出 false、page errors=[]。

截图使用合成身份和数值：[桌面](assets/m16-4-1/desktop.png)、[手机](assets/m16-4-1/mobile.png)。

## 部署、回滚与真实限制

1. 部署前备份生产数据库，核对 Alembic HEAD 为 0050；后端和前端一起更新并重启。
2. 无需 0051、无需历史 Hash 回填或消息改写。常规 upgrade head 为确认已有结构，不拉数据、不补算。
3. 应用回滚保留原有表和全部新/旧报告/比较；新 schema 只在 JSON 中扩展，旧应用无法读取新快照时应暂时关闭报告入口，不能强制改写其快照或降级数据库。
4. `CLAIM_SNAPSHOT_ONLY`、`SOURCE_PAYLOAD_NOT_ARCHIVED`、`REPLAY_UNAVAILABLE` 保留。旧 M14/M15 快照无法凭空获得成本/会计/日期集合/Window 血缘；本轮不从实时数据库补洞，策略差值仍失败关闭。
5. 旧 bar 缺完整语义描述时提示 `CHART_SEMANTICS_INCOMPLETE` 并保留原表。当前来源不具完整日序列，任何 line 契约均保守退回表格。
6. 金融差值使用 Decimal；ECharts 所需 Number 仅用于屏幕坐标，绑定检查使用十进制文本精确身份，原值/单位始终保留。
7. 本轮未访问真实 LLM/生产数据，未触发九个 Agent 工具、回测、研究计算或策略变更；真实网络/模型连接不属于本次验收。
