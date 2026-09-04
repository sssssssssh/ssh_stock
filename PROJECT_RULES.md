# 项目开发规则

## 文档权威顺序

1. `docs/股票机会发现系统_PRD_V1.0.md`
2. `docs/股票机会发现系统_系统设计_V1.0.md`
3. `PROJECT_RULES.md`
4. `README.md`

发现冲突时，不擅自改业务口径；在代码 TODO、README 和开发总结中说明冲突。

## 当前阶段

当前已完成 Milestone 0 到 Milestone 8：

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
- `recalc-market` / `recalc-sectors` CLI，并接入 daily/recalculate
- 状态表 `stock_state_daily`
- 策略信号表 `strategy_signal`
- RightSideScore / TrendScore
- S0-S6 状态机
- RIGHT_SIDE_NEW / TREND_ENTER / MAIN_UP_ENTER / TREND_DECAY / LEADER_BREAKOUT 信号生成
- `recalc-states` CLI，并接入 daily/recalculate
- 完整 REST API：dashboard / stocks / sectors / jobs / research
- 数据覆盖率接口：`GET /api/v1/system/data-coverage`
- 前端数据任务入口：通过 `POST /api/v1/jobs/sync-basic` 同步基础信息，通过 `POST /api/v1/jobs/backfill` 创建原始行情回填任务
- 前端任务状态面板：轮询 `GET /api/v1/jobs` 展示当前任务、最近任务、进度条、步骤和行数
- 后验评估表 `signal_forward_eval`
- `evaluate-signals` CLI
- Vue 3 + TypeScript + Vite + ECharts 前端
- Milestone 8 数据可靠性改造：历史股票池 Point-in-Time、动态日线覆盖率、行业历史成分有效期、NULL upsert 保护、dirty range 向后重算、计算版本追踪
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
- Tushare Provider 必须执行进程级请求节流，间隔由 `TUSHARE_MIN_INTERVAL_SECONDS` 控制，默认 1.5 秒；历史回填失败频繁时优先调大到 2-3 秒。
- 业务服务依赖 `MarketDataProvider` 协议，不依赖具体 SDK。
- 日期在业务层使用 `YYYY-MM-DD` / `datetime.date`，调用 Tushare 时才转换为 `YYYYMMDD`。
- 原始数据表和任务表必须幂等写入。
- 数据库迁移用 Alembic，不手写临时建表脚本替代迁移。
- 配置阈值放在 `config/strategy.yaml`。
- `stock_basic` 必须同步 `L`、`D`、`P` 状态；历史股票池必须使用 `list_date/delist_date/trade_date` 判断，不得只依赖当前 `list_status == L`。
- `daily` 原始数据质量不得使用固定 `min_rows=1`；必须按当日 Point-in-Time 股票池计算 expected_count，并按 `config/strategy.yaml` 的 `data_quality.daily` 阈值判定 PASS/WARNING/ERROR。
- `data_quality_daily` 记录日线覆盖率和跨表完整性；`data-calendar` 状态支持 `DEGRADED`，表示有原始数据但质量 ERROR。
- 跨表质量必须支持 ERROR 阈值；`adj_vs_daily`、`basic_vs_daily`、`factor_vs_daily`、`state_vs_factor` 出现 ERROR 时，`daily` / `recalculate` 必须失败，不得标记 SUCCESS。`backfill` 只负责原始行情同步，必须按 `stock_daily`、`stock_adj_factor`、`stock_daily_basic`、`index_daily` 四个 Raw 数据集逐项判断完整性并做数据集级跳过/补拉。`sector_factor_daily` 与股票粒度不同，本阶段不得直接按股票行数阻断。
- `sector_member` 历史计算必须使用 `valid_from/valid_to`，`is_latest` 只可用于当前展示，不得参与历史回测过滤。
- 申万行业成分必须按一级行业 `L1` 分批请求 `is_new=Y/N`，保存当前和历史成分，去重键必须包含行业、股票和有效日期，不能只按 `ts_code` 去重。
- 原始事实表启用 NULL upsert 保护时，新 NULL 不得覆盖已有非空值；历史原始非空值发生修订时必须记录 `data_dirty_range`。
- `recalculate` 支持 `manual` 和 `dirty_repair` 两种模式；`dirty_repair` 从最早可修复 dirty date 重算到最新已拉取交易日，完成后标记 RESOLVED。可修复范围为 `OPEN` 或 `FAILED` 且 `retry_count < app.scheduler.dirty_max_retry_count`；失败后 dirty range 必须标记 `FAILED`，累加 `retry_count`，并写入 `last_error`、`last_failed_at`。
- `stock_factor_daily`、`market_daily`、`sector_factor_daily` 必须写入 `calc_version`、`config_hash`、`calc_run_id`、`calculated_at`。
- 后验收益只能写入 `signal_forward_eval`，不得反写当日因子、状态或信号表。
- 前端 API 地址用 `frontend/.env` 的 `VITE_API_BASE_URL` / `VITE_API_PROXY_TARGET` 控制，不在源码里写死云端地址。
- 网页用户可见名称和浏览器标题统一使用“空间”，不要显示“股票机会发现系统”。
- 前端一级目录固定为 `总览`、`数据`、`长线`、`短线`。基础信息同步入口、原始行情拉取入口、补算因子入口、任务状态、数据覆盖日历和数据覆盖表必须放在 `数据` 页面；长线股票池和行业热度放在 `长线` 页面；短线风险池、信号计数和短线动量放在 `短线` 页面。
- 数据页面的主要面板必须支持点击标题收起/展开；收起时只保留标题行和右侧操作区，不卸载任务轮询和数据状态。
- 股票池中的股票代码必须可点击查看实时 K 线；实时 K 线使用 `GET /api/v1/stocks/{ts_code}/realtime-kline?days=180`，只从 Tushare 查询并返回前端绘图，不写入本地数据库。默认展示 180 个自然日，并支持 90 / 180 / 365 日切换。
- 后端必须提供 `POST /api/v1/jobs/sync-basic` 作为页面基础信息同步入口，只同步 `stock_basic`、`sector`、`sector_member`，不得触发因子、市场、行业热度、状态、信号或后验计算。
- 后端必须提供 `POST /api/v1/jobs/backfill` 作为页面原始行情拉取入口，只同步交易日历、`stock_daily`、`stock_adj_factor`、`stock_daily_basic`、`index_daily`，不得接受或展示 `evaluate_signals`，不得触发因子、市场、行业热度、状态、信号或后验计算。
- 后端必须提供 `POST /api/v1/jobs/recalculate` 作为页面补算入口，按因子、市场、行业、状态、信号评估的顺序运行；因子阶段必须按自然月分块执行，并持续更新 `job_run.step`、`row_count`、`job_metadata.progress_pct`、`factor_chunk_index`、`factor_chunk_count`、`factor_chunk_start` 和 `factor_chunk_end`。
- `recalculate` 的 `row_count` 在因子分块完成写库后更新；前端在分块计算中必须提示“当前因子分块完成后更新行数”，避免把 0 行误解为卡死。
- 数据覆盖日历使用 `GET /api/v1/system/data-calendar`，状态含义固定为 `CLOSED` 休市、`MISSING` 未拉取、`DEGRADED` 数据质量异常、`RAW_ONLY` 已拉未算、`ANALYZED` 基础分析完成、`COMPLETE` 行业热度也完成。
- 前端数据覆盖明细表必须分页展示，默认每页 20 条，支持 10 / 20 / 50 / 100 条切换；不得直接全量渲染成长页面。
- `GET /api/v1/system/data-coverage` 不传 `limit` 时必须返回全部已拉取交易日；可选 `limit` 不设置后端最大上限，前端默认不得写死最近 120 条。
- 修改 `frontend/src/style.css` 或页面主布局后，必须重启 Vite 开发服务并用浏览器检查 `.workspace-shell`、`.nav-button` 等关键样式是否命中，避免新模板加载旧 CSS。
- API 触发基础信息同步、数据拉取、补算或存量校验时必须创建 `job_run` 记录；同一时间只允许一个 `daily/sync_basic/backfill/recalculate/validate_data` 任务处于 `QUEUED/RUNNING`。
- 长任务必须持续更新 `job_run.step`、`row_count` 和 `job_metadata.progress_pct`，前端不得只显示“已提交”。
- 前端任务面板必须根据 `job_run.started_at/finished_at` 展示耗时；运行中任务显示实时已耗时，完成/失败任务显示总耗时。
- 前端任务列表必须展示 `error_message`，不能只显示“失败”。
- 前端任务列表默认请求最近 30 条任务，列表内部滚动展示；步骤、日期范围、耗时和错误信息必须提供完整 `title`，方便鼠标悬停查看完整文本。
- 前端任务列表的错误信息必须跨整行展示，并占用独立网格行撑开当前任务行，不能挤在步骤/日期列下面，也不能覆盖下一条任务。
- 前端必须把 `job_run.step` 的英文内部步骤映射成中文可读步骤，同时在 `title` 中保留原始步骤便于排查。
- backfill 仅负责原始行情拉取；补算任务 `recalculate` 在因子阶段必须按自然月分块更新进度，写入 `factor_chunk_index`、`factor_chunk_count`、`factor_chunk_start`、`factor_chunk_end`；进入市场、行业、趋势和信号阶段前必须清理上一交易日拉取阶段的 `current_trade_date`，避免前端展示过期日期。
- `row_count` 在长时间批量计算阶段可能只在阶段或分块完成后更新，前端必须给出“当前计算阶段完成后更新行数”的提示。
- `backfill` 和 `validate-data` 启动前必须检查 `stock_basic` 已具备 `L` 和 `D` 状态；缺失时必须失败并提示 `stock_basic is missing or incomplete, run sync-basic first`。
- `trade_calendar` 返回为空、无有效日期或返回范围不覆盖请求日期时必须失败；`daily` 遇到目标日期休市时必须以 `SUCCESS` + `noop=true` 结束，不继续拉行情或计算。
- backfill 重跑同一日期范围时必须跳过原始数据已完整的交易日；完整条件为 `stock_daily`、`stock_adj_factor`、`stock_daily_basic` 满足覆盖率阈值，`index_daily` 覆盖全部配置指数。
- backfill 遇到 `data_quality_daily(stock_daily)` 缺失的旧历史数据时，必须先用库内已有数据补做质量校验；只有 PASS/WARNING 才能跳过原始数据下载，ERROR 必须重新拉取。
- backfill 跳过完整交易日时必须更新任务步骤为 `30 skip existing raw {date}`，并在 `job_metadata.skipped_raw_days`、`current_day_datasets`、`synced_dataset_count`、`skipped_dataset_count`、`error_dataset_count` 记录当前数据集状态。
- 后端必须提供 `POST /api/v1/jobs/validate-data` 和 `python -m app.cli validate-data`，用于不访问 Tushare 的存量历史 Raw 质量补校验；任务元数据必须包含 `total_trade_days`、`completed_trade_days`、`pass_days`、`warning_days`、`error_days` 和 `progress_pct`。
- stale `PROCESSING` dirty range 自动恢复暂未实现；后续如需要应按“超过 6 小时恢复 OPEN”的规则补充。
- `TushareProvider.get_stock_basic()` 如果核心状态 `L/D` 缺失，最终异常必须包含缺失状态和对应 Tushare 原始错误；不得只返回 `required statuses missing` 这类聚合错误。
- Tushare 代理请求的 `requests` 网络异常必须自动重试；重试耗尽后再写入 FAILED。
- `index_daily` 历史回填必须优先使用指数代码 + 日期区间批量拉取，避免对每个交易日重复请求同一指数。
- `provider_api_log` 必须使用独立数据库 Session 写入；Provider 日志成功或失败不得提前提交业务 Session。
- `config/strategy.yaml` 的 `provider.tushare.safe_limits` 用于标记疑似截断的 Tushare 响应；达到安全行数时 Provider 日志应记录 WARNING。
- 当前 Raw 完整性检查不扣除停牌股票，expected 股票池按上市/退市日期判断；停牌数据纳入 Milestone 9 以后再扩展。
- `validate-data` 必须调用 `check_raw_completeness()`，并用 `RawCompletenessResult.overall_status` 汇总 `pass_days/warning_days/error_days`，不得单独按 `stock_daily` 覆盖率统计。
- `validate-data` API 进度必须包含当前四类 Raw 数据集状态；CLI 成功后必须显式 `commit()`，异常时必须 `rollback()`。
- `sync_daily()` 负责写入 `stock_daily` 首次采集阶段的 `duplicate_count/null_count`；`RawCompleteness` 和 `validate-data` 这类二次完整性校验不得覆盖已有的明细计数。
- Raw 完整性必须只把有效字段计入 actual：`stock_adj_factor.adj_factor` 非空且大于 0；`index_daily.close/pre_close` 非空且大于 0；`stock_daily_basic` 只检查 `close/total_mv/circ_mv` 非空。
- Raw 字段无效记录必须写入 `data_quality_daily.issue_codes.invalid_count/invalid_codes`，`invalid_codes` 最多保留 100 个。
- `sector_member` 当前成员批次 `is_new=Y` 返回空结果必须失败，历史批次 `is_new=N` 返回空结果允许；错误信息必须包含 L1 code。
- Raw 数据层按 Milestone 8 当前范围封版；下一阶段只在 Milestone 9 接入可交易性数据，不继续重构当前数据拉取架构。
- 本地开发时如果后端端口从 8000 改为 9034，必须同步修改 `frontend/.env` 的 `VITE_API_PROXY_TARGET`，否则前端会继续请求旧端口。
- `DailyJob` 在 `stock_daily`、`stock_adj_factor`、`stock_daily_basic`、`index_daily` 四类 Raw 同步后必须执行 `check_raw_completeness(..., persist=True)` 作为计算前 Gate；ERROR 禁止进入因子、市场、行业、趋势和信号计算，WARNING 当前允许继续。
- `DailyJob` 的 RawCompleteness Gate 和跨表质量 Gate 必须先提交 `data_quality_daily` 证据，再把任务置为 FAILED；不得因为后续 rollback 丢失 ERROR 明细。
- `run_recalculation()` 在趋势状态计算后、信号评估前必须执行范围 Cross Table Quality Gate；`start~end` 内任一交易日 `stock_daily_vs_expected`、`adj_vs_daily`、`basic_vs_daily`、`factor_vs_daily`、`state_vs_factor` 为 ERROR 时，必须先提交质量证据，再把 `recalculate` 标记 FAILED，且不得继续执行 Signal Evaluation。
- API、Scheduler 和 CLI 数据任务入口必须共用 `app.services.job_guard`；创建新 `daily/sync_basic/backfill/recalculate/validate_data/catchup` 前必须恢复 stale 任务并拒绝活跃任务。
- stale `QUEUED/RUNNING` 数据任务默认超过 `app.scheduler.stale_job_hours` 后自动标记 `FAILED`，错误信息固定说明为进程重启后的 stale recovery。
- Scheduler 必须按 `app.timezone` 计算当前日期，不得直接使用系统默认 `date.today()`；`daily_cron` 的工作日字段必须正确传给 APScheduler。
- Scheduler 触发时执行 Catch-up，而不是只跑当天；Raw/Analysis 必须使用最近 `max_catchup_trade_days` 个 open_date 作为同一候选窗口逐日分类，先判断 Raw，只有 Raw 完整才判断 Analysis，不得把窗口外未检查 Raw 的历史日期误归为 analysis-only。
- Analysis Complete 必须同时满足当前 `config_hash`、`factor_v1/market_v1/sector_v1`、当前 `algo_version`，并且 `factor_vs_daily` 与 `state_vs_factor` 覆盖率达到现有跨表质量 PASS 阈值；不得只用 `MAX(stock_state_daily.trade_date)` 或单表存在 1 行判断完整。
- Catch-up 中 Raw 已完整但分析缺失的交易日只能触发计算修复，不得重新访问 Tushare；Raw 缺失或 Raw ERROR 的交易日才补 Raw 并计算。少量缺失交易日自动补齐，超过 `max_catchup_trade_days` 时跳过并提示手动 backfill。
- Scheduler 自动 refresh 最近 `refresh_recent_trade_days` 个交易日 Raw 时必须是 Raw-only，只同步 `stock_daily`、`stock_adj_factor`、`stock_daily_basic`、`index_daily`，不得重复同步 `stock_basic`，不得按日复用完整 `DailyJob`。
- Recent refresh 后如存在可修复 dirty range，Scheduler 必须自动执行 Dirty Repair，从最早 dirty start 重算到最新 Raw 交易日；成功标记 `RESOLVED`，失败标记 `FAILED`，超过 `dirty_max_retry_count` 的 FAILED dirty range 不再自动重试并提示人工介入。
- `index_daily` 区间预拉取只是性能优化，失败时必须降级为逐日拉取，并最终由 RawCompleteness 判断成败。
- Milestone 8、Raw 数据层、数据拉取层和自动运行层按最终封版范围封版；不得继续扩展 advisory lock、heartbeat、startup catchup、Raw/Scheduler/Job 架构或 Milestone 9 数据。

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
- 对应 `.docx` 版本仅在用户明确要求或准备正式导出时更新

Markdown 是源码级文档，`.docx` 是面向阅读的导出版。
