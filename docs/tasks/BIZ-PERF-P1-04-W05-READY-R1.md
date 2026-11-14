# BIZ-PERF-P1-04-W05-READY-R1：Ruff B007 最小整改

2026-11-14。执行端：远程 ssssssh 的 Codex 桌面 **GP** 项目持久会话。独立审阅、外层常规 Git 推送和 CI 核验由 ChatGPT 完成。

## 1. 精确问题与基线

- 唯一起始 HEAD、origin/master、GitHub master：`8dc973e3f7dbc32356619f50b5b15a70c146a499`。
- 同 SHA A4-1 workflow #43606218183 的 contracts job、Publication V1.3 #43606218212 的 contracts job 均出现 **Ruff B007**，主 CI 的 workflow-contracts 亦失败；A4-2 当前可能仍运行，无需等待旧 SHA 测试完才能进行这个独立静态修复。
- Linux Ruff 原始失败：`scripts/biz_perf_p1_04_w05_readiness.py:154:13 B007 Loop control variable kind not used within loop body`。
- 当前代码：
  ```python
  evidence = request["evidence"]
  keys(evidence, {"ci", "review", "resource"})
  for kind, row in evidence.items():
      keys(row, {"source", "sha", "run_uuid", "reference"})
      need(label(row["source"]) and label(row["reference"]), "EVIDENCE_INCOMPLETE")
      need(row["sha"] == expected_sha, "SHA_MISMATCH")
      need(row["run_uuid"] == run, "RUN_MISMATCH")
  ```
- 已确认 `kind` 无任何业务用途，符合最小修复 `for row in evidence.values():`，要求验证行为不变；不能只靠重命名忽略检查或修改 Ruff 规则。

## 2. 执行步骤

1. 先按 `AGENTS.md` 核查 HEAD、origin/master、工作树；仅允许新任务书作为事先已授权未跟踪文件。若存在其它脏改动/远端 SHA 漂移，立即停止并报告，不覆盖。
2. 按 AGENTS 顺序阅读治理文件和必要业务文档，定位上述确切源码及失败原因（**无须重写之前 W05 任务或引入新功能**）。
3. **仅修改源码这一处**：`scripts/biz_perf_p1_04_w05_readiness.py` 的 `for kind, row in evidence.items():` → `for row in evidence.values():`。不要改任何逻辑、异常信息、文档或现有测试。
4. 运行 `python -B -m pytest tests/unit/test_biz_perf_p1_04_w05_readiness.py -q` 和任务指定旧安全离线回归集合，注意禁止连接真实 PG17、Worker、Scheduler、Docker、云资源和用户业务/测试数据库。禁止全量本机 pytest，因为它可能触及真实外部资源。
5. 尝试 `python -B -m ruff check scripts/biz_perf_p1_04_w05_readiness.py`，如 Windows 本机未安装则如实标 `ENV_BLOCKED`，**不要装/升级依赖**；在 GitHub 新精确 SHA Linux CI 以 Ruff 判断，不能因本地无包而宣称通过。
6. `git diff --check`，只允许源码上述一行变更（另有本任务书新增）；逐项核验五份冻结 Git blob 与旧业务、E02-E05/PRETEST 零改动；不能更改 workflow/CI/pytest_safety/依赖/任何基线门禁。
7. 若正常环境允许，常规 `git add` 仅两条文件、一次 `git commit -m "fix(perf): resolve W05 readiness Ruff B007"` 并非 force 推送 `master`。若 Codex sandbox 无权写 .git 或网络 SSH 拒绝，则**不绕过**，保留工作区且向 ChatGPT 汇报：ChatGPT 将独立核查测试和范围，使用已有授权的外层 PowerShell 安全提交推送。
8. 记录实际通过数、Ruff 状态、提交与推送状态和风险；推送后由 ChatGPT 核实新 SHA 的主 CI、A4-1、Publication、A4-2，**不以失败旧 SHA 的重跑等同于新 SHA 的证明**。

## 3. 绝对红线

- 不运行真实 PG17、Worker、Scheduler、迁移、Docker、容量实验、性能根任务；不改任何数据库连接、业务代码、Git 配置/历史、Ci workflow、策略、E02-E05/PRETEST/W05 既有测试与历史回执。
- 冻结五源码与此前 SHA 严格一致：
  - `scripts/business_recalc_measure.py` `782e45ba53c8de8df0d12ffa84c219855316cfda`
  - `scripts/biz_perf_p1_04_diagnostic.py` `714f78017ec252791ac6a89f9fb0e0a984333c37`
  - `scripts/perf03_lnx_w04a_offline_contract.py` `931fd4fec38551d9fac59791d2bde5ce0e6a1d48`
  - `scripts/biz_perf_03_b_once.py` `2ea473491f590893ad575b90a0ba42f932e37129`
  - `scripts/business_sql_snapshot.py` `e7532b0a0242f1e3d3b047fdc03fca7ffc3ce7c6`
- `ROOT_ATTEMPTS=0`, `HOTSPOT=NONE_PROVEN`, `B_GATE=NOT_APPROVED`, `TARGETED_PG17_GATE=NOT_APPROVED`, `AUTHORIZATION=AUTHORIZATION_PENDING`。
- 此次任务允许写入的**唯二 Git 路径**：本任务书 `docs/tasks/BIZ-PERF-P1-04-W05-READY-R1.md` 和 `scripts/biz_perf_p1_04_w05_readiness.py`；不能夹带其它文档/测试修改、临时文件。

## 4. Codex GP 回执

任务在 GP 持久会话中明确列出：`TASK=W05-READY-R1`, `BASELINE_SHA`, `CHANGED_LINE`, `SAFE_TESTS`, `RUFF`, `FROZEN_5`, `PUSH`, `FINAL_SHA`, `CI_RUN`, `ROOT_ATTEMPTS=0`, `B_GATE=NOT_APPROVED`, `TARGETED_PG17_GATE=NOT_APPROVED`, `NEXT=CHATGPT_INDEPENDENT_REVIEW`。若仅本地完成，注明 CI PENDING，不可宣称最终验收成功。
