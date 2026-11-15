# W05-LAB-03 纯离线交付回执

2026-11-15；`TASK=W05-LAB-03`；`BASELINE_SHA=2c1583081cc2579a8b0e73d5a2e06923fd46ce4d`。
本会话候选状态 `TOPOLOGY_OFFLINE_IMPLEMENTED / REVIEW_PENDING`。
最高可验收状态 `W05_LAB03_TOPOLOGY_OFFLINE_ACCEPTED` 留给外层独立复测/审阅；本轮不自授验收。
本轮沿用用户指定的 Codex 桌面持久会话，未启动独立 codex exec。
期望归属 GP，projectId=`01a15f75-2c79-7d30-9232-651a6ef4253d`，
会话名 `BIZ-PERF-P1-04 W05-LAB-03 隔离Worker拓扑`；工具无法独立读取桌面项目/会话元数据，
不能声称已独立核验或修改该归属/名称。

## 基线与授权范围

首条命令 `git status --short --branch`：master，唯一未跟踪文件为负责人下发的本任务书。
HEAD 与 origin/master 均为 `2c1583081cc2579a8b0e73d5a2e06923fd46ce4d`。
实时 `git ls-remote origin refs/heads/master` 退出1，GitHub SSH22 `Permission denied`。
未绕过沙箱、改 SSH/Git/代理/权限或重试其他网络路径；实时 GitHub master 未独立核实。
起始主CI43666985057、A4-1 43666985003、A4-2 43666985033、Publication43666985068
的 SUCCESS 仅引用任务书及外层基线事实，未重新查询，也不是本次候选代码的CI结果。

按顺序读取五份治理文件及相关 PRD/设计/PROJECT_RULES/README，再读本任务书、LAB-01
Compose/检查器/PLAN、LAB-02 业务桥/INTEGRATION/回执、相关测试、生产 claim/execute、
根 Dockerfile/Compose 与历史CI证据。治理文件旧指针及四文档维护规则与本轮范围不同，
以用户最新六路径授权为准，全部已有文件保持原字节。
任务书原文 SHA256：`aa65c73efd73f2d87fddfcf35b19d34e4cbcdd9546992557e051592a4cff75c9`。

唯一六条新增路径（含任务书，`FILES=6`）：

1. `docs/tasks/BIZ-PERF-P1-04-W05-LAB-03.md`（负责人原文保留）
2. `infra/biz_perf_w05/compose.worker.yaml`
3. `scripts/biz_perf_p1_04_w05_worker_gate.py`
4. `tests/unit/test_biz_perf_p1_04_w05_worker_gate.py`
5. `docs/acceptance/BIZ_PERF_P1_04_W05_LAB03_TOPOLOGY.md`
6. `docs/acceptance/BIZ_PERF_P1_04_W05_LAB03_CLOSEOUT.md`

overlay 仅增加 `w05_worker`，沿用 LAB-01 同项目名/私网引用，无第二份PG/卷。
使用无默认镜像占位符、手动profile、固定非root UID/GID、只读rootfs、cap_drop ALL、
no-new-privileges、pids限制、3GiB内存/swap草案；无depends_on/端口/挂载/secret/外网/构建。
`pull_policy=never` 仅声明使用未来已独立审阅的本地镜像，当前没有镜像供应。
入口无条件打印 `EXECUTION_NOT_AVAILABLE` 并退出2；与显式固定文件只读审核分开。
纯函数精确白名单拒绝额外服务、宿主/生产配置、权限提升、业务入口及伪授权；
正常结果也始终 execution_available=false、real_network_verified=false、两 Gate NOT_APPROVED。
镜像格式符合不代表真实性。没有新审批/签名/lease/日志系统、执行许可或成功运行模式。

## RED → GREEN 与实际测试

| 阶段 | 实际结果 |
| --- | --- |
| RED：先写测试，入口模块尚不存在 | 退出1，ImportError，1 collection error；无资源操作 |
| 首轮实现与负例 | 110 passed / 1 failed / 2 errors，退出1；镜像规则错误接受 `https://` 前缀，两个大型输入自动生成超长测试ID导致Windows setup错误 |
| 修正 | 收紧引用分段语法，保留原拒绝断言；为大型输入设置短的明确ID，不减少测试 |
| GREEN：新文件定向 | 112 passed，0.15s，退出0 |
| 指定17文件离线集合 | 985 passed，26.41s，退出0；新增112 + 历史873，无失败/跳过 |
| Ruff | `python -B -m ruff check` 两个新Python文件退出1：No module named ruff；ENV_BLOCKED，未安装依赖 |
| AST/行长 | 两个新Python文件均解析通过，无超过100字符行；入口模块125行，测试338行 |

新增测试从真实 overlay 读取基准，再逐项修改配置；49个结构负例覆盖拓扑/入口/资源/安全/
镜像/权限/连接目标/根.env/secret/执行hook/伪授权，另有必填项缺失、非结构和镜像语法测试。
固定文件测试拒绝重复JSON键、非有限值、YAML扩展、无效UTF8、超限、深递归、非bytes、
链接/祖先链接/reparse point/硬链接/目录/尺寸/身份变化/丢失/不可读，atime变化允许正常只读。
进程内拦截外部操作，验证导入/纯函数无IO、review仅一次固定文件只读。
受限Python子进程禁止socket/进程创建/业务或DB导入/文件写入，验证任意参数与真正
`__main__` 均固定拒绝2；子进程只运行检查代码，没有启动业务Worker或连接数据库。

集合沿用 LAB-02 的16个显式离线文件，加本轮新测试；包括 LAB-02 74项、LAB-01 84项、
W05-READY 133项、PRETEST、E05/E04/E03/E02/W04A和fake PG guard。
默认source_contract_pytest插件保留，未改旧断言、收集、安全插件或覆盖率要求。
复测命令（仅离线）：

```text
python -B -m pytest tests/unit/test_biz_perf_p1_04_w05_worker_gate.py tests/unit/test_biz_perf_p1_04_w05_root_bridge.py tests/unit/test_biz_perf_p1_04_w05_lab_plan.py tests/unit/test_biz_perf_p1_04_w05_readiness.py tests/unit/test_biz_perf_p1_04_pretest_report.py tests/unit/test_biz_perf_p1_04_e05_audit.py tests/unit/test_biz_perf_p1_04_e05_checkpoint.py tests/unit/test_biz_perf_p1_04_e04_packet.py tests/unit/test_biz_perf_p1_04_e04_journal.py tests/unit/test_biz_perf_p1_04_e04_review.py tests/unit/test_biz_perf_p1_04_e03_guard.py tests/unit/test_biz_perf_p1_04_e03_evidence.py tests/unit/test_biz_perf_p1_04_e03_collectors.py tests/unit/test_biz_perf_p1_04_measure_wiring.py tests/unit/test_biz_perf_p1_04_diagnostic.py tests/unit/test_perf03_lnx_w04a_offline_contract.py tests/unit/test_r1_integration_pg_guard.py -q -p no:cacheprovider
```

集合退出时pytest atexit对既有 `pytest-current` 临时链接清理出现 WinError5 PermissionError；
解释器忽略该清理异常、测试进程退出0。没有清理用户目录、改权限或绕权，测试通过不代表
该临时链接清理成功。Ruff和精确新SHA完整Linux工程回归仍需外层CI。

## 冻结、未执行与交接

`ROOT_ATTEMPTS=0 / HOTSPOT=NONE_PROVEN / REAL_PG17=NOT_RUN / REAL_WORKER=NOT_RUN`。
`B_GATE=NOT_APPROVED / TARGETED_PG17_GATE=NOT_APPROVED`，
`AUTHORIZATION=AUTHORIZATION_PENDING / BUDGET=DRAFT_NOT_APPROVED`。
未调用Docker或Compose（包括config/build/up），未创建/连接PG或其他数据库，
未运行Worker/Scheduler/seed/迁移/SQL/EXPLAIN/真实root/性能实验，未访问云、生产凭据或.env。
未跑Windows全量pytest、安装依赖或修改CI/环境；本次明确禁令优先于通用验证矩阵。
PIT、Decimal、S0–S6、五OFF、预热/回看、500行批次、300秒发布预算、原像/质量/取消/
心跳/原子发布、append-only与未知提交处理均未改变。

真实镜像与fingerprint、Compose实际合并/连通、独立资源/空队列、仓库外secret与最小权限、
Session/LiveBusinessPort/PostRead/Seed装配、硬预算/watchdog/独立退出/cleanup均未验证或未实现。
生产claim无指定ID，错误claim后的拒绝无法撤销claim，这是未来实机硬阻断。
详见[拓扑与阻断](BIZ_PERF_P1_04_W05_LAB03_TOPOLOGY.md)。
本次不签发许可，不把离线通过写成部署可用；资源创建、成本与唯一root仍须用户独立明确批准。

SSH已被沙箱拒绝，按用户要求保留工作区交外层；不执行git add/commit/push或旁路。
`PUSH=NOT_RUN_SANDBOX_SSH_DENIED / TARGET_BRANCH=master / NEW_SHA=NONE / CI_RUN=PENDING`。
HEAD仍为基线，没有本轮提交哈希；不预填CI成功、不以旧SHA证据替代本次候选CI。
外层须先重核实时HEAD/origin/master/GitHub master、精确六路径与原字节、冻结和测试，
完成独立审阅后普通提交、非force推送master，再核对新SHA主CI/A4-1/A4-2/Publication及Linux Ruff。
若远端漂移应先停止核对；不自动进入W05-RUN或E06。
`NEXT=CHATGPT_INDEPENDENT_REVIEW`。

## 最终原字节与差异核验

最终 `git status --short --branch` 仍为master，恰好上述六条未跟踪路径；
HEAD/origin/master仍为基线。`git diff --exit-code HEAD --`、`git diff --check`、
`git diff --cached --check`均退出0；已有跟踪文件零差异，暂存区零变化。
普通git diff不展示未跟踪文件，因此另对六条路径逐条执行
`git diff --no-index --check -- NUL PATH`：全部无空白错误，退出1仅表示有新增内容。
Git现有LF/CRLF提示不作字节转换或配置修改；外层须审阅六份新增全文。

开始与结束对全部1629个已跟踪普通文件逐项计算原字节SHA256，按路径排序的JSON摘要均为
`830552489db1786a5233aac8616cd00cef5dde3e1a8c3d4cf3aa158558f670c5`。
这包括LAB-01/LAB-02、根Dockerfile/Compose、旧测试与治理文件；任务书摘要也与起始一致。
五份冻结同时核对HEAD Git blob和工作树规范LF Git blob（仅在内存中归一，未回写）：

| 冻结路径 | 两者均匹配的Git blob |
| --- | --- |
| `scripts/business_recalc_measure.py` | `782e45ba53c8de8df0d12ffa84c219855316cfda` |
| `scripts/biz_perf_p1_04_diagnostic.py` | `714f78017ec252791ac6a89f9fb0e0a984333c37` |
| `scripts/perf03_lnx_w04a_offline_contract.py` | `931fd4fec38551d9fac59791d2bde5ce0e6a1d48` |
| `scripts/biz_perf_03_b_once.py` | `2ea473491f590893ad575b90a0ba42f932e37129` |
| `scripts/business_sql_snapshot.py` | `e7532b0a0242f1e3d3b047fdc03fca7ffc3ce7c6` |

`OFFLINE_TESTS=112_NEW_985_TOTAL / FROZEN_5=UNCHANGED / FILES=6`。
`PUSH=NOT_RUN_SANDBOX_SSH_DENIED / NEW_SHA=NONE / CI_RUN=PENDING`。
不创建提交、不推送；全部候选文件留给ChatGPT外层独立审阅与常规交付。
