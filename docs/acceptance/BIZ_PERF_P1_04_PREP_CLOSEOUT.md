# BIZ-PERF-P1-04 离线准备回执

**R1 离线整改通过，`B_GATE=NOT_APPROVED`。** 原 `PREP_BLOCKED` 来自 W04-A A20 对旧测量器的字节冻结。R1 在获批的新路径实现离线入口和单测，原冻结脚本和断言原样保留。[任务簿、操作边界和待批表](../tasks/BIZ-PERF-P1-04.md)

## 基线与阻断复现

- 本地 HEAD、`origin/master` 和 GitHub `master` 均为 `391dca85cf9cc5b2e1858f4ea7fa19f98f52f079`。初轮 W00 开工时工作区干净；R1 接续时只有初轮两份未跟踪文档。治理、业务和历史归档沿用该基线。
- [基线 Main CI 42980518305](https://github.com/sssssssssh/ssh_stock/actions/runs/42980518305)，attempt 1，`completed/success`。test Job `130389600563` 的全量 pytest、Ruff 和路由成功；设计任务书记载 6,682 passed、1 skipped、90.02% 覆盖率。authorize、capacity、lookup-tail-attribution、publication-release-gate 等跳过。当前文档修改未触发 CI。
- `scripts/business_recalc_measure.py` Git Blob 为 `782e45ba53c8de8df0d12ffa84c219855316cfda`。现有 A20 `assert_frozen_file` 比较完整文件 SHA256，当前工作字节 CRLF 哈希 `49a10219c68a19406bd0cf4720400c99d82277e9db20bde411dd7bddafae2475`。在仓库外的临时副本分别对 LF、CRLF 增加一条注释，两个原字节样本均通过、两个候选均报 `W04A_FROZEN_CONTENT_MISMATCH`。测试源码与仓库测量器字节未动。
- 业务源摘要为 `529d933c6997a6a5fb133c5ec2a59c5c06d4e78a087cfd06032011c2d806095a`。与原测量器的 `git_text_sources_sha256` 同口径，对 `backend/`、`config/`、`migrations/` 下 438 个已跟踪 .py/.yaml 文件以 LF 规范化后，按路径汇总 SHA256。业务源码、迁移、Workflow、旧测试及旧控制器均无差异。

## 证据与验收

| 任务段 | 实际结果 |
|---|---|
| W00 | 完成，仓库外 `W00_FINDINGS.md`、`source_contract.md` 记录入口、根/SQL/FETCH/发布时序和冻结冲突。 |
| W01 | 初轮复现旧测量器 LF/CRLF 临时副本的冻结拒绝。R1 另批独立入口。 |
| W02 | 独立入口校验预注册夹具、保存原始事件、冻结根快照和独立后验摘要；真实 `execute` 在处理文件前返回拒绝。 |
| W03 | 新 T01–T20 共 66 passed；W04-A 原合同和换行保护共 72 passed、168 subtests passed；其余相关离线回归 40 passed。三组 pytest 均 exit 0。 |
| W04 | Ruff、`git diff --check`、未跟踪文件空白检查和四文件范围校验通过。未提交或推送。 |
| W05 | 待批表保留。真实接线还需独立批准和审阅，绑定精确实施 SHA、物理资源、操作主体及清理权限。 |
| W06 | `NOT_RUN`。 |

T01–T05 覆盖授权、源码与实例身份、旧协议和开关。T06–T12 覆盖根与后验边界、计量重叠、缺测、零 CPU、持久化、摘要漂移及坏样本。T13–T20 覆盖路径/大小/磁盘、单根、业务终态、超时与取消、清理身份、脱敏、Windows 路径替身及历史样本拒绝。结果均为离线替身或文件夹具；发布和清理字段只验证合同。

三组定向测试均以 `python -m pytest -p scripts.a42331_pytest_safety -p no:cacheprovider -q` 执行。新测试为 `test_biz_perf_p1_04_diagnostic.py`。W04-A 运行 `test_perf03_lnx_w04a_offline_contract.py` 与 `test_w04a_line_ending_integrity.py`。其余回归运行 `test_business_recalc_measure.py`、`test_biz_perf_04_a.py` 和旧 03-B 的三个协议/测量边界节点。另执行 `python -m ruff check --no-cache backend tests migrations scripts`。初轮仓库外 `.codex_tmp/biz_perf_p1_04/` 的原始记录保留。

本轮范围为 `scripts/biz_perf_p1_04_diagnostic.py`、`tests/unit/test_biz_perf_p1_04_diagnostic.py`、`docs/tasks/BIZ-PERF-P1-04.md` 和本回执。真实隔离测量仍需 B_GATE 以及可审计的执行封装。当前实现不加载旧测量器、不连接数据库、不启动 Worker，只有离线校验路径。

```text
TASK=BIZ-PERF-P1-04-R1
BASELINE_SHA=391dca85cf9cc5b2e1858f4ea7fa19f98f52f079
FROZEN_SOURCE_MUTATION=NONE
NEW_ENTRY=scripts/biz_perf_p1_04_diagnostic.py
T01_T20=66 passed
W04A_REGRESSION=72 passed, 168 subtests passed
RUFF=PASS
GIT_DIFF_CHECK=PASS
A_GATE=OFFLINE_VALIDATED
BUSINESS_SOURCE_DIGEST=529d933c6997a6a5fb133c5ec2a59c5c06d4e78a087cfd06032011c2d806095a
RUNTIME_TESTS=NOT_RUN
MAIN_CI=NOT_TRIGGERED
B_GATE=NOT_APPROVED
PG17=NOT_RUN
WORKER=NOT_RUN
ROOT_ATTEMPTS=0
COMMIT=NOT_COMMITTED
PUSH=NOT_PUSHED
OFF_ON=NO_GO
CAPACITY=NOT_MEASURED
ROOT_HOTSPOT=NONE_PROVEN
D04_OWNER=PENDING
R1=PARTIAL
NEXT=CHATGPT_INDEPENDENT_REVIEW
```
