# A 股机会发现与趋势研究系统

本项目按 `docs/` 下两份 V1.0 Markdown 文档开发：

- `docs/股票机会发现系统_PRD_V1.0.md`
- `docs/股票机会发现系统_系统设计_V1.0.md`

当前实现范围：Milestone 0 到 Milestone 8。也就是项目骨架、数据库迁移、Tushare 原始数据同步、个股因子、市场温度、行业热度、趋势状态机、策略信号、完整 REST API、Vue 前端、后验评估、研究接口、数据可靠性改造、CLI 和测试。

已在 2026-09-01 增加 Milestone 8 数据可靠性改造：历史股票池 Point-in-Time、动态日线覆盖率检查、行业历史成分有效期、原始表 NULL upsert 保护、dirty range 向后重算、因子/市场/行业计算版本追踪。2026-09-02 追加数据拉取链路优化：Raw 数据按数据集完整性恢复、基础信息前置校验、Provider 日志独立事务、Tushare 进程级限流和指数区间拉取。

当前网页显示名称为“空间”。

## 已实现

- Python 3.12 + FastAPI 后端骨架
- SQLAlchemy 2.x 数据模型
- Alembic 数据库迁移
- PostgreSQL Docker Compose 本地开发配置
- Pydantic Settings + YAML 配置加载
- MarketDataProvider 抽象
- TushareProvider，token 只从环境变量读取
- stock_basic / trade_calendar / stock_daily / stock_adj_factor / stock_daily_basic / index_daily 入库服务
- sync-basic / backfill / recalculate 三段式任务：基础信息、原始行情、分析计算分开运行
- daily / scheduler CLI 保留收盘后一体化日更流水线
- job_run 与 provider_api_log 运行日志
- P0 原始数据质量检查
- stock_factor_daily 因子表
- Factor Engine：复权 OHLC、MA、收益率、斜率、ATR、突破、higher-low、回撤、趋势效率、Eligible Universe、RPS
- market_daily 市场温度表：Market Score、Regime、市场宽度、涨跌家数、新高新低、成交额活跃度
- sector / sector_member / sector_factor_daily 行业表：行业元数据、行业成分、Sector Heat、Heat Momentum、Lifecycle
- recalc-market / recalc-sectors CLI，并已接入 daily / recalculate
- stock_state_daily 趋势状态表：RightSideScore、TrendScore、S0-S6、OpportunityScore
- strategy_signal 策略信号表：RIGHT_SIDE_NEW、TREND_ENTER、MAIN_UP_ENTER、TREND_DECAY、LEADER_BREAKOUT
- recalc-states CLI，并已接入 daily / recalculate
- signal_forward_eval 后验评估表
- evaluate-signals CLI：计算信号后 5/10/20/60 个交易日收益、MFE20、MAE20
- Dashboard / Stocks / Sectors / Research REST API
- Vue 3 + TypeScript + Vite + ECharts 前端
- pytest 单元测试与 API 集成测试

## 先判断你的数据库环境

### 场景 A：你用云端 PostgreSQL

你已经有云端 PostgreSQL，例如 PG17。

这种情况下：

- 不需要执行 `docker compose up -d postgres`
- 只需要在 `.env` 里填写云端 `DATABASE_URL`
- 仍然需要执行 `python -m alembic upgrade head` 创建业务表

`.env` 示例：

```dotenv
DATABASE_URL=postgresql+psycopg://用户名:密码@云数据库地址:5432/数据库名
TUSHARE_TOKEN=你的TushareToken
TUSHARE_HTTP_URL=https://fastapic.stockai888.top
TUSHARE_MIN_INTERVAL_SECONDS=1.5
API_HOST=127.0.0.1
API_PORT=8000
APP_TIMEZONE=Asia/Shanghai
LOG_LEVEL=INFO
```

如果云数据库要求 SSL，使用：

```dotenv
DATABASE_URL=postgresql+psycopg://用户名:密码@云数据库地址:5432/数据库名?sslmode=require
```

### 场景 B：你用本机已安装的 PostgreSQL

你电脑上已经安装并启动了 PostgreSQL。

这种情况下：

- 不需要执行 `docker compose up -d postgres`
- 只需要把 `.env` 的 `DATABASE_URL` 指向本机 PostgreSQL
- 仍然需要执行 `python -m alembic upgrade head` 创建业务表

`.env` 示例：

```dotenv
DATABASE_URL=postgresql+psycopg://stock:stock@127.0.0.1:5432/stock_db
TUSHARE_TOKEN=你的TushareToken
TUSHARE_HTTP_URL=https://fastapic.stockai888.top
TUSHARE_MIN_INTERVAL_SECONDS=1.5
API_HOST=127.0.0.1
API_PORT=8000
APP_TIMEZONE=Asia/Shanghai
LOG_LEVEL=INFO
```

### 场景 C：你没有数据库，想用 Docker 本地启动 PostgreSQL

这种情况下才需要执行：

```powershell
docker compose up -d postgres
```

`.env` 可以使用：

```dotenv
DATABASE_URL=postgresql+psycopg://stock:stock@127.0.0.1:5432/stock_db
POSTGRES_PASSWORD=stock
TUSHARE_TOKEN=你的TushareToken
TUSHARE_HTTP_URL=https://fastapic.stockai888.top
TUSHARE_MIN_INTERVAL_SECONDS=1.5
API_HOST=127.0.0.1
API_PORT=8000
APP_TIMEZONE=Asia/Shanghai
LOG_LEVEL=INFO
```

## 第一次启动流程

### 1. 复制环境变量文件

```powershell
Copy-Item .env.example .env
```

作用：生成本机私有配置文件。

什么时候跳过：如果你已经有 `.env`，不要重复覆盖，直接编辑现有 `.env`。

### 2. 编辑 `.env`

必须填写：

```dotenv
DATABASE_URL=你的数据库连接
TUSHARE_TOKEN=你的TushareToken
TUSHARE_HTTP_URL=https://fastapic.stockai888.top
TUSHARE_MIN_INTERVAL_SECONDS=1.5
```

说明：

- `DATABASE_URL` 控制 Alembic、API、CLI 连接哪个数据库。
- `TUSHARE_TOKEN` 用来调用 Tushare 代理接口。
- `TUSHARE_HTTP_URL` 是 Tushare SDK 的代理 API 地址，当前使用 `https://fastapic.stockai888.top`。
- `TUSHARE_MIN_INTERVAL_SECONDS` 控制整个后端进程内每次 Tushare 请求之间的最小间隔，默认 `1.5` 秒。代理频繁断开时可以改成 `2` 或 `3`；确认不限流时可以改成 `0` 关闭节流。
- `.env` 不会进入 Git，不要把密码写进 README 或代码。

本项目使用代理版 Tushare 初始化方式：先执行 `ts.set_token(TUSHARE_TOKEN)`，再执行无参数 `ts.pro_api()`，最后把 SDK 内部请求地址改为 `TUSHARE_HTTP_URL`。这段逻辑集中在 `backend/app/providers/tushare_provider.py`，业务服务不要直接调用 `tushare`。

如果你曾经在系统环境变量里单独设置过 Tushare SDK 自己使用的 token，建议删除或确保它和 `.env` 里的 `TUSHARE_TOKEN` 一致。项目代码会显式调用 `ts.set_token(...)`，但保留旧的系统级 token 容易让排查变复杂。

### 3. 安装 Python 依赖

推荐普通安装：

```powershell
python -m pip install -r requirements-dev.txt
```

作用：安装运行、开发和测试依赖。

什么时候跳过：同一台电脑已经安装过，且 `requirements*.txt` 没变，可以跳过。

也可以使用 editable 安装：

```powershell
python -m pip install -e .[dev]
```

作用：把当前项目以开发模式安装到 Python 环境。频繁开发 Python 包时更方便。

### 4. 设置 PYTHONPATH

```powershell
$env:PYTHONPATH = "backend"
```

作用：让 Python 能找到 `backend/app` 里的 `app` 包。

什么时候跳过：

- 如果你使用的是 `uvicorn --app-dir backend` 启动 API，可以不设置。
- 如果你已经执行过 `python -m pip install -e .[dev]`，多数情况下也可以不设置。
- 如果执行 `python -m app.cli ...` 提示找不到 `app`，就必须设置。

### 5. 启动数据库

只有场景 C 需要执行：

```powershell
docker compose up -d postgres
```

作用：用 Docker 在本机启动 PostgreSQL。

什么时候跳过：

- 你使用云端 PostgreSQL，跳过。
- 你使用本机已安装 PostgreSQL，跳过。

### 6. 自动建表

```powershell
python -m alembic upgrade head
```

作用：读取 `.env` 里的 `DATABASE_URL`，自动在目标 PostgreSQL 里创建或升级业务表。

什么时候跳过：

- 第一次连接一个新数据库时不能跳过。
- 后续代码没有新增 migration 时可以跳过。
- 拉到新代码后如果 `migrations/versions/` 有新增文件，需要再执行一次。

当前会创建这些表：

- `stock_basic`
- `trade_calendar`
- `stock_daily`
- `stock_adj_factor`
- `stock_daily_basic`
- `index_daily`
- `job_run`
- `provider_api_log`
- `stock_factor_daily`
- `market_daily`
- `sector`
- `sector_member`
- `sector_factor_daily`
- `stock_state_daily`
- `strategy_signal`
- `signal_forward_eval`
- `data_quality_daily`
- `data_dirty_range`

### 7. 启动 API

```powershell
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

作用：启动后端 HTTP 服务。

启动后检查：

```text
http://127.0.0.1:8000/health
```

查看系统数据状态：

```text
http://127.0.0.1:8000/api/v1/system/status
```

什么时候跳过：如果你只想跑 CLI 同步数据，不需要打开 API，可以跳过。

如果你像之前一样使用 `9034` 端口启动，命令改成：

```powershell
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 9034
```

对应检查地址就是：

```text
http://127.0.0.1:9034/health
http://127.0.0.1:9034/api/v1/system/status
```

如果 Windows 启动 8000 端口时报 `WinError 10013` 或提示端口绑定权限不允许，可以直接改用 9034；同时把 `frontend/.env` 里的 `VITE_API_PROXY_TARGET` 改成 `http://127.0.0.1:9034`。

注意：`/` 根路径没有页面，直接打开会返回 404。后端健康检查用 `/health`，前端页面用下面的 Vite 地址。

### 8. 启动前端

第一次进入前端目录需要安装依赖：

```powershell
cd frontend
npm install
```

作用：安装 Vue、Vite、ECharts 等前端依赖。

什么时候跳过：同一台电脑已经执行过，且 `frontend/package-lock.json` 没变化，可以跳过。

启动前端：

```powershell
npm run dev
```

默认打开：

```text
http://127.0.0.1:5173
```

前端默认把 `/api` 代理到 `http://127.0.0.1:9034`。如果你的后端跑在 8000，把 `frontend/.env.example` 复制为 `frontend/.env` 后修改：

```dotenv
VITE_API_BASE_URL=/api/v1
VITE_API_PROXY_TARGET=http://127.0.0.1:8000
```

## 常用命令

### 检查配置是否读到

```powershell
$env:PYTHONPATH = "backend"
python -m app.cli check-config
```

作用：脱敏显示当前读取到的 `.env` 路径、数据库连接是否存在、Tushare token 是否存在、token 长度、首尾掩码、Tushare 代理地址和请求最小间隔。

如果 `tushare_token_length` 明显不是你预期的长度，通常是 `.env` 中 `TUSHARE_TOKEN` 填错、复制了额外内容、带了多余空格/引号，或者填成了其他平台的 token。如果 `tushare_http_url` 不是 `https://fastapic.stockai888.top`，说明代理地址没有按当前项目要求加载。如果 `tushare_min_interval_seconds` 太小，历史回填时可能更容易触发代理限流或瞬断。

### 检查 Tushare token 是否可用

```powershell
$env:PYTHONPATH = "backend"
python -m app.cli check-tushare
```

作用：调用一个很小的 Tushare `trade_cal` 请求，确认 token 是否能被 Tushare 服务端接受。

如果返回类似 `token无效` 或 Tushare 错误码 `40101`，说明当前 `.env` 里的 token 没有被 Tushare 接受。此时先去 Tushare Pro 个人中心重新复制 token，只复制 token 本身，不要复制说明文字、前后空格或换行。

### 常见报错处理

如果 `daily` 报 SQLAlchemy 链接 `https://sqlalche.me/e/20/e3q8`，先看报错前面的真实错误：

- 如果数据库迁移版本不是最新，执行 `python -m alembic upgrade head`。当前最新应为 `0008_dirty_retry_metadata`。
- 如果看到 `number of parameters must be between 0 and 65535`，说明旧代码一次性 upsert 行数太多；当前代码已经把 `upsert_rows` 改为自动分批写入。
- 如果 `sector_factor_daily rows=0` 但任务成功，通常是因为数据库只有单日行情，Eligible Universe 需要历史 lookback。先做历史回填，再重算行业热度。

如果前端任务状态显示失败，并且错误中包含 `SSLEOFError`、`UNEXPECTED_EOF_WHILE_READING` 或 `Max retries exceeded with url: /trade_cal` / `/stock_basic`，通常是 Tushare 代理 HTTPS 连接被中途断开，不是数据库重复或建表问题。当前 `TushareProvider` 已对 `requests` 网络异常做 3 次自动重试，并默认在每次 Tushare 请求之间等待 `TUSHARE_MIN_INTERVAL_SECONDS=1.5` 秒；如果仍失败，可以把 `.env` 改成 `TUSHARE_MIN_INTERVAL_SECONDS=2` 或 `3`，重启后端后再重新点击“拉取数据”。可以先执行：

```powershell
$env:PYTHONPATH = "backend"
python -m app.cli check-tushare
```

如果 `check-tushare` 返回 `tushare_ok=true`，说明 token 和代理当前可用。

### 健康检查

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

### 同步某一天数据

```powershell
$env:PYTHONPATH = "backend"
python -m app.cli daily --trade-date 2026-08-25
```

作用：调用 Tushare，执行指定交易日的完整收盘后流水线。

会同步：

- 交易日历
- 股票基础信息
- A 股日线
- 复权因子
- 每日指标
- 指数日线
- 申万行业元数据
- 申万行业成分

随后会自动计算：

- `stock_factor_daily`
- `market_daily`
- `sector_factor_daily`
- `stock_state_daily`
- `strategy_signal`

什么时候使用：你想对某一个交易日执行“拉取 + 计算”的完整日更任务时使用。

什么时候跳过：如果你只是启动 API 看服务是否能跑，或者只想拉原始数据、不想计算，可以跳过。只拉原始数据时用下面的 `sync-basic` + `backfill`。

### 同步基础信息

```powershell
$env:PYTHONPATH = "backend"
python -m app.cli sync-basic
```

作用：只调用 Tushare 同步股票基础信息、申万行业元数据和申万行业成分。

会同步：

- `stock_basic`
- `sector`
- `sector_member`

不会计算：

- `stock_factor_daily`
- `market_daily`
- `sector_factor_daily`
- `stock_state_daily`
- `strategy_signal`

什么时候使用：第一次建库、Tushare 股票状态变化后，或者前端拉原始数据前发现 `stock_basic` 缺失时使用。这个任务容易受 Tushare 基础资料接口影响，已经和原始行情回填、因子计算拆开。

### 历史回填

```powershell
$env:PYTHONPATH = "backend"
python -m app.cli backfill --start 2021-01-01 --end 2026-08-25
```

作用：按交易日循环同步历史原始行情数据。

会同步：

- 交易日历
- A 股日线
- 复权因子
- 每日指标
- 指数日线

不会同步：

- 股票基础信息
- 行业元数据
- 行业成分

不会计算：

- 个股因子
- 市场温度
- 行业热度
- 趋势状态
- 策略信号
- 信号后验

什么时候使用：第一次初始化历史数据库时使用。

注意：历史回填会比较慢，也会消耗 Tushare 调用额度。回填前必须先完成“同步基础信息”，否则无法建立 Point-in-Time 股票池。回填同一日期范围时，已经完整并通过质量校验的 Raw 数据集会跳过，避免重复拉取。回填完成后如需更新总览、行业热度和股票池，再执行 `POST /api/v1/jobs/recalculate` 或下面的补算命令。

### 重算因子

```powershell
$env:PYTHONPATH = "backend"
python -m app.cli recalc-factors --start 2026-08-25 --end 2026-08-25
```

作用：从数据库中的 `stock_daily`、`stock_adj_factor`、`stock_basic`、`index_daily` 读取数据，计算并写入 `stock_factor_daily`。

什么时候使用：

- 你已经同步过原始行情，想单独重算因子。
- 修改了 `config/strategy.yaml` 中的 universe / factor 参数。
- 新增或修复因子计算逻辑后，需要回填历史因子。

注意：`backfill` 当前只拉原始数据，不会自动调用因子、市场温度、行业热度、趋势状态和策略信号计算；手动 `recalc-factors` 主要用于补算或重算个股因子。`daily` 仍保留完整日更流水线。

### 重算市场温度

```powershell
$env:PYTHONPATH = "backend"
python -m app.cli recalc-market --start 2026-08-25 --end 2026-08-25
```

作用：从数据库中的 `stock_factor_daily`、`stock_daily`、`index_daily` 读取数据，计算并写入 `market_daily`。

什么时候使用：

- 已经有原始行情和个股因子，想单独重算 Market Score / Regime。
- 修改了 `config/strategy.yaml` 中 `market` 或 `benchmark` 参数。
- 修复市场温度算法后，需要回填历史市场状态。

注意：市场温度依赖 `stock_factor_daily`，所以如果你刚改过因子逻辑，先执行 `recalc-factors`。

### 重算行业热度

```powershell
$env:PYTHONPATH = "backend"
python -m app.cli recalc-sectors --start 2026-08-25 --end 2026-08-25
```

作用：从数据库中的 `sector_member`、`stock_factor_daily`、`index_daily` 读取数据，计算并写入 `sector_factor_daily`。

什么时候使用：

- 已经同步过行业元数据、行业成分和个股因子，想单独重算 Sector Heat。
- 修改了 `config/strategy.yaml` 中 `sector` 或 `benchmark` 参数。
- 修复行业热度或生命周期算法后，需要回填历史行业热度。

注意：行业热度依赖 `sector`、`sector_member` 和 `stock_factor_daily`。如果行业表没有数据，先执行一次 `python -m app.cli sync-basic` 或在页面点击“同步基础信息”，让系统同步行业元数据和成分。

### 重算趋势状态和策略信号

```powershell
$env:PYTHONPATH = "backend"
python -m app.cli recalc-states --start 2026-08-25 --end 2026-08-25 --algo-version v1.0
```

作用：从数据库中的 `stock_factor_daily`、`market_daily`、`sector_member`、`sector_factor_daily` 和历史 `stock_state_daily` 读取数据，计算并写入 `stock_state_daily` 和 `strategy_signal`。

什么时候使用：

- 已经完成原始行情、个股因子、市场温度和行业热度计算，想单独重算 S0-S6。
- 修改了 `config/strategy.yaml` 中 `right_side` 或 `trend` 参数。
- 修复状态机或信号规则后，需要回填历史状态和信号。

注意：如果数据库只有单日行情，系统会先生成基础状态；RIGHT_SIDE_NEW 等信号通常需要足够历史 lookback 才会出现。

### 评估信号后验收益

```powershell
$env:PYTHONPATH = "backend"
python -m app.cli evaluate-signals --signal-type RIGHT_SIDE_NEW --algo-version v1.0
```

作用：读取 `strategy_signal` 和 `stock_factor_daily`，计算信号后 5/10/20/60 个交易日收益、MFE20、MAE20，并写入 `signal_forward_eval`。

什么时候使用：

- 已经完成历史回填，并且 `strategy_signal` 中有信号。
- 想查看某类信号的真实后验表现。
- 修改信号规则后，需要重新评估历史信号。

注意：后验评估只写入 `signal_forward_eval`，不会反写当日因子、状态或信号表，避免未来函数。

### 常用 API

```text
GET /api/v1/dashboard/summary
GET /api/v1/system/data-coverage?start=&end=&limit=
GET /api/v1/sectors/heat?trade_date=&level=L1&sort=heat_score&limit=30
GET /api/v1/sectors/{sector_id}?trade_date=
GET /api/v1/sectors/{sector_id}/history?start=&end=
GET /api/v1/stocks/right-side?trade_date=&new_only=true&limit=50
GET /api/v1/stocks/trends?trade_date=&states=S4,S5&limit=50
GET /api/v1/stocks/decay?trade_date=&limit=50
GET /api/v1/stocks/{ts_code}/overview?trade_date=
GET /api/v1/stocks/{ts_code}/history?start=&end=
GET /api/v1/stocks/{ts_code}/factors?start=&end=
GET /api/v1/stocks/{ts_code}/realtime-kline?days=180
GET /api/v1/research/signals/stats?signal_type=RIGHT_SIDE_NEW&algo_version=v1.0
GET /api/v1/research/signals/buckets?signal_type=RIGHT_SIDE_NEW&bucket_field=opportunity_score
GET /api/v1/jobs?status=success&job_type=daily&limit=20&offset=0
POST /api/v1/jobs/daily
POST /api/v1/jobs/sync-basic
POST /api/v1/jobs/backfill
POST /api/v1/jobs/recalculate
POST /api/v1/jobs/validate-data
```

`/api/v1/system/data-coverage` 用来查看已经拉取了哪些交易日，以及每个交易日在核心数据表里的行数。前端“数据”页面的“数据覆盖”面板已经接入这个接口。
不传 `limit` 时会返回数据库里全部已拉取交易日；传入 `start` / `end` 时只返回日期范围内的已拉取交易日；传入 `limit` 时只截取指定条数且不设置后端最大上限。

前端已经改为带目录的页面切换结构，左侧目录包含：

- `总览`：市场核心指标、市场分布图、行业热度图、信号后验统计。
- `数据`：基础信息同步、原始行情拉取、分析补算、当前任务、最近任务、覆盖日历和覆盖明细表。
- `长线`：右侧池、趋势池和行业热度列表。
- `短线`：衰退/风险池、策略信号计数和行业短线动量。

长线股票池和短线风险池里的股票代码可以点击查看实时 K 线。该功能调用 `GET /api/v1/stocks/{ts_code}/realtime-kline?days=180`，后端实时从 Tushare 查询最近 180 个自然日的日 K 数据，返回前端绘制 K 线和 MA5 / MA20 / MA60，不写入本地数据库。180 个自然日通常覆盖约 120 个交易日，适合观察中期趋势；页面也提供 90 / 180 / 365 日切换。

如果页面出现目录按钮像浏览器默认按钮、内容从最左侧裸排的情况，通常是 Vite 开发服务仍在返回旧的 `frontend/src/style.css`。处理方式：在前端终端按 `Ctrl+C` 停掉 `npm run dev`，重新执行 `npm run dev -- --host 127.0.0.1 --port 5173`，然后浏览器强制刷新页面。

“数据”页面的“拉取数据与任务”面板分成两个入口：

- 点击“同步基础信息”：调用 `POST /api/v1/jobs/sync-basic`，只同步 `stock_basic`、`sector`、`sector_member`，不计算因子和股票池。
- 选择开始日期和结束日期后点击“拉取原始数据”：调用 `POST /api/v1/jobs/backfill`，只同步交易日历、日线、复权因子、每日指标和指数日线，不计算因子和股票池。

“数据”页面里的“补算因子与股票池”“拉取数据与任务”“数据覆盖日历”三个面板支持点击标题收起/展开。收起后只保留标题行和右侧操作区，方便减少页面纵向占用。

“数据”页面第一块是“补算因子与股票池”。当你已经补拉了更早的原始行情，但总览、行业热度、股票池仍然为空时，可以在这里选择日期范围并点击“开始补算”。它会调用 `POST /api/v1/jobs/recalculate` 创建后台任务，依次重新计算：

- `stock_factor_daily`：均线、收益、RPS、Eligible Universe 等个股因子。
- `market_daily`：市场温度。
- `sector_factor_daily`：行业热度。
- `stock_state_daily` / `strategy_signal`：趋势状态和股票池信号。
- 可选 `signal_forward_eval`：信号后验评估。

补算任务的因子阶段会按自然月拆分执行。页面任务状态会显示当前分块范围、累计写入行数和进度百分比；行数会在当前因子分块完成并写库后更新，所以单个分块计算中可能短时间保持 0。

推荐使用顺序：先“同步基础信息”，再“拉取原始数据”，最后按同一日期范围执行“开始补算”。如果只是 Tushare 基础资料接口失败，只需要重试“同步基础信息”，不会占用时间去计算因子。

“数据覆盖日历”会按月份显示数据覆盖情况：

- `休`：休市日。
- `缺`：交易日但还没有拉取日线。
- `原`：已拉原始行情，但还没有完成分析补算。
- `算`：已经完成因子、市场和状态等基础分析。
- `全`：基础分析和行业热度都已完成。
- `差`：原始数据存在，但质量检查发现 ERROR，系统会阻止当日下游计算。

### 数据可靠性规则

本项目当前数据层遵循以下规则：

- `stock_basic` 同步时会分别拉取 `L` 当前上市、`D` 退市、`P` 暂停/其他历史状态，避免历史研究只剩当前上市股票。
- 历史股票池不再依赖当前 `list_status == L`，而是使用 `list_date <= trade_date` 且 `delist_date` 为空或 `trade_date <= delist_date`。
- `daily` 不再使用固定 `min_rows=1`。系统会从 `stock_basic` 计算当日 expected 股票数，再和 Tushare 返回的实际代码集合比较。
- 覆盖率阈值在 `config/strategy.yaml`：

```yaml
data_quality:
  daily:
    warning_coverage_rate: 0.98
    error_coverage_rate: 0.95
  cross_table:
    adj_vs_daily:
      warning_coverage_rate: 0.98
      error_coverage_rate: 0.95
    basic_vs_daily:
      warning_coverage_rate: 0.98
      error_coverage_rate: 0.95
    factor_vs_daily:
      warning_coverage_rate: 0.98
      error_coverage_rate: 0.90
    state_vs_factor:
      warning_coverage_rate: 0.98
      error_coverage_rate: 0.90
raw_quality:
  adj_factor:
    warning_coverage_rate: 0.98
    error_coverage_rate: 0.95
  daily_basic:
    warning_coverage_rate: 0.98
    error_coverage_rate: 0.95
provider:
  tushare:
    safe_limits:
      stock_basic: 5800
      daily: 5800
      daily_basic: 5800
```

达到 WARNING 时可以继续入库；低于 ERROR 时会记录 `data_quality_daily` 并阻止后续因子、市场、行业、状态和信号计算。
跨表校验中，`adj_vs_daily`、`basic_vs_daily`、`factor_vs_daily`、`state_vs_factor` 出现 ERROR 时，`daily` / `recalculate` 不允许标记 SUCCESS。`backfill` 现在只负责原始数据拉取，并按 `stock_daily`、`stock_adj_factor`、`stock_daily_basic`、`index_daily` 四个 Raw 数据集逐项判断完整性；完整数据集会跳过，不完整数据集才重新请求 Tushare。

- `stock_daily`、`stock_adj_factor`、`stock_daily_basic`、`index_daily` 启用 NULL upsert 保护。新数据字段为 NULL 时不会清空数据库已有非空值。
- 如果已有原始数据被新的非空值修订，系统会记录 `data_dirty_range`。后续可以用 `POST /api/v1/jobs/recalculate` 的 `mode=dirty_repair` 从最早 dirty date 重算到最新已拉取交易日。repair 失败后 dirty range 会恢复为 `OPEN`，并记录 `retry_count`、`last_error`、`last_failed_at`，下一次可以继续重试。
- `stock_factor_daily`、`market_daily`、`sector_factor_daily` 新增 `calc_version`、`config_hash`、`calc_run_id`、`calculated_at`，用于追溯这条衍生数据由哪个配置和哪次任务算出。
- `backfill` 和 `validate-data` 启动前会检查 `stock_basic` 是否同时具备 `L` 和 `D` 状态；缺失时会失败并提示 `stock_basic is missing or incomplete, run sync-basic first`。
- 申万行业成分同步按一级行业 `L1` 分批请求 `is_new=Y/N`，同时保存当前和历史成分，不再只按股票代码去重。
- `index_daily` 历史回填会优先按指数代码和日期区间批量拉取，避免逐交易日重复请求指数。
- Provider API 调用日志使用独立数据库 Session 写入，不会提前提交业务数据；业务入库成功和失败仍由同步服务自己的事务控制。
- 交易日历为空或返回范围不覆盖请求日期时会失败；`daily` 如果目标日期是休市日，会以 `SUCCESS` + `noop=true` 结束，不继续拉行情和计算。
- 当前 Raw 完整性检查尚未扣除停牌股票，expected 股票池仍按上市/退市日期判断；停牌维度留到 Milestone 9 以后增加。

Dirty repair API 请求示例：

```json
{
  "start": "2026-01-01",
  "end": "2026-08-31",
  "evaluate_signals": true,
  "mode": "dirty_repair"
}
```

`dirty_repair` 模式下后端会自动使用 `data_dirty_range` 的最早 OPEN 日期作为开始日期，并以最新 `stock_daily` 日期作为结束日期；请求里的 `start/end` 只是为了保持接口兼容。

如果在“补算因子与股票池”里勾选“评估信号”，补算完成后会继续执行一次 `evaluate-signals`，把已有信号的后验收益写入 `signal_forward_eval`。“拉取原始数据”不会触发信号评估。

同一时间只允许一个 `daily`、`sync_basic`、`backfill`、`recalculate` 或 `validate_data` 任务处于 `QUEUED/RUNNING` 状态，避免重复点击造成多个长任务同时跑。任务进度可以通过 `GET /api/v1/jobs?limit=30` 查看。

存量历史 Raw 数据质量补校验：

```powershell
$env:PYTHONPATH = "backend"
python -m app.cli validate-data --start 2020-01-01 --end 2026-08-31
```

也可以调用 API：

```http
POST /api/v1/jobs/validate-data
Content-Type: application/json

{"start":"2020-01-01","end":"2026-08-31"}
```

`validate-data` 不访问 Tushare，不重新下载历史数据，只基于数据库中已有的 `stock_daily`、`stock_adj_factor`、`stock_daily_basic`、`index_daily`、交易日历和 Point-in-Time 股票池补写 `data_quality_daily`，并同步记录跨表质量。旧数据库升级后建议先执行 `validate-data`，再执行 backfill / recalculate。

Raw 数据层最终收尾已完成：

- `validate-data` 与 `backfill` 共用 `check_raw_completeness()`，按 Raw 四类数据集统一判断 PASS / WARNING / ERROR。
- `validate-data` 汇总的 `pass_days`、`warning_days`、`error_days` 根据 `RawCompletenessResult.overall_status` 统计，不再只看 `stock_daily`。
- API 进度元数据会返回 `current_day_datasets`、`current_day_status` 和 `current_day_invalid_counts`。
- CLI `validate-data` 在成功后显式 `commit()`，异常时显式 `rollback()`。
- RawCompleteness / validate-data 二次完整性校验不会覆盖 `sync_daily()` 首次采集记录的 `duplicate_count` 和 `null_count`。
- Raw 核心字段有效性已纳入完整性：`adj_factor` 必须非空且大于 0，`index_daily.close/pre_close` 必须非空且大于 0，`daily_basic` 只检查 `close/total_mv/circ_mv`。
- `sector_member` 当前成员批次 `is_new=Y` 返回空结果会失败并提示 L1 行业代码；历史批次 `is_new=N` 允许为空。
- Raw 数据层按当前 Milestone 8 范围封版；后续可交易性数据进入 Milestone 9。

数据覆盖面板中间会显示“当前任务”和“最近任务”：

- `当前任务`：显示排队中/运行中/已完成/失败、进度条、当前步骤、当前交易日、已处理交易日数量和已写入行数。
- `当前任务`：运行中会每秒刷新“已耗时”。
- `最近任务`：默认请求最近 30 个任务，列表区域内部滚动展示；显示任务类型、状态、步骤、日期范围和耗时。已完成/失败任务显示总耗时，运行中任务显示当前已耗时。
- 任务步骤、日期范围和错误信息如果被列宽截断，可以把鼠标移动到对应行或错误文本上查看完整内容。
- 页面每 5 秒自动刷新任务状态；有运行中任务时也会同步刷新数据覆盖表。
- 底部“覆盖明细”默认加载全部已拉取交易日，并按页展示，默认每页 20 条，可切换为 10 / 20 / 50 / 100 条，避免数据多时页面无限下拉。

### 本地定时任务

```powershell
$env:PYTHONPATH = "backend"
python -m app.cli scheduler
```

作用：启动本地 APScheduler，按 `config/app.yaml` 里的时间运行 daily job。

什么时候跳过：你打算手动执行 daily，或者用云服务器 crontab/定时任务调度时，可以跳过。

## 最简启动路径

### 你已经填好云端数据库连接

终端 1 执行：

```powershell
python -m pip install -r requirements-dev.txt
$env:PYTHONPATH = "backend"
python -m alembic upgrade head
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

终端 2 执行：

```powershell
cd frontend
npm install
npm run dev
```

不要执行：

```powershell
docker compose up -d postgres
```

### 你要用 Docker 本地数据库

终端 1 执行：

```powershell
Copy-Item .env.example .env
python -m pip install -r requirements-dev.txt
docker compose up -d postgres
$env:PYTHONPATH = "backend"
python -m alembic upgrade head
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

终端 2 执行：

```powershell
cd frontend
npm install
npm run dev
```

## 测试

```powershell
$env:PYTHONPATH = "backend"
python -m pytest
python -m ruff check .
cd frontend
npm run build
```

## 数据任务进度说明

- 任务列表默认显示最近 30 条，列表内部滚动；错误信息会单独占整行展示，鼠标悬停可以看完整错误。
- 失败任务的错误信息会占用独立的第二行并撑开当前任务行，不会覆盖下一条任务。
- `30/40/50/60` Raw 拉取阶段会显示当前交易日和当前数据集。
- backfill 失败后可以重跑同一日期范围；系统会按 `stock_daily`、`stock_adj_factor`、`stock_daily_basic`、`index_daily` 分数据集判断完整性，已完整的数据集会跳过，未完整的数据集才重新请求 Tushare。
- 旧历史数据如果 `quality_status=None`，backfill 不会直接当作已验证；系统会先用库内已有数据补做一次质量校验，PASS/WARNING 才跳过，ERROR 会重新拉取。
- `90 计算个股因子` 阶段按自然月分块显示，行数会在当前分块完成写库后更新。
- `recalculate` 的 `100/110/120` 分别表示计算市场温度、行业热度、趋势状态与策略信号；这些批量计算阶段可能在完成后才更新处理行数。`daily` 不再同步行业元数据和行业成分，行业基础信息由 `sync-basic` 独立维护。
- `stock_basic required statuses missing` 会同时展示 Tushare 对应状态的原始错误，例如限频、代理 SSL 或接口返回异常，便于判断真实失败原因。
- 如果后端正在执行旧进程中的任务，修改后的后端进度展示规则要等该任务结束并重启后端后，才会作用于新任务。

## 换电脑继续开发

1. 安装 Python 3.12、Docker Desktop、Git、Node.js 22 LTS。
2. 进入项目根目录。
3. 阅读 `PROJECT_RULES.md`、`docs/` 下两份 Markdown 文档和本 README。
4. 复制 `.env.example` 为 `.env`，填入数据库连接和 `TUSHARE_TOKEN`。
5. 执行 `python -m pip install -r requirements-dev.txt`。
6. 如果使用 Docker 本地数据库，执行 `docker compose up -d postgres`；如果使用云数据库或已有本机数据库，跳过。
7. 执行 `python -m alembic upgrade head`。
8. 旧数据库升级后执行 `python -m app.cli validate-data --start 历史最早日期 --end 当前最新raw日期`。
9. 执行 `python -m pytest` 确认环境正确。
10. 进入 `frontend`，执行 `npm install` 和 `npm run build` 确认前端环境正确。

## 给 Codex 的继续开发约束

- 先完成当前 Milestone 的验收标准，再进入下一个 Milestone。
- 不要把阈值硬编码进业务代码，必须从 `config/strategy.yaml` 或配置对象读取。
- 不要在服务层直接 import `tushare`，只能通过 Provider 抽象访问数据源。
- 不要把 token、密码、数据库 dump、缓存数据提交进项目。
- 所有信号和后验统计必须避免未来函数。
- 每次修改后同步更新 README、PROJECT_RULES 和 `docs/` 下两份 Markdown 的“实现进度”。
