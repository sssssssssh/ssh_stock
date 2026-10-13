# M16.5.1 Evidence Archive / Report v3 一致性收尾

## 改动与边界

- Report v3 冻结字段按 FACT、COMPARISON、结构化 INFERENCE 分派校验。直接事实的引用必须与字段路径逐项同序；推断只验证现有 FACT/COMPARISON 支持图、Evidence 子集和去重继承引用，不声称因果成立。旧 v1/v2 快照只执行原契约。
- 创建报告在 Archive 复核和 Report 行 `flush` 后、`commit` 前执行完整 `verify_report` 与 Manifest 绑定校验。失败回滚；请求 ID 幂等和原 JSON/Hash 保持不变。没有新增或修改迁移，0051 仍为 HEAD。
- 离线响应的 `facts_status` 表示直接字段复核；`status` 表示该 Claim 的支持或比较口径状态。新增可选 `check_kind`、`facts_applicable`、`support_status`、`claim_recheck_summary`。前端分别显示字段、比较许可、推断支持；M14/M15 缺完整冻结证明时不授予差值。
- 不查询最新业务表，不重跑算法，不修改九工具公开 Schema、Evidence v2 Hash、策略参数、已冻结 Snapshot/Archive/Comparison。

## 验证

- 修复前新增 FACT + INFERENCE 冻结报告单测稳定失败于 `frozen field bindings`；修复后通过。
- 本地 `python -m pytest tests/unit -q`：1002 passed；`python -m ruff check backend tests migrations scripts`、`git diff --check` 通过。`npm run test:coverage`：91 passed，语句覆盖率 81.42%；`npm run build` 通过。当前公网 `stock_db` 是业务库，没有在其中运行写入/清理型集成测试。
- 功能提交 `a69fb8952db3f40a57a0ef796075d9b972017f13` 的 [GitHub CI #79](https://github.com/sssssssssh/ssh_stock/actions/runs/38334164706) Success：隔离 PostgreSQL 17 完成 Alembic upgrade/downgrade/upgrade、`python -m pytest --cov=backend/app --cov-report=term-missing --cov-fail-under=70`（1214 passed，86.74% 覆盖率）、ruff、Docker Compose config/build、Nginx 配置检查、前端 91 项与 build。
- 新集成用例使用真实 Chat Compiler、Archive Assembler 与 Repository，覆盖混合 Claim 创建/读取/导出/归档/回放及预提交校验失败回滚与同 Request ID 重试。

## npm 依赖风险分类

`npm audit --registry=https://registry.npmjs.org --json`：11 项（4 critical、3 high、4 moderate）。镜像 `registry.npmmirror.com` 不实现 audit 接口，故改用官方 registry 查询，未执行 `npm audit fix`。

- 浏览器运行路径：`echarts <6.1.0` 的 XSS 告警（moderate），需要单独评估图表输入与 ECharts 6 兼容性，再安排升级。
- 构建/本地开发路径：`vite`、`esbuild`、`source-map-js`、`brace-expansion`；Vite 在本仓库列于 dependencies，但生产部署为 Nginx 静态产物，不运行 Vite dev server。开发机只绑定可信网络并避免打开不可信项目。
- 测试路径：`vitest`、`@vitest/coverage-v8`、`@vitest/mocker`、`tinypool`、`happy-dom`；其中含 critical 告警。不要公开测试 UI/服务，升级需配套 Node 版本和测试兼容评估。
- 当前 Windows Node 18 对部分锁定依赖出现 EBADENGINE 警告，后续依赖升级应先统一受支持的 Node 版本。本次不升级锁文件或改变生产依赖。

## 部署与回滚

上线前备份 PostgreSQL；应用后端与前端作为一组版本部署，0050/0051 无结构变更。观察 `REPORT_SNAPSHOT_INTEGRITY_ERROR`、`REPORT_ARCHIVE_UNVERIFIABLE`、创建后重试冲突率。若预验误拒绝，回退应用并暂停新报告创建；既有归档、报告和 Hash 不修改、不删除。关闭 `agent.archive.enabled` 只停止新归档捕获，不改变历史报告身份。

功能提交及 CI 已通过。本文档补录提交仅追加验收记录，不改变功能代码；其最终 SHA 与 CI 状态在交付回复中核对。M16.5.1 可按本文范围封版，仍保留上述 M14/M15 冻结口径及 npm 依赖告警限制。
