# BIZ-PERF-P1-04-W05-READY：单次隔离性能测试准入核验与最终执行决策包

发起日期：2026-11-14。负责人：用户；执行：远程 ssssssh 的 Codex 桌面 GP 项目；独立审阅及安全推送：ChatGPT。
唯一基线：GitHub/master、origin/master、HEAD `67d9b19cc19440ad91bd4562b9bc3eebf2077751`，精确提交主 CI run `43592407760` attempt 1 `SUCCESS`，Linux pytest 7245 passed / 1 skipped / 0 failed，Ruff 与 CI-OPT 成功。
此阶段叫 **W05-READY**，不是 E06/PRETEST-02。任务目标：把 P1-04 父任务 W05、PRETEST-01 的真实申请草案和现有执行链路的缺口整理成**可以供负责人独立作出批准/拒绝决定的核验结果**；新增小型、纯离线、只读的自检程序 + 测试，不能再扩建身份/审计/授权平台。

## 0. 绝对不可越过的边界

本轮 **不允许**访问/启动真实 PostgreSQL17、Worker、Scheduler、Docker、K8s、云、外部网络、已有业务/测试库；不得创建或删除库、卷、容器、执行迁移、运行因子重算、执行真实 SQL/EXPLAIN、性能实验，绝不调用任何 real create/claim/execute/cleanup。真实测试资源未来须是**新隔离实例**，不能使用既有 PG17/生产资源。不得提供带 side effect 的 runbook 命令；不得修改或调用现有实际执行入口。
保持 `ROOT_ATTEMPTS=0`、`HOTSPOT=NONE_PROVEN`、`B_GATE=NOT_APPROVED`、`TARGETED_PG17_GATE=NOT_APPROVED`、`AUTHORIZATION=AUTHORIZATION_PENDING`、`BUDGET=DRAFT_NOT_APPROVED`。即使离线材料所有字段均填写，也只可返回 `REVIEWABLE_ONLY`，**绝不可返回 APPROVED / EXECUTABLE / GO**；`execute`（含 --allow/--force/--permit 变体）始终 `AUTHORIZATION_PENDING` 和 exit 2。
不可改动五份冻结文件，实际 Git blob 必须一致：
- `scripts/business_recalc_measure.py` `782e45ba53c8de8df0d12ffa84c219855316cfda`
- `scripts/biz_perf_p1_04_diagnostic.py` `714f78017ec252791ac6a89f9fb0e0a984333c37`
- `scripts/perf03_lnx_w04a_offline_contract.py` `931fd4fec38551d9fac59791d2bde5ce0e6a1d48`
- `scripts/biz_perf_03_b_once.py` `2ea473491f590893ad575b90a0ba42f932e37129`
- `scripts/business_sql_snapshot.py` `e7532b0a0242f1e3d3b047fdc03fca7ffc3ce7c6`
本轮**不修改** backend/frontend、任何生产代码、E02–E05、PRETEST-01、历史回执、数据模型/迁移、requirements、Docker、CI workflows、环境变量或 GitHub 配置；不改交易日/PIT/250 交易日预热/430 日历日回看/500 行候选批/300 秒发布预算/原像与候选身份/质量和原子发布规则。

## 1. W00 真实基线及阅读

先 `git status --short --branch`、`git rev-parse HEAD` 与 origin/master；只允许一个负责人本轮新写的未跟踪任务书 `docs/tasks/BIZ-PERF-P1-04-W05-READY.md`。其它未预期 dirty 立即停止。Codex 沙箱如无法 `git ls-remote`（SSH 权限拒绝），依据任务书所列**由 ChatGPT 外层已核对**的远端基线继续，但须如实注明未自行验证远端；不要换代理、改权限、替代 index 或绕过仓库保护。
按 `AGENTS.md` 规定先阅读五份治理文件 `PROJECT_CHARTER.md`、`PROJECT_STATUS.md`、`PROJECT_ROADMAP.md`、`DECISION_LOG.md`、`docs/tasks/README.md`，然后 PRD、系统设计、`PROJECT_RULES.md`、`README.md`、`docs/tasks/BIZ-PERF-P1-04.md`、`docs/acceptance/BIZ_PERF_P1_04_ISOLATED_RUN_REQUEST_DRAFT.md`、`docs/acceptance/BIZ_PERF_P1_04_PRETEST_01_REPORT.md` 和 E03/E04/E05/PRETEST 回执，再核对 `scripts/v14_test_database.py`、`scripts/business_recalc_measure.py`（只读）、E02 测量合同、E03 guard、E04 journal/review 和既有测试。当前新需求与旧治理内容存在冲突则指出，不擅改治理状态。

## 2. W05-A：真实测试前缺口矩阵（文档，明确区分代码和现实）

新增 `docs/acceptance/BIZ_PERF_P1_04_W05_READY_ASSESSMENT.md`，至少逐项列出：
1. **可复用但非真实授权**：E02 root/Worker/post、SQL/FETCH/CPU/RSS；E03/04/05 离线身份/日志/未知 ACK；PRETEST 只读样本视图。说明目前不等于真实执行接线/独立可信审计。
2. **PG17 资源**：新 Linux x86_64 实例、PG17 major、版本/镜像 digest、UUID marker、offline/online `system_identifier`、独占 PGDATA、卷/网络/cgroup/owner、唯一 lease、清理边界。源代码里 `verified_test_url` 的环回 + marker + physical ID 是必要检查但**不足以证明未来新实例独占及全流程安全**。
3. **执行能力与职责**：现有真正业务脚本如 `business_recalc_measure.py` 会创建/删除数据库，受 W04-A 冻结且使用旧协议；E02/03/04/05 的新适配入口拒绝真实运行。写出未来必须独立评审的最小接口/插入点，**仅静态设计，不写可执行实时适配器**。
4. **预算/时间边界**：明确新资源创建、seed 900 日历日历史、库迁移和预热、root 计时、after-root 验证、清理，哪些包含在 20min 内、哪些单列；当前缺证据时标 `UNDECIDED`，不能把 900 日合成 seed 当成 900 个真实交易日，也不能把 5320 股日行当成真实生成表行数；root <15min + 最后 5min 保留清理仅是草案。
5. **审批与身份**：负责人、操作人、验收人、时间窗口、精确实施 SHA 的真实 CI、配置/策略/数据 fingerprint、成本承担、CPU/磁盘/IO/限额、清理主体/失败处置、完整证据留存，以及单次尝试和 UNKNOWN_ACK 人工中止。
6. **测量可回答的问题**：只调查 8 股、2025-01 固定五 OFF 的一根真实样本；可能的热点位于读取/因子计算/候选查询与写入/发布校验；`FactorInputWindow._verify` 在 factor_input_reuse_enabled=false 的路径通常不会执行，绝不伪造其性能归因；root SQL 总耗时缺测保留 UNKNOWN；无多次样本不得报告 p95/优化提升/容量结论。
每项有 `evidence_source`（真实路径/函数/文档）、`what_code_proves`、`what_requires_live_observation`、`owner_action`、`disposition`（`CODE_VERIFIED` / `NOT_VERIFIED` / `OWNER_DECISION_REQUIRED`）。避免重复写几十页既有安全框架内容；提供一页优先级汇总，最多 5 个关键阻断项。

## 3. W05-B：最小只读“核验清单”程序（必须有源码和测试）

仅新增 `scripts/biz_perf_p1_04_w05_readiness.py` 和 `tests/unit/test_biz_perf_p1_04_w05_readiness.py`。做一个**纯函数 + 可选只读 CLI**，不调用外部网络、数据库、文件写入、Worker、容器或旧执行器，默认输入为外部显式提供的有限大小、严格 JSON 申请清单。不要重新实现 E03–E05 的准入签名、租约、日志、审批验证；这只是“人工待确认事项的完整性检查”，不能签发 permit。
建议 `assess(request, expected_sha)` 输出固定字段：`schema`、`mode=DOCUMENTARY_READINESS_REVIEW`、`status=BLOCKED` 或 `REVIEWABLE_ONLY`、`unverified_claims`、`blockers`（固定代码）、`owner_decisions`、`approved=false`、`execution_available=false`、`root_attempts=0`、`hotspot=NONE_PROVEN`、`b_gate=NOT_APPROVED`、`targeted_pg17_gate=NOT_APPROVED`、`authorization=AUTHORIZATION_PENDING`。**不能从 JSON 自述 `ci_status=SUCCESS`、签名串、资源身份、`approval=true`、`permit`、某个路径存在性推导可信事实。** 即使结构齐全也只能 `REVIEWABLE_ONLY`，源认证/实际资源必须另行独立核验。
验证固定范围：股票数8、2025-01-01～2025-01-31、单次根、900历史日、五开关 false、未来全新 Linux/PG17、预算草案 20min/保留末5min、3GiB/4GiB/10GiB/10MiB、具名负责人/操作人/窗口/清理人/成本限额、最终实施 SHA、run UUID、CI/审阅/资源证据字段是否**存在且类型合规**（绝不验证真实性），seed/root/post/cleanup 时间分段必须一致且不能隐藏不包含的步骤。使用固定短错误码脱敏，拒绝重复键、未知字段、NaN/Inf、无界整数、路径不可信/超限。输入如果由 CLI 读取，最多 64KiB，仅显式本地路径，参考既有安全文件读取器；不要自动读取用户 .env 或 PG 配置。没有真实数据时提供**仓库内测试夹具生成函数/单测构造**，不要提交看似已批准的实例凭证。
可选 CLI `review-offline --input FILE --expected-sha HEX` 输出小于64KiB的 JSON 到 stdout，无任何文件写入、无连接；`execute` / `--allow` / `--force` 固定 exit 2。测试结果不构成 B_GATE 提升。
重点：代码要简单、最小化。**若申请清单无法在 250 行内清楚实现，可缩小为 1 个纯函数，而不是扩大成新系统**。

## 4. W05-C：单次真实试验“操作员待批清单”而非执行脚本

新增 `docs/acceptance/BIZ_PERF_P1_04_W05_OPERATOR_CHECKLIST.md`，按照 PRETEST 草案组织成具名待填写字段（不写真实凭据），分 `PREPARE`（独立资源、新 PG17 物理身份、seed、成本）、`MEASURE`（一次 root、原始证据、stop）、`VERIFY`（post root/摘要/无 B 泄漏）、`CLEANUP`（只清理已证明归属的本次资源，未知 ACK 则停止）四段；分别说明每段计时是否计入拟议 20min；缺项写 `NOT_VERIFIED`/ `OWNER_DECISION_REQUIRED`。不输出直接运行/删库的命令，不自动填操作人、机器、资金、system identifier 或许可。结论固定为 `OWNER_SIGNOFF_PENDING`，新授权须用户单独明确提出。

## 5. W05-D：针对性测试、文档及交付验收

先 RED 探针，再 GREEN；新增至少 20 项**非重复**单元测试，覆盖：格式、股票/月份/seed 规模、五开关、两种边界 root<15min/清理末5min、忘记 seed 计时、预算缺失/整数溢出、未知 CI 来源、审批自述、签名伪造、UNKNOWN_ACK 不可恢复、缺 owner、跨 SHA/run、重复 JSON 键/非有限、执行入口恒拒绝、产物只读/CLI 脱敏、无 DB/worker import 和资源接触。只测试**本机安全离线**的专属文件 + PRETEST-01、E05/E04/E03/E02、原 diagnostic/W04A/fake-PG17-guard；不触发任何真实资源测试。`python -m ruff check` 如本机缺包，记录 ENV_BLOCKED，不升级依赖；GitHub 新精确 SHA Linux CI 验证 Ruff。校验 5 frozen blob、`git diff --check`、AST/新增文件白名单、旧业务文件零差异。
新增 `docs/acceptance/BIZ_PERF_P1_04_W05_READY_CLOSEOUT.md` 记录源代码证据、短阻断清单、RED→GREEN、真实测试数量、哪些检查仅结构/声明、实际提交/推送情况及尚未批准项；明确本轮只完成决策准备，不产生任何可执行许可。

**仅允许如下路径新增，无旧文件改动：**
- `docs/tasks/BIZ-PERF-P1-04-W05-READY.md`（本任务书，由 ChatGPT 下发，保留原文）
- `scripts/biz_perf_p1_04_w05_readiness.py`
- `tests/unit/test_biz_perf_p1_04_w05_readiness.py`
- `docs/acceptance/BIZ_PERF_P1_04_W05_READY_ASSESSMENT.md`
- `docs/acceptance/BIZ_PERF_P1_04_W05_OPERATOR_CHECKLIST.md`
- `docs/acceptance/BIZ_PERF_P1_04_W05_READY_CLOSEOUT.md`
如果发现该范围阻断，先报告，不修改其他代码。不得在本轮创建额外文件到 Git 跟踪范围。

## 6. Git 推送与 ChatGPT 独立复核

本任务从 Codex 桌面软件 **GP 项目**的持久会话启动，名称 `BIZ-PERF-P1-04 W05-READY 准入核验`，在该会话中列出阶段进度、测试和最终回执，不能用独立 `codex exec` 替代。
完成后在权限允许范围下正常 `git add` 仅上述 6 文件、单次 `git commit`、非 force `git push origin master`；若沙箱 .git/index.lock/SSH 拒绝，**禁止绕过**，留工作区交由 ChatGPT 已获授权的外层 PowerShell 先独立复测和文件核验后安全提交/推送。严禁丢弃/覆盖任何其他用户更改，远端 master 若出现漂移应立即停止交回。
推送后由 ChatGPT 独立检查精确 SHA 的主 CI/A4-1/A4-2/Publication、核心测试、Ruff、冻结文件、源码边界，完整通过后结论为 `W05_READY_DOCUMENTARY_ACCEPTED`，**绝不称 B_GATE APPROVED**。如发现问题，给出整改；否则本线结束，下一步只有负责人决定是否提供真正的新隔离资源和单次真实测量授权。
最终 GP 会话报告：`TASK=W05-READY`、`FINAL_SHA`、`PUSH`、`CI_RUN`、`OFFLINE_TESTS`、`FROZEN_5`、`ROOT_ATTEMPTS=0`、`HOTSPOT=NONE_PROVEN`、`B_GATE=NOT_APPROVED`、`TARGETED_PG17_GATE=NOT_APPROVED`、`NEXT=CHATGPT_INDEPENDENT_REVIEW`。
