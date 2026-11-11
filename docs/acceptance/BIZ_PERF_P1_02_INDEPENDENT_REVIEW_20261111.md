# BIZ-PERF-P1-02 独立证据审阅报告

审阅日期：2026-11-11
项目：`sssssssssh/ssh_stock`
基线 / 当前远端 `master`：`1fbb98c5b189be2a49fb9f576fc27d72fd9e853a`
审阅对象：上传的 `BIZ_PERF_P1_02_REVIEW_PACK.zip`，ZIP SHA256：`d16780efca963697cf480f95efeebb0206cb9cb1169efa7e83da7424efd3ad09`

## 一、裁决

**EVIDENCE_PACK_VALID / REVERT_EVIDENCE_CONSISTENT / LOCAL_PERFORMANCE_INCONCLUSIVE / P1-02 BUSINESS_CHANGE_REJECTED**。

支持按原任务书停止和撤回候选；**不支持宣称候选已提速、完全业务等价或正式 PG17 / Worker 性能验收通过**。本轮正式代码变更为零，项目处于“仅本地未跟踪验收回执”的归档状态（以归档 Git 状态证明为依据）。此审阅不授权真实业务库、Worker、正式性能实验或生产部署。

## 二、审阅范围和可信度

- ZIP CRC 解包检查：PASS，无错误成员。
- `integrity/PACK_MANIFEST.tsv`：33 条，33 条成员均存在、大小与 SHA256 全匹配；打包清单不包含自身（正常自引用排除）。ZIP 总计 34 个文件成员。
- 原始 `integrity/SHA256SUMS.txt`：30 个条目内容哈希全部一致。验收回执从原 `docs/acceptance/...` 迁到包内 `receipt/...`，其**原路径不能直接解析**，但按已记录的归档位置映射后哈希一致；属于轻微打包可用性问题，不是文件篡改。
- 已归档候选文件 `diff/input_records_candidate.py`：Windows 工作树 SHA256 = `138ffe242c466fcfc7bce0d8917e8f7f80b4c7ad25b1043e4a2275d07e9dde2d`；按 CRLF→LF 规范化后的 Git Blob SHA1 = `ede57bb64b9c80f88b857fd8db798396b151736f`，与撤回记录一致。
- GitHub 基线 `backend/app/services/factors/input_records.py` 的远端 Git Blob SHA1 = `11cf64776ab49d4a508b25f82c27686e806acc10`，与归档撤回证明声称的恢复目标一致。`master` 仍为上述基线 SHA。
- `git/current_state.txt`、`logs/final_git_check.log`、`integrity/revert-proof.json` 三者指向相同结论：tracked diff 为空，唯一 untracked 为本轮 `CLOSEOUT.md`。**没有直接连接用户当前本地磁盘，故本地恢复状态仅能评价为“多份归档证据一致”，不能冒充独立现场重验。**

## 三、RED/GREEN、回归及 Windows 错误

| 检查 | 归档证据 | 评价 |
|---|---|---|
| 基线 RED | `red.log`：24 passed, 1 failed | PASS（失败为既定结构测试） |
| 候选 GREEN | `green.log`：25 passed | PASS（日志自洽，非本审阅重跑） |
| 旧回归（候选） | `regression.log`：52 passed, 1 failed | PARTIAL |
| 旧回归（恢复后） | `regression-restored.log`：52 passed, 1 failed | PARTIAL |
| WinError 1314 | `symlink_diagnostic.log`，旧用例 `test_runtime_source_rejects_symlinked_module_directories` | 创建符号链接权限失败，不能标记业务断言通过 |
| Ruff（候选/恢复后） | 两份 `ruff*.log` 均通过 | PASS（归档日志） |
| 隔离 PG17 与 Worker | 未运行 | NOT_RUN |

`red_fixture_initial.log` 最初记录 4 failed / 21 passed；修复 fake-policy 夹具缺少的 `observe_stage` 后，`red.log` 收敛为单一预定 RED。该过程已保存，不应将初次夹具失败当作业务 Bug。

独立核对了 `diff/full.diff`：候选生产改动仅在 `blocks_to_frame`，改为对每一块先恢复 NULL / specials、汇总全列 `Series` 后一次构造 `DataFrame`；未改查询、因子公式、事务或发布调用。候选不在当前 GitHub `master`。

## 四、性能证据判定

`diff/bench.py::paired` 中，15 对交错采样先保存在进程内 `samples`，但写盘调用发生在计算 `decision` 之后。约第 410 行的 `b["cpu_ns"]["median"] / a["cpu_ns"]["median"]` 遇到基线 CPU 中位为 0，触发 `ZeroDivisionError`；`logs/microbench.log` 栈与源码完全对应。异常只在单个样本采集阶段捕获，不覆盖汇总阶段，导致已执行的首档 15 对样本未落盘。`logs/microbench.json` 是后来生成的失败状态说明，不包含原始配对计时。

| 档位 | 采样状态 | 原始可复算样本 | 性能结论 |
|---|---|---|---|
| 5,000 行 | 15 对循环执行 | 0 对持久化 | INCONCLUSIVE |
| 25,000 行 | 未运行 | 0 | NOT_RUN |
| 50,000 行 | 未运行 | 0 | NOT_RUN |
| PG17 / Root / 容量 | 未运行 | 0 | NOT_MEASURED |

因此不能倒推出 wall median/P95、也不能把 CPU 中位为零解释成 CPU 消耗为零。候选撤回是正确的预注册停止行为。**`INCONCLUSIVE` 不等于 `NO_MEASURABLE_GAIN`，更不等于优化失败的因果证明。**

另已检查 `logs/local_attribution.json`：它是**候选开发前的离线 fake Session 归因数据**，并非上述丢失的 15 对候选基准。归档记录 50,000 行、六个月场景下四类有日期输入的读取行数，S0 每类 299,997，现有 S1 输入复用每类 66,413（减少约 77.86% 的重复返回行数）；`stock_basic` 查询从 6 次减至 1 次。五类输入每月仍需要 DataFrame 组装。这说明进一步针对整链定位有意义，但**不能把 fake Session 的取数削减转述为真实数据库或整根任务的提速**。

## 五、GitHub CI 核对

基线 Main CI `42954512719`，attempt 1：`completed/failure`。实际完整 pytest 为 **6,681 passed / 1 failed / 1 skipped / 90.02% coverage**；失败的 `test` Job 在完整 pytest 步骤及随后路由校验，`ci-opt-01-ci` 因强制检查不通过失败。其他 `lookup-diagnosis`、`workflow-contracts`、`dependency-audit` Job 成功；高成本/权限相关 Job 有跳过，不等于执行或验收。该 CI 基于 `1fbb98c`，**不是本轮未提交 P1-02 候选的 CI**。与 Windows WinError 1314 为不同事实，不能互相归因。

## 六、独立审阅发现与建议

| 编号 | 严重性 | 发现及处理 |
|---|---|---|
| O-01 | P1（测量可信度；候选已撤回） | 原始样本没有在每对/每档完成后先原子持久化；汇总异常造成全部样本丢失。下一次若另行批准基准开发，先修该可靠性问题，且必须对缺失、部分和非有限值明确失败关闭。不要重跑本次实验凑结果。 |
| O-02 | P2 | CPU 中位数为零缺少保护。`process_time_ns` 在此 Windows 样本上有量化为零的可能；对于该比率应输出 `UNDEFINED` 和原始值，不能用补零、伪造精度或扣除异常样本来规避。 |
| O-03 | P2（验收边界） | 候选只有离线 fake 等价证据；PG17 的 B 覆盖 A、tombstone、跨事务、发布回滚和 Worker 实例均未经本轮实跑。`FINANCIAL_EQUALITY=OFFLINE_PASS` 需始终保留限定。 |
| O-04 | P2（工程主线） | 基线 Main CI 仍为失败；建议单独基于精确失败节点处理，不为 P1-02 篡改旧断言或跳过既有质量门禁。 |
| O-05 | P3（归档易用性） | 原 `SHA256SUMS.txt` 中回执路径为旧的 `docs/acceptance/...`，包内搬移到 `receipt/...`。内容哈希正确，未来包装时可额外附带路径映射，避免工具按原路径误判缺失。 |

## 七、最终阶段状态和下一步

- `PACK_INTEGRITY=PASS`
- `REVERT_EVIDENCE=CONSISTENT`（非本地独立访问）
- `RED_GREEN_LOG_EVIDENCE=CONSISTENT`
- `PERFORMANCE_DECISION=INCONCLUSIVE`
- `BUSINESS_CANDIDATE=REVERTED`
- `PG17_ISOLATED_TEST=NOT_RUN`
- `REAL_ROOT_OFF_ON=NO_GO`
- `FORMAL_CAPACITY=NOT_MEASURED`
- `D04_OWNER=PENDING`
- `R1=PARTIAL`
- `NEXT=ARCHIVE_CLOSEOUT_THEN_EVIDENCE_DRIVEN_ROOT_HOTSPOT_SELECTION`

建议只做 P1-02 回执与现有 ZIP 归档，不继续修改 `input_records.py`；下一阶段优先采用**现有整链观测数据**判定 SQL、来源核验、帧转换、因子计算与发布的真实耗时占比，而非直接开启另一轮未经量化的新候选改写。任何真实 PG17/Worker 性能实验仍需独立授权。

---

*审阅方法：读取上传 ZIP（不执行其中脚本）、逐条验证包内文件大小/哈希、静态核对脚本与异常栈、计算留存的 fake 归因数字，并通过 GitHub 只读接口核对远端源码 Git Blob、master 与历史 CI。未访问本地机器、未重跑测试/性能、未触达业务数据库。*
