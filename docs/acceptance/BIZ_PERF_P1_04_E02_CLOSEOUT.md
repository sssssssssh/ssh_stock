# BIZ-PERF-P1-04 E-02 离线测量接线验收回执

任务：BIZ-PERF-P1-04-E02-MEASURE-WIRING-01
基线：`e4502b86fb52b42945a4a977f62e75afa013b498`
日期：2026-11-13

---

## 0. 一页结论

```
E_02 = OFFLINE_VALIDATED
ROOT_ATTEMPTS = 0
TARGETED_ASSERTION_SITE = NOT_MEASURED
TARGETED_PG17_GATE = NOT_APPROVED
B_GATE = NOT_APPROVED
HOTSPOT = NONE_PROVEN（本轮不主张任何性能增益）
PERFORMANCE_GAIN = NOT_CLAIMED
```

本轮完成 **测量事件的离线产生、严格计时边界定义、与既有 P1-04 离线校验器的受控连接**。
真实 `execute` 入口仍然严格拒绝；未连接 PG17，未调用 Worker，未消耗一次性测量名额。

## 1. 口径表（Codex 与审阅共用）

| 指标 | 起点 | 终点 | 不得做什么 |
|---|---|---|---|
| `root_elapsed_ms` | `create_recalculation_job`/claim **之前** | 唯一 `execute_claimed_job` 返回且 Worker 自身 `finally`/清理完成后 `root_frozen` | **不得**包含独立 Job/ledger/来源/表摘要的后验读取 |
| `execute_claimed_job_ms` | 调用唯一 Worker 前 | Worker 返回（含其自身 finally） | 是 root 的**子区间**，**绝不能**与 root 相加 |
| `post_root_validation_ms` | `root_frozen` | 后验校验完成 | **绝不**折入 root；后验 SQL 不得进入 root 快照 |
| `stage_inclusive_ms` | 阶段真实开始 | 阶段结束 | 阶段可嵌套/重叠，**不求和**；`aggregation=INCLUSIVE_DO_NOT_SUM` |
| `sql_execute_ms` / `sql_calls` | 归属的 execute 调用 | 返回或异常边界 | SQLAlchemy execute 时间**不是** PG 服务端 CPU |
| `fetch_observed_ms` / `fetched_rows` | 驱动 FETCH 开始 | 驱动返回且实际收到行 | 可能与 SQL 等待重叠；逐块进度行 ≠ FETCH 返回行 |
| `process_cpu_ms` | root 窗口内的 `process_time` 差值 | root freeze | 为 0 时派生比率为 `UNDEFINED` |
| `rss_peak_bytes` | root 观测窗口 | root freeze | 峰值，**不是**单阶段分配量 |

**时间基准**：全部时长来自注入的单调时钟。UTC 时间戳仅作审计元数据，**不参与**任何时长计算。

## 2. 新增与冻结

**新增**

| 文件 | 说明 |
|---|---|
| `scripts/biz_perf_p1_04_measure_wiring.py` | 纯离线、注入式的事件记录与状态机适配层 |
| `tests/unit/test_biz_perf_p1_04_measure_wiring.py` | T21–T40 合同测试（21 项） |
| `docs/acceptance/BIZ_PERF_P1_04_E02_CLOSEOUT.md` | 本回执 |

**冻结（本轮字节未动）**

- `scripts/business_recalc_measure.py`：blob `782e45ba53c8de8df0d12ffa84c219855316cfda`
  （W04-A A20 完整字节保护），工作区 SHA256 `49a10219…`。
- `scripts/biz_perf_03_b_once.py` 及其 03-B 协议。
- `scripts/perf03_lnx_w04a_offline_contract.py` 与 A20 冻结断言。
- `scripts/biz_perf_p1_04_diagnostic.py`：**未修改**。`execute` 仍返回 `AUTHORIZATION_PENDING`、退出码 2；
  校验器 schema 未调整（无 W00 兼容性阻断）。
- `backend/`、`config/`、`migrations/`、`frontend/`、`.github/workflows/`。

## 3. 适配层设计要点

### 3.1 不可能发起真实执行

- 模块内无 `create_engine`、无 `psycopg`、无 DB、无网络、无后台任务入口。
- 执行能力通过 `executor` 端口注入，默认实现 `RefusedExecutor` **直接拒绝**
  （`EXECUTION_NOT_AVAILABLE`），而非静默 no-op。
- 导入模块与实例化记录器均无副作用（T40b 用子进程验证未加载 `psycopg`）。

### 3.2 状态机与事件顺序

```
root_started → worker_started → stage* → root_frozen → post_root_validation → cleanup
```

失败路径使用 `failure`（`ROOT_FAILED`/`ROOT_CANCELLED`/`ROOT_UNKNOWN`/`TIMEOUT`/`OOM`）。
第二轮 `root_started` 被拒（`ONE_ATTEMPT_CONSUMED`），符合"一次性名额"语义。

### 3.3 与既有校验器的连接

`emit_fixture()` 生成 `preflight.json` + `events.jsonl`，直接交给**未修改的**
`biz_perf_p1_04_diagnostic.validate_bundle()`。实测输出：

```
status=OFFLINE_VALIDATED
hotspot_decision=NONE_PROVEN
root_attempts=0
evidence_complete=True
aggregation=INCLUSIVE_DO_NOT_SUM
products: preflight.json raw_events.jsonl root_snapshot.json
          post_root_validation.json summary.json integrity.json
```

**没有任何断言被放宽**。校验器给出的 `EVIDENCE_INCOMPLETE`（无 instrumented 阶段或
root 总数为 0）、`CLEANUP_BLOCKED`（清理身份不符）等原有拒绝语义全部保留，适配层
按契约生成合规证据，而不是绕过检查。

### 3.4 证据安全边界

- 字段集合由校验器 `fields()` 精确校验，多一个少一个都被拒。
- 事件先 `sink.append` 落盘，再产生派生数据（T34 验证：sink 故障时只保留已持久化前缀）。
- 计数失败不伪装成功：`RootCounts` 冻结后 `begin()` 返回 `False`（T27）。

## 4. 合同测试清单（T21–T40）

| 编号 | 断言 |
|---|---|
| T21 | 单根事件顺序、seq 连续、run_uuid/root_id 一致、executor 只被调用两次 |
| T22 | 单调时钟递增；UTC 独立于时长 |
| T23 | 正样本通过**未修改**的 `validate_bundle`：`OFFLINE_VALIDATED`/`root_attempts=0` |
| T24 | `integrity.json` 为 5 个工件的摘要清单，`evidence_complete=True` |
| T25 | post-root 窗口严格在 root 窗口之外，不得折入 |
| T26 | Worker 区间是 root 的子区间 |
| T27 | 冻结后快照不可被后续查询改变 |
| T28 | SQL 计数与 FETCH 指标独立 |
| T29 | 缺测保留 `UNKNOWN`，`coverage_reason=NOT_INSTRUMENTED` |
| T30 | 零 CPU 派生比率不伪造；RSS 为峰值 |
| T31 | 第二轮根被拒（`ONE_ATTEMPT_CONSUMED`），且未调用 executor |
| T32 | 重复 worker、重复 freeze 均被拒 |
| T33 | 根 ID 不符、非法阶段名被拒 |
| T34 | sink 故障只保留已持久化前缀，不伪造后续事件 |
| T35 | 截断尾行被校验器拒绝 |
| T36 | 坏 JSON 行被校验器拒绝 |
| T37 | 任一开关为 true 被拒（`FLAG_MISMATCH`） |
| T38 | 实施 SHA 不符被校验器拒绝 |
| T39 | `python -m scripts.biz_perf_p1_04_diagnostic execute` 退出 2 且输出 `AUTHORIZATION_PENDING` |
| T40 | 默认 executor 拒绝；`root_attempts=0` |
| T40b | 导入适配层不加载 `psycopg`/`backend.*` |

## 5. 实际验证

| 检查 | 结果 |
|---|---|
| `pytest tests/unit/test_biz_perf_p1_04_measure_wiring.py` | **21 passed** |
| `ruff check scripts tests migrations backend` | PASS |
| `git diff --check` | PASS |
| 端到端 `emit_fixture → validate_bundle` | PASS（6 工件，`OFFLINE_VALIDATED`） |

## 6. 剩余 Gate 与风险

| 项 | 状态 | 说明 |
|---|---|---|
| E-02 离线接线 | **OFFLINE_VALIDATED** | 本轮交付 |
| E-03 资源/身份/授权/真实运行封装 | **NOT_STARTED** | 需另开任务书 |
| B_GATE | **NOT_APPROVED** | 真实 8 股 5320 股日行执行未获许可 |
| TARGETED_PG17_GATE | **NOT_APPROVED** | 无 Linux 主机、Docker、PG17、Python 3.12.16 |
| 性能结论 | **NONE_PROVEN** | 本轮只修测量可信度，不重做优化 |
| Python 3.12.16 | **NOT_VERIFIED** | 实际验证环境为 3.12.11 |

**已知限制**

1. 适配层是**离线替身**，未在真实 PG17/Worker 上运行。计时口径的可实现性只经过
   状态机与校验器验证，不等于真实运行已验证。
2. `process_cpu_ms`/`rss_peak_bytes` 在离线夹具中使用注入的固定读数，真实采集器
   须由 E-03 提供。
3. 真实 `execute` 入口未接线；本轮**没有**修改它的拒绝行为。

## 7. 明确不主张的内容

- 不主张发现当前性能热点（`NONE_PROVEN`）。
- 不主张达到任何性能提升门槛。
- 不主张 CI 工程通过等同于 P1-04 真实测量通过。
- 不主张历史 `AssertionError` 已解决。
- 不推进 E-03、B_GATE 或任何真实执行授权。
