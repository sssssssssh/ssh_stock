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
- 跨表质量必须支持 ERROR 阈值；`adj_vs_daily`、`basic_vs_daily`、`factor_vs_daily`、`state_vs_factor` 出现 ERROR 时，`daily` / `recalculate` 必须失败，不得标记 SUCCESS。`backfill` 只负责原始行情同步，必须按 `stock_daily`、`stock_adj_factor`、`stock_daily_basic`、`index_daily`、`stock_st`、`suspend_d`、`stk_limit` 七个 Raw 数据集逐项判断完整性并做数据集级跳过/补拉。`sector_factor_daily` 与股票粒度不同，不得直接按股票行数阻断。
- `sector_member` 历史计算必须使用 `valid_from/valid_to`，`is_latest` 只可用于当前展示，不得参与历史回测过滤。
- 申万行业成分必须按一级行业 `L1` 分批请求 `is_new=Y/N`，保存当前和历史成分，去重键必须包含行业、股票和有效日期，不能只按 `ts_code` 去重。
- 原始事实表启用 NULL upsert 保护时，新 NULL 不得覆盖已有非空值；历史原始非空值发生修订时必须记录 `data_dirty_range`。
- `recalculate` 支持 `manual` 和 `dirty_repair` 两种模式；`dirty_repair` 从最早可修复 dirty date 重算到最新已拉取交易日，完成后标记 RESOLVED。可修复范围为 `OPEN` 或 `FAILED` 且 `retry_count < app.scheduler.dirty_max_retry_count`；失败后 dirty range 必须标记 `FAILED`，累加 `retry_count`，并写入 `last_error`、`last_failed_at`。
- `stock_factor_daily`、`market_daily`、`sector_factor_daily` 必须写入 `calc_version`、`config_hash`、`calc_run_id`、`calculated_at`。
- Raw 表只保存 Provider 事实数据；衍生表的范围重算是 authoritative，计算 scope 内本次未再生成的 stale rows 必须删除，不得仅 upsert 后保留旧结果。
- `stock_factor_daily`、`market_daily`、`sector_factor_daily`、当前 `algo_version` 的 `stock_state_daily` 和 `strategy_signal` 重算必须使用 authoritative replace-slice；仍成立的信号必须保留原 `signal_id`，删除信号时由外键级联删除 `signal_forward_eval`。
- 后验收益只能写入 `signal_forward_eval`，不得反写当日因子、状态或信号表。
- 前端 API 地址用 `frontend/.env` 的 `VITE_API_BASE_URL` / `VITE_API_PROXY_TARGET` 控制，不在源码里写死云端地址。
- 网页用户可见名称和浏览器标题统一使用“空间”，不要显示“股票机会发现系统”。
- 前端一级目录固定为 `总览`、`数据`、`长线`、`短线`。基础信息同步入口、原始行情拉取入口、补算因子入口、任务状态、数据覆盖日历和数据覆盖表必须放在 `数据` 页面；长线股票池和行业热度放在 `长线` 页面；短线风险池、信号计数和短线动量放在 `短线` 页面。
- 数据页面的主要面板必须支持点击标题收起/展开；收起时只保留标题行和右侧操作区，不卸载任务轮询和数据状态。
- 股票池中的股票代码必须可点击查看实时 K 线；实时 K 线使用 `GET /api/v1/stocks/{ts_code}/realtime-kline?days=180`，只从 Tushare 查询并返回前端绘图，不写入本地数据库。默认展示 180 个自然日，并支持 90 / 180 / 365 日切换。
- 后端必须提供 `POST /api/v1/jobs/sync-basic` 作为页面基础信息同步入口，只同步 `stock_basic`、`sector`、`sector_member`，不得触发因子、市场、行业热度、状态、信号或后验计算。
- 后端必须提供 `POST /api/v1/jobs/backfill` 作为页面原始行情拉取入口，只同步交易日历和七类 Raw 数据集（`stock_daily`、`stock_adj_factor`、`stock_daily_basic`、`index_daily`、`stock_st`、`suspend_d`、`stk_limit`），不得接受或展示 `evaluate_signals`，不得触发因子、市场、行业热度、状态、信号或后验计算。
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
- backfill 重跑同一日期范围时必须按七类 Raw 数据集分别判断和跳过；`stock_st`、`suspend_d` 即使返回 0 行，也必须存在当次成功同步的质量证据后才可视为完整。
- backfill 遇到 `data_quality_daily(stock_daily)` 缺失的旧历史数据时，必须先用库内已有数据补做质量校验；只有 PASS/WARNING 才能跳过原始数据下载，ERROR 必须重新拉取。
- backfill 跳过完整交易日时必须更新任务步骤为 `30 skip existing raw {date}`，并在 `job_metadata.skipped_raw_days`、`current_day_datasets`、`synced_dataset_count`、`skipped_dataset_count`、`error_dataset_count` 记录当前数据集状态。
- 后端必须提供 `POST /api/v1/jobs/validate-data` 和 `python -m app.cli validate-data`，用于不访问 Tushare 的存量历史 Raw 质量补校验；任务元数据必须包含 `total_trade_days`、`completed_trade_days`、`pass_days`、`warning_days`、`error_days` 和 `progress_pct`。
- stale `PROCESSING` dirty range 超过 `dirty_processing_timeout_minutes` 后必须恢复为 `FAILED`，增加 `retry_count` 并保留错误信息。
- `TushareProvider.get_stock_basic()` 如果核心状态 `L/D` 缺失，最终异常必须包含缺失状态和对应 Tushare 原始错误；不得只返回 `required statuses missing` 这类聚合错误。
- Tushare 代理请求的 `requests` 网络异常必须自动重试；重试耗尽后再写入 FAILED。
- `index_daily` 历史回填必须优先使用指数代码 + 日期区间批量拉取，避免对每个交易日重复请求同一指数。
- `provider_api_log` 必须使用独立数据库 Session 写入；Provider 日志成功或失败不得提前提交业务 Session。
- `config/strategy.yaml` 的 `provider.tushare.safe_limits` 用于标记疑似截断的 Tushare 响应；达到安全行数时 Provider 日志应记录 WARNING。
- `stock_daily` 的 expected 股票池必须按交易日使用 `active_on_date - suspended_on_date`；`adj_factor`、`daily_basic` 保持各自经实证确认的 expected 语义，不得机械照搬停牌扣除口径。
- `validate-data` 必须调用 `check_raw_completeness()`，并用 `RawCompletenessResult.overall_status` 汇总 `pass_days/warning_days/error_days`，不得单独按 `stock_daily` 覆盖率统计。
- `validate-data` API 进度必须包含当前七类 Raw 数据集状态；CLI 只创建 `QUEUED` 任务，实际校验及事务提交由 Worker 完成。
- `sync_daily()` 负责写入 `stock_daily` 首次采集阶段的 `duplicate_count/null_count`；`RawCompleteness` 和 `validate-data` 这类二次完整性校验不得覆盖已有的明细计数。
- Raw 完整性必须只把有效字段计入 actual：`stock_adj_factor.adj_factor` 非空且大于 0；`index_daily.close/pre_close` 非空且大于 0；`stock_daily_basic` 只检查 `close/total_mv/circ_mv` 非空。
- Raw 字段无效记录必须写入 `data_quality_daily.issue_codes.invalid_count/invalid_codes`，`invalid_codes` 最多保留 100 个。
- `sector_member` 当前成员批次 `is_new=Y` 返回空结果必须失败，历史批次 `is_new=N` 返回空结果允许；错误信息必须包含 L1 code。
- Milestone 8 Raw 数据层保持封版；Milestone 9 只新增 `stock_st_daily`、`stock_suspend_daily`、`stock_limit_daily` 及衍生的 `stock_trade_status_daily`，不借此重构既有 Raw 拉取架构。
- 本地开发时如果后端端口从 8000 改为 9034，必须同步修改 `frontend/.env` 的 `VITE_API_PROXY_TARGET`，否则前端会继续请求旧端口。
- `DailyJob` 在七类 Raw 同步后必须执行 `check_raw_completeness(..., persist=True)` 作为计算前 Gate；ERROR 禁止进入 `stock_trade_status_daily`、因子、市场、行业、趋势和信号计算，WARNING 当前允许继续。
- `DailyJob` 的 RawCompleteness Gate 和跨表质量 Gate 必须先提交 `data_quality_daily` 证据，再把任务置为 FAILED；不得因为后续 rollback 丢失 ERROR 明细。
- `run_recalculation()` 在趋势状态计算后、信号评估前必须执行范围 Cross Table Quality Gate；`start~end` 内任一交易日 `stock_daily_vs_expected`、`adj_vs_daily`、`basic_vs_daily`、`factor_vs_daily`、`state_vs_factor` 为 ERROR 时，必须先提交质量证据，再把 `recalculate` 标记 FAILED，且不得继续执行 Signal Evaluation。
- API、Scheduler 和 CLI 数据任务入口必须共用 `app.services.job_guard`；创建新 `daily/sync_basic/backfill/recalculate/validate_data/catchup` 前必须恢复 stale 任务并拒绝活跃任务。
- stale recovery 必须区分 `queued_stale_hours`、`running_heartbeat_timeout_minutes` 和 `dirty_processing_timeout_minutes`；Worker 约每 60 秒检查一次，不得只在启动时恢复。
- Scheduler 必须按 `app.timezone` 计算当前日期，不得直接使用系统默认 `date.today()`；`daily_cron` 的工作日字段必须正确传给 APScheduler。
- Scheduler 触发时执行 Catch-up，而不是只跑当天；Raw/Analysis 必须使用最近 `max_catchup_trade_days` 个 open_date 作为同一候选窗口逐日分类，先判断 Raw，只有 Raw 完整才判断 Analysis，不得把窗口外未检查 Raw 的历史日期误归为 analysis-only。
- Analysis Complete 必须同时满足当前 `config_hash`、`factor_v1/market_v1/sector_v1`、当前 `algo_version`，并且 `factor_vs_daily` 与 `state_vs_factor` 覆盖率达到现有跨表质量 PASS 阈值；不得只用 `MAX(stock_state_daily.trade_date)` 或单表存在 1 行判断完整。
- Catch-up 中 Raw 缺口只能执行 Raw-only 修复：同步七类 Raw 并执行 RawCompleteness，不得按缺口日期运行完整 `DailyJob`，也不得重复同步 `stock_basic`。任一 Raw ERROR 必须先提交质量证据并阻止后续重算；通过后先生成 PIT 交易状态再计算因子。
- Catch-up 的 Raw 缺口全部修复后，必须合并 `raw_required_dates` 与 `analysis_required_dates`，从最早日期到 `latest_raw_trade_date` 统一且只调用一次 `run_recalculation()`；历史 Raw 新插入行即使未产生 Dirty Range，也必须触发该向后重算。只有 Analysis 缺口时不得访问 Tushare Raw。
- Scheduler 自动 refresh 最近 `refresh_recent_trade_days` 个交易日 Raw 时必须是 Raw-only，只同步七类 Raw，不得重复同步 `stock_basic`，不得按日复用完整 `DailyJob`。
- Recent refresh 必须在 Catch-up 统一重算后执行，并跳过本轮刚完成 Raw-only 修复的日期；之后继续按现有逻辑执行 Dirty Repair。
- Recent refresh 后如存在可修复 dirty range，Scheduler 必须自动执行 Dirty Repair，从最早 dirty start 重算到最新 Raw 交易日；成功标记 `RESOLVED`，失败标记 `FAILED`，超过 `dirty_max_retry_count` 的 FAILED dirty range 不再自动重试并提示人工介入。
- `index_daily` 区间预拉取只是性能优化，失败时必须降级为逐日拉取，并最终由 RawCompleteness 判断成败。
- Milestone 8、既有 Raw 数据层和自动运行层保持封版；本轮按阶段任务书进入 Milestone 9，不得超出三个新增可交易性 Raw 数据集继续扩展 Raw/Scheduler/Job 架构。
- 历史 ST 判断只允许使用 `stock_st_daily(trade_date, ts_code)`；禁止使用当前 `stock_basic.name` 推断历史 ST。2000-01-01 以前必须保存 `is_st=NULL` / `st_status_unknown=true`，不得伪造状态。
- `stock_trade_status_daily` 是 PIT 衍生表：`tradable = is_active AND NOT is_suspended`；`strategy_eligible` 在此基础上应用 ST 策略过滤；ST 本身不得令 `tradable=false`，涨跌停收盘标志保持独立字段。
- `stock_basic` 必须按 `L/D/P × SSE/SZSE/BSE` 最多 9 个分片拉取；L/D 任一分片失败则整体失败，P 可选；任一分片触发截断 warning 时，聚合 DataFrame 必须保留该 warning。
- `index_member_all` 不得传递未文档化的 `src` 参数；L1 分片达到 `provider.tushare.safe_limits.index_member_all` 时不得接受原结果，必须按 L2，必要时按 L3 继续拆分后聚合去重。
- `sector_member.in_date` 缺失时不得回退到股票上市日或 `1900-01-01`；历史记录标记为 `PIT_INVALID` 并跳过，当前 `is_new=Y` 记录缺日期时 `sync-basic` 必须失败。
- Sector 元数据同步必须保留历史行；本次源中消失的既有 `source_code` 只更新为 `is_active=false`。Scheduler 按 `app.scheduler.basic_info_cron` 每周复用 `BasicInfoJob` 刷新基础信息。
- `python -m app.cli provider-smoke-test` 只调用 Provider、不写数据库；必须检查任务书列出的 11 个接口返回 DataFrame 且含必需字段。
- 所有 State/Signal API 的默认 latest date 必须先按请求或当前 `algo_version` 过滤；系统状态、数据日历和覆盖率不得让旧算法版本或旧配置结果垫高当前完成度。
- 因子、市场和行业当前结果的统计口径固定为各自 `factor_v1/market_v1/sector_v1 + current config_hash`；状态和信号按 current `algo_version`。API meta 必须返回当前 `algo_version/config_hash`。
- `stock_state_daily` 和 `strategy_signal` 必须写入 `calc_version/config_hash/calc_run_id/calculated_at`；同一次趋势计算的状态与信号共用一个 `calc_run_id`。
- 状态机逻辑或信号定义变化必须 bump `algo_version`；普通参数变化通过 `config_hash` 区分，不得混用旧配置结果。
- API、Scheduler 与 `daily/sync-basic/backfill/validate-data` CLI 只允许原子创建 `JobRun(status=QUEUED)` 并立即返回；`daily/sync_basic/backfill/recalculate/validate_data/catchup` 只能由 DB Worker 领取。CatchUp 内同步执行的 Recalculate 子任务必须直接以 `RUNNING` 创建并标记 `execution_owner=catchup`。
- DB Worker 必须使用 `SELECT ... FOR UPDATE SKIP LOCKED` 领取任务，并写入 `worker_id/heartbeat_at`；领取后由使用独立 `SessionLocal` 的后台线程按 `job_id + RUNNING + worker_id` 所有权条件周期刷新 heartbeat，任务结束必须停止，不能依赖业务 `update_job()` 保活。
- “检查 active -> 创建任务”必须在 PostgreSQL transaction advisory lock 内完成，API、Scheduler 和 CLI 共用 `create_queued_ingestion_job()`；禁止引入 Redis/Celery/Kafka。
- Dirty Range 进入 PROCESSING 时必须写 `processing_started_at`；Worker 周期性把超时 PROCESSING 恢复为 FAILED，增加 retry_count 并记录 `stale processing recovered`。
- Signal 后验默认使用 `eval_v3 + NEXT_OPEN + MARKET_TRADING_DAY`；NEXT_OPEN 的 Day 0 是入场日，`retN` 使用入场后第 N 个市场交易日收盘价，同时支持 SIGNAL_CLOSE/NEXT_CLOSE，不得按个股下一条可用行情偷偷顺延 horizon。
- eval_v3 必须根据 PIT 停牌和涨跌停判断 entry/exit executable；不能成交时 `entry_price/return` 保持 NULL 并记录原因。MFE/MAE 使用与入场价一致复权口径的 Entry 后第 1~20 个市场交易日 high/low。
- `signal_forward_eval` 以 `signal_id + eval_version + entry_basis` 唯一，允许历史 eval_v1/eval_v2 与当前 eval_v3 并存；eval_v2 为历史 signal-relative 版本，不得用 entry-relative 新算法继续写入。研究 API 必须支持 eval_version、entry_basis、executable_only 筛选。
- `stock_st_daily`、`stock_suspend_daily`、`stock_limit_daily` 必须按交易日权威快照对账；Provider 成功返回 0 行表示无事件，必须删除该日旧行、写 PASS 质量证据，并在确有变化时创建 Dirty Range。
- `expected_stock_daily_codes()` 是 `sync_daily`、RawCompleteness、Cross Table、validate-data、Backfill、CatchUp 唯一日线 expected universe 定义；ST/停牌必须先于日线同步。
- `sync_daily()` 只能删除数据库中 `existing_codes - expected_codes` 的确定无效日线，Provider 暂时漏回但仍在 expected universe 的旧行不得删除；Provider 返回的停牌等 authoritative extra 不得重新写入。执行删除前必须确认 `stock_basic` 完整、当日 `suspend_d` 有 PASS 源同步证据且 expected universe 非空，删除或修改均须创建 Dirty Range。
- `run_recalculation()` 必须在 TradeStatus 前让请求区间及预热区间逐开市日通过七类 Raw prerequisites；TradeStatus、Factor、Market、Sector、Trend 均向前扩展最多 250 个开市日进行 current-config warmup，并使用同一 `calc_run_id`。Cross Table Gate 与 Signal Evaluation 仍只执行请求区间 `start~end`。
- 当前 State 必须同时匹配 current algo、`trend_v1`、current config hash；当前 Signal 必须同时匹配 current algo、`signal_v1`、current config hash。Market/Sector/Trend 服务不得读取 old-config 上游结果。
- SW `sector_member` 只在完整 Provider 快照成功并通过 PIT 校验后，对 active SW sector 执行 stale natural-key 删除；inactive sector 的历史成员永久保留。任何分片失败、空快照或重复键都禁止删除。

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
## Phase 7 部署与依赖规则（2026-09-15）

- 生产容器固定使用 PostgreSQL 17；业务容器必须等待数据库健康且迁移容器成功执行 `alembic upgrade head` 后才能启动。
- API、DB worker 和 scheduler 是三个独立进程；API 只入队，worker 消费 `job_run`，scheduler 只负责定时编排。
- `/health` 必须同时验证 API 存活和数据库 `SELECT 1`，数据库不可用时返回 HTTP 503。
- `postgres`、`backend`、`worker` 使用 `restart: unless-stopped`；scheduler 同样按长期服务运行。
- Python 部署依赖以 `requirements.lock` 为准，尤其不得自行猜测或漂移 Tushare 版本。
- Tushare 代理地址只能由 Provider 内 `_configure_tushare_http_url()` 配置；SDK 私有结构变化时必须明确失败，禁止静默退回官方地址。
- CI 必须在 PostgreSQL 17 上实际执行 Alembic，随后运行完整 pytest、ruff 和前端生产构建。
## Phase 8 性能与可维护性规则（2026-09-15）

- realtime-kline 必须先检查 `stock_daily` 与 `trade_calendar`；本地交易日覆盖完整时禁止实例化或调用 Provider，存在缺口时才拉取并按交易日合并，且不写库。
- 关键业务日期统一通过 `app.core.clock.business_today()` 按 `APP_TIMEZONE` 计算；禁止在业务入口裸用 `date.today()`。
- 历史指数区间请求按 730 天分块；任一分块失败仍由 Backfill 保留逐日 fallback。
- Provider 只重试超时、断连、SSL EOF、临时不可用和限频等瞬时错误；token、权限、参数和积分错误不得重试。
- 日线源数据触发 duplicate/其他 Raw ERROR 时，必须先把 `duplicate_count`、`null_count` 和 issue code 提交到 `data_quality_daily`，再使任务失败。
- Backfill 的全区间指数完整性预检必须使用单次批量查询，禁止为每个交易日重复运行完整七数据集校验。
- 前端职责组件固定为 Dashboard、StockPool、SectorHeat、DataQuality、JobCenter、Research；`App.vue` 负责状态编排，不再堆叠这些页面的完整模板。
