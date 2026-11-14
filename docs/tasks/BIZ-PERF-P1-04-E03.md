# BIZ-PERF-P1-04-E03 — 真实执行前资源、身份、授权与采集器安全封装

日期 2026-11-14。起点精确 SHA：22e92d291732d4f31a0e9ba3d787ff877c20a868；R2 CI #43464657765 SUCCESS。

## 权限与硬限制
用户本轮授权：离线开发、测试、提交并推送 master，交给 ChatGPT 独立审阅。**没有授权**真实 PG17、Worker、Scheduler、数据库、Docker/云资源的创建/删除/测量，也没有授权给真实执行签发 permit、手动 CI rerun/dispatch、Environment 审批。所有新入口默认 fail-closed；旧 execute 必须保持 AUTHORIZATION_PENDING / exit 2。任何 fixture/mock 都不可标记 LIVE_VERIFIED。始终 ROOT_ATTEMPTS=0、HOTSPOT=NONE_PROVEN、B_GATE=NOT_APPROVED、TARGETED_PG17_GATE=NOT_APPROVED。禁止读写真实凭据、DSN、敏感日志。

## W00 基线和权威文件
先 git status/HEAD/origin/master/GitHub SHA，必须干净且和起点一致，保护用户工作。严格遵守 AGENTS.md：先读 PROJECT_CHARTER.md、PROJECT_STATUS.md、PROJECT_ROADMAP.md、DECISION_LOG.md、docs/tasks/README.md，接着 PROJECT_RULES.md、PRD、设计和本文件。仔细读 docs/tasks/BIZ-PERF-P1-04.md，R2 closeout，scripts/biz_perf_p1_04_diagnostic.py、scripts/biz_perf_p1_04_measure_wiring.py、scripts/business_recalc_measure.py、scripts/business_sql_snapshot.py 和旧 PG guard/03-B/W04A 测试。报告现有门禁差距；若冻结约束冲突，不能自行解冻。

## E03-A 严格预检和默认拒绝（纯离线）
新增 scripts/biz_perf_p1_04_e03_guard.py（允许依职责拆分）和专属 unit tests。构造显式只读 execution-plan/身份 preflight 契约：精确 implementation SHA、worktree=CLEAN、CI SUCCESS 的 SHA 绑定、独立审阅凭证、run UUID、输入/策略/业务 digest、五优化开关全部 false、8 股及 2025-01 一个月、历史 Seed 665 开市日对应 5320 股日行（不能用单一数字取代逐表行预算）、one root。所有缺失、伪造、类型/键不符、跨 SHA、不相符状态固定拒绝码；不可从环境变量或布尔 allow=true 获得执行许可。仅提供 plan/inspect/validate-offline 等离线入口；**execute 必须拒绝**。复用原 diagnostic schema，不允许直接调用旧 business_recalc_measure.py。

## E03-B 资源/所有权模型
建立可注入的 Inspector / IdentityAttestor / ApprovalVerifier / BudgetGuard / ExecutorPort 接口，默认 Refused*。EXPECTED/OBSERVED_OFFLINE/OBSERVED_LIVE 不能混淆，mock 不能给出 LIVE_VERIFIED。检验 Linux x86_64、PG17、独占新 PGDATA、UUID marker、physical system identifier、owner/volume/network digest、新建数据库归属、独占 lease、CPU/内存/卷/时限/输出上限；当前只通过 mock 验证拒绝语义。任何不明资源归属标 CLEANUP_BLOCKED，不能真的清理。禁止多 root、重试、未知 ACK 自动续跑；不得生成可执行生产准入令牌。预算参数维持待批草案：20min 末5min清理、Worker3GiB、PG4GiB、卷10GiB、证据10MiB，不视为已批准。

## E03-C 采集器接口（不连接真实执行）
定义或整理单调时钟、累计 CPU、峰值 RSS、root SQL、driver FETCH 的端口与 coverage；保持 R2 run_offline → _capture_root → freeze_root 的单次冻结语义；0 CPU、UNKNOWN、NOT_INSTRUMENTED、重叠 stage DO_NOT_SUM、post_root 之外的查询均准确。可纯离线演示真实 reader 形状，不能安装真实 Worker hook 或启动任何生产进程。读数失败不得伪装为零，不得在 return 后继续采样污染 root。冻结文件不得改动。

## E03-D 证据/错误/清理合同
沿用 FileJsonlSink 和原 diagnostic 验证器，seq 单调、run/root 一致、固定失败码、长度上限、脱敏、fail-closed。模拟 create/claim 失败、claim 后未知 ACK、Worker 失败、超时/预算、采集失败、sink 短写/fsync、清理所有权未知。前缀可检查而不能伪造 completed；不得自动再执行一次。只写离线状态机测试，不建立真实实例、绝不执行 cleanup/drop。

## 负例/验收
先在 R2 基线 RED 证明，再 GREEN：无授权 execute exit2；错/缺 SHA、CI 未完成、dirty、审阅缺失、run UUID 重用、错误开关/规模拒绝；PG major/system identifier/marker/volume/network/owner/budget 任一失配拒绝；unknown ACK 无重试；CPU/RSS/FETCH 缺失保留 UNKNOWN；后续 CPU/SQL 和 wall 不混入 root；文件故障粘滞、证据不齐拒绝；只读 mock plan→offline proof→refusal→原 validator 回归，不产生 LIVE_VERIFIED。必须继续跑 E02/R1/R2 + diagnostic + W04A 离线相关测试，提交前 Ruff、diff-check、五份 frozen blob 一致。不要在有真实数据库连接风险的 Windows 本机直接运行全量 pytest；完整回归交 GitHub CI 隔离执行。

## 可修改文件
允许新增 scripts/biz_perf_p1_04_e03_*.py、tests/unit/test_biz_perf_p1_04_e03_*.py、docs/acceptance/BIZ_PERF_P1_04_E03_CLOSEOUT.md；确有证明必要时才小改 E02 wiring 公开注入端口，且不破坏旧测试。
**绝对冻结** scripts/business_recalc_measure.py、scripts/biz_perf_p1_04_diagnostic.py、scripts/perf03_lnx_w04a_offline_contract.py、scripts/biz_perf_03_b_once.py、scripts/business_sql_snapshot.py；不改 backend、frontend、migrations、依赖、CI、Docker、策略及治理基线。超出范围需单独报告，不自行执行。

## 交付和自动闭环
按 W00→设计→RED→实现→GREEN→离线回归→审计→单个提交→push master。回执必须包含最终 SHA、测试真实统计、五份 frozen blob SHA、CI run URL/attempt（未知写 PENDING）、未测事项、所有门禁原值。推送前检查 git status/diff/check；推送后核对 HEAD == origin/master。不得在回执里虚构已完成 CI。给 ChatGPT 清晰的结果供其通过 GitHub 复查。若发现不可解决的冻结冲突，停止冲突部分并说明，不要破坏原约束。

## W00 专项放行说明（由 ChatGPT 下发本任务的负责人补充）
本任务书 `docs/tasks/BIZ-PERF-P1-04-E03.md` 是当前用户明确要求直接下发的唯一新增未跟踪文件，属于 **本轮授权交付物**，不是既有用户改动。若 `git status --porcelain` 仅包含这一条 `?? docs/tasks/BIZ-PERF-P1-04-E03.md`，允许视作 W00 基线例外，开发结束时把它与本轮新增源码及测试一起提交。任何其他 dirty 文件仍必须停止。ChatGPT 刚才通过连接的 GitHub API 核验远端 master SHA 为 `22e92d291732d4f31a0e9ba3d787ff877c20a868`，同时通过这台 ssssssh 电脑**外层正常 PowerShell**执行 `git ls-remote origin refs/heads/master` 取回完全相同 SHA，退出码 0。Codex workspace-write 沙箱内 SSH 失败属于网络权限限制，不应被误判为代码版本漂移；本轮不要求 Codex 在受限沙箱中再次访问 GitHub。完成开发后若沙箱内无法 push，提交本地 commit 并输出 SHA 与阻断，由 ChatGPT 使用已获授权的外层终端执行安全 push、检查 CI 与独立审阅。其余数据库/Worker/资源执行门禁一律不变。
