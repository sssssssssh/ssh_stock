# BIZ-PERF-P1-04 E-02-R1 计量正确性整改回执

任务：BIZ-PERF-P1-04-E02-R1-METRIC-CORRECTNESS
审阅基线：`e8ef6f1aacd126e589eb4c326608b2f64cd8e98d`
日期：2026-11-13

---

## 0. 一页结论

```
E_02_R1 = OFFLINE_VALIDATED
M01 = FIXED   M02 = FIXED   M03 = FIXED
M04 = FIXED   M05 = FIXED   M06 = FIXED
RED_PROVEN_ON_BASELINE = 6/6   GREEN_AFTER_FIX = 6/6
ENGINEERING_CI = SUCCESS (run 43376516292, Python 3.12.16)
ROOT_ATTEMPTS = 0
HOTSPOT = NONE_PROVEN
PERFORMANCE_GAIN = NOT_CLAIMED
TARGETED_PG17_GATE = NOT_APPROVED
B_GATE = NOT_APPROVED
```

本轮只做**离线测量代码的定向整改与测试**。未连接 PG17，未调用 Worker，未消耗测量名额，
未手工重跑 CI，未进入 E-03。工程 CI 由普通 push 自动触发并通过（§6）。

## 1. 口径修正（逐项）

### M01 `process_cpu_ms` 改为区间差值

**缺陷**：`begin_root()` 保存了 `_cpu_start`，但 `freeze_root()` 直接写入
`self._stats.cpu_ms()`，把**进程累计 CPU** 当成区间值。

**修正**：`ProcessStats` 文档明确 reader 返回**累计毫秒**语义；新增 `_interval_cpu()`
求 `cpu_end - cpu_start`。只在两端均为非负整数且不回退时给出区间值，否则一律
`UNKNOWN`。

**实测**：基线累计 100→135 报 **135**；整改后报 **35**。

| 场景 | 结果 |
|---|---|
| 累计 100 → 135 | `35` |
| 累计 100 → 100（零区间） | `0`（真实观测到的零，非 UNKNOWN） |
| 累计 100 → 90（回退） | `UNKNOWN` |
| reader 为 None / `"100"` / `1.5` / `True` / `-5` | `UNKNOWN` |

零区间值使派生比率 `wall_per_cpu` 为 `UNDEFINED`（由原有校验器决定，本轮未修改它）。

### M02 允许嵌套/重叠阶段

**缺陷**：`record_stage()` 要求 `begin_ms >= self._last_elapsed`，误用**事件发出顺序**
禁止了历史阶段的开始时间，把合法嵌套拒绝为 `CLOCK_REGRESSION`。

**修正**：删除该约束。现在只约束
- `end >= begin`（`STAGE_INTERVAL_REJECTED`）
- 阶段整体位于 worker 窗口内（`begin >= worker_started`）
- 结束不晚于当前观测时刻（`STAGE_END_IN_FUTURE`）
- **事件**时间单调（不是阶段开始时间）

**实测**：内层 10–20 先完成，外层 5–40 后完成并被接受。基线对此报
`CLOCK_REGRESSION`。

**DO_NOT_SUM 实证**：阶段墙时长合计 **45ms**，root 冻结在 **40ms**——重叠绝不可求和。

### M03 `end_ms` 与事件时间绑定

**缺陷**：`record_stage()` 接收 `end_ms` 却未使用，事件 `elapsed_ms` 由 `_emit()` 重新
采样，两者可静默漂移。

**修正**：采用**唯一口径**——`end_ms` 就是观测到的阶段结束时刻，事件
`elapsed_ms` 被强制设为 `end_ms`（`_emit(_forced_elapsed=...)`），并校验其
* 单调不低于上一事件
* 不晚于当前时钟

**实测**：基线声明 end=99、事件 elapsed=10，漂移 **-89ms**；整改后事件 elapsed
严格等于声明值，未来结束被 `STAGE_END_IN_FUTURE` 拒绝且不产生任何 stage 事件。

### M04 根级 FETCH 不再默认零

**缺陷**：`_fetch_ms` / `_fetched_rows` 初始化为 0 且在 `freeze_root()` 永远写零，
即使某阶段已标注真实 FETCH，导致根快照误报"已观测且无 FETCH"。

**修正**：根级 FETCH 默认 `UNKNOWN`。只有通过注入的**根级 FETCH 端口**
（`freeze_root(fetch={"observed_ms":…, "rows":…})`，字段集精确校验）才写入实测值。
**绝不**把可能嵌套的阶段值相加。

**实测**：基线阶段 500 行、根级报 0；整改后根级报 `UNKNOWN`。

### M05 冻结绑定到 Worker 返回时刻

**缺陷**：`emit_fixture()` 在 `execute_claimed_job()` 返回后先人工加 SQL 计数、再
`clock.advance(6)` 才冻结，使 `execute_claimed_job_ms` 吸收了 Worker 已返回后的空档。

**修正**：
- `run_offline()` 在 `execute_claimed_job()` 返回瞬间捕获 `_worker_returned_ms`；
- `freeze_root()` 强制以该时刻作为事件 elapsed；
- 根 SQL 计数移入 `CountingExecutor`，**在 worker 调用期间**完成，不再返事后补记。

**实测**：Worker 真实 20ms；基线报 **26ms**（多 6ms 空档），整改后报 **20ms**。

### M06 Sink 耐久性声明与实现对齐

**缺陷**：`ListSink` 只追加内存列表，却被当作可证明落盘的证据来源；T34 仅证明内存前缀。

**修正**：
- `ListSink` 明确声明为**非持久化测试替身**（文档 + `DURABLE = False`）；
- 新增 `FileJsonlSink`：每次 `append` 立即 write→flush→**fsync**，`DURABLE = True`；
  拒绝覆盖既有文件（`SINK_EXISTS`）、拒绝重入（`SINK_REENTRANT`）、父目录必须为真实目录。

**实测**：基线 `ListSink.append` 不落盘；整改后 `FileJsonlSink` 在 close 前即可读到 2 行，
进程异常退出后仍保留 2 行。

## 2. RED → GREEN 证据

RED 探针在**基线精确 SHA `e8ef6f1`** 上运行，随后在同一探针上验证整改结果。

| 缺陷 | 基线 RED 证据 | 整改后 GREEN |
|---|---|---|
| M01 | 报 135，应为 35 | 报 35 |
| M02 | 嵌套被 `CLOCK_REGRESSION` 拒绝 | 接受，且 45ms > 40ms root |
| M03 | 声明 99 / 事件 10，漂移 -89ms | 事件 = 声明；未来结束 fail-closed |
| M04 | 阶段 500 行、根级 0 | 根级 `UNKNOWN` |
| M05 | 真实 20ms 报 26ms | 报 20ms，空档 0 |
| M06 | `ListSink` 无逐次落盘 | 声明非持久 + `FileJsonlSink` 逐次 fsync |

基线 `defects_proven = 6`；整改后 `defects_proven = 0`。

## 3. 测试与验证

| 项 | 结果 |
|---|---|
| `tests/unit/test_biz_perf_p1_04_measure_wiring.py` | **39 passed**（原 21 + 新增 18） |
| `tests/unit/test_biz_perf_p1_04_diagnostic.py`（未修改校验器） | 通过 |
| 两者合计 | **105 passed** |
| `tests/unit/test_perf03_lnx_w04a_offline_contract.py` | **20 passed, 168 subtests** |
| `tests/unit/test_w04a_line_ending_integrity.py` | 51 passed, 1 failed（既有 Windows 符号链接限制） |
| `tests/unit/test_biz_perf_03_b_once.py` | 145 passed, 9 failed（既有 Windows 进程组限制，基线同样 9 failed） |
| `ruff check backend tests migrations scripts` | PASS |
| `git diff --check` | PASS |
| 端到端 `emit_fixture → validate_bundle` | `OFFLINE_VALIDATED` / `NONE_PROVEN` / `root_attempts=0` / `INCLUSIVE_DO_NOT_SUM` |

**冻结文件 blob 与基线逐一比对，5/5 UNCHANGED**：
`business_recalc_measure.py`、`biz_perf_p1_04_diagnostic.py`、
`perf03_lnx_w04a_offline_contract.py`、`biz_perf_03_b_once.py`、
`business_sql_snapshot.py`。

`execute` 仍为 `AUTHORIZATION_PENDING` / exit 2；`RefusedExecutor` 仍抛
`EXECUTION_NOT_AVAILABLE`。

## 4. 新增测试清单

| 用例 | 断言 |
|---|---|
| `test_M01_process_cpu_is_interval_delta_not_cumulative` | 100→135 得 35，非 135 |
| `test_M01_zero_cpu_interval_is_zero_not_undefined` | 真实零区间得 0 |
| `test_M01_regressing_cumulative_reader_yields_unknown` | 回退得 UNKNOWN |
| `test_M01_bad_cpu_types_yield_unknown` | None/str/float/bool/负数 → UNKNOWN |
| `test_M01_missing_reader_is_unknown_not_zero` | 无 reader 不伪造零 |
| `test_M02_nested_overlapping_stages_are_accepted` | 内 10–20、外 5–40 均接受 |
| `test_M02_illegal_stage_intervals_still_refused` | 结束先于开始 / 未来 / worker 前 |
| `test_M03_end_ms_is_bound_to_event_elapsed` | 事件 elapsed == 声明 end |
| `test_M03_future_end_is_fail_closed` | 拒绝且不产事件 |
| `test_M04_root_fetch_is_unknown_when_unobserved` | 阶段 500 行、根级 UNKNOWN |
| `test_M04_root_fetch_accepted_only_from_validated_port` | 端口给出 7ms/42 行才写入 |
| `test_M04_malformed_fetch_port_is_refused` | 结构错误一律拒绝 |
| `test_M05_freeze_binds_to_worker_return_not_later_work` | freeze 不受事后推进影响 |
| `test_M05_validator_never_sees_post_return_gap` | 校验器算出的 worker 区间无空档 |
| `test_M06_listsink_is_declared_non_durable` | 文档 + DURABLE=False + 无 fsync |
| `test_M06_file_sink_fsyncs_each_append` | close 前已落盘 |
| `test_M06_file_sink_refuses_overwrite_and_reentrancy` | 既有文件不被覆盖 |
| `test_M06_file_sink_survives_abort_after_partial_writes` | 异常退出仍保留全部行 |

## 5. 剩余 Gate 与未测项

| 项 | 状态 |
|---|---|
| E-03（资源/身份/授权/真实运行封装） | NOT_STARTED |
| 真实 PG17 / Worker 测量 | 未执行，`ROOT_ATTEMPTS=0` |
| `TARGETED_PG17_GATE` / `B_GATE` | NOT_APPROVED |
| 真实 CPU/RSS/FETCH 采集器 | 未实现；离线仅用注入替身 |
| 工程 CI（自动触发） | **success**，见 §6 |
| Python 3.12.16 | **VERIFIED_BY_CI**（见 §6；本机为 3.12.11） |

**未测项说明**：本轮的所有"实测值"都来自注入的确定性替身，用于证明**口径正确**，
不代表真实采集器可用。真实 `process_time`、RSS 采样与 driver FETCH 观测须由 E-03 提供。

## 6. 工程 CI 结果（push 自动触发）

普通 push 后由 GitHub 自动触发，**未手工重跑**。

| 项 | 值 |
|---|---|
| Run | [`43376516292`](https://github.com/sssssssssh/ssh_stock/actions/runs/43376516292) |
| Commit | `218861e26cd03dd3fb00d13ef2fe59e054de873e` |
| 触发方式 / attempt | `push` / 1 |
| 结论 | **success** |
| `test` Job | 63/63 步骤 success，耗时 71.4 分钟 |
| pytest（JUnit） | 8800 项，**0 失败** |
| 本模块测试 | 39 项，**0 失败** |
| 覆盖率 | 90.02%（门槛 70%） |
| Python | **3.12.16**（`/opt/hostedtoolcache/Python/3.12.16/x64`） |

全部工作流均 success：`CI`、`Publication V1.3`、`A4-1 read baseline diagnosis`、
`A4-2 isolated read experiments`。

**Python 3.12.16 说明**：本机验证环境为 3.12.11，此前记为 `NOT_VERIFIED`。
上述 CI 在 3.12.16 上跑通全量 pytest 且包含本模块 39 项测试，因此该版本兼容性
由 CI 覆盖，记为 `VERIFIED_BY_CI`；本机 `NOT_VERIFIED_FOR_3_12_16` 的表述仅适用于
本机运行。

**历史失败归因（供审阅参考）**：E-02 原提交 `e8ef6f1` 的 CI 曾在
`tests/unit/test_perf03_lnx_offline_supervisor.py` 的一个参数化 scene 上失败 1 次。
该用例与本次改动无 import 关联（本模块仅被自身测试引用），在本机基线与当前提交
上均 `58 failed / 23 passed`（Windows 平台差异）。后续运行中该失败未复现，
判定为时序抖动，非本模块缺陷。

## 7. 明确不主张

- 不主张真实 PG17 或 Worker 测量已完成。
- 不主张发现热点或达到性能门槛（`NONE_PROVEN` / `NOT_CLAIMED`）。
- 不主张 E-02-R1 通过即代表 E-03 或 B_GATE 可推进。
- 不主张工程 CI 通过等同于 P1-04 真实测量通过。
