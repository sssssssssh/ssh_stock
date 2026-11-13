# BIZ-PERF-P1-04 E02-R2 根边界整改回执

日期：2026-11-14（Asia/Shanghai）。任务：
`BIZ-PERF-P1-04-E02-R2-ROOT-BOUNDARY-AUDIT`。

## 基线、范围与当前结论

开始时 master 干净，由 `f7d8e264041db4f7d5600e1ce5b2bbd6b7ff0345`
快进拉取至 `e1a25b7ffba10f0e4458710e7d096e05e261f0e1`；HEAD、origin/master、
实时远端一致。已按顺序读取五份治理文件；其中旧接续指针未包含后续 P1 代码，
本次以负责人最新任务书限定范围，不重排路线图，不修改旧治理或验收事实。

本次仅修改：

- `scripts/biz_perf_p1_04_measure_wiring.py`
- `tests/unit/test_biz_perf_p1_04_measure_wiring.py`
- 本回执

根返回边界缺陷已通过直接代码路径 RED→GREEN 验证。当前为
`LOCAL_OFFLINE_VALIDATED / INDEPENDENT_REVIEW_PENDING / CI_PENDING`。
最终 SHA、自动 CI run/attempt 及各 Job 结论在提交后单独交付，不为回填本文自身 SHA
连续提交。完整工程闭环仍要求本次精确 SHA 主 CI 成功及独立审阅。

## RED → GREEN

基线实现未修改时，新增三个探针均失败（退出 1，3 failed / 39 deselected）。
测试通过真实 `run_offline`、注入 Executor 及原 `RootCounts` 路径，未伪造冻结事件。

| 探针 | 基线实际结果 | 修复后 |
| --- | --- | --- |
| `test_R2_cpu_window_closes_at_worker_return` | 累计 CPU 100→120，返回后再到 140，报 CPU=40 | Wall=40、CPU=20；reader 只读 100、120 |
| `test_R2_sql_window_closes_at_worker_return` | 返回后 `begin("UPDATE")` 仍为 True | False；快照仅 SELECT=2 |
| `test_R2_post_return_clock_cpu_sql_cannot_pollute_snapshot` | Wall=40、CPU=40、SELECT=2/UPDATE=1 | Wall=40、CPU=20、仅 SELECT=2 |

原 FileJsonlSink 的短写、write/flush/fsync 故障也先由四项参数化测试复现
（退出 1，4 failed）；随后增加完整写入检查、固定拒绝码和失败粘滞状态。
修复后这四项全部通过，失败包交给未修改的校验器拒绝，未生成 summary/integrity。

命令口径（`OUT` 为仓库外的新证据目录；临时目录、日志和 JUnit 均写入 OUT）：

```text
python -B -m pytest tests/unit/test_biz_perf_p1_04_measure_wiring.py -k test_R2 -q
python -B -m pytest tests/unit/test_biz_perf_p1_04_measure_wiring.py -k sink_fault -q
python -B -m pytest tests/unit/test_biz_perf_p1_04_measure_wiring.py tests/unit/test_biz_perf_p1_04_diagnostic.py tests/unit/test_perf03_lnx_w04a_offline_contract.py -q --junitxml=OUT/final-offline.xml
```

最初一次编辑脚本因默认 GBK 解码失败而未修改源码，当次随后测试仍为 3 failed / 39 passed；
后续明确按 UTF-8 编辑，未放宽断言。新增端到端夹具初次遗漏完整表摘要，继而遗漏根 SQL，
分别被原校验器以 BUSINESS_VALIDATION_FAILED / EVIDENCE_INCOMPLETE 拒绝；
已补齐假的执行期 SQL 和完整表摘要，保持原校验器不变。所有失败日志保留于本次仓库外证据中。

## 单一捕获终点与状态

`run_offline()` 的唯一注入 Worker 调用返回后，其 finally 已完成，立即执行
`_capture_root()`：捕获单调 Wall 终点、封闭原 RootCounts、读取累计 CPU 差值和 RSS，
同时固定根 FETCH（未提供观测为 UNKNOWN）。后续 `freeze_root()` 只发布捕获的快照，
不会重新读取 CPU、RSS、SQL 或 FETCH，也拒绝事后覆盖指标和追加 stage。
create/claim 仍在根区间；新增测试确认根 45ms、Worker 子区间 40ms，返回后的 20ms 不混入。

手动 `begin_root → begin_worker → freeze_root` 没有 Worker 返回信号，
故 freeze 的当前时刻是终点；保留此路径原有累计 CPU / 根 FETCH 参数校验。
没有将手动路径宣称为已捕获的 Worker-return instant。

Worker 异常时先封闭计数，记录静态 ROOT_FAILED 失败事件并终止；返回快照捕获失败、
Sink 失败后均不能恢复成成功根或第二次调用 Executor。Sink 首事件失败也消耗该 recorder
的单次状态，不允许回退 INITIAL 重开。事件 seq 仅在成功追加后推进，已有证据不覆盖。

CPU 缺测、回退继续为 UNKNOWN；累计 100→100 明确为 0。T30 改用零区间的完整端到端
夹具，严格断言 CPU=0、`wall_per_cpu="UNDEFINED"`、RSS=2048。
原校验器也将 UNKNOWN CPU 的派生比率标为 UNDEFINED；合法离线夹具仍可验证结构完整，
这不表示缺测 CPU 已采集、真实执行已通过或获得性能资格。

## P2 Sink 审阅边界

- POSIX：打开 immediate parent 的 O_DIRECTORY/O_NOFOLLOW fd，再通过 dir_fd
  独占、no-follow 创建文件并 fsync 父目录。后续写入始终使用固定文件 fd；测试覆盖
  文件路径替换后仍写原 fd，以及父目录 fsync 顺序和失败拒绝。
- 信任前提仍为稳定可信的祖先目录；这不是面向敌对祖先、恶意挂载或硬件的安全证明。
  Windows 分支不宣称目录项崩溃耐久性，`directory_synced=False`。
- 每行必须完整 write、flush、fsync 后才增加 count。短写或 I/O 故障返回静态 SINK_FAILED，
  sink 与 recorder 均粘滞拒绝后续追加；不回显底层异常细节。故障最后一行可能不完整，
  也可能可读但尚未确认耐久；count 仅表示已确认的完整前缀，不将不确定尾部计为成功。
- 本机文件读取和注入故障测试不能证明断电存活。POSIX 专属分支由新提交 Linux CI
  核验，不把 Windows 上通过的平台条件分支冒充 Linux 文件系统测试。
- `emit_fixture` 仍使用 ListSink，模拟成功后统一写盘，只证明夹具与原校验器兼容，
  不提供真实故障前缀留存或 E-03 持久层实现证据。

## 验证与冻结证明

本机 Windows / CPython 3.12.7 / pytest 7.4.4，未升级依赖。

| 项目 | 实际结果 |
| --- | --- |
| 测量适配器（含原 E02/R1） | 58 passed（原 39，加本次 19 个参数展开后的测试项） |
| 未修改的 diagnostic | 66 passed |
| 关键 W04-A offline contract | 20 passed |
| 本次组合 | **144 passed / 0 failed / 0 skipped**，4.80s，退出 0 |
| `emit_fixture → validate_bundle` | 原校验器通过；完整固定 schema 和 integrity；root_attempts=0、NONE_PROVEN |
| `execute` / RefusedExecutor | 原断言通过：AUTHORIZATION_PENDING / exit 2；EXECUTION_NOT_AVAILABLE |
| `git diff --check` | PASS |
| 本机 `python -m ruff check backend tests migrations scripts` | ENV_BLOCKED，退出 1，No module named ruff；未安装依赖，须另核新 SHA CI Ruff |
| 本机全量 pytest / 真实数据库集成 | NOT_RUN；仅授权离线替身，无本机 PG17 测试目标许可 |

以上统计不累计重复测试轮次，也不将 subTest 数量当顶层测试数。

以下 Git blob 与 `218861e26cd03dd3fb00d13ef2fe59e054de873e` 和拉取基线均一致，
且本机原始字节 SHA256 与开始时逐一一致：

| 冻结文件（scripts/） | Git blob |
| --- | --- |
| business_recalc_measure.py | 782e45ba53c8de8df0d12ffa84c219855316cfda |
| biz_perf_p1_04_diagnostic.py | 714f78017ec252791ac6a89f9fb0e0a984333c37 |
| perf03_lnx_w04a_offline_contract.py | 931fd4fec38551d9fac59791d2bde5ce0e6a1d48 |
| biz_perf_03_b_once.py | 2ea473491f590893ad575b90a0ba42f932e37129 |
| business_sql_snapshot.py | e7532b0a0242f1e3d3b047fdc03fca7ffc3ce7c6 |

拉取基线的主 CI 43406729877 / push / attempt 1 已只读核实 completed/success；
test、workflow-contracts、dependency-audit、lookup-diagnosis、ci-opt-01-ci 成功，
authorize、lookup-tail-attribution、ui-visual-acceptance、capacity、publication-release-gate
为 skipped。另三条普通工作流 43406729960、43406729707、43406729863 亦 success。
这些仅证明 e1a25b7，绝不替代本次修复的 CI。
旧 e8ef6f1 的 Supervisor 失败第二轮未复现；第二轮后续 Docker pip BrokenPipe 失败属于
另一失败事实。本次不将“时序抖动”升级为严格根因，也不修改或重跑历史记录。

## 交接

```text
TASK=BIZ-PERF-P1-04-E02-R2-ROOT-BOUNDARY-AUDIT
BASELINE_SHA=e1a25b7ffba10f0e4458710e7d096e05e261f0e1
FINAL_SHA=REPORTED_AFTER_COMMIT
RED_CPU_WINDOW=PASS (baseline assertion failed as expected)
RED_SQL_WINDOW=PASS (baseline assertion failed as expected)
GREEN_CPU_WINDOW=PASS
GREEN_SQL_WINDOW=PASS
E02_OFFLINE_VALIDATOR=PASS
FROZEN_BLOBS=UNCHANGED
RUFF=LOCAL_ENV_BLOCKED / NEW_SHA_CI_PENDING
GIT_DIFF_CHECK=PASS
MAIN_CI=NEW_SHA_PENDING
REAL_PG17=NOT_RUN
REAL_WORKER=NOT_RUN
ROOT_ATTEMPTS=0
B_GATE=NOT_APPROVED
HOTSPOT=NONE_PROVEN
NEXT=INDEPENDENT_REVIEW
```

没有连接真实数据库、运行真实 Worker/Scheduler、部署或手动 dispatch/rerun。
E-03 真实执行封装、资源身份和执行许可仍须独立任务；本轮不启动下一阶段。
