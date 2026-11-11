# BIZ-PERF-P1-02 因子月分段读取与组帧收尾

## 结论

`PERFORMANCE_DECISION=INCONCLUSIVE`，`SOURCE_MUTATION=REVERTED`。候选通过 25 项离线测试。首次配对微基准在写入首档样本前异常退出，无法判定中位数和 P95 门槛。已撤回候选和新增实验测试。业务源码恢复到基线 Git blob `11cf64776ab49d4a508b25f82c27686e806acc10`，基线与恢复后的源码 diff 为空。本次 Git 归档包含本回执和[独立审阅报告](BIZ_PERF_P1_02_INDEPENDENT_REVIEW_20261111.md)。

## W00 基线与读取路径

开工时仓库处于干净的 `master`，本地 HEAD、origin/master 和 GitHub 实时 master 均为 `1fbb98c5b189be2a49fb9f576fc27d72fd9e853a`。上一轮 P1-01 已撤回准备段候选，本轮单独归因。以下是本轮基线 SHA 的 attempt 1。

| 工作流 | Run | 已核实结论 | 跳过的 Job |
|---|---|---|---|
| Main CI | [42954512719](https://github.com/sssssssssh/ssh_stock/actions/runs/42954512719) | completed/failure。全量 pytest 6,681 通过、1 失败、1 跳过，覆盖率 90.02%。路由校验和汇总失败。现有摘要未提供失败测试节点。 | authorize、ui-visual-acceptance、lookup-tail-attribution、capacity、publication-release-gate |
| A4-1 | [42954512799](https://github.com/sssssssssh/ssh_stock/actions/runs/42954512799) | completed/success | authorize、isolated-baseline |
| A4-2 | [42954512817](https://github.com/sssssssssh/ssh_stock/actions/runs/42954512817) | completed/success | authorize、laboratory、a42-acceptance-gate |
| Publication V1.3 | [42954512931](https://github.com/sssssssssh/ssh_stock/actions/runs/42954512931) | completed/success | authorize、candidate-performance |

Main CI `42954512719` 是基线提交的历史工程验证结果。P1-02 的性能结论来自 W04 离线配对证据缺失。

`run_recalculation` 使用 `_month_chunks`，同一 `FactorService` 每段执行取消检查和进度更新，再由 `recalc` 读取 stock_daily、stock_adj_factor、stock_basic、stock_trade_status_daily 和 index_daily，计算后调用 `replace_slice_rows` 并提交。每段保留 430 日历日回看，分析起点仍由 250 交易日预热逻辑确定。以 2024-12 起算的 1、3、12 月区间中，每对相邻段的有日期输入窗重叠 430 天。静态交集只记录日期，实际行数取决于数据。

S0 为默认 OFF。S1 为现有因子输入复用 ON，后续窗口的四类有日期输入各读一次新尾段，stock_basic 整个根任务读取一次。S1 仍每段组帧五次。S2 仅替换 S1 组帧函数。三个方案中的 Raw batch、因子 CPU 优化和 A/B merge read 均为 OFF。

`prepare` 在原连接事务中检查 Owner、版本、策略、作业身份和取消，持 SHARE 锁对五类公开输入及当前根任务状态候选核验来源，随后绑定事务。下一段提交后重做 prepare；最终发布前仍有来源复核。两个原有排序按代码、日期，其他输入保持已有读取语义。查询、FETCH/网络、摘要扫描、锁、计算、写入和整链真实耗时均为 `UNKNOWN`。

## W01 离线归因

固定纯内存样本使用工作日分布、原查询列、SQL NULL、NaN、signed zero，并另用独立样本核对 Decimal、pd.NA、pd.NaT、date、UUID、bool 及重复值。真实 `FactorService.recalc`、`FactorInputWindow.read` 和 `read_calculation_frame` 在 fake Session 上运行，计算、写入和来源扫描用替身。1、3、6 月的五类读取独立记录请求范围、查询数、行数、输入 SHA256。Windows 使用 Python 3.12.11、pandas 3.0.5、NumPy 2.3.3、SQLAlchemy 2.0.52。

下表为 stock_daily 的相邻窗基线组件。P95 使用 nearest-rank。分配峰值由独立 tracemalloc 调用取得，未计入 wall。

| 行数 | 保留 / 新尾行 | 整窗压缩中位 ms | 裁剪中位 ms | 组帧中位 / P95 ms | 组帧分配峰值中位 bytes |
|---:|---:|---:|---:|---:|---:|
| 5,000 | 4,648 / 352 | 16.405 | 1.906 | 5.742 / 6.033 | 826,579 |
| 25,000 | 23,328 / 1,672 | 79.868 | 9.643 | 19.213 / 22.194 | 4,086,451 |
| 50,000 | 46,656 / 3,344 | 160.116 | 18.370 | 38.101 / 58.861 | 8,161,515 |

S0/S1 的 50,000 行、6 月档中，四类有日期输入每类均执行 6 次读取，各返回 299,997 / 66,413 行；stock_basic 分别执行 6 / 1 次读取，返回 912 / 152 行。此结果为 fake 数据调用规模。S1 已消除大量重复取数，仍逐月处理整窗组帧，组帧在三个档位的离线 wall 中位均高于裁剪。

## W02–W03 单热点候选与验证

只修改了 `blocks_to_frame`。候选按块恢复 SQL NULL 和特殊值，再汇总完整列供 pandas 推断，一次构造 DataFrame。保持块、窗口、查询、缓存预算、计算与发布原边界。修改只触达现有 opt-in 路径。

| 检查 | 结果 |
|---|---|
| RED，基线结构断言 | 24 通过、1 预期失败，exit 1。基线逐列调用 DataFrame 赋值。初次测试夹具还缺少 fake policy 的 observe_stage，修正夹具后再于基线上取得此 RED，原日志已保留。 |
| GREEN，候选 | 25 通过，exit 0。逐列检查标量类型、精确值、顺序、dtype、NULL、NaN 和 Decimal 表示。覆盖跨月、跨年、空窗、尾部读取、5,000 行 FETCH 边界、裁剪、跨事务、来源及候选摘要漂移、Owner/连接/root、取消、类型及 SQL 故障、游标及 observer 关闭、内存限制。 |
| B/A、tombstone、PIT、身份 | 离线 fake 提供根任务视图的可见行，真实服务的日期、计算版本和配置哈希谓词参与核对。真实 PostgreSQL 上的视图、B 覆盖 A 及 tombstone 行为仍是后续集成门禁。 |
| 五个原有回归模块 | 候选与撤回后各 52 通过、1 失败，exit 1。失败均为 `test_runtime_source_rejects_symlinked_module_directories`。直接运行原测试复核到 Windows 创建符号链接时 `WinError 1314`，尚未到业务断言。 |
| Ruff | 候选与恢复后均 exit 0。 |
| 真实 PG17 集成 | `NOT_RUN`。后续门禁包括 `test_business_recalc_performance.py`、`test_calculation_frame_streaming.py`、发布、Job 和取消相关用例。 |

## W04 配对验收与撤回

预设 5,000、25,000、50,000 行各 15 对，AB/BA 交错，使用固定输入和版本，每档 wall 中位改善至少 8%，候选 P95 不超过基线的 110%。5,000 行档执行了 15 对并完成样本等价断言。汇总脚本用基线 CPU 中位数计算相对变化，Windows 进程 CPU 采样在短运行中量化为 0，导致 `ZeroDivisionError`，exit 1。脚本当时尚未落盘首档原始记录。该档的 wall/CPU/分配原样本与中位数、P95 均不可用，后两档未运行。保留异常日志与失败状态记录，未重采。局部性能门槛无法判定，已完整撤回。

仓库外保留 `baseline.json`、`monthly_read_call_map.md`、`local_attribution.json`、`w02_decision.md`、`red.log`、`green.log`、`regression.log`、`regression-restored.log`、`ruff.log`、`commands.txt`、`full.diff`、`microbench.log`、`microbench.json` 和 `revert-proof.json`。其中 `microbench.json` 记录失败位置与样本缺失。

| 交付状态 | 结果 |
|---|---|
| PERFORMANCE_DECISION | INCONCLUSIVE |
| SOURCE_MUTATION | REVERTED，恢复后与基线一致 |
| BUSINESS_EQUALITY | OFFLINE_PASS（候选阶段） |
| LOCAL_MICROBENCH | INCONCLUSIVE，三档门槛未验证 |
| PG17_ISOLATED_TEST | NOT_RUN |
| REAL_ROOT_OFF_ON | NO_GO |
| REAL_ROOT_PERFORMANCE / FORMAL_CAPACITY | NOT_MEASURED |
| CI | 基线 Main CI failure。归档提交的自动 CI 以该提交对应的 GitHub 运行记录为准。 |
| D04_OWNER | PENDING |
| R1 | PARTIAL |
| 独立审阅 | 支持撤回与归档。离线等价结论限候选阶段。 |

```text
PERFORMANCE_DECISION=INCONCLUSIVE
SOURCE_MUTATION=REVERTED
BUSINESS_EQUALITY=OFFLINE_PASS（候选阶段）
PG17_ISOLATED_TEST=NOT_RUN
REAL_ROOT_OFF_ON=NO_GO
D04_OWNER=PENDING
```
