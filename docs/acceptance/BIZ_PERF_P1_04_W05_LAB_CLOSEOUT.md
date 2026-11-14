# W05-LAB-01 离线交付回执

2026-11-15；`TASK=BIZ-PERF-P1-04-W05-LAB-01`。
本次在当前 Codex 桌面会话执行，未另开 `codex exec`。
会话归属及名称由桌面宿主管理，本轮未通过接口独立核验 projectId/会话名称元数据。
交付候选状态：`LAB_SPEC_READY_FOR_OWNER_REVIEW / REVIEW_PENDING / CI_PENDING`。
资源准备检查始终 `BLOCKED`，该交付状态不表示实机就绪或真实测试获准。

## 基线、阅读和范围

- 首条 Git 命令为 `git status --short --branch`：master，唯一未跟踪文件为负责人下发的任务书。
  HEAD 与 origin/master 均为 `80355a7fce8e165c30c67d88fc49f1386ffb10b6`。
- `git ls-remote origin refs/heads/master` 失败（执行工具报告退出1）：沙箱拒绝 GitHub SSH 22端口。
  未绕过、未更改代理/Git设置，不能独立保证 GitHub 最新 master；使用任务书/外层已核实基线。
  任务书列明四条历史 CI SUCCESS，本轮没有独立重查或借用为本次候选结果。
- 按序读取五份治理文件及相关 PRD、系统设计、PROJECT_RULES、README；随后核对父任务、
  隔离申请草案、W05-READY评估/操作员清单与R1任务书、E03三个源码及资源/PG17身份合同。
  静态核对生产 Compose、v14 guard、冻结测量器调用链；未调用真实连接、迁移或测量入口。
- 用户最新六文件白名单优先于旧治理指针/四文档维护要求；未修改旧治理、PRD或任何跟踪文件。
  任务书原文保留，原始字节 SHA256 为
  `439d758052c34f299c2510be771bc4e8444fa9b0e36cdcda28b82aee13bb949d`。

仅新增以下六条路径（包含原已下发任务书）：

1. `docs/tasks/BIZ-PERF-P1-04-W05-LAB-01.md`
2. `infra/biz_perf_w05/compose.pg17.yaml`
3. `scripts/biz_perf_p1_04_w05_lab_plan.py`
4. `tests/unit/test_biz_perf_p1_04_w05_lab_plan.py`
5. `docs/acceptance/BIZ_PERF_P1_04_W05_LAB_PLAN.md`
6. `docs/acceptance/BIZ_PERF_P1_04_W05_LAB_CLOSEOUT.md`

## RED → GREEN 和验证事实

| 验证 | 实际结果 |
| --- | --- |
| RED：先新增用例，检查器未实现 | 新模块 ImportError，1 collection error，执行工具报告退出1；未调用任何真实资源。 |
| 首次实现 | 78 passed / 1 failed，退出1；真实文件读取更新 atime 后被误拒绝。 |
| atime 定向 RED | 增加访问时间、内容变化、链接负例后，80 passed / 3 failed，退出1；访问时间定向用例复现缺陷。 |
| 修正 GREEN | 读取前后比较 dev/ino/size/mtime/mode/nlink，保留链接与变化拒绝；83 passed，退出0，0.08s。 |
| 首轮指定离线集合 | 798 passed，退出0，24.75s。 |
| 最终指定离线集合 | 补充 secret 路径尾换行负例后，799 passed，退出0，24.41s；无测试失败或跳过。 |
| Ruff | `python -B -m ruff check scripts/biz_perf_p1_04_w05_lab_plan.py tests/unit/test_biz_perf_p1_04_w05_lab_plan.py` 退出1：No module named ruff；`ENV_BLOCKED`，未安装/升级；待新SHA Linux CI核验。 |
| 源码 AST / 行数 | 两个新增 Python 文件解析成功；检查器173行（≤250），两文件均无超过100字符行。AST断言仅标准库依赖，无连接/执行/写入 API。 |
| 导入/只读/负例 | 合成模块导入禁止文件访问，review仅允许固定Compose的rb读取；拒绝socket、子进程、os.system/getenv。覆盖秘密引用、错误镜像/UUID、自述权限、危险Compose配置和CLI。 |
| 根 Compose / 旧路径 | 根Compose规范LF字节 SHA256 `9c67276868fe2daff1a9d88772f0e070b538830cf28554d261a4e2ac2f6fcf9e`匹配；旧跟踪文件零差异。 |

最终纯离线命令（保持默认源码合同插件，未降低断言/跳过/容差）：

```text
python -B -m pytest tests/unit/test_biz_perf_p1_04_w05_lab_plan.py tests/unit/test_biz_perf_p1_04_w05_readiness.py tests/unit/test_biz_perf_p1_04_pretest_report.py tests/unit/test_biz_perf_p1_04_e05_audit.py tests/unit/test_biz_perf_p1_04_e05_checkpoint.py tests/unit/test_biz_perf_p1_04_e04_packet.py tests/unit/test_biz_perf_p1_04_e04_journal.py tests/unit/test_biz_perf_p1_04_e04_review.py tests/unit/test_biz_perf_p1_04_e03_guard.py tests/unit/test_biz_perf_p1_04_e03_evidence.py tests/unit/test_biz_perf_p1_04_e03_collectors.py tests/unit/test_biz_perf_p1_04_measure_wiring.py tests/unit/test_biz_perf_p1_04_diagnostic.py tests/unit/test_perf03_lnx_w04a_offline_contract.py tests/unit/test_r1_integration_pg_guard.py -q -p no:cacheprovider
```

两轮集合均在退出时出现 pytest 临时目录 `pytest-current` 的 WinError 5：
atexit cleanup PermissionError 被解释器忽略；进程退出0、测试通过，但临时链接清理未完成。
未对该目录执行删除、改权限或规避沙箱。该环境限制不应被隐去，也不证明任何实机能力。
测试的 Python 子进程只用于已有离线拒绝入口/文件日志模型，不是 Worker/Scheduler。

## 冻结和历史语义

以下 index blob 与工作树规范LF计算的 Git blob 均逐项匹配；工作树未被规范化改写：

| 冻结路径 | Git blob |
| --- | --- |
| `scripts/business_recalc_measure.py` | `782e45ba53c8de8df0d12ffa84c219855316cfda` |
| `scripts/biz_perf_p1_04_diagnostic.py` | `714f78017ec252791ac6a89f9fb0e0a984333c37` |
| `scripts/perf03_lnx_w04a_offline_contract.py` | `931fd4fec38551d9fac59791d2bde5ce0e6a1d48` |
| `scripts/biz_perf_03_b_once.py` | `2ea473491f590893ad575b90a0ba42f932e37129` |
| `scripts/business_sql_snapshot.py` | `e7532b0a0242f1e3d3b047fdc03fca7ffc3ce7c6` |

E05/E04/E03/E02、PRETEST、W05/R1及W04A原源码/测试未改。
无并行审计状态机、签名/审批框架、真实执行/清理适配器、permit或新业务逻辑。
前次 `OWNER_SIGNOFF_PENDING`、E04/E05永久占用/UNKNOWN_ACK人工处置、E02根冻结和post分离不变。
PIT、Decimal、版本身份、原像、质量、取消/心跳、原子发布及所有金融语义未变。

## 实机不可做、交接和剩余风险

本轮未运行全量 pytest、覆盖率、Alembic、真实SQL/EXPLAIN、PG17、Seed、Worker、Scheduler、
Docker/Compose config/build/up、云资源、性能测量或清理。用户明确禁止本次执行Compose，
因此未运行通用验证矩阵中的Compose命令；未声称配置已获Docker运行时验证。
内存里的镜像digest与UUID全是虚构格式测试，不能用于实际启动。
具体预算、profiles/插值/secret/配额与真实身份缺口见[操作说明](BIZ_PERF_P1_04_W05_LAB_PLAN.md)。

永远保持：`ROOT_ATTEMPTS=0 / HOTSPOT=NONE_PROVEN / REAL_PG17=NOT_RUN / REAL_WORKER=NOT_RUN`，
`B_GATE=NOT_APPROVED / TARGETED_PG17_GATE=NOT_APPROVED / AUTHORIZATION=AUTHORIZATION_PENDING`，
`BUDGET=DRAFT_NOT_APPROVED`。尚缺真实受控资源及外部观察、新建归属证明、真实root/post接线、
六段预算/费用签认、具名责任人与新的单次明确授权。H01/H02/H03仅待调查方向，瓶颈UNKNOWN。

Git提交/推送和最终差异检查结果在下方追加；本文件不预填自身最终SHA或CI成功。
下一步仅由ChatGPT外层独立核对精确提交与四条CI，再交负责人审阅；不能从代码交付自动进入执行。

## Git交付结果

普通 `git add --` 精确六条白名单路径尝试一次失败（执行工具报告退出1）：
`Unable to create .git/index.lock: Permission denied`。没有重试、提权、绕过或改Git配置。
因暂存失败，未运行commit或push；SSH此前已被拒绝，不再重复尝试。
`FINAL_SHA`仍为起点 `80355a7fce8e165c30c67d88fc49f1386ffb10b6`，无本次新提交哈希；
`PUSH=NOT_RUN / TARGET_BRANCH=master / CI_RUN=PENDING`。
六文件保留在工作区，供ChatGPT外层常规PowerShell独立验证后安全提交推送。
外层需重新核对HEAD/origin/master/GitHub master一致、六路径及冻结文件，不能把缓存的origin/master当远端实时值。

最终差异审计：`git diff --check`、`git diff --cached --check`均退出0；
`git diff --exit-code HEAD --`退出0，旧跟踪路径零差异；未跟踪文件集合与六文件白名单精确相等。
另对六个新增文件逐个执行`git diff --no-index --check -- NUL PATH`，均无空白错误输出；
命令退出1表示存在新增差异，stderr仅现有Git的LF→CRLF提示，未修改Git配置或任务书字节。
检查器/测试AST、JSON子集解析和五冻结blob均通过；这些静态结果不能替代尚未执行的Linux CI/Ruff或实机隔离核验。
