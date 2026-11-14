# W05-READY 纯离线决策准备回执

2026-11-14（Asia/Shanghai）。`LOCAL_OFFLINE_VALIDATED / EXTERNAL_GIT_DELIVERY_PENDING /
CI_PENDING / INDEPENDENT_REVIEW_PENDING`。本轮仅完成决策准备，不签发任何可执行许可，
不自行声明 W05_READY_DOCUMENTARY_ACCEPTED 或负责人已批准真实测试。

## W00 与交付范围

开始执行 `git status --short --branch`：master...origin/master，唯一未跟踪文件为
负责人本次下发的 `docs/tasks/BIZ-PERF-P1-04-W05-READY.md`，按明确授权原文纳入交付。
HEAD / origin/master 均为 `67d9b19cc19440ad91bd4562b9bc3eebf2077751`。
`git ls-remote origin refs/heads/master` 实际退出1，SSH port22 Permission denied；
依任务书 W00 使用外层已核对的远端基线继续，未换代理、改权限或进行替代网络访问。
起点主CI `43592407760` attempt1 SUCCESS、7245 passed/1 skipped 是任务书提供的
外层核验信息，本会话没有独立查询，也不把它算作新 W05 版本的CI证据。

已按顺序阅读五份治理文件，再核对相关PRD、系统设计、PROJECT_RULES、README、
P1-04父任务、隔离申请草案、PRETEST报告和回执、E03/E04/E05/E02回执，及实际
v14 guard、冻结旧测量器、E02 recorder、E03 guard、E04 journal/review、原始读取器与测试。
旧治理文件仍有历史阶段指针；一般四文档维护规则与本次“仅新增六路径”不一致时，
遵循用户最新明确授权，不擅改治理状态、产品四文档或历史事实。

仅六个新增交付路径，未修改任何旧跟踪文件：

- `docs/tasks/BIZ-PERF-P1-04-W05-READY.md`：负责人任务原文。
- `scripts/biz_perf_p1_04_w05_readiness.py`：203行，纯函数及可选只读CLI。
- `tests/unit/test_biz_perf_p1_04_w05_readiness.py`：内存虚构申请构造及针对性负例。
- `docs/acceptance/BIZ_PERF_P1_04_W05_READY_ASSESSMENT.md`：五项关键阻断汇总及完整缺口矩阵。
- `docs/acceptance/BIZ_PERF_P1_04_W05_OPERATOR_CHECKLIST.md`：四段操作员待批字段，无副作用命令。
- 本回执。

## 实现与源代码证据

| 任务 | 实际交付与核对 | 边界 |
| --- | --- | --- |
| W05-A | ASSESSMENT每行包含 evidence_source / what_code_proves / what_requires_live_observation / owner_action / disposition；覆盖测量、资源、真实接线、预算/seed、身份/审批、单样本可回答问题 | 五项现实阻断未解除；CODE_VERIFIED只指静态代码能力 |
| W05-B | `assess(request, expected_sha)`；严格键集/类型、固定8股/2025-01/一次根/900日历日/五OFF、新Linux PG17声明、同SHA/run、具名主体、fingerprint、固定预算及六段计时；最多BLOCKED或REVIEWABLE_ONLY | 不读证据reference、不认证自述CI/签名/审批/资源、不签permit；全部真实性声明继续unverified |
| W05-B读取与拒绝 | `decode_request`复用冻结严格JSON；CLI复用diagnostic `directory/read_file`，64KiB输入、有界固定输出、只读显式本地文件；execute及allow/force/permit变体读取前退出2 | 无文件写入、连接、Worker、容器、执行端口或新审批/租约框架；依赖可信稳定祖先 |
| W05-C | PREPARE / MEASURE / VERIFY / CLEANUP，主体/机器/资金/资源/许可均未填；每段说明20min计时关系，准备项UNDECIDED | OWNER_SIGNOFF_PENDING，新的明确用户请求必需；本清单没有执行能力 |
| W05-D | RED/GREEN、新增133项与原指定582项联合离线回归；AST/白名单/原文件零diff/frozen与空白审计 | 测试证明结构、拒绝和离线语义，不证明真实授权或性能 |

计时检查明确六段不能遗漏seed/迁移/预热；准备三段可显式单列，但须给出单列上限，
输出excluded_steps及待批项，操作窗口须覆盖20min加单列限额。root/post/cleanup必须计入，
cleanup前包含步骤合计<900s、cleanup≤300s、总计≤1200s。该保守文书约束不等于实际预算批准，
也未替负责人决定准备步骤是否计入。实际CPU/磁盘/IO/费用强制及时间观察仍未验证。

`v14_test_database.py::verified_test_url`会连接数据库，`isolated_v14_database`会建库/迁移/删库，
本轮均未调用；环回+marker+physical ID不能证明新实例独占及全流程安全。
旧测量器受W04A冻结，新E02–E05入口仍拒绝真实执行。未来最小插入点评审仅写在矩阵里，
没有增加真实适配器或调用旧入口。五OFF通常不运行FactorInputWindow._verify，不伪造其归因。
根级SQL总时长仍UNKNOWN，inclusive/SQL/FETCH不求和，单样本不报P95/提升/容量。

## RED → GREEN 和精确验证

1. 新源码不存在时两个探针：**2 failed，退出1**。原因分别是模块不存在、CLI退出1而非合同要求的2；
   不将缺少新模块称为已有真实执行漏洞。
2. 实现203行模块后，同探针：**2 passed，退出0**。
3. 首次扩展收集：**1 collection error，退出2**，pytest默认将5001位整数转换为测试ID，
   触发Python整数转字符串限制。仅给新增参数指定短ID，未放宽整数限制/断言或改旧测试。
4. 新W05单独：**133 passed，0.29s，退出0**。
5. 最终指定组合单次实际结果：**715 passed / 0 failed / 0 errors / 0 skipped，24.51s，退出0**。
   不累计前面重复轮次。

环境：Windows / CPython3.12.7 / pytest7.4.4，未安装或升级依赖。

| 模块 | 最终passed |
| --- | ---: |
| 新W05 readiness | 133 |
| PRETEST-01 | 65 |
| E05 audit / checkpoint | 93 / 44 |
| E04 packet / journal / review | 45 / 28 / 53 |
| E03 guard / collectors / evidence | 75 / 7 / 17 |
| E02/R1/R2 measure_wiring | 58 |
| 冻结diagnostic / W04A offline | 66 / 20 |
| fake DB-API PG identity guard | 11 |
| 合计 | 715 |

最终命令（TEMP是新建系统临时目录，JUnit在其旁，未提交测试产物）：

```text
python -B -m pytest tests/unit/test_biz_perf_p1_04_w05_readiness.py tests/unit/test_biz_perf_p1_04_pretest_report.py tests/unit/test_biz_perf_p1_04_e05_audit.py tests/unit/test_biz_perf_p1_04_e05_checkpoint.py tests/unit/test_biz_perf_p1_04_e04_packet.py tests/unit/test_biz_perf_p1_04_e04_journal.py tests/unit/test_biz_perf_p1_04_e04_review.py tests/unit/test_biz_perf_p1_04_e03_guard.py tests/unit/test_biz_perf_p1_04_e03_collectors.py tests/unit/test_biz_perf_p1_04_e03_evidence.py tests/unit/test_biz_perf_p1_04_measure_wiring.py tests/unit/test_biz_perf_p1_04_diagnostic.py tests/unit/test_perf03_lnx_w04a_offline_contract.py tests/unit/test_r1_integration_pg_guard.py -q --basetemp TEMP --junitxml TEMP.xml -p no:cacheprovider
python -B -m ruff check backend tests migrations scripts
git diff --exit-code HEAD
git diff --check
```

Ruff实际退出1，`No module named ruff`，记ENV_BLOCKED；没有升级依赖。
AST/行长/空白审计不代替Ruff，新精确SHA的Linux CI完整回归及Ruff仍PENDING。
未执行本机全量pytest、真实PG17/Worker/Scheduler、迁移、Docker、云、SQL/EXPLAIN或性能实验；
本轮按最新禁止范围仅运行指定安全离线文件，不将未运行项写成通过。

新增负例覆盖格式/严格JSON/重复嵌套键/非有限/超限/深度/巨大整数、股票/月/seed/一次根、
五开关、root900秒及cleanup300秒边界、计入准备和post挤占root、忘记seed计时或单列预算、
预算缺失/溢出、具名主体/窗口、跨SHA/run/lease、未知CI来源、SUCCESS/approval/permit/
签名自述及未知字段、UNKNOWN_ACK人工中止、hardlink/UNC/穿越/ADS/.env、固定脱敏错误、
纯函数不访问证据引用、CLI文件集合/inode/mtime/字节不变。独立Python进程audit hook拒绝
socket/子进程/资源目录创建/文件写入/.env访问，正常只读CLI仍通过；确认不导入
app/psycopg/sqlalchemy/dotenv。AST检查新模块无写入/真实执行方法，源码≤250行。
原E04/E05未知ACK崩溃、永久占用和不恢复测试均保留运行，没有建立平行历史状态。

## 冻结与差异审计

逐一核对 `git rev-parse HEAD:path`、`git hash-object path` 与任务书指定blob：

| scripts/文件 | 实际匹配的Git blob |
| --- | --- |
| business_recalc_measure.py | 782e45ba53c8de8df0d12ffa84c219855316cfda |
| biz_perf_p1_04_diagnostic.py | 714f78017ec252791ac6a89f9fb0e0a984333c37 |
| perf03_lnx_w04a_offline_contract.py | 931fd4fec38551d9fac59791d2bde5ce0e6a1d48 |
| biz_perf_03_b_once.py | 2ea473491f590893ad575b90a0ba42f932e37129 |
| business_sql_snapshot.py | e7532b0a0242f1e3d3b047fdc03fca7ffc3ce7c6 |

五份工作区原字节同时等于HEAD blob或其精确LF→CRLF checkout投影，没有改写换行。
`git diff --exit-code HEAD`及`git diff --check`退出0，所有已有跟踪文件零差异。
普通diff不显示未跟踪新增文件，因此六个新增路径另逐份核对白名单、UTF-8、行尾空白、
LF结尾及两份Python的AST/100字符行长；任务书原文未编辑。
无缓存、coverage、构建、临时fixture、JUnit、凭据或数据库产物交付。
E05/E04/E03/E02、backend/frontend、模型/迁移/策略、依赖、Docker/CI/环境配置均未改变。

## Git交接与剩余风险

本环境权限明确`.git`只读，GitHub SSH已拒绝。本会话没有尝试越权git add或写index/refs，
没有改权限、替代index、代理、强推或重写历史。**未生成commit，未push，无新SHA CI run**。
当前HEAD/origin/master仍为基线。六路径保留在工作区，交ChatGPT已授权外层PowerShell
先独立复测/核对文件及远端是否漂移，再单次普通commit和非force push origin master；
若远端漂移停止交回。推送后等待精确SHA主CI/A4-1/A4-2/Publication并独立审阅；
本回执不预填其成功，不为追填自身SHA重复提交。

主要剩余风险即矩阵五项阻断：真实新资源、真实接线、预算/时间/成本、来源与身份、
新的明确执行授权尚缺。本核验器可对完全伪造且自洽的声明返回REVIEWABLE_ONLY，
这正是文书完整性检查的适用范围，不能提供真实可信审计或任何执行能力。
可信祖先/本地文件系统由调用者保证；未证明恶意管理员、挂载替换、跨机器唯一性、
断电耐久性、真实性能或现场结束安全。E04/E05原信任边界保持不变。
本轮不是E06/PRETEST-02，不继续扩建框架；下一步仅独立审阅和负责人决定。

```text
TASK=W05-READY
BASELINE_SHA=67d9b19cc19440ad91bd4562b9bc3eebf2077751
FINAL_SHA=NOT_CREATED_GIT_METADATA_READ_ONLY
CURRENT_HEAD=67d9b19cc19440ad91bd4562b9bc3eebf2077751
COMMIT=NOT_ATTEMPTED_GIT_METADATA_READ_ONLY
PUSH=NOT_ATTEMPTED_EXTERNAL_POWERSHELL_REQUIRED
PUSH_BRANCH=master_PENDING_EXTERNAL_DELIVERY
CI_RUN=NOT_STARTED_PENDING_EXTERNAL_COMMIT
OFFLINE_TESTS=715_PASSED_0_FAILED_0_ERRORS_0_SKIPPED
NEW_W05_TESTS=133_PASSED
RUFF=ENV_BLOCKED_NO_MODULE
FROZEN_5=5_OF_5_MATCH
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
