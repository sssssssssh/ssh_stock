# BIZ-PERF-P1-04-E05 详细开发任务书：离线独立审计、故障归因与人工处置证据包

- 发起日期：2026-11-14；负责人：用户；执行：远程 ssssssh 上 Codex 桌面软件 GP 项目的可见持久会话；独立验收：ChatGPT。
- 唯一代码基线：GitHub master / 本机 HEAD / origin/master = `cdae418f48ae2621bc8f5ae0ed6007473e227ca9`；E04 主 CI #43562907139，attempt 1，completed/success；A4-1/A4-2/Publication V1.3 均同 SHA 成功。
- 当前基线：E04 提供 `admission_packet` / `evidence_manifest`、`OfflineLeaseJournal`、mock-only `review_receipt`；380 项指定离线本机复测通过，Linux 主 CI 7043 passed、1 skipped、Ruff/全工作流 PASS。以上仅证明**离线原型**，不是生产执行许可。
- E05 目标：针对 E04 回执列出的未验证风险，建立**无执行权限的只读独立审计器**，能够对异常终止/未知 ACK/日志损坏/证据缺失/身份漂移/证据替换输出可复核的“人工处置证据包”，阻断任何自动重试或自动清理，并明确哪些结论在缺少外部可信事实时仍为 UNKNOWN。

## 0. 安全红线——优先于所有开发目标

**绝不**连接真实 PostgreSQL 17、Worker、Scheduler、Docker、云资源、GitHub API（Codex 代码运行期间）、生产服务、真实数据，也不建/删库、执行迁移或性能实验；不要添加 live adaptor、cleanup/drop、resume/retry、真实 lease/资源申请、生产 token/permit、自动化人审批准功能。不得通过 CLI、环境变量、mock 签名、CI 状态、自称 review=APPROVED 来改变权限。所有本轮新模块的 `execute` 指令都必须固定输出 `AUTHORIZATION_PENDING` 并 exit 2，即使附带 `--allow`、`--force`、`--permit` 也不能执行动作。保持 `ROOT_ATTEMPTS=0`、`HOTSPOT=NONE_PROVEN`、`B_GATE=NOT_APPROVED`、`TARGETED_PG17_GATE=NOT_APPROVED`、`AUTHORIZATION=AUTHORIZATION_PENDING`、`BUDGET=DRAFT_NOT_APPROVED`。

以下五份历史冻结源码**绝对不改**，也不得通过复制改名或间接覆写绕过：
1. `scripts/business_recalc_measure.py` = `782e45ba53c8de8df0d12ffa84c219855316cfda`
2. `scripts/biz_perf_p1_04_diagnostic.py` = `714f78017ec252791ac6a89f9fb0e0a984333c37`
3. `scripts/perf03_lnx_w04a_offline_contract.py` = `931fd4fec38551d9fac59791d2bde5ce0e6a1d48`
4. `scripts/biz_perf_03_b_once.py` = `2ea473491f590893ad575b90a0ba42f932e37129`
5. `scripts/business_sql_snapshot.py` = `e7532b0a0242f1e3d3b047fdc03fca7ffc3ce7c`

不得修改 backend/frontend、真实业务公式、数据源/策略/候选/发布、迁移、requirements/锁文件、Docker、CI 工作流、GitHub Environment 和历史治理/归档。优先纯新增 E05 独立模块，不要改 E04/E03；若确有阻断性缺陷，先留只读诊断/测试，不扩大任务范围；不得擅自“修复”旧测试并改变基线语义。

## 1. W00 基线复核与文档阅读

先检查 master/HEAD/origin/master、`git status --short`、最新 SHA，任何非本轮授权 dirty 项立即停止；唯一例外为 ChatGPT 新写的 `?? docs/tasks/BIZ-PERF-P1-04-E05.md`，应纳入最终 1 次提交。若 Codex 沙箱 SSH 被拒，则使用负责人已通过连接器和外层终端核实的 SHA 作为**外层已核验基线**，不以网络错误宣称漂移。不能通过 sandbox 时不修改 Git 权限、替代 index/refs、代理网络、绕开审批；提交推送交由 ChatGPT 的外层 PowerShell。

按 `AGENTS.md` 顺序阅读 `PROJECT_CHARTER.md`、`PROJECT_STATUS.md`、`PROJECT_ROADMAP.md`、`DECISION_LOG.md`、`docs/tasks/README.md`、权威 PRD/系统设计、`PROJECT_RULES.md`、父任务 `docs/tasks/BIZ-PERF-P1-04.md`、E03/E04 任务及 closeout，并直接查看 E04 三模块与测试、E03/E02 验证器。不修改旧治理文件；旧的历史状态不能被强行解释为已批准真实实验。

## 2. E05-A 独立只读审计入口（READ_ONLY_AUDIT）

新增 `scripts/biz_perf_p1_04_e05_*.py`，优先实现 `audit_bundle()` 或等效单一只读入口：参数为外部调用者明确给定的预期实施 SHA、run UUID、E04 packet bundle 路径、journal 路径、raw evidence 路径及可选先前独立保存的“可信检查点”对象。不接受仓库内 JSON 自述的 expected_sha 作为唯一信任根；不从网络/环境变量自动取得授权。

仅调用 E04 `load_bundle`、`OfflineLeaseJournal.inspect`、`review_receipt` 或旧冻结 Replay 的**读取与校验逻辑**；不得调用 `OfflineLeaseJournal.create/reserve`、`_Lease.transition`、`run_mock`、`publish_review` 或任何会写文件/触发执行的端口。对预期 SHA/run、packet/manifest 摘要、journal 事件链、mock output 绑定、原始 `preflight.json` / `events.jsonl`、源 E03/E04 的拒绝门禁做端到端证据关联。

输出显式分开的：
- `audit_status`：`OFFLINE_EVIDENCE_CONSISTENT`、`OFFLINE_EVIDENCE_INCOMPLETE`、`MANUAL_REVIEW_REQUIRED`、`EVIDENCE_TAMPER_SUSPECTED` 或 `AUDIT_REFUSED`（可按实现合理收窄状态集）。
- `next_action`：**一律不可执行**；`HOLD_FOR_MANUAL_REVIEW` 或 `NO_AUTO_ACTION`；绝不能是 PROCEED/RETRY/DELETE/CLEANUP/EXECUTE/RELEASE。
- `unverified`：至少列出 CI/审批来源真实性、外部检查点信任、跨机器唯一性、真实资源归属、Windows 目录项断电耐久性、真实执行结果；未知不得推定成功。
- `error_code`：固定有限脱敏枚举，绝不回显路径、敏感 payload、SQL、凭据、堆栈。
- 精确 SHA、run UUID、原始证据 digest、检查点 digest、journal 状态与锁异常、固定位的全部 NOT_APPROVED 门禁；任何正例仍显式 `OFFLINE_ONLY`。

## 3. E05-B 未知 ACK/事故分级与无动作处置清单

建立显式、确定性的离线 incident taxonomy 和 pure classification：
- `PLANNED`、`RESERVED`、`UNKNOWN_ACK`、`MOCK_RETURNED`、`BLOCKED`、`MANUAL_REVIEW_REQUIRED`；
- 中途崩溃、残留 `writer.lock`、非连续序号、短写、部分落盘、hash 链中断、重复 JSON 键、NaN/Inf、非法 state、跨 SHA/UUID digest、文件同内容被替换 inode、journal 被交换、raw 被篡改、manifest 缺失、未知资源归属、过期预算；
- 统一 `no_replay` / `no_retry` / `no_cleanup` / `no_release` 的证据状态，不因 ACK 过期、时间已超限、模拟成功或人工阅读过日志而解除占用。
- 按情况给出**人工检查建议文本的固定代码**（不是可执行命令或步骤），例如 `CHECK_OWNER_OUT_OF_BAND`、`CHECK_ORIGINAL_CI_AT_SOURCE`、`PRESERVE_EVIDENCE`；不调用外部系统，不签发或复用任何 permit。

区分“一个离线 bundle 内所有证据一致”和“事实可信”：E04 verifier 仅 mock，不能从自洽推导真实 provenance。审计不具备防管理员/恶意文件系统、跨机器唯一性、独立认证事实的能力，必须在回执里写清楚。

## 4. E05-C 防回滚和竞态的只读检查点协议

为**外部可选导入的检查点**定义确定性的 bounded schema（调用者明确传入，脱离当前 evidence bundle 的当前内容）；至少有 implementation SHA、run_uuid、manifest/packet digest、journal marker digest、最近 seq/chain head、输出证据 digest、check_time/scan_source 离线标签和自身 canonical digest。检查点为普通离线文件/对象，**没有外部签名或可信存储时只能证明与该检查点的相对差异，不能证明绝对防回滚**。

扫描采用 read-before/read-after/原始字节 hash/inode（可用平台内）检查，检测更换内容、inode、mtime/size 漂移；对于无法检查 inode/platform 差异返回 UNKNOWN/FALSE_CONFIDENCE，不编造“安全”。同样目录不同字节、同一 uuid 的旧日志重新出现、以前 seq 变小、同 seq hash 变化、log 正常但 raw 替换、证据目录路径 symlink/junction、hardlink、父目录被换、Windows/POSIX 文件身份差异，必须 fail closed。所有比较为**只读，不创建新目录、不写入账本/原证据**。严禁实现 checkpoint 更新为“接受新状态从而允许二次执行”的工作流。

可实现 `scan()/compare_checkpoint()/render_incident_packet()` 纯函数/安全读取端口。离线报告可以返回 dict 或由调用者自行保存；若提供 CLI，只允许输出有界脱敏 JSON 到 stdout，不写磁盘，不接受凭据/生产 URL。

## 5. E05-D 负例矩阵 + 与 E04 的反向回归

新增 `tests/unit/test_biz_perf_p1_04_e05_*.py`，按 RED→GREEN：先证明确实缺 E05 独立审计入口，再实现。至少覆盖下列类别：
1. 完整 E04 **纯 mock** 证据的只读校验（先完成已知固定 mock fixture，不访问真实系统）。
2. UNKNOWN_ACK、RESERVED 后崩溃、损坏 writer.lock、未知所有权、资源身份漂移、预算超限，全部 `HOLD_FOR_MANUAL_REVIEW`，无自动重试/清理。
3. packet↔manifest↔journal↔raw 四类错绑及缺失证据；重复键/NaN/无限值/非法 UTF-8/超限文件。
4. 独立检查点前后不一致（seq 回退、同 seq 摘要变、journal/root 路径置换、检查点不可信），不应自行升级证明等级。
5. 两个独立读取进程并发扫描，不产生任何新写文件或改动已有 evidence inode、mtime、size/sha；必要的对照夹具全部放新建系统临时目录，不触及工作仓库真实 DB/Worker 资源。
6. 公开 CLI `execute`、`--allow`、`--permit`、`--force` 固定 `AUTHORIZATION_PENDING`/exit 2；没有 `resume`、`cleanup`、`release` 任何真实入口。
7. 五份 frozen 不改；E04/E03/E02 原测试仍全绿；POSIX 专属文件属性仅在 Linux 可运行时检查，不以 Windows 代理断言冒充 Linux 完整结论。

## 6. 允许文件 / 禁止扩大范围

允许**新增**：
- `scripts/biz_perf_p1_04_e05_*.py`（E05 独立审计、检查点、incident classifier 等，命名清晰可控制在 2-4 个模块）；
- `tests/unit/test_biz_perf_p1_04_e05_*.py`；
- `docs/acceptance/BIZ_PERF_P1_04_E05_CLOSEOUT.md`；
- 本 `docs/tasks/BIZ-PERF-P1-04-E05.md`。

严格不改任何 E04/E03/E02/冻结/业务/治理/CI 源码；如发现真正阻断，先给出最小复现和独立修复提案，**不擅自跨任务改动**。不能只交文档；必须有可执行的离线源码和测试。优先 Python 标准库，不安装或升级依赖。

## 7. 测试与质量关卡

- 必须先做 E05 RED 探针，记录真实失败，再实现 GREEN；Windows 本地安全套件仅限 `tests/unit/test_biz_perf_p1_04_e05_*.py` + E04 packet/journal/review + E03 guard/collectors/evidence + E02 wiring + frozen diagnostic + W04A offline + PG identity fake-db guard；不跑触碰真实连接的全量 pytest。
- 检查 `python -m ruff check backend tests migrations scripts`，若 Windows 缺 `ruff` 则记 `ENV_BLOCKED`，**不修改依赖、不伪称通过**；最终以 GitHub 精确 SHA Linux CI 的 Ruff 为准。
- `git diff --check`、新文件行尾空白审计/AST 语法检查、新旧基线 hash 对照（含 Windows CRLF 与 git LF 的等价投影）；五 frozen blob 必须逐项与本书 40 hex 对齐，所有测试数量按实际运行统计。
- 回执须记录实际方案、复杂性边界、失败矩阵、RED/GREEN、准确 tests、可验证范围、不确定状态、无真实执行声明、提交/推送/CI 是否真实完成。

## 8. Git 交接 / GP 可见性 / ChatGPT 独立审阅

本任务由远程 **Codex app-server 的 `thread/start(projectId=GP)` 新建持久会话**执行，名称 `BIZ-PERF-P1-04 E05 只读独立审计开发`，你必须在该 GP 会话中展示阶段进展、源码差异、测试与收尾结论；不得用独立 `codex exec` 替代。开发期间不手动更改 GitHub 环境或创建真实资源。

代码通过离线测试和范围审计后，若普通授权环境允许，执行单次常规 commit + push `master`，不 force、不重置、不改历史、不使用备用 index。若 Codex 沙箱不允许写 `.git` 或 SSH，**保留全部改动**，将交付路径、测试结果、阻断原因交给 ChatGPT；ChatGPT 会使用已授权的外层 PowerShell 先独立复测/审查再安全提交并推送。推送后必须核对新 exact SHA / CI run attempt / Jobs，CI 完成后由 ChatGPT 独立审阅。禁止把 E04 的已成功 CI 冒充 E05 的结果。

最后在 GP 会话里用固定字段结束：
`TASK=E05`、`FINAL_SHA`、`PUSH`、`MAIN_CI_RUN`、`OFFLINE_TESTS`、`RUFF`、`FROZEN_5_SHA`、`REAL_PG17=NOT_RUN`、`REAL_WORKER=NOT_RUN`、`ROOT_ATTEMPTS=0`、`B_GATE=NOT_APPROVED`、`TARGETED_PG17_GATE=NOT_APPROVED`、`NEXT=CHATGPT_INDEPENDENT_REVIEW`。

任何离线“审计成功”都**不等于**资源许可、执行许可、性能结论或实验阶段结束；正式准入仍需未来独立审批。
