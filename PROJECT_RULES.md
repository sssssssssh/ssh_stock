# 项目开发规则

## 文档权威顺序

1. `docs/股票机会发现系统_PRD_V1.0.md`
2. `docs/股票机会发现系统_系统设计_V1.0.md`
3. `PROJECT_RULES.md`
4. `README.md`

发现冲突时，不擅自改业务口径；在代码 TODO、README 和开发总结中说明冲突。

## 当前阶段

当前已完成 Milestone 0 到 Milestone 7：

- 工程骨架
- 数据库与迁移
- Provider 抽象
- Tushare 原始数据同步
- daily/backfill CLI
- 幂等 upsert
- 运行日志和原始数据质量检查
- 因子表 `stock_factor_daily`
- 复权 OHLC、MA、收益率、斜率、ATR、突破、higher-low、回撤、趋势效率、Eligible Universe、RPS
- 市场温度表 `market_daily`
- 行业元数据表 `sector`、行业成分表 `sector_member`
- 行业热度表 `sector_factor_daily`
- Market Score、Regime、Sector Heat、Heat Momentum、Lifecycle
- `recalc-market` / `recalc-sectors` CLI，并接入 daily/backfill
- 状态表 `stock_state_daily`
- 策略信号表 `strategy_signal`
- RightSideScore / TrendScore
- S0-S6 状态机
- RIGHT_SIDE_NEW / TREND_ENTER / MAIN_UP_ENTER / TREND_DECAY / LEADER_BREAKOUT 信号生成
- `recalc-states` CLI，并接入 daily/backfill
- 完整 REST API：dashboard / stocks / sectors / jobs / research
- 数据覆盖率接口：`GET /api/v1/system/data-coverage`
- 前端数据拉取按钮：通过 `POST /api/v1/jobs/backfill` 创建后台回填任务
- 前端任务状态面板：轮询 `GET /api/v1/jobs` 展示当前任务、最近任务、进度条、步骤和行数
- 后验评估表 `signal_forward_eval`
- `evaluate-signals` CLI
- Vue 3 + TypeScript + Vite + ECharts 前端
- pytest

当前阶段剩余重点：

- 补充更长历史数据后的真实策略参数校验。
- 基于更多历史样本扩展后验分桶和导出功能。
- 生产部署、权限控制和前端配置页。

## 架构规则

- API 与 worker 共用 `backend/app` Python package。
- 前端代码放在 `frontend/`，通过 `/api/v1` 调用后端。
- Tushare 只允许出现在 `backend/app/providers/tushare_provider.py`。
- 当前 Tushare 使用代理版 SDK 初始化：`ts.set_token(...)`、无参数 `ts.pro_api()`、再设置 `_DataApi__http_url` 为 `TUSHARE_HTTP_URL`。
- Tushare Provider 必须执行请求节流，间隔由 `TUSHARE_MIN_INTERVAL_SECONDS` 控制，默认 1.5 秒；历史回填失败频繁时优先调大到 2-3 秒。
- 业务服务依赖 `MarketDataProvider` 协议，不依赖具体 SDK。
- 日期在业务层使用 `YYYY-MM-DD` / `datetime.date`，调用 Tushare 时才转换为 `YYYYMMDD`。
- 原始数据表和任务表必须幂等写入。
- 数据库迁移用 Alembic，不手写临时建表脚本替代迁移。
- 配置阈值放在 `config/strategy.yaml`。
- 后验收益只能写入 `signal_forward_eval`，不得反写当日因子、状态或信号表。
- 前端 API 地址用 `frontend/.env` 的 `VITE_API_BASE_URL` / `VITE_API_PROXY_TARGET` 控制，不在源码里写死云端地址。
- API 触发数据拉取时必须创建 `job_run` 记录；同一时间只允许一个 `daily/backfill` 任务处于 `QUEUED/RUNNING`。
- 长任务必须持续更新 `job_run.step`、`row_count` 和 `job_metadata.progress_pct`，前端不得只显示“已提交”。
- 前端任务列表必须展示 `error_message`，不能只显示“失败”。
- Tushare 代理请求的 `requests` 网络异常必须自动重试；重试耗尽后再写入 FAILED。
- 本地开发时如果后端端口从 8000 改为 9034，必须同步修改 `frontend/.env` 的 `VITE_API_PROXY_TARGET`，否则前端会继续请求旧端口。

## 安全规则

- `TUSHARE_TOKEN` 只能来自环境变量。
- `TUSHARE_HTTP_URL` 只能来自环境变量或配置默认值，当前默认代理地址为 `https://fastapic.stockai888.top`。
- `.env` 不进入版本控制。
- 日志中不得输出 token。
- 本地服务默认只绑定 `127.0.0.1`。

## 可迁移规则

- 禁止在代码中写入本机绝对路径。
- Docker Compose 是本地和上云的共同部署基线。
- 迁移到新电脑时，以 README 的“换电脑继续开发”为准。
- Python 依赖以 `pyproject.toml` 为主；`requirements.txt` 和 `requirements-dev.txt` 作为传统 pip 安装入口同步维护。
- 前端依赖以 `frontend/package.json` 和 `frontend/package-lock.json` 为准。

## 文档维护规则

每次功能推进后同步更新：

- `README.md`
- `PROJECT_RULES.md`
- `docs/股票机会发现系统_PRD_V1.0.md`
- `docs/股票机会发现系统_系统设计_V1.0.md`
- 对应 `.docx` 版本

Markdown 是源码级文档，`.docx` 是面向阅读的导出版。
