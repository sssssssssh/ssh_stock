# BIZ-PERF-03-A：W00 调用链审查与待审插桩清单

日期：2026-11-02。W00 设计已获负责人批准；最终实做及缺口见 BIZ_PERF_03_A_closeout.md。
W00 评审材料经负责人明确回复“没问题，可以开始实施”后实施；保留下列原设计供逐项对照。

## 1. 基线与范围

- 当前分支 master；HEAD、origin/master、直接读取远端 refs/heads/master 均为
  `fe94bddc6cf597b3e3a48f11024993cc6c7f2b01`。
- 工作区已跟踪与未跟踪文件检查为空；远端 heads 仅有 master。没有拉取新提交、切换或创建分支。
- 已阅读任务书全文、AGENTS、四份权威文档的相关现行/历史边界，以及下表的真实实现。
- 本阶段不做 SQL/算法/索引/批次优化，不改变金融、候选、事务、发布、取消及任务状态语义。
- 未读取 .env，未实例化应用 Settings，未导入会创建 Engine 的 app.core.db，未连接任何数据库。
- 未启动服务、pytest、迁移、重算、Provider 请求或高成本专项实验。
- 用户已授权最终提交推送；任务书附录 B 另要求先审阅本清单再开始实施，该前置步骤仍保留。

## 2. 本机环境事实

通过标准库及 distribution metadata 读取，不加载应用配置：

| 项目 | 实测/边界 |
| --- | --- |
| Python | 3.12.14 |
| SQLAlchemy / psycopg | 2.0.52 / 3.3.4 |
| pandas / NumPy | 3.0.5 / 2.3.3 |
| Pydantic / pytest / Ruff | 2.13.4 / 9.1.1 / 0.16.4 |
| 平台 | Windows 10，AMD64，8 逻辑 CPU |
| 物理内存 | 34,271,772,672 bytes |
| 读取瞬间可用内存 | 12,088,561,664 bytes；瞬时值，不代表持续容量 |
| PostgreSQL | 仓库基线 17；当前运行实例版本未探测 |
| 数据库连接位置 | NOT_INSPECTED；遵守不读取 .env、不连接生产库的限制 |
| Worker 实际运行环境 | 未启动 Worker；上述仅是当前开发进程所在主机能力 |

不新增 psutil 依赖。优先复用 calculation_memory.process_memory_bytes，明确进程生命周期
高水位与本 trace 边界采样最大值的区别；不把 POSIX fallback 的峰值冒称当前 RSS。

## 3. 真实根任务调用链

```text
app.cli.worker()
  -> job_worker.run_worker()                  冻结 worker_source
  -> _run_worker_with_source()
  -> _run_worker_loop()
       -> claim_next_job(claim Session)        原领取事务与 commit
       -> execute_claimed_job(execution Session, owner/token)
            -> Execution / CalculationProgress / SessionRegistry
            -> ExecutionPolicy.freeze + QueryObserver.install
            -> 原心跳线程
            -> PublicationWorkspace.open      原 pinned Connection / 私有 VIEW
            -> run_recalculation
                 -> 原始数据前置核验
                 -> TradeStatusService.recalc
                 -> FactorService.recalc      逐月；原预热和回看不变
                 -> Market / Sector / Theme / Trend / Opportunity
                 -> validate_cross_table_range
                 -> 可选 SignalEvaluationService.evaluate
                 -> update_job(SUCCESS)
                      -> _update_owned_data_job
                           -> finish_publication
                           -> 原 Job owner/token/cancel CAS
                           -> db.commit       真正原子提交点
            -> 原异常/取消/未知提交处理
            -> finally：心跳停止、Workspace close、observer/policy 清理、上下文恢复
```

DailyJob.run 是独立逐日编排；CatchUpJob 的 _run_analysis_repair 和
_run_dirty_repair_if_needed 创建既有子 Job，再调用 run_recalculation。
根 trace 必须跟随现有 Execution，而不是每次子函数调用重新生成根身份。
API/CLI 入队及空队列轮询不应创建伪业务根报告。

## 4. 阶段映射与计时边界

| 阶段 | 已确认真实入口 | 拟采集及限制 |
| --- | --- | --- |
| task.queue_wait | job_worker.claim_next_job；JobRun.started_at / execution_started_at | 复用已加载时间戳，UTC 差值是排队估算，不伪称 monotonic 实测；不新增查询 |
| worker.claim | claim_next_job；execute_claimed_job 初始化 | 先在内存记录领取时间，成功领取后绑定 root；空轮询不落报告；领取锁序与 commit 不变 |
| raw.read | FactorService._read_* -> _read_input -> read_calculation_frame；可选 FactorInputWindow.read | SQL 执行、分批获取分开，读的是 Raw 还是 Derived 要按固定标签区分，不把 trade_status 当 Raw |
| data.transform | read_calculation_frame 的 pd.DataFrame；read_calculation_windows 构帧/排序；既有 operation(frame/materialize) | 只包围原转换，不提前/重复消费 Result，不额外序列化行来估算字节 |
| factor.compute | calculation_progress.run_calculation -> calculate_stock_factors；其余 compute 调用 | 在现有统一入口建立阶段；不逐股票打点，不改 engine 公式 |
| candidate.query | replace_slice_rows 查询 existing_keys；PublicationWorkspace._lookup_batch | 查询及原 Python 组装为包含区间；细分 execute 由事件提供；迭代获取不可分部分明确说明 |
| candidate.filter | run_calculation(opportunity.compute) -> calculate_opportunities | 当前引擎把上下文、评分与筛选合在一起；先报告该整体区间，纯筛选子阶段 NOT_INSTRUMENTED，避免改写金融引擎来拆段 |
| quality.check | run_recalculation 前置/跨表校验；daily_quality.record_cross_table_quality / validate_cross_table_range | 只计时，六次原单行质量写入及原异常前缀不变；不得重新合并上轮已撤回候选 |
| candidate.write | replace_slice_rows -> upsert_rows -> route_upsert -> PublicationWorkspace.upsert -> _store/_store_batch | 原 500 行批次不变；候选准备与写入分别记录，处理行数不等于已发布行数 |
| publish.prepare | finish_publication -> _verify_candidate、原像/身份/预算核验及原发布 SQL | 函数不 commit；不得以返回 PUBLISHED 对象就认定持久化成功 |
| publish.commit | job_run._update_owned_data_job 中 CAS 后已有 db.commit | 包围原 commit 调用；未知 ACK 标 incomplete，不新增读库确认/重试，不把所有 checkpoint commit 称为最终发布 |
| task.finalize | execute_claimed_job finally | 在原清理外侧记录收尾/flush，失败不覆盖原异常；无法确认终态时保持 incomplete |

缺失阶段会在 coverage 中带原因，不能生成零耗时 success 占位。
queue_wait 属于任务开始前的外部区间，不计入 Worker active wall 的分母。
重复尝试各有 trace_id，沿用同 task/root 身份，并标明 attempt 关系；不改变幂等/重试策略。

## 5. 已有能力与复用方案

- execution_diagnostics.py：已有 ContextVar、有限标签、operation、record_duration，
  128 组聚合/32 条 recent；目前没有 span 树和完整 JSON，且 rows 默认 0 不能当新模型未知值。
  保留旧接口/旧快照语义，通过兼容的本地 report sink 复用，不改旧 DB 诊断合同。
- calculation_progress.py：已有阶段开始、完成、批次事件，复用入口；新诊断不能改变进度/CAS。
- calculation_policy.py：已有 QueryObserver 的 SQLAlchemy 三事件、DriverFetchObserver 的
  psycopg server_cursor_factory 包装。复用既有 fetch 观察点，避免叠加改变消费方式的 Result 代理。
  新统计不进入冻结 policy/config 身份，不影响 policy guard 的行为。
- worker_observation.py：现有诊断会写 job_metadata，并有独立短事务。新性能报告不经此
  persist_observation 写入，也不自动启用 WORKER_DIAGNOSTICS_ENABLED。
- core/db.py：模块导入会构建 Settings/Engine。本轮离线汇总工具不能导入该模块或 app.cli。
- calculation_memory.py：已有 Windows/POSIX 资源能力；复用 RSS，CPU 使用 process_time 差值，
  区间 CPU% = CPU delta / monotonic wall delta × 100（单核口径，可超过 100%）。
  原生线程数不可得则 null，不用 Python threading.active_count 冒称所有 OS 线程。

## 6. 拟实现设计

1. 单一新总开关 PERF_DIAGNOSTICS_ENABLED=false；旧 Worker 诊断独立兼容。
   关闭时不安装新事件、不创建文件或线程、不新增 SQL。
2. ContextVar 管理 root/span，固定阶段枚举；CPU/RSS 仅根及主要阶段边界采集。
   心跳线程不自动继承主执行 trace；线程指标范围明确，不悄悄漏计为零。
3. SQLAlchemy before/after_cursor_execute + handle_error 做执行统计，回调自身异常隔离。
   不保存 SQL、参数、异常消息或地址。指纹使用清理后的语句结构摘要，处理字面量/注释/
   dollar quoting；不确定形态标 unavailable，不能把完整 SQL 当慢查询摘要。
4. before/after 时间仅是驱动 execute 区间：普通游标可能含缓冲传输，server cursor 不含
   后续所有 FETCH；现有 driver fetch/partition 观测分别标注 driver 或 Python 混合口径，
   两者是嵌套，不相加。负 rowcount -> null，网络/结果字节不可得 -> null。
5. 精确 Git 身份复用 Worker 启动 source 快照，不拿任务结束时磁盘 HEAD 替代已加载代码。
   无 Git 的镜像如无可信精确 SHA，填 null + warning，不捏造身份或自动改变构建系统。
6. 现有 runtime logging 是 stderr，无统一运行时 artifact 服务；已有 data/ 与 .codex_tmp/
   忽略目录。拟使用 data/diagnostics/performance/<UTC-date>/<trace_id>.json，避免另造顶层
   artifacts 体系。路径由安全配置指定，文件名由内部 UUID 生成，不写数据库。
   JSON 有界；超出记录上限保留聚合/丢弃数量和 incomplete 明细标记。
7. 一次性安全 flush；异常仅固定脱敏 warning。进程可处理退出尽力 finally，SIGKILL/断电
   无法保证最终文件，明确限制；不得安装改变 Worker 原退出时序的信号处理器。
8. 离线脚本只读 JSON，按源码/配置/数据范围分组；嵌套/并行用区间并集计算覆盖墙钟，
   inclusive 与 exclusive 分开；SQL/fetch 不与父阶段重复相加；P95 样本不足明确标注。
9. 开销要测整个固定轻量工作负载，包括诊断建立/收尾及 flush；OFF/ON 至少各三次交错，
   保留原始耗时、SQL 次数、输出摘要和离散程度，不补跑筛选有利结果。
   超过 3% 不标 PASS，也不能用纯计时器微基准替代真实调用链结果一致性。

## 7. 拟修改文件清单（审阅后实施）

| 路径 | 预计改动 |
| --- | --- |
| backend/app/services/performance_diagnostics.py（新增） | trace/span、资源、安全 flush、严格模型与汇总所需元数据 |
| backend/app/services/performance_sql_diagnostics.py（新增） | SQL 事件、指纹与有界聚合；无查询执行能力 |
| backend/app/services/execution_diagnostics.py | 兼容桥接现有 operation/record_duration，本地报告与旧 DB 快照隔离 |
| backend/app/services/job_worker.py | 根生命周期、领取内存观测及 finally；不改调度/状态路径 |
| backend/app/services/calculation_progress.py | 既有阶段/计算入口映射及输出行数 |
| backend/app/services/calculation_policy.py | 在原 driver fetch 观察点旁转发事实；不改 policy 判定/身份/输运 |
| backend/app/repositories/calculation_frame.py | 原 execute/partition/构帧边界及 null-aware 行数，保持结果消费顺序 |
| backend/app/repositories/job_run.py | 仅原最终 commit 周围计时及已知终态通知，未知 ACK 不推定成功 |
| backend/app/services/data_publication.py | 原候选 lookup/store 与发布准备的计时边界；SQL/批次/检查点原样 |
| backend/app/core/config.py、.env.example | 默认关闭开关、本地输出目录及中文说明；不触碰 .env |
| scripts/performance_diagnostics_report.py（新增） | 无应用初始化的纯 JSON 汇总 CLI |
| tests/unit/test_performance_diagnostics.py（新增） | T01–T09、重叠区间/注入/脱敏/flush 故障/上下文隔离 |
| tests/integration/test_performance_diagnostics.py（新增） | 小型隔离 PG17 的 SQL/FETCH/取消/原子发布/结果全等及三对开销 |
| docs/acceptance/BIZ_PERF_03_A_mapping.md（新增） | 本审查及最终真实插桩对应 |
| docs/acceptance/BIZ_PERF_03_A_closeout.md（新增） | T01–T12、命令、结果、diff、CI 与剩余限制 |
| docs/acceptance/biz_perf_03_a/（新增限定证据） | JSON Schema、脱敏样例、开销原始测量及汇总示例 |
| README.md、PROJECT_RULES.md、PRD、系统设计 | 开关、字段、使用/回滚及阶段边界；不改历史验收记录 |

优先通过现有共用入口完成覆盖；不为覆盖率新增无意义的大范围包装。
不拟修改 core/db.py、业务 engine、SQL、Raw、迁移、前端、Compose、工作流、旧测试或历史合同。
若现有阶段入口不足以安全覆盖，则登记 NOT_INSTRUMENTED，而非改动算法或事务来凑齐。

## 8. 验证与待审边界

W00 仅进行了静态代码审查、Git 网络只读核对及本机依赖/资源元数据读取。
没有修改业务源码，没有执行性能对照，也没有当前阶段测试通过结论。

实施后的顺序：先 trace 模型单测，继而 SQL/FETCH/资源与文件故障测试，最后小型隔离
PG17 结果全等与 OFF/ON 三对开销，完整 pytest、Ruff、git diff --check。
生产库不作为测试库；测试 fixture 只使用明确隔离的合成 PG17。Windows 缺少 Linux
进程能力的全量结果不得写成通过，可由普通 Linux CI 完成；不触发高成本专项实验。
所有现场/容量/百万行真实性验证继续未授权，不自动进入 BIZ-PERF-03-B。

任务书附录 B 原文：
> 第一步只做仓库状态核对和真实调用链审查，输出当前 master SHA、工作区状态、Worker 根任务入口、数据库访问层、因子计算、候选查询/写入和发布链路的函数映射，以及拟插桩文件清单。负责人审阅该清单后再开始实施。

本清单为该审阅步骤的具体交付。获得本步骤审阅结论后，再实施 W01–W07；用户已明确
授权的最终提交推送无需重复询问，交付时仍提供完整 diff、测试与开销实测证据。
