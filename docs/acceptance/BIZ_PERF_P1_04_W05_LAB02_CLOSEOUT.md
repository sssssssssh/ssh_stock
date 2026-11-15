# W05-LAB-02 离线交付回执

2026-11-15；`TASK=BIZ-PERF-P1-04-W05-LAB-02`。
候选结论 `LAB02_ADAPTER_OFFLINE_VERIFIED / REVIEW_PENDING`；精确新 SHA 的 CI 和外层独立复测待完成。
本轮在用户提供的当前 Codex 桌面持久会话执行，未启动独立 codex exec。
projectId/会话名称由桌面宿主管理，本轮工具没有独立核验这些元数据的能力，不能声称已核验归属。
期望归属与名称沿用任务书：GP / `01a15f75-2c79-7d30-9232-651a6ef4253d` /
`BIZ-PERF-P1-04 W05-LAB-02 真实调用适配`。

## 基线、范围及实现事实

首条命令 `git status --short --branch`：master，唯一未跟踪项为负责人下发任务书。
HEAD 与 origin/master 均为 `109921758eb949b4e986b08c58b3d3f6b117bd94`。
`git ls-remote origin refs/heads/master` 退出1，SSH22被沙箱拒绝；未改代理/Git配置或绕权重试。
GitHub 最新 master 只能引用任务书/外层的起始核验，不能把 origin/master 当成本轮实时远端证明。
起始四条 CI SUCCESS 是任务书提供的历史事实，未独立重查，不能充当候选代码 CI。

按顺序读取五份治理文件、相关 PRD/系统设计/PROJECT_RULES/README，随后核对父任务、
PRETEST-01、W05-READY、LAB-01、E02/E03/E04/E05 与冻结旧测量器。
静态核对 v14 guard、生产 create/claim/execute、job_guard 的 commit/refresh/flush/去重、
JobRun/DataPublication、ProgressStep 与 RootCounts；未导入业务应用或读取凭据。
旧治理指针和四文档维护规则与本次五文件白名单存在范围差异，以用户最新要求为准，旧文件不改。
任务书原文 SHA256：`e28be58a546b976bd921d4ebb0b9e354304d8fa4d9e2d84a70634f00f95cf756`。

仅新增以下五条路径，任务书保持原字节：

1. `docs/tasks/BIZ-PERF-P1-04-W05-LAB-02.md`
2. `scripts/biz_perf_p1_04_w05_root_bridge.py`
3. `tests/unit/test_biz_perf_p1_04_w05_root_bridge.py`
4. `docs/acceptance/BIZ_PERF_P1_04_W05_LAB02_INTEGRATION.md`
5. `docs/acceptance/BIZ_PERF_P1_04_W05_LAB02_CLOSEOUT.md`

桥包含精确生产函数懒映射、共用参数适配、单根/去重/owner/token核对、单次尝试消费、
根快照封口与独立 post，以及有限脱敏失败事件；默认和未来 live port 固定拒绝。
完整 fake 路径为 create→claim→refresh→execute（含finally）→post，测得的25/20/7ms全是模拟时钟。
真实 claim 不支持目标 ID，未来空队列隔离与真实 post reader/采集/协调端仍是缺口。
详见[接线决策书](BIZ_PERF_P1_04_W05_LAB02_INTEGRATION.md)，不把映射存在写成实机验证。

## RED/GREEN 与验证记录

| 验证 | 实际结果 |
| --- | --- |
| RED：先写新测试，模块尚不存在 | 退出1，ImportError，1 collection error；无资源操作。 |
| 首轮实现 | 60 passed / 1 failed，退出1；无SQL采集 fake 仍持有独立计数器，后验封口断言失败。 |
| 修正 fake 计数器接线 | 保留封口断言，61 passed，退出0，0.17s。 |
| 扩充返回采集、慢sink、阶段范围和硬拒绝测试 | 72 passed，退出0，0.19s；阶段/SQL/CPU缺测不捏造。 |
| 首轮指定离线历史集合 | 新72项+旧799项，871 passed，退出0，24.74s。 |
| 最终定向新增 | 补充不可写尝试状态、零根区间拒绝，74 passed，退出0，0.20s。 |
| Ruff | `python -B -m ruff check` 两个新Python文件退出1：No module named ruff。ENV_BLOCKED，未安装依赖，留精确新SHA Linux CI核验。 |

新用例覆盖准确参数/原生UUID/worker/token/刷新后身份、去重与缺根、None/错claim、单次和重入、
create/claim/Worker/post失败/崩溃/UNKNOWN_ACK、SUCCESS与PUBLISHED分别校验、范围/source/行数/B泄漏、
跨root/run/SHA/token拒绝、封口后计数、CPU0/倒退/缺测、时钟倒退/非有限值/overflow、阶段重叠与缺测、
采集器失败、sink失败/后延、快照防御性拷贝、无副作用导入/反射和默认生产端口拒绝。
新测试全是内存 fake；子进程仅检查 Python 模块导入/反射和默认拒绝，没有业务 Worker。

指定集合沿用 LAB-01 的15个离线文件，再加本轮新文件；默认 source_contract_pytest 插件保持启用。
未执行数据库测试或全量 Windows pytest，未删断言/跳测/扩大容差。
首轮集合退出时出现 pytest 临时目录 pytest-current 的 WinError5 atexit cleanup PermissionError；
解释器忽略该清理异常、进程退出0。未清理目录/改权限/绕过沙箱，测试通过不表示临时链接清理成功。
最终集合、AST、空白、冻结与 Git 交付事实在下方追加，不预填结果。

复测命令（纯离线）：

```text
python -B -m pytest tests/unit/test_biz_perf_p1_04_w05_root_bridge.py tests/unit/test_biz_perf_p1_04_w05_lab_plan.py tests/unit/test_biz_perf_p1_04_w05_readiness.py tests/unit/test_biz_perf_p1_04_pretest_report.py tests/unit/test_biz_perf_p1_04_e05_audit.py tests/unit/test_biz_perf_p1_04_e05_checkpoint.py tests/unit/test_biz_perf_p1_04_e04_packet.py tests/unit/test_biz_perf_p1_04_e04_journal.py tests/unit/test_biz_perf_p1_04_e04_review.py tests/unit/test_biz_perf_p1_04_e03_guard.py tests/unit/test_biz_perf_p1_04_e03_evidence.py tests/unit/test_biz_perf_p1_04_e03_collectors.py tests/unit/test_biz_perf_p1_04_measure_wiring.py tests/unit/test_biz_perf_p1_04_diagnostic.py tests/unit/test_perf03_lnx_w04a_offline_contract.py tests/unit/test_r1_integration_pg_guard.py -q -p no:cacheprovider
```

## 保留门禁与交接

`REAL_PG17=NOT_RUN / REAL_WORKER=NOT_RUN / ROOT_ATTEMPTS=0 / HOTSPOT=NONE_PROVEN`。
`B_GATE=NOT_APPROVED / TARGETED_PG17_GATE=NOT_APPROVED`，
`AUTHORIZATION=AUTHORIZATION_PENDING / BUDGET=DRAFT_NOT_APPROVED`。
未启动/连接 PostgreSQL、Worker、Scheduler、Docker/Compose/K8s、云、真实seed/迁移/SQL/EXPLAIN/性能根。
未运行全量pytest/coverage、Alembic或Compose config/build；用户本轮明确禁止，不能套通用矩阵扩大授权。
没有外部watchdog/cgroup、镜像/凭据/PG物理身份/独占资源/硬预算/结束清理的实机证明。
离线事件也不是已持久化完整E03 bundle，不能提供真实瓶颈或容量结论。

下一步仅 ChatGPT 外层对精确基线、五路径、测试、差异与冻结独立审核，再由外层常规提交推送master，
核对精确新SHA的主CI/A4-1/A4-2/Publication。没有新SHA前CI_PENDING；普通CI不批准实机。
后续资源、单次实验及责任人/窗口/预算必须由负责人另批，不进入E06或自动执行W05-RUN。

`NEXT=CHATGPT_INDEPENDENT_REVIEW`。

## 最终复测、差异审计与 Git 交付事实

最终上述16文件集合：**873 passed，退出0，25.07s**（新增74项+历史799项），无失败/跳过。
退出时仍出现同一 pytest-current 的 WinError5 atexit 清理限制；未隐去或修改原安全测试。
两份新Python均AST解析通过、无超100字符行或尾随空白；脚本354行、测试525行。
静态与子进程检查确认无main/CLI、顶层无app/SQLAlchemy/psycopg/dotenv导入，
无生产连接/环境发现/模块文件写入；默认及未绑定live方法在生产导入之前固定拒绝。

差异精确为前述五条路径全部新增、零删除，旧跟踪文件零差异：
`git diff --exit-code HEAD --`、`git diff --check`、`git diff --cached --check`均退出0；
`git ls-files --others --exclude-standard`与五路径白名单精确相等。
逐条运行 `git diff --no-index --check -- NUL PATH`，五项均无空白错误输出；
退出1表示存在新增差异，stderr仅现有Git的LF→CRLF提示，未改Git配置或规范化工作树。
完整新增差异可由外层对五条路径分别运行 `git diff --no-index -- NUL PATH`复核；未跟踪内容
不会出现在普通 `git diff` 中，不能仅凭后者的空输出声称已审阅新代码。

| 新增内容（本回执不自写自身摘要） | 精确原字节SHA256 |
| --- | --- |
| 任务书，73行 | `e28be58a546b976bd921d4ebb0b9e354304d8fa4d9e2d84a70634f00f95cf756` |
| 业务桥，354行 | `a76b4fdbc7051175e97b93f26a8119cea634c584917c123cb50e248bb47f2d98` |
| 新测试，525行 | `fb5f417edd32fa007da1cbfd84a437847cec787218c76f2ba63a3bcd41276b26` |
| 接线决策书，110行 | `f69bb72ebd070b528d08c6e98d4909f29706e9d16becafb7d91e1fc477bddef2` |

五份frozen的HEAD blob和工作树规范LF的Git blob均逐项匹配（只读计算，没有回写字节）：

| 冻结路径 | Git blob |
| --- | --- |
| `scripts/business_recalc_measure.py` | `782e45ba53c8de8df0d12ffa84c219855316cfda` |
| `scripts/biz_perf_p1_04_diagnostic.py` | `714f78017ec252791ac6a89f9fb0e0a984333c37` |
| `scripts/perf03_lnx_w04a_offline_contract.py` | `931fd4fec38551d9fac59791d2bde5ce0e6a1d48` |
| `scripts/biz_perf_03_b_once.py` | `2ea473491f590893ad575b90a0ba42f932e37129` |
| `scripts/business_sql_snapshot.py` | `e7532b0a0242f1e3d3b047fdc03fca7ffc3ce7c6` |

普通 `git add --` 精确五路径只尝试一次，退出1：无法创建 `.git/index.lock`，Permission denied。
没有重试/提权/改权限/旁路；未执行commit/push。SSH也已在起始查询被拒绝。
`PUSH=NOT_RUN_SANDBOX_DENIED / TARGET_BRANCH=master`。
`BASELINE_SHA=109921758eb949b4e986b08c58b3d3f6b117bd94`；
`FINAL_SHA=109921758eb949b4e986b08c58b3d3f6b117bd94`（仍为原HEAD，无本轮新提交）。
`SAFE_TEST_COUNTS=74_NEW_873_TOTAL / FROZEN_5=UNCHANGED / CI_RUN=PENDING`。
`CHANGED_PATHS`为本回执列明的五条路径；文件全部留在工作区。
外层须重新核对HEAD/origin/master/GitHub实时master与当前diff，远端漂移则停止，
再独立复测、普通提交、非force推送master及精确新SHA四条CI审阅；不能借用旧SHA结果。
资源事实、独立复测、Ruff/Linux CI、桌面元数据独立确认及新的实机批准缺口均仍保留。
