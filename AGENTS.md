# Codex 项目执行指南

本文件适用于整个仓库，是 Codex 在本项目中的执行入口。它规定开发流程和安全边界，
不替代产品需求、系统设计或里程碑冻结规则。具体业务口径始终以项目权威文档为准。

## 开始工作前

1. 先执行 `git status --short --branch`，确认当前分支和已有未提交修改。不得覆盖、回退或
   清理不属于当前任务的用户改动。
2. 按以下权威顺序阅读与任务相关的内容：
   - `docs/股票机会发现系统_PRD_V1.0.md`
   - `docs/股票机会发现系统_系统设计_V1.0.md`
   - `PROJECT_RULES.md`
   - `README.md`
3. 再阅读用户提供的当前任务书。任务书用于限定本次交付范围；如果它与仓库权威文档或
   用户最新要求冲突，不得自行改变业务口径，应明确指出冲突并以用户最新要求为准。
4. 查看相关代码、迁移和测试后再修改。不要只根据任务书中的文件名或旧代码片段猜测当前实现。
5. 保持当前检出的分支，不擅自切换分支、重置提交或拉取会覆盖本地状态的内容。

## 当前基线与范围

- 当前仓库已完成 Milestone 0 至 Milestone 16.2；准确状态以 `PROJECT_RULES.md` 的“当前阶段”
  和最新 Git 提交为准。
- 已封版模块、版本身份、PIT 语义、收益口径和 append-only 约束必须遵守
  `PROJECT_RULES.md`。除非用户任务明确要求，不扩展或重构这些边界。
- Milestone 16.1 的确定性八工具接口保持只读兼容。Milestone 16.2 可选 Chat Runtime 默认关闭；
  启用后也只能由模型编排这八个工具，不得开放任意 SQL/HTTP/代码执行、修改策略参数或触发
  数据、回测和研究计算。
- 不修改生产策略权重、阈值、S0-S6 定义或研究口径，除非任务书和用户明确要求且同步提供
  对应验收标准。
- 用户可见产品名称统一为“空间”。

## 项目结构

- `backend/app/api`：FastAPI 路由和请求边界。
- `backend/app/services`：应用服务与业务编排。
- `backend/app/domain`：领域模型和不依赖基础设施的计算逻辑。
- `backend/app/repositories`：数据库访问和持久化边界。
- `backend/app/providers`：外部数据源适配；Tushare SDK 只能出现在
  `tushare_provider.py`。
- `backend/app/models`、`backend/app/schemas`：ORM 与输入输出模型。
- `backend/app/jobs`：Worker、Scheduler 和任务执行入口。
- `frontend`：Vue 3、TypeScript、Vite 和 ECharts 前端。
- `migrations`：Alembic 迁移；数据库结构变更必须通过迁移交付。
- `config/strategy.yaml`：策略、质量和 Provider 阈值，不得在业务代码中重复硬编码。
- `tests/unit`、`tests/integration`：单元与 PostgreSQL 集成测试。

## 不可破坏的边界

- PostgreSQL 17 是数据库基线。API、Worker、Scheduler 共用 `backend/app`，但以独立进程运行。
- API 只负责校验和入队；长任务由 Worker 执行，Scheduler 只负责定时编排。
- 业务服务只能依赖 `MarketDataProvider` 协议，不得直接依赖 Tushare SDK。
- Raw 表只保存 Provider 事实数据。Derived、Research、Portfolio、Experiment 和 Walk-forward
  必须遵守现有 PIT、版本、配置哈希、source hash、owner 和 generation identity 约束。
- 当前结果查询必须使用当前身份过滤；历史研究不得用当前行业或题材成员覆盖历史快照。
- 已定义为 append-only 的 Artifact、快照和历史身份不得原地改写。
- 缺失值不得按 0 处理；失败不得伪装成空结果、成功或自动回退到旧身份。
- 日期在业务层使用 `datetime.date` 或 `YYYY-MM-DD`；交易日和业务“今天”使用项目 Clock 与
  `Asia/Shanghai` 口径，时间戳继续遵守现有 UTC 约定。
- Portfolio、Accounting、Research 和 Validation 中已有 Decimal 口径的计算不得退回 float。

## 数据库与安全

- `.env`、Token、密码、Cookie、数据库转储、生产数据和私有连接信息不得提交或写入日志。
- 不在代码、测试、文档或迁移中写入本机绝对路径和真实凭据。
- `python -m alembic upgrade head` 只升级表结构，不会拉取 Raw、补算因子或执行 Research。
- 不对用户数据库执行 `DROP`、`TRUNCATE`、全表 `DELETE`、降级迁移或批量清库，除非用户在
  当前请求中明确指定目标和范围；执行前必须再次核对连接目标与影响范围。
- 对模型、约束或索引的修改应同时提供 Alembic 迁移和 PostgreSQL 验收测试。不要用
  `create_all()` 或临时建表脚本替代正式迁移。
- 测试前确认 `DATABASE_URL` 指向允许测试的 PostgreSQL 17。不得为了让测试通过而修改或
  清理无关的用户业务数据。
- 本地服务默认绑定 `127.0.0.1`。对外绑定 `0.0.0.0` 时必须同时考虑防火墙、反向代理、
  TLS、管理员密码和安全 Cookie。

## 实现原则

- 先定位根因和现有抽象，再做最小范围修改；不顺带重构无关模块。
- 复用现有 Service、Repository、DTO、identity builder 和事务边界，不建立平行实现。
- 对外部输入使用结构化校验；新增 Agent 工具参数继续使用 Pydantic 且 `extra=forbid`。
- 数据写入必须保持幂等、事务原子性和既有锁序。失败路径同样需要保存规定的质量或审计证据。
- 修复缺陷必须增加能先复现问题、再证明修复有效的回归测试。
- 不通过降低断言、跳过测试、吞掉异常、扩大容差或静默 fallback 来制造通过结果。
- 修改前端时沿用现有组件与视觉体系，检查桌面和窄屏布局、加载态、空态、失败态及长文本。

## 验证矩阵

先运行最贴近改动的测试，再按影响范围扩大验证。文档改动至少执行：

```bash
git diff --check
```

后端或共享业务逻辑改动执行相关测试，并在交付前运行：

```bash
python -m pytest
python -m ruff check backend tests migrations scripts
```

数据库模型或迁移改动还要在 PostgreSQL 17 上执行：

```bash
python -m alembic upgrade head
python -m alembic current
python -m alembic heads
```

`current` 与 `heads` 必须一致。不要在含用户数据的数据库上运行 CI 中的降级测试。

前端改动在 `frontend/` 下执行：

```bash
npm ci
npm run test:coverage
npm run build
```

部署、依赖、Dockerfile 或 Compose 改动还要执行：

```bash
docker compose config
docker compose build
```

不得使用包含占位凭据的 `.env` 启动服务，也不得把“镜像构建成功”等同于“运行时连接已验证”。
无法运行某项验证时，交付总结必须写明原因和剩余风险。

## 文档维护

- 功能推进按照 `PROJECT_RULES.md` 的“文档维护规则”同步维护四份 Markdown 权威文档。
- `README.md` 记录环境、启动、部署、运维和用户可见流程。
- `PROJECT_RULES.md` 记录长期有效的业务不变量、冻结边界和当前阶段。
- PRD 记录产品范围与验收口径；系统设计记录架构、数据模型、流程和技术约束。
- `.docx` 是导出版，只有用户明确要求或准备正式导出时才更新。
- 本文件只记录跨任务长期有效的开发流程。临时任务步骤、一次性进度和聊天摘要不要写入本文件。

## Git 交付

- 提交前检查 `git status --short`、`git diff` 和 `git diff --check`，只包含本次任务相关文件。
- 不提交 `.env`、缓存、覆盖率文件、构建产物、临时归档或数据库文件。
- 不修改、压平或重写已有历史提交。只有用户明确要求时才创建提交或推送远端。
- 推送前运行本次影响范围要求的验证；推送后确认本地 `HEAD` 与目标远端分支一致。
- 最终汇报包含改动摘要、验证结果、提交哈希、推送分支，以及未执行项或剩余风险。

## 完成标准

任务只有在实现、回归测试、必要文档、迁移检查和用户要求的 Checklist 均完成后才算完成。
如果任务书限制了范围，验收时逐项对照，不以额外功能替代未完成条目。
