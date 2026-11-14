# BIZ-PERF-P1-04 E04 纯离线开发回执

日期：2026-11-14（Asia/Shanghai）。状态：
`LOCAL_OFFLINE_VALIDATED / EXTERNAL_GIT_DELIVERY_PENDING / CI_PENDING / INDEPENDENT_REVIEW_PENDING`。
这是离线协议、文件原型和测试交付，不是生产准入凭证或性能资格；不自行关闭负责人验收。

## W00、授权和范围

本会话开始时 `git status --short --branch` 为 master...origin/master，唯一未跟踪项为
`docs/tasks/BIZ-PERF-P1-04-E04.md`。按负责人及任务书明确例外将其纳入本次交付。
HEAD / origin/master 均为 `52a9abdee7317338464f04834690f45432dd59a0`。
执行 `git ls-remote origin refs/heads/master` 退出 1，SSH port 22 Permission denied；
没有绕过沙箱、改 Git 配置或发起替代网络访问。
GitHub master 同 SHA、E03 主 CI `43545268807` / attempt 1 / SUCCESS 是任务书提供的
负责人核验信息，本会话没有独立确认其远端实时状态，更没有将其作为新 E04 的 CI 结果。

已按顺序阅读 PROJECT_CHARTER、PROJECT_STATUS、PROJECT_ROADMAP、DECISION_LOG、
docs/tasks/README；随后核对相关 PRD、系统设计、PROJECT_RULES、README、父任务、
E03 任务及 closeout、E03 源码/专属测试、E02 wiring、冻结 validator 和 fake PG guard。
旧治理指针保留其历史语境，本轮唯一范围以负责人最新 E04 指令为准。
任务书明确禁止修改旧归档/治理记录及四份权威文档，本次没有同步改写它们。

新增三个 E04 源码模块、三个专属测试文件、本回执，连同任务书共八个交付路径。
既有已跟踪文件修改数为 0，包括 E03、E02/R1/R2、五份 frozen 文件、旧测试、业务代码、
依赖、CI、Docker、策略及治理记录。没有需要解冻的实现冲突。

## 协议与验收对应

| 范围 | 实现和拒绝证据 | 信任边界 |
| --- | --- | --- |
| E04-A admission_packet / evidence_manifest | `biz_perf_p1_04_e04_packet.py`；固定五文件、精确键集、严格 JSON、64KiB/文件、精确实施 SHA/外部预期 run UUID、规范 SHA256；CI 来源/run ID/attempt、review 来源/scope/角色、资源观察均单独绑定 subject | 仅离线声明；自述 SUCCESS/APPROVED、签名字符串、CI 或模拟审阅不能启用执行 |
| 无自循环证据图 | subject 是去掉下游 CI/review receipt hash 的完整 E03 plan 摘要；evidence → manifest → packet 逐级绑定；manifest 只允许 ci.json/review.json/resources.json | 禁止 packet/manifest 自引用、路径引用、重复来源 UUID、跨 SHA/run、哈希失配或缺项；原 E03 validator 继续校验业务/输入/策略、五 OFF 开关、8 股/2025-01、逐表 seed、资源和预算草案 |
| 注入验证器 | 默认 RefusedVerifier；仅接收精确 packet/manifest/SHA/run 绑定、OBSERVED_OFFLINE 的 mock 返回合同；传入独立副本并在返回后重新读取全部文件 | 状态只能为 OFFLINE_DECLARATIONS_ONLY / OFFLINE_ATTESTED_MOCK_ONLY；没有远端 CI/审批认证实现，也不信任 JSON 内自称的真实性 |
| 路径与替换 | 固定文件名、原有 no-follow/普通文件/单 hardlink/祖先检查；验证前后比较目录/文件 inode 和原始字节；测试同字节替换、改字节替换、hardlink、目录 symlink/junction | 祖先目录必须由调用者信任并保持稳定；不是对抗恶意文件系统管理员、挂载替换或任意 Python 注入的沙箱 |
| E04-B 持久占用 | `biz_perf_p1_04_e04_journal.py`；create 只接受新建目录；UUID 子目录 mkdir 是跨进程排他占用；固定小记录、O_EXCL、追加序号文件、hash chain、write/flush/fsync；永不删除 UUID 目录 | 同一可信账本中双抢只允许一个；不是跨机器/任意新目录的全局唯一性或生产 lease |
| 合法迁移 | PLANNED → RESERVED → UNKNOWN_ACK → MOCK_RETURNED，或 BLOCKED / MANUAL_REVIEW_REQUIRED；终态不能续跑；调用前持久化未知 ACK；MOCK_RETURNED 绑定 raw 文件摘要 | 只有当前进程内的 handle 能追加；重开账本只有 inspect/reserve，没有 resume/release；PID 变化、非法迁移和写入失败使 handle 粘滞拒绝 |
| 崩溃与未知 ACK | 两个真实本地 Python 进程争抢；首次事件前崩溃、未知 ACK 后进程退出、短写、文件/目录 fsync 故障、返回记录落盘而锁未确认移除、尾行损坏/重复键/非有限数/身份与 seq 损坏 | 所有失败保留占用；lease 过期也不释放，不自动重试或启动第二根。未知 ACK / RESERVED 前缀与失败锁一律人工裁决 |
| E04-C 资源与预算 | `biz_perf_p1_04_e04_review.py` 的纯函数及默认拒绝 ResourceReader；复用 E03 资源归属校验，覆盖 PG17、Linux x86_64、physical ID、marker、卷/网络/owner、库归属、lease；usage 必须是有界整数 | 只比较 EXPECTED / OBSERVED_OFFLINE；未知 ACK → MANUAL_REVIEW_REQUIRED；归属未知、身份漂移、预算失败 → CLEANUP_BLOCKED；没有 cleanup/drop 方法或真实控制调用 |
| 固定预算草案 | root <900000ms、cleanup <1200000ms；3GiB Worker、4GiB PG、10GiB volume、10MiB evidence；CPU 1..64000 milli-CPU 为待批字段 | 边界、超限、缺测、bool/负值/巨大整数/NaN/Infinity 均拒绝；CPU 配额与累计 CPU 时间不混用；DRAFT_NOT_APPROVED 始终保留，无实际 watchdog/资源强制器 |
| E04-D mock 与证据 | 精确 OfflineMockExecutor 类型才可注入 E03 MockLifecycle；默认或任意 real executor 在调用前拒绝；原 BoundedEvidenceSink → FileJsonlSink → 冻结 Replay/validate_bundle | 仅内存、假时钟、本地新文件；mock root SUCCESS 与 cleanup COMPLETE 是夹具事件，实际 ROOT_ATTEMPTS=0；没有真实 Worker/清理调用 |
| 独立审阅 receipt | review_receipt / publish_review / read_review；读取原事件、调用原 Replay.summary、核对持久状态与 raw 摘要、原子无覆盖发布固定 review_receipt.json；新读者重新复核所有字段 | 完整时只报 OFFLINE_EVIDENCE_REVIEWED_ONLY；缺证据/坏尾行/未知 ACK/漂移为 MANUAL_REVIEW_REQUIRED；不生成 completed/integrity 成功声明，不产生 permit |

每个新模块被作为 CLI 调用 execute 时都固定 `AUTHORIZATION_PENDING / exit 2`，
包括额外 allow/permit/CI 参数。E03 与原 diagnostic 的拒绝合同和测试原样保留。
唯一读取命令为：

```text
python -B -m scripts.biz_perf_p1_04_e04_packet validate-offline --input-dir OFFLINE_BUNDLE_DIR --expected-implementation-sha EXPECTED_40_HEX_SHA --expected-run-uuid EXPECTED_RUN_UUID
python -B -m scripts.biz_perf_p1_04_e04_packet execute
python -B -m scripts.biz_perf_p1_04_e04_journal execute
python -B -m scripts.biz_perf_p1_04_e04_review execute
```

输入目录固定为 admission_packet.json、evidence_manifest.json、ci.json、review.json、resources.json。
每个封装均有 canonical_sha256：对去掉该字段的对象按原 d.encode（ASCII、sort_keys、紧凑分隔、
末尾 LF、禁止非有限数）计算 SHA256；manifest 同时校验每个证据文件原始 bytes/SHA256。
测试夹具展示完整构造顺序；它们不提供真实来源认证。读取命令不创建账本、执行根任务或写入文件。

## RED → GREEN 与最终验证

基线尚无 E04 模块时执行新增三项探针：**3 failed，退出 1**。失败分别为 packet 模块不存在、
execute 子进程退出 1 而非固定拒绝 2、journal 模块不存在。这证明缺少合同入口，
不将“模块缺失”夸称为已有生产执行漏洞。最小入口实现后同三项 **3 passed，退出 0**。

扩展 packet/journal 首轮为 **64 passed / 2 setup errors，退出 1**：
长 bytes 参数的默认测试 ID 导致 Windows pytest 临时路径问题；默认 pytest 临时根也报告
pytest-current 权限错误。仅给新参数指定短 ID，后续使用新建的系统临时 basetemp；
没有改旧测试、依赖、平台判断或断言。修正后该阶段 **65 passed**，随后继续增加负例。

最终环境：Windows、CPython 3.12.7、pytest 7.4.4。最终完整指定离线组合为：

| 测试模块 | 最终 passed |
| --- | ---: |
| E04 packet | 45 |
| E04 journal | 28 |
| E04 review | 53 |
| E03 guard / collectors / evidence | 75 / 7 / 17 |
| E02/R1/R2 measure_wiring | 58 |
| 原 diagnostic | 66 |
| 原 W04A offline contract | 20 |
| 原 PG identity guard（fake DB-API，无网络） | 11 |
| 合计（单次最终运行，不累计重复轮次） | **380** |

最终 **380 passed / 0 failed / 0 errors / 0 skipped，10.17s，退出 0**；
其中 E04 新测 126，原指定套件 254。JUnit 置于系统临时目录，不提交测试产物。
完整 mock 正例同时经过冻结 validate_bundle，并验证原 OFFLINE_VALIDATED/integrity
仅为夹具校验产物；unknown ACK 等负例不得生成 summary/integrity。

最终命令（E04_TEMP 为本次新建的系统临时目录，JUnit 位于其旁，不记录本机绝对路径）：

```text
python -B -m pytest tests/unit/test_biz_perf_p1_04_e04_packet.py tests/unit/test_biz_perf_p1_04_e04_journal.py tests/unit/test_biz_perf_p1_04_e04_review.py tests/unit/test_biz_perf_p1_04_e03_guard.py tests/unit/test_biz_perf_p1_04_e03_collectors.py tests/unit/test_biz_perf_p1_04_e03_evidence.py tests/unit/test_biz_perf_p1_04_measure_wiring.py tests/unit/test_biz_perf_p1_04_diagnostic.py tests/unit/test_perf03_lnx_w04a_offline_contract.py tests/unit/test_r1_integration_pg_guard.py -q --basetemp E04_TEMP --junitxml E04_TEMP-core.xml
python -m ruff check backend tests migrations scripts
git diff --check
```

Ruff 命令退出 1，`No module named ruff`，记为 **ENV_BLOCKED**；未安装或升级依赖。
新文件另做 AST 解析、行长和全新增文件 whitespace 审计；这些检查不冒充 Ruff。
本机未运行全量 pytest、真实 PG、Worker/Scheduler、迁移、Docker、性能、云平台或生产操作；
Linux/POSIX 完整回归及 Ruff 仍需新精确 SHA 的普通 GitHub CI，不能预填成功。

没有执行旧 03-B once/archive 扩展套件；E03 closeout 中九个 Windows POSIX API 缺失的
历史失败保留，不以本轮指定组合通过声称其已消除，也未修改或跳过旧用例。

## 五份 frozen 与差异审计

`git rev-parse HEAD:path` 与 `git hash-object path` 逐一一致：

| scripts/ 文件 | Git blob SHA |
| --- | --- |
| business_recalc_measure.py | 782e45ba53c8de8df0d12ffa84c219855316cfda |
| biz_perf_p1_04_diagnostic.py | 714f78017ec252791ac6a89f9fb0e0a984333c37 |
| perf03_lnx_w04a_offline_contract.py | 931fd4fec38551d9fac59791d2bde5ce0e6a1d48 |
| biz_perf_03_b_once.py | 2ea473491f590893ad575b90a0ba42f932e37129 |
| business_sql_snapshot.py | e7532b0a0242f1e3d3b047fdc03fca7ffc3ce7c6 |

本机 checkout 为 CRLF，Git 对象为 LF。直接拿工作区原字节与 LF blob 比较的首个审计断言
退出 1；随后逐份确认工作区字节恰好等于对应 blob 的精确 LF→CRLF checkout 投影，全部通过，
没有重写文件或改变换行。W04A 原字节冻结合同也通过。工作区原始 SHA256 留证如下：

| scripts/ 文件 | 当前 CRLF 字节 SHA256 |
| --- | --- |
| business_recalc_measure.py | 49a10219c68a19406bd0cf4720400c99d82277e9db20bde411dd7bddafae2475 |
| biz_perf_p1_04_diagnostic.py | 12d3de5312306ef0470a38b4ef43ec1bd33e79777ba6b2ca1bb16a0cee91ed09 |
| perf03_lnx_w04a_offline_contract.py | 17a09bc86be0bdbdd0b2b0e60897210ac9c31de94e0fdde16fce9ec368245add |
| biz_perf_03_b_once.py | 0812639bc9a929a9d024f9ace5003a3aee0c766ea69f4843ccf399d3540524b9 |
| business_sql_snapshot.py | 61241291eb4328daf7561c9de3385758d1ff3cfee08641a95da565331dc7b97d |

`git diff --exit-code` 确认已跟踪文件无变化。普通 git diff 不显示未跟踪新增文件，
因此另外逐份审查新增源码/测试/文档并执行 no-index whitespace 检查。
八份 no-index 检查均仅报告新增差异（退出 1）和 Git LF/CRLF checkout 提示，无 whitespace
错误；独立全文件行尾空白/AST 审计及 `git diff --check` 均退出 0。
只交付这八个授权路径，不包含缓存、覆盖率、JUnit、临时夹具、凭据或数据库文件。

## Windows/POSIX、持久性与剩余风险

- POSIX 分支对新目录父目录和每条记录目录执行 fsync，创建目录 0700 / 文件 0600，
  重新打开时校验 owner 与私有 mode。本机未执行 POSIX 分支，待 Linux CI 验证；即便 CI
  通过也不是物理断电、文件系统或存储设备耐久性证明。
- Windows 执行文件 fsync，目录 fsync 按既有实现不提供保证；ACL 和祖先目录信任由外部负责。
  Windows 单测、进程崩溃模拟和目录 junction 拒绝均不证明断电后目录项永久存在。
- 账本必须长期保留并由可信主体独占管理。删除/替换整个账本、换一个新账本路径、跨机器
  协调、恶意管理员、任意 Python monkeypatch、真实 lease 服务均超出原型保证；不提供生产唯一性。
- 证据真实性仍为离线声明/mock：没有 GitHub/审批认证验证器、真实资源读取器、真实 Executor、
  Worker hook、CPU/cgroup 强制、watchdog 或清理实现，没有签发 permit。
- 异常退出、短写/fsync、坏记录、过期未知 ACK 和身份/归属不明均保持占用/阻断，
  不能自动恢复；未来人工裁决或真实执行须独立授权与实现。

## Git 交接与完成信号

本环境权限明确 `.git` 只读，SSH 同时被拒绝。依用户和 W00 指示，不尝试越权暂存，
不改用替代 index/refs、不改权限或 Git 配置，不创建空提交或强推。
因此本会话**没有 commit、没有 push、新精确 SHA CI 未启动**。
HEAD/origin/master 仍为基线；全部八个路径保留工作区，交由 ChatGPT 已获授权的外层
PowerShell 先复核状态/八路径 diff，再单次提交并普通推送 master、核对远端 SHA、等待 CI
并独立审阅。不要将本回执或自检表述为 ChatGPT 已独立审阅，不为追填本文自身 SHA 再提交。

```text
BASELINE_SHA=52a9abdee7317338464f04834690f45432dd59a0
FINAL_SHA=NOT_CREATED_GIT_METADATA_READ_ONLY
CURRENT_HEAD=52a9abdee7317338464f04834690f45432dd59a0
COMMIT=BLOCKED_GIT_METADATA_READ_ONLY
PUSH=NOT_ATTEMPTED_NO_NEW_COMMIT
PUSH_BRANCH=master_PENDING_EXTERNAL_DELIVERY
CI_RUN=PENDING
CI_ATTEMPT=PENDING
TEST_COUNTS=380_PASSED_0_FAILED_0_ERRORS_0_SKIPPED
RUFF=ENV_BLOCKED_NO_MODULE
FROZEN_BLOBS=5_OF_5_MATCH
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
NEXT=CHATGPT_REVIEW
```
