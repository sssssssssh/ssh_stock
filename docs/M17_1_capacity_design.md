# M17.1 容量与可观测性设计

状态：盘点和设计已交付。**监控聚合 API、近阈值 UI、近 30 日增长与限流器均 DEFERRED，未实现**。
本轮没有新增接口或后台定时聚合，没有提高现有阈值，也不清理不可变财务记录。

## 当前盘点

| 数据 | performance._preflight 当前纳入行数/record_json 字节总预算 | 其他读取方式 |
|---|---|---|
| NAV、三个阶段头、持仓、订单、Fill、草案、OutcomeReview | 是，按 owner/account 统计七类表；持仓计全部历史，不只最后一天 | 各自分页；汇总再加载预算内必要事实 |
| Ledger、OrderAttempt、ApprovalEvent、AccountEvent | 否 | owner/account 分页，单页 1–100 条 |
| Job 派发/取消/恢复收据 | 收据在 AccountEvent，未计入 performance 总预算 | 事件/任务分页；Job active_count 为账户全历史活跃计数 |
| DecisionObservation | 否，账户绑定在 record_json 中 | owner 过滤，按账户引用/绑定的既有分页语义 |
| JobRun 与 job_metadata | 否 | 私有 PAPER Job 分页；通用 jobs/runtime 不泄露私有任务 |

已有汇总先统计行数，再统计 UTF-8 JSON 文本字节，超过 decision.max_source_rows 或
paper.max_history_bytes 即 PAPER_HISTORY_CAPACITY_EXCEEDED，不输出假空绩效。
默认字节预算 32 MiB，最大 64 MiB；这不是整账户、数据库或索引的总大小。
当前只显示容量错误，没有容量百分比/趋势告警界面。图表超过 2000 点停止绘图，明细仍可分页。

M17.1 历史依赖验证只读取标量和分组信息，限制日历跨度和计算 Job 组数，不加载历史 JSON。
SQL 次数固定，但历史 Raw/Derived 行和依赖分组变大仍增加数据库工作量。两股票合成样本的
1/30/250 日测量不能当作 5000 股、多年数据的生产性能承诺；记录见关闭说明。

## 后续聚合接口方案（未实施）

建议单独只读 capacity 端点，先按 owner/account 查账户，不存在或跨用户一律 404，再做聚合：
累计冻结交易日、每表/合计行数、近 30 日新增、UTF-8 内容字节、当前预算分母和使用比例、测量时间。
同一事件只计一次；收据是 AccountEvent 的分类，不再额外叠加。通用 Observation 可能被引用，
需区分“账户引用规模”和物理存储；不可把共有引用重复累计为整个数据库大小。
近 30 日按 created_at 统计写入增量，同时保留 trade_date 的业务口径，两者不能混用。

聚合使用 COUNT/SUM(octet_length(...::text))，不把全量 JSON 传到应用；大历史聚合仍可能重，
应以 EXPLAIN 和实测决定批量缓存/频率，而不是每 5 秒重扫全账。未来索引变更需要新迁移。
建议 NORMAL/NEAR_LIMIT/EXCEEDED 三态；80% 只是待批准的设计预警线，不是当前生效配置。
接近上限时提示后续扩容/归档设计；达到上限保留安全错误、可分页历史，不造 NAV 或自动提高上限。

## 证据保留与限流

- 不能删除 Fill、Ledger、NAV、Position、审批、账户事件或派发收据来降低百分比。
- 通用 retention 已保护 PAPER Job，但不保护全部 Raw/Derived 计算 Job。M17.1 无法验证被清理的
  历史计算血缘时会失败关闭；操作上应保护所需证据、在输入稳定后做现有完整补算，或从可信备份恢复。
  后续需单独设计来源 Job 保留/冻结血缘摘要；本轮没有修改 retention 或伪造旧 Job。
- started_at 是入队时间。若消费者提前排队，无法证明其在上游结束后读取，应等待完成后提交新补算任务；
  不允许手调数据库时间。更精确的执行起点/跨版本血缘是后续独立设计，不在本轮扩大 Job 架构。
- 现有 request_id、账户串行锁和单账户活跃任务约束继续有效。本阶段未新增跨用户请求限流、
  周期配额或容量告警任务；后续接口必须覆盖 404、空态、预警/超限、长文本和数据库异常测试。
