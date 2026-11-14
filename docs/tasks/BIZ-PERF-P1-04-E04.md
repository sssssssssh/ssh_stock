# BIZ-PERF-P1-04-E04 任务书：持久化准入凭证与一次性执行防护（纯离线）

- 日期：2026-11-14；负责人：用户；执行者：Codex GP 项目。
- 唯一基线：master HEAD/origin/master/GitHub master = `52a9abdee7317338464f04834690f45432dd59a0`；E03 主 CI run `43545268807` attempt 1 SUCCESS。
- 目标：补全 E03 明确未覆盖的“跨进程防重复、可信证据与实例归属判定、未知 ACK 和失联后的安全恢复决策”，**仅交付可审阅的离线协议、原型、测试与文档**；不把功能开发当成真实执行许可。

## 0. 硬性禁止事项（最高优先级）

绝不连接真实 PostgreSQL 17、Worker/Scheduler、Docker、云平台或生产网络资源；不得拉取真实数据、执行建库/删库/迁移/清理、运行真实性能样本，不对已有资源发控制命令，不创建可用的生产执行许可。**所有 execute 入口恒为 AUTHORIZATION_PENDING / exit 2；不提供从 CLI 参数、环境、fixture、数字签名字符串、CI 通过、模拟审阅通过到真实执行的提权路径。** 保持 `ROOT_ATTEMPTS=0`、`HOTSPOT=NONE_PROVEN`、`B_GATE=NOT_APPROVED`、`TARGETED_PG17_GATE=NOT_APPROVED`、`BUDGET=DRAFT_NOT_APPROVED`。

冻结文件绝对禁止改动：
- `scripts/business_recalc_measure.py`
- `scripts/biz_perf_p1_04_diagnostic.py`
- `scripts/perf03_lnx_w04a_offline_contract.py`
- `scripts/biz_perf_03_b_once.py`
- `scripts/business_sql_snapshot.py`

不修改 backend、frontend、迁移、依赖、Docker、GitHub Actions、策略、旧归档/治理记录；不更改 PIT、候选、原子发布规则，不以修本机环境为由修改旧测试。既有 E02、E03 语义必须完全向后兼容。

## 1. W00 严格基线

先检查 git status、HEAD、origin/master、真实远端 GitHub master 与新 SHA CI；必须确认基线和工作区状态。允许唯一未跟踪项为本轮 ChatGPT 新建的 `docs/tasks/BIZ-PERF-P1-04-E04.md`，并把它纳入最终提交。不要误判为用户旧改动；任何其他未预期 dirty 立即停止。Codex 沙箱内 GitHub SSH 或 .git/index.lock 可能不可写：**不越权、不强推、不改变 Git 配置**；本轮可在离线测试结束后把无法 git add/commit/push 的实情交给 ChatGPT 通过已授权外层终端处理。

依照 AGENTS.md 顺序阅读 `PROJECT_CHARTER.md`、`PROJECT_STATUS.md`、`PROJECT_ROADMAP.md`、`DECISION_LOG.md`、`docs/tasks/README.md`，随后相关 PRD/系统设计、PROJECT_RULES.md、`docs/tasks/BIZ-PERF-P1-04.md`、E03 任务与 closeout、E03 源码和测试。较旧治理进度不同步时写明历史指针，不得擅自改写原始记录或解冻其他任务。

## 2. E04-A 可信证据输入与离线验证

新增 `scripts/biz_perf_p1_04_e04_*.py` 及 `tests/unit/test_biz_perf_p1_04_e04_*.py`。定义精确 SHA 和单一 run UUID 绑定的规范化 `admission_packet` 与 `evidence_manifest`，至少覆盖：实施 SHA、reviewer/implementer 区分、CI 成功证据来源与 run attempt、review receipt 的来源和 scope、输入/策略/业务 64 hex、五 OFF 开关、8 股、2025-01、逐表 seed 预算摘要、资源身份 marker/PG17 system identifier/卷/owner/lease、预算草案、所有项的 evidence_kind 和 canonical digest。

只验证**离线声明、摘要及注入只读验证器返回的合同**，严禁把一份 JSON 内自述 CI=SUCCESS、REVIEW=APPROVED 解释为“已信任”或“可执行”。任何伪造、自循环引用、字段重复/未知、路径不可信、跨 SHA、跨 run UUID、哈希不符、缺证据、观察身份漂移均以固定脱敏码 fail-closed。真实远端 GitHub 和审批系统的认证验证属于未来独立阶段，当前用明确的 `OFFLINE_DECLARATIONS_ONLY`/ `OFFLINE_ATTESTED_MOCK_ONLY` 等状态。

## 3. E04-B 跨进程一次性占用和故障状态

E03 的 `OfflineJournal` 只是内存集合。设计一个**仅操作新建离线测试目录**的持久化 `OfflineLeaseJournal`：唯一 UUID、单次创建、独占文件（或等效标准库原语）、不覆盖、追加/原子落盘、固定小体积记录、明确权限与目录可信边界。多进程/并发双抢同 UUID 只允许一个成功；其余明确拒绝，绝不自动启动第二根。模拟 create/claim ACK unknown、异常退出、文件短写/fsync、记录损坏、重入、目录 symlink/junction、身份不符、lease 过期但 ACK unknown 的情形：**仍保持占用/人工裁决，不自动释放或重试**。POSIX 父目录 fsync 和 Windows 目录项耐久性差异必须单独写明，禁止把 Windows 单测宣称为断电证明。

绝不接真实 worker。仅内存/文件系统测试替身，默认拒绝任何 real Executor。每个事件须含固定状态：PLANNED、RESERVED、UNKNOWN_ACK、MOCK_RETURNED、BLOCKED、MANUAL_REVIEW_REQUIRED 等，明确合法迁移、互斥、故障粘滞；记录中不能包含凭据、异常堆栈、连接串或真实业务数据。

## 4. E04-C 资源身份与清理前证明

定义纯函数及可注入读取端口，比较 EXPECTED/OBSERVED_OFFLINE 的 PG17 major、Linux x86_64、system identifier、UUID marker、卷/网络/owner digest、数据库归属、独占 lease 和预算；不能产生 OBSERVED_LIVE 或 LIVE_VERIFIED。unknown ACK/identity drift/cleanup ownership unknown 统一返回 `CLEANUP_BLOCKED` 或 `MANUAL_REVIEW_REQUIRED`，不得调用实际 cleanup/drop。草案预算 root=15min + cleanup=5min，Worker=3GiB、PG=4GiB、volume=10GiB、raw evidence=10MiB，CPU 仍是待批字段；纯函数边界、时间超限、cleanup window、整数溢出、缺测与失败均增加负例。

## 5. E04-D 证据闭环和验收

复用 E03 `BoundedEvidenceSink`/ `MockLifecycle`、E02 `FileJsonlSink`、原冻结 validator，不得重写兼容层。产出可独立读取的离线审阅 receipt：精确 SHA、manifest 摘要、单次 UUID、state transitions、错误静态码、文件 digest、未验证项、root attempts 0 和所有未批准门禁。证据缺失时不得产生 completed/integrity 成功声明；未知 ACK 不生成 root success/可执行许可。为 schema、非有限数、重复键、损坏尾行、路径替换、平台差异、二次领取、跨进程双抢/进程崩溃后阻断提供负例；不能真的使用真实数据库或 Worker 证明。

## 6. 允许范围 / 交付

允许新增 `scripts/biz_perf_p1_04_e04_*.py`、`tests/unit/test_biz_perf_p1_04_e04_*.py`、`docs/acceptance/BIZ_PERF_P1_04_E04_CLOSEOUT.md`，以及本任务书。确有必要可最小修改 E03 纯离线模块及其专属测试；**不得**修改 R2/E02 或 5 份冻结文件。必须提交具体源码/测试，不能只写方案文档。优先标准库，不增依赖，不运行临时真实服务。

从 RED 失败探针 → 最小实现 → GREEN → E04 新测 + E03 + E02/R1/R2 + diagnostic + W04A + 原 PG identity 离线套件；本机仅运行安全单测，不运行可能碰真实 DATABASE_URL 的全量 pytest。Ruff 若本机缺失，记录 ENV_BLOCKED，不升级依赖，后续以精确 SHA Linux GitHub CI 校验。执行 `git diff --check` 与 5 frozen blobs SHA 对照。非本阶段 POSIX 平台错误不得篡改/跳过旧断言。

交付：离线闭环回执（文件/测例/RED→GREEN/不覆盖资源/Windows-POSIX 差异/失败边界/遗留风险），在可用权限下单次 commit + 普通 push master；若 git 受限保留原样并交接给 ChatGPT 外层终端。推送后由 ChatGPT 独立审阅精确 SHA、主 CI、资源授权安全；不在任务书内凭空填写 CI SUCCESS。E04 完成仍无真实性能资格。

## 7. Codex GP 可见性和完成信号

本任务由 Codex app-server `thread/start` **明确 projectId=GP** 创建持久会话，名称 `BIZ-PERF-P1-04 E04 持久准入开发`，请在该会话内展示计划、RED/GREEN、进度、最终回执。处理完成后在会话最后输出：FINAL_SHA / PUSH / CI_RUN / TEST_COUNTS / FROZEN_BLOBS / ROOT_ATTEMPTS / B_GATE / TARGETED_PG17_GATE / NEXT=CHATGPT_REVIEW。审阅由 ChatGPT 在远端源码和 GitHub 独立完成；不可自称独立审阅。
