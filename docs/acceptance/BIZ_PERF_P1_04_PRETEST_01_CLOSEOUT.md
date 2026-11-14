# BIZ-PERF-P1-04 PRETEST-01 离线开发回执

2026-11-14（Asia/Shanghai）。
`LOCAL_OFFLINE_VALIDATED / EXTERNAL_GIT_DELIVERY_PENDING / CI_PENDING / INDEPENDENT_REVIEW_PENDING`。
本回执是本会话自检，未声称 ChatGPT 已独立审阅或负责人已最终验收。

## W00、范围与交付

首先执行 `git status --short --branch`：master...origin/master，唯一未跟踪项为
负责人下发的本次任务书，按明确授权纳入交付。HEAD / origin/master 均为
`b5207a39fd98b1508b8745fadae799ff34a3609d`，收尾复核仍一致。
`git ls-remote origin refs/heads/master` 退出 1，GitHub SSH port 22 Permission denied。
远端基线及 E05 CI `43574455659` 的信息来自负责人任务书，本会话没有独立核实实时远端，
没有使用替代网络、修改 SSH/Git 配置、权限、index 或 refs 绕过沙箱。

按顺序读取五份治理文件，核对相关 PRD、系统设计、PROJECT_RULES、README、
P1-04 父任务、E02/E03/E04/E05 closeout，以及冻结 Replay、E02 wiring、E03 三模块、
相关测试和实际业务源码。旧 G0 接续指针保留历史语境，本轮按用户最新 PRETEST 范围执行。
通常四文档维护和状态更新规则与本轮严格新增白名单有差异，依最新明确要求，
不改 PROJECT_STATUS、其他治理/产品文档、历史回执、旧代码或测试。

只新增六个路径：

- `docs/tasks/BIZ-PERF-P1-04-PRETEST-01.md`（保留负责人原文）
- `scripts/biz_perf_p1_04_pretest_report.py`（一个只读模块）
- `tests/unit/test_biz_perf_p1_04_pretest_report.py`（65 项）
- `docs/acceptance/BIZ_PERF_P1_04_PRETEST_01_REPORT.md`
- `docs/acceptance/BIZ_PERF_P1_04_ISOLATED_RUN_REQUEST_DRAFT.md`
- `docs/acceptance/BIZ_PERF_P1_04_PRETEST_01_CLOSEOUT.md`

## 对照任务验收

| 项目 | 完成交付及限制 |
| --- | --- |
| PRETEST-A | 显式 expected SHA + 固定 fixture 两文件 → 原 decode/preflight/Replay.summary → bounded JSON；只读、无报告落盘，无审批、审计或执行框架。 |
| 业务化视图 | root/Worker 子区间/post 分列，阶段 inclusive 排序带 DO_NOT_SUM，SQL 次数/阶段耗时、FETCH 行数/耗时、CPU、RSS 分列；无根 SQL 时长就 UNKNOWN，零 CPU 比率 UNDEFINED；缺测不填0。 |
| 位置覆盖 | factors.compute、candidate_lookup_batch/store、publication.verify 复用原 stage_observations；factors.input_verify 真实源码存在但不在冻结 allowlist，明确 NOT_INSTRUMENTED。 |
| PRETEST-B | 报告三条固定源码假设：窗口/输入 fingerprint、候选批量查找和序列化、发布验证与后验重叠；逐条区分 CODE_OBSERVED / HYPOTHESIS / MEASURED_OFFLINE_FIXTURE / REAL_NOT_RUN。 |
| 关键源码事实 | 输入复用关闭时不装配 FactorInputWindow，不能归因其 _verify；当前 upsert 的批次 lookup 是一条组合 SQL，不因两个进度标签假设两次查找。 |
| PRETEST-C | W05 精简申请草案含8股/2025-01/同900日 Seed/一次尝试/五OFF/全新Linux PG17身份/20分钟与资源预算/人工待签项/未知ACK停止；没有执行程序或许可。 |
| PRETEST-D | RED/GREEN、65项专属测试、517项既有指定安全模块联合回归、AST/空白/白名单/frozen与原文件零diff检查；未运行本机全量pytest。 |

## RED → GREEN 与精确验证

1. 新模块不存在时，入口与 execute 拒绝探针为 **2 failed，退出1**。
   这是缺少新入口的 RED，不表述为已有真实执行漏洞。实现后同两项 **2 passed，退出0**。
2. 初轮扩展 **54 passed / 2 failed，退出1**：测试假定原 emit_fixture 的 create/claim
   推进时钟，实际该 mock 窗口为0。仅调整新增报告测试的 fixture，显式加入5ms非零窗口，
   保留更严格的 root>Worker 和越界断言；原 wiring、测试及任何业务代码未动。
   该组随后 **56 passed，退出0**。
3. 加入候选缺测、冻结完整性及失败边界后，首轮联合 **580 passed，24.07秒，退出0**。
4. 再补两个真正 Python CLI 进程用例（仅导入/读取本地 fixture/拒绝 execute），
   并清理新模块异常类型的冗余声明，最终联合结果如下；不累加多轮用例数。

环境：Windows / CPython 3.12.7 / pytest 7.4.4；使用 `python -B -m pytest`、
每轮全新的系统临时 basetemp/JUnit，未安装或升级依赖，未提交测试产物或本机路径。

| 模块 | 最终 passed |
| --- | ---: |
| 新 pretest_report | 65 |
| E05 audit / checkpoint | 93 / 44 |
| E04 packet / journal / review | 45 / 28 / 53 |
| E03 guard / collectors / evidence | 75 / 7 / 17 |
| E02/R1/R2 measure_wiring | 58 |
| 冻结 diagnostic / W04A | 66 / 20 |
| PG identity guard（fake DB-API） | 11 |
| 合计 | **582** |

最终 **582 passed / 0 failed / 0 errors / 0 skipped，24.08秒，退出0**。
安全组合的完整命令（TEMP 是新建系统临时目录，不是仓库目录）：

```text
python -B -m pytest tests/unit/test_biz_perf_p1_04_pretest_report.py tests/unit/test_biz_perf_p1_04_e05_audit.py tests/unit/test_biz_perf_p1_04_e05_checkpoint.py tests/unit/test_biz_perf_p1_04_e04_packet.py tests/unit/test_biz_perf_p1_04_e04_journal.py tests/unit/test_biz_perf_p1_04_e04_review.py tests/unit/test_biz_perf_p1_04_e03_guard.py tests/unit/test_biz_perf_p1_04_e03_collectors.py tests/unit/test_biz_perf_p1_04_e03_evidence.py tests/unit/test_biz_perf_p1_04_measure_wiring.py tests/unit/test_biz_perf_p1_04_diagnostic.py tests/unit/test_perf03_lnx_w04a_offline_contract.py tests/unit/test_r1_integration_pg_guard.py -q --basetemp TEMP --junitxml TEMP.xml
python -B -m ruff check backend tests migrations scripts
git diff --check
git diff --exit-code HEAD
```

Ruff 实际退出1，`No module named ruff`，记 **ENV_BLOCKED**；AST/行长/空白检查不代替 Ruff。
未执行本机全量 pytest、迁移、PostgreSQL、真实 Worker/Scheduler、Docker、云资源、
HTTP/SQL/EXPLAIN 或性能实验；也未执行历史03-B扩展套件，不宣称其Windows平台问题已消失。
未来精确交付 SHA 的 Linux 完整回归和 Ruff 由普通 CI 校验，当前均 PENDING。

专属负例覆盖非零 root/Worker/post 双计、阶段重叠、SQL/FETCH重叠、缺 CPU/零 CPU、
缺 FETCH/合法0、缺 lookup/store、RSS 不分配、伪造 summary 对象、跨实施SHA/UUID/根、
缺结束、坏质量/未知根/清理阻断、非法阶段、缺LF、重复键、NaN/Infinity/溢出/非法UTF-8、
坏 preflight/source 摘要、来源/权限自称、旧03-B、缺文件、大小/单行超限、hardlink/穿越、
CLI错误脱敏、有界输出及execute在任何读取前拒绝。
完整正例使用原 wiring.emit_fixture；报告前后文件集合、inode、mtime与字节完全相同。
其间将原 validator 写入口、publish 和 recorder 构造替换为失败探针，读取仍通过。
CLI导入进程确认未加载 app/psycopg/sqlalchemy/dotenv，没有触碰 DATABASE_URL。

## 五 frozen 和差异审计

`git rev-parse HEAD:path` 与 `git hash-object path` 逐项匹配以下完整 Git blob：

| scripts/ 文件 | Git blob SHA |
| --- | --- |
| business_recalc_measure.py | 782e45ba53c8de8df0d12ffa84c219855316cfda |
| biz_perf_p1_04_diagnostic.py | 714f78017ec252791ac6a89f9fb0e0a984333c37 |
| perf03_lnx_w04a_offline_contract.py | 931fd4fec38551d9fac59791d2bde5ce0e6a1d48 |
| biz_perf_03_b_once.py | 2ea473491f590893ad575b90a0ba42f932e37129 |
| business_sql_snapshot.py | e7532b0a0242f1e3d3b047fdc03fca7ffc3ce7c6 |

工作区原字节另与 HEAD blob 的 LF 或精确 LF→CRLF checkout 投影核对；没有改写换行。
`git diff --exit-code HEAD` 与 `git diff --check` 退出0，所有已有跟踪文件零diff。
普通diff不展示未跟踪文件，六个新增文件另外逐份检查内容、AST（两个Python）、
行尾空白、LF结尾与路径白名单；未交付缓存、coverage、构建、JUnit、临时fixture或凭据。
E05/E04/E03/E02、backend/Repository/模型/迁移/配置/frontend/依赖/CI均未变。

## 交接与剩余风险

环境权限明确 `.git` 为只读且 SSH 已拒绝；按用户指令未尝试越权暂存、替代index/refs、
修改权限或强推。**本会话没有生成 commit，没有 push，也没有新 SHA 的 CI run。**
六份文件保留工作区，交 ChatGPT 外层已授权 PowerShell 复核六路径差异后，
单次常规 commit、非force push origin master，核对精确远端SHA并等待主CI/A4-1/A4-2/Publication，
CI完成后独立审阅。不要为回填本文自身SHA再次提交，也不以E05基线CI代替本次结果。

只读报告是离线假设视图，不认证事件真实性、资源归属、执行许可或性能。
真实业务瓶颈未知；窗口 fingerprint 阶段不在冻结allowlist且拟议五OFF不启用该路径。
真实采集/结束边界和输出一致性均尚未实机验证；草案的CPU/磁盘/成本/主体/窗口及清理
权限待负责人签认。既有E05文件系统/来源信任限制继续保留，本轮没有扩展其框架。
本次不是E06，后续停止安全框架类迭代；下一步仅独立审阅及负责人决定是否另行明确授权
单次隔离实际测量，不自动派生PRETEST-02或切换执行。

```text
BASELINE_SHA=b5207a39fd98b1508b8745fadae799ff34a3609d
FINAL_SHA=NOT_CREATED_GIT_METADATA_READ_ONLY
CURRENT_HEAD=b5207a39fd98b1508b8745fadae799ff34a3609d
COMMIT=BLOCKED_GIT_METADATA_READ_ONLY
PUSH=NOT_ATTEMPTED_EXTERNAL_POWERSHELL_REQUIRED
PUSH_BRANCH=master_PENDING_EXTERNAL_DELIVERY
CI_RUN=NOT_STARTED_PENDING_EXTERNAL_COMMIT
TEST_COUNTS=582_PASSED_0_FAILED_0_ERRORS_0_SKIPPED
NEW_TEST_COUNTS=65_PASSED
RUFF=ENV_BLOCKED_NO_MODULE
FROZEN_5_SHA=5_OF_5_MATCH
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
NEXT=CHATGPT_REVIEW_AND_OWNER_APPROVAL_DECISION
```
