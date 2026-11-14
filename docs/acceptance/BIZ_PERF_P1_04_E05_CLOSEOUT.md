# BIZ-PERF-P1-04 E05 纯离线只读审计回执

日期：2026-11-14（Asia/Shanghai）。状态：
`LOCAL_OFFLINE_VALIDATED / EXTERNAL_GIT_DELIVERY_PENDING / CI_PENDING / INDEPENDENT_REVIEW_PENDING`。
本回执是源码、测试与本会话自检结果，不代表 ChatGPT 已独立审阅，不关闭负责人验收。

## W00 与允许范围

起点为 master，HEAD / origin/master 同为
`cdae418f48ae2621bc8f5ae0ed6007473e227ca9`。
唯一未跟踪项为负责人下发的 `docs/tasks/BIZ-PERF-P1-04-E05.md`，按明确授权纳入交付。
执行 `git ls-remote origin refs/heads/master` 退出 1，SSH port 22 Permission denied。
实时 GitHub master 与 E04 CI 采用任务书提供的外层已核验基线；未通过其他网络入口重查，
没有把网络拒绝解释成代码漂移，没有请求 permit、提权或改变 Git 配置。

已按顺序阅读五份治理文件并核对相关 PRD、系统设计、PROJECT_RULES、README、父任务、
E03/E04 任务与回执，以及 E04 三模块/测试、E03/E02 的读取和冻结校验边界。
旧治理指针保留历史语境，本轮以用户最新 E05 白名单和纯离线限制为准。
通常四份产品文档维护与本任务“仅新增、不得修改治理/旧文档”的范围有差异，
依最新明确要求，仅新增本回执，不改旧文档、旧测试或既有实现。

交付仅六个新增路径：

- `scripts/biz_perf_p1_04_e05_audit.py`
- `scripts/biz_perf_p1_04_e05_scan.py`
- `tests/unit/test_biz_perf_p1_04_e05_audit.py`
- `tests/unit/test_biz_perf_p1_04_e05_checkpoint.py`
- `docs/acceptance/BIZ_PERF_P1_04_E05_CLOSEOUT.md`
- `docs/tasks/BIZ-PERF-P1-04-E05.md`（负责人原文保留）

## 方案与验收对应

| 项目 | 本次实现 | 权限和可信边界 |
| --- | --- | --- |
| E05-A 单一入口 | `audit_bundle(expected_sha, run_uuid, bundle, journal_path, raw_dir, checkpoint=None, elapsed_ms=0)`；显式外部 SHA/UUID、固定文件名、原始字节摘要；调用 E04 load_bundle、只读 Journal 构造/inspect、review_receipt 和冻结 Replay | 不接受 JSON 自述 SHA 作为唯一预期身份；无网络、环境授权、可注入执行器或写入端口 |
| 端到端关联 | packet/manifest/三个来源文件 → journal binding/hash chain → raw preflight/events；完整结果仍经原 Replay.summary 和 E04 review_receipt | 不调用会写产物的 validate_bundle；不创建 summary/integrity 或审阅文件；mock SUCCESS 不等于真实执行 |
| 回执 | 五类 audit_status、固定 error_code、SHA/UUID、原始摘要、检查点摘要/比较、journal_state、writer_lock、file_identity、未验证项及原 NOT_APPROVED 门禁 | 包括 CLI 解析失败的回执也保持完整拒绝字段；不输出路径、原 payload、SQL、异常原文或堆栈 |
| E05-B 事故分类 | PLANNED/RESERVED/UNKNOWN_ACK/MOCK_RETURNED/BLOCKED/MANUAL_REVIEW_REQUIRED；未知所有权、资源漂移、残留锁、预算过期和损坏分类 | 全部 next_action=HOLD_FOR_MANUAL_REVIEW；no_replay/no_retry/no_cleanup/no_release 恒 true；检查建议仅为固定代码 |
| 预算 | 显式调用者 elapsed_ms 只用于离线分类；RESERVED/UNKNOWN_ACK 的 900000ms root 边界及 1200000ms 总边界拒绝放行 | 没有 watchdog、资源读取、时钟认证、期限续期或预算批准；DRAFT_NOT_APPROVED 恒定 |
| E05-C 扫描 | 外层读取前后各一次 scan，每次 scan 再作两次有界观察；比较原始字节 SHA、文件 dev/inode/mode/nlink/size/mtime/ctime、目录身份/成员、祖先身份及路径摘要 | atime 不参与比较；不写原证据、不建目录。未知 inode 拒绝为 FILE_IDENTITY_UNKNOWN；读取期间 ABA 不能绝对检测 |
| 路径 | 拒绝 symlink/junction、非普通文件、hardlink、路径穿越、超限文件/目录成员；固定最多六条 journal 记录 | 祖先必须可信、稳定；不是对抗恶意文件系统或管理员的沙箱，不保证跨机器唯一性 |
| 外部检查点 | 独立传入普通对象或 CLI 读取最多 4096 bytes 的文件；严格 schema、时间标签、来源离线标签、自身 canonical digest、SHA/UUID、packet/manifest/marker、seq/chain、输出与扫描摘要 | `make_checkpoint` 只返回对象；无保存/更新/接受新状态入口。匹配仅 RELATIVE_MATCH_ONLY，信任恒 UNVERIFIED_EXTERNAL_CHECKPOINT |
| 检查点差异 | seq 减小为 CHECKPOINT_ROLLBACK；同 seq 换摘要、文件同字节换 inode、整个日志/输出目录置换等为 CHECKPOINT_MISMATCH | 相对差异产生 EVIDENCE_TAMPER_SUSPECTED；不证明恶意行为，也不证明检查点本身真实或未回滚 |
| E05-D 反向回归 | E05 负例与完整 mock；原 E04/E03/E02、diagnostic、W04A、fake DB-API guard 保留原测试执行 | 不修改旧断言、收集器、平台分支、冻结源码、依赖或 CI；不运行真实连接或本地全量 pytest |

正常回执仍显式 `OFFLINE_ONLY`。固定未验证项包括 CI/审批来源真实性、外部检查点信任、
跨机器唯一性、真实资源归属、Windows 目录项断电耐久性、真实执行结果、恶意管理员/文件系统
以及两次观察之间的 ABA。离线自洽不能推导事实可信、执行许可或性能结论。

复杂性有界：固定五个 packet 文件（各至多 64KiB）、六条 journal 记录及锁/marker
（各至多 4096 bytes）、preflight（64KiB）、events（8MiB）；日志沿用原 4096 事件上限。
目录迭代也受限：journal 根最多 128 个成员，其余固定目录最多八个成员。
超限拒绝，不递归读取未知 evidence 子树。回执只导出固定标签摘要和有限代码。
扫描/旧校验存在多次只读遍历，不是性能执行，也不提供线性化或存储耐久性证明。

## CLI 与检查点用法

```text
python -B -m scripts.biz_perf_p1_04_e05_audit audit --expected-implementation-sha EXPECTED_40_HEX_SHA --expected-run-uuid EXPECTED_RUN_UUID --bundle OFFLINE_PACKET_DIR --journal OFFLINE_JOURNAL_DIR --raw OFFLINE_RAW_DIR
python -B -m scripts.biz_perf_p1_04_e05_audit audit --expected-implementation-sha EXPECTED_40_HEX_SHA --expected-run-uuid EXPECTED_RUN_UUID --bundle OFFLINE_PACKET_DIR --journal OFFLINE_JOURNAL_DIR --raw OFFLINE_RAW_DIR --checkpoint EXTERNALLY_PRESERVED_CHECKPOINT_JSON --elapsed-ms 1200000
python -B -m scripts.biz_perf_p1_04_e05_audit execute --allow --force --permit=MOCK
python -B -m scripts.biz_perf_p1_04_e05_scan execute --permit=MOCK
```

audit 只向 stdout 输出有界脱敏 JSON；完整且自洽时退出 0，其余退出 2。
退出 0 也始终 HOLD_FOR_MANUAL_REVIEW，不授予动作。
两个模块的 execute 都固定输出 AUTHORIZATION_PENDING，退出 2。
没有 resume/cleanup/release 入口；环境中的 permit 字符串不能改变结果。

外部调用者可对回执 observation 调用
`make_checkpoint(observation, check_time="2026-11-14T00:00:00Z")` 得到普通对象，
保存行为和可信存储由调用者负责。当前目录生成的自述检查点、伪造签名或与当前内容一同
回滚的检查点均不能建立绝对 freshness；匹配不能解除占用或允许二次执行。

## RED → GREEN 与精确统计

1. 未实现模块时，真实入口存在性和 execute 拒绝探针为 **2 failed，退出 1**。
   原因是模块不存在，execute 子进程退出 1，不是已证明存在真实执行漏洞。
2. 两模块最小入口实现后，同一探针 **2 passed，退出 0**。
3. 首次扩展收集出现 **2 collection errors，退出 1**：新增测试误将旧 p fixture 函数
   用作模块常量。仅修正新增测试的模块引用，旧夹具/测试未改；随后 **121 passed**。
4. 补充 raw 摘要重新绑定后仍必须通过原 Replay、非对象检查点、raw 缺失/超限、
   root 期限和完整 CLI 拒绝回执等负例后，E05 共 **137 项**。

最终指定组合（本机 Windows / CPython 3.12.7 / pytest 7.4.4）：

| 模块 | passed |
| --- | ---: |
| E05 audit | 93 |
| E05 checkpoint | 44 |
| E04 packet / journal / review | 45 / 28 / 53 |
| E03 guard / collectors / evidence | 75 / 7 / 17 |
| E02/R1/R2 measure_wiring | 58 |
| 冻结 diagnostic | 66 |
| 冻结 W04A offline | 20 |
| PG identity guard（fake DB-API，无真实连接） | 11 |
| 合计（单次最终运行，不累计重复轮次） | **517** |

最终 **517 passed / 0 failed / 0 errors / 0 skipped，22.85s，退出 0**。
此前同组合一轮 517 passed / 23.16s；补齐 CLI 拒绝信封后重验得到上述最终结果。
JUnit 在系统临时目录，未将本机路径或测试产物纳入交付。

主要负例覆盖：未知 ACK、RESERVED 崩溃前缀、永久占用、损坏/有效残留 writer.lock、
序号断档/回退、短写/空文件/部分落盘/hash 断链、重复键、NaN/Inf/非法 UTF-8、
非法 state/elapsed、跨 SHA/UUID/packet/manifest/journal/raw、来源/所有权/资源身份漂移、
预算超限、缺失文件、超限文件、检查点自称 TRUSTED/额外 permit/畸形对象/循环对象、
同 seq 改 chain、同内容换 inode、marker/整个 journal/输出根置换、hardlink、
Windows junction/POSIX symlink 分支及读取期间内容/inode/mtime/父目录置换。

两个独立 Python 进程同时 CLI 扫描完整 mock，均退出 0，回执完全相同；
对比前后文件集合、每文件 inode/mtime/size/SHA256 均不变，没有创建新 evidence 文件。
正例另将 E04 create/reserve/run_mock/publish_review 端口替换成失败探针，读取仍通过。

最终安全组合命令（E05_TEMP 表示新建系统临时目录）：

```text
python -B -m pytest tests/unit/test_biz_perf_p1_04_e05_audit.py tests/unit/test_biz_perf_p1_04_e05_checkpoint.py tests/unit/test_biz_perf_p1_04_e04_packet.py tests/unit/test_biz_perf_p1_04_e04_journal.py tests/unit/test_biz_perf_p1_04_e04_review.py tests/unit/test_biz_perf_p1_04_e03_guard.py tests/unit/test_biz_perf_p1_04_e03_collectors.py tests/unit/test_biz_perf_p1_04_e03_evidence.py tests/unit/test_biz_perf_p1_04_measure_wiring.py tests/unit/test_biz_perf_p1_04_diagnostic.py tests/unit/test_perf03_lnx_w04a_offline_contract.py tests/unit/test_r1_integration_pg_guard.py -q --basetemp E05_TEMP --junitxml E05_TEMP-core.xml
python -m ruff check backend tests migrations scripts
git diff --check
```

Ruff 实际退出 1，`No module named ruff`：**ENV_BLOCKED**，未安装或升级依赖。
AST/行长/空白检查、源码调用端口审查与 Git 差异审计单独完成，不冒充 Ruff。
没有在本机执行完整 pytest、真实 PostgreSQL/Worker/Scheduler、迁移、Docker、云资源、
性能或生产操作；普通 Linux CI、POSIX 属性分支及完整工程验收仍待新精确 SHA。

## Frozen 五文件与范围审计

`git rev-parse HEAD:path` 和 `git hash-object path` 逐项一致，且工作区原字节恰好为
HEAD LF blob 的 CRLF checkout 投影，没有重写任何 frozen 文件。

| scripts/ 文件 | 完整 Git blob SHA |
| --- | --- |
| business_recalc_measure.py | 782e45ba53c8de8df0d12ffa84c219855316cfda |
| biz_perf_p1_04_diagnostic.py | 714f78017ec252791ac6a89f9fb0e0a984333c37 |
| perf03_lnx_w04a_offline_contract.py | 931fd4fec38551d9fac59791d2bde5ce0e6a1d48 |
| biz_perf_03_b_once.py | 2ea473491f590893ad575b90a0ba42f932e37129 |
| business_sql_snapshot.py | e7532b0a0242f1e3d3b047fdc03fca7ffc3ce7c6 |

任务书第五项原文 `e7532b0a0242f1e3d3b047fdc03fca7ffc3ce7c` 仅 **39 位**，
少写末尾 `6`，不能按其文字声称是匹配的 40 hex SHA。
实际 HEAD、工作区 Git hash、E03/E04 回执均一致为上表完整 40 位；本轮保留任务书原文，
未修改冻结目标或采用新的源码值。该文字差异供 ChatGPT 独立审阅核对。

`git diff --exit-code` 及 `git diff --check` 退出 0，已跟踪文件无变化。
未跟踪新增文件另外进行逐份差异、AST、行尾空白及允许路径检查；普通 git diff 本身
不会展示这些新增文件。没有交付缓存、覆盖率、JUnit、临时夹具、凭据或数据库文件。
E04/E03/E02、业务、依赖、迁移、工作流、历史归档和治理原件保持原字节。

## 交接与剩余风险

本环境明确 `.git` 只读，GitHub SSH 亦已返回权限拒绝；按用户指令不越权尝试写入，
不使用替代 index/refs、修改权限、代理网络或强推。
因此本会话没有创建 commit、没有 push、没有 E05 新精确 SHA 的 CI run。
六份文件保留在工作区，交由 ChatGPT 使用已获授权的外层 PowerShell 独立复测/审查后，
单次常规提交并推送 master，核对新 HEAD/远端 SHA、CI attempt/Jobs，CI 完成后独立审阅。
不将 E04 CI 或本会话自检冒充 E05 CI/独立验收，不为回填文档自身 SHA 再提交。

尚未证明：来源认证、检查点独立可信存储、绝对防回滚、跨机器唯一性、恶意管理员/文件系统
抵抗、线性化快照、两次观测间 ABA、Windows/POSIX 断电耐久性、真实资源归属、真实执行。
这些在回执中保持 UNKNOWN/未验证，任何人工阅读或离线自洽也不解除一次性占用。

```text
TASK=E05
BASELINE_SHA=cdae418f48ae2621bc8f5ae0ed6007473e227ca9
FINAL_SHA=NOT_CREATED_GIT_METADATA_READ_ONLY
PUSH=NOT_ATTEMPTED_EXTERNAL_POWERSHELL_REQUIRED
PUSH_BRANCH=master_PENDING_EXTERNAL_DELIVERY
MAIN_CI_RUN=PENDING
OFFLINE_TESTS=517_PASSED_0_FAILED_0_ERRORS_0_SKIPPED
RUFF=ENV_BLOCKED_NO_MODULE
FROZEN_5_SHA=5_OF_5_MATCH_HEAD_AND_CHECKOUT_PROJECTION
REAL_PG17=NOT_RUN
REAL_WORKER=NOT_RUN
REAL_SCHEDULER=NOT_RUN
REAL_RESOURCES_CREATED=0
REAL_RESOURCES_DELETED=0
ROOT_ATTEMPTS=0
HOTSPOT=NONE_PROVEN
B_GATE=NOT_APPROVED
TARGETED_PG17_GATE=NOT_APPROVED
AUTHORIZATION=AUTHORIZATION_PENDING
BUDGET=DRAFT_NOT_APPROVED
NEXT=CHATGPT_INDEPENDENT_REVIEW
```
