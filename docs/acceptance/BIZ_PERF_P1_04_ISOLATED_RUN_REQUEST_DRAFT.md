# P1-04 单次隔离测试申请草案

2026-11-14；沿用 [P1-04 W05](../tasks/BIZ-PERF-P1-04.md#w05-单次执行待批表)。
`DRAFT_NOT_APPROVED / AUTHORIZATION_PENDING / B_GATE=NOT_APPROVED / TARGETED_PG17_GATE=NOT_APPROVED`。
本文仅供负责人审阅，不是凭证，不含执行程序或启动命令；本次 ROOT_ATTEMPTS=0。

| 审阅项 | 拟议范围及待填信息 |
| --- | --- |
| 样本与次数 | 8 股；2025-01-01～2025-01-31；同原 900 日历日合成 Seed；一条根任务、一次尝试。失败、超时、未知 ACK 均停止，不补样、不自动重试。 |
| 输入身份 | 设计 SHA=`391dca85cf9cc5b2e1858f4ea7fa19f98f52f079`；最终实施 SHA、模型/配置摘要、business_source、dataset/strategy fingerprint、逐表 SHA256、run UUID 均待独立固定签认；PRETEST 的基线 SHA 不自动成为未来实施 SHA。 |
| 行数 | 静态 Seed 预期 665 合成开市日×8=5320 股日；calendar=931、stock_basic=8、sector=1、sector_member=8；stock_daily/stock_adj_factor/stock_daily_basic/stock_limit_daily 各5320，index_daily=665×待确认 benchmark_count，ST/suspend=0，输入 quality=1330；均属 E03 seed_rows 静态规则，非真实观测。因子/派生及后验 quality 等实际行数与摘要必须实生成后核验，不填猜测值。合成工作日日历不冒充交易所真实日历。 |
| 五开关 | factor_input_reuse_enabled、raw_preflight_batch_enabled、factor_cpu_optimization_enabled、ab_merge_read_enabled、perf_diagnostics_enabled 全部 false。不使用旧 03-B 的4股/5000行/420秒协议。 |
| 业务不变量 | 沿用原交易日/PIT、250 交易日预热、430 日历日回看、500 行候选批、300 秒发布预算；公式/策略/身份/排序、原像、质量、取消/心跳、原子发布及未知 ACK 语义不变；不为观察 fingerprint 启用输入复用。 |
| 新隔离资源 | 仅未来全新 Linux x86_64 + PG17 UUID 实例和新 UUID 库；待提供版本/镜像身份、专用且独占 PGDATA、offline/online 物理 system identifier、UUID marker、隔离网络/cgroup、库/卷 owner、独占 lease 及清理权限。不得复用用户生产或旧 PG/测试库。 |
| 预算草案 | 总计最多20分钟，末5分钟清理（root 窗口少于15分钟）；Worker 3GiB、PG 4GiB、卷10GiB、原始脱敏证据10MiB。CPU/milli-CPU、磁盘配额/IO、成本上限、外部中止控制与具体停止阈值待负责人签字；不将累计 CPU 时间视为配额。 |
| 授权与主体 | 负责人批准引用：待填写；具名操作主体/机器/时间窗口：待填写；独立审阅人及结论：待填写。当前无人获准执行，普通 CI/离线 mock/虚拟 ACK 均无授权能力。 |
| 精确 CI 证据 | 未来精确实施 SHA 的真实主 CI/A4-1/A4-2/Publication run、attempt、Job/Step 与独立审阅凭证：待填写；不得复用 E05 基线 CI 当新版本结果，不把 skipped 当性能通过。 |
| 资源与成本凭证 | 新建资源观测时间、物理身份、网络/cgroup、卷归属、数据库所有权、成本承担者及新建费用：待填写；仅自述 JSON 不构成真实观测。 |
| 结束及人工处理 | 清理负责人/窗口/权限/结束证明：待填写。只可清理已核实归属的本次新资源；归属漂移、未知 ACK 或清理不确定记录 CLEANUP_BLOCKED，停止并交人工；不能自动重放、释放或再次启动根任务。 |
| 证据与可作结论 | 原始脱敏前缀、root/Worker/post 边界、SQL/FETCH/CPU/RSS、阶段覆盖和结果一致性；不得拼接跨根、跨 SHA 样本。单样本仅调查方向，不做提升、P95/P99、容量或生产资格结论；未观测字段保留 UNKNOWN/NOT_INSTRUMENTED。 |

只有负责人发起**新的明确用户授权请求**，另行明确执行环境、操作主体、窗口、精确源码、
资源和预算、证据及人工结束方案之后，才可评估是否具备真实执行条件。
本草案不会改变 E03/E04/E05 的拒绝入口，不签发 permit；本任务不得自行转入执行。
