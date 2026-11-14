# BIZ-PERF-P1-04-W05-LAB-01：全新隔离 PG17 实验环境定义与离线核验

发起：2026-11-15。代码执行：远程 ssssssh 的 Codex 桌面 **GP 项目**。独立审阅、Git/CI 追踪：ChatGPT。
固定基线：`80355a7fce8e165c30c67d88fc49f1386ffb10b6`；对应主 CI `43607325209`、A4-1 `43607325218`、A4-2 `43607325244`、Publication `43607325253` 全部 SUCCESS。工作树应干净。

## 任务定位和结果

本项目已经开发 E02–E05、PRETEST-01、W05-READY/R1，离线测试与代码审阅完成；**现在不再建设新的通用审计/身份/授权框架**。下一步真正的阻断是没有全新隔离 PG17 实验环境，以及无可被批准的实机资源来源。Codex 本轮仅准备**一份能在用户将来明确授权后使用的、独立于生产 docker-compose 的实验环境定义**，再用离线静态测试验证其明显风险。当前不得启动它。本次不实现实际 Worker/root 运行器，不伪装已有实际实验能力。
范围仅**新隔离 PG17 资源描述 + 非执行静态检查 + 一份精简操作者手册**，不要再做 W05-READY 重复清单，不改股市业务代码。

## W00 基线检查与阅读

1. 先 `git status --short --branch`，`git rev-parse HEAD`，`git rev-parse origin/master`，核验上面 SHA；只允许用户下发的本任务书作为未跟踪文件。未预期脏文件/源版本漂移则停止。若 Codex 沙箱阻断 GitHub SSH，不尝试越权，使用外层已核实 SHA，但注明不独立保证远端状态。
2. 按 `AGENTS.md` 指定顺序阅读五份治理文件、PRD/系统设计/PROJECT_RULES/README；尤其阅读 `docs/tasks/BIZ-PERF-P1-04.md`、`docs/acceptance/BIZ_PERF_P1_04_ISOLATED_RUN_REQUEST_DRAFT.md`、`docs/acceptance/BIZ_PERF_P1_04_W05_READY_ASSESSMENT.md`、`docs/acceptance/BIZ_PERF_P1_04_W05_OPERATOR_CHECKLIST.md` 和 R1 任务书。
3. 静态核对现有 `docker-compose.yml`（包含项目 `.env`、migration/worker/scheduler，禁止复用）、`scripts/v14_test_database.py`（会连接、迁移/删库，不调用）、`scripts/business_recalc_measure.py`（冻结，含真实 DDL/DML，不调用）、E03 资源预算和 PG17 身份合同。源码比对、无资源行为。

## A. 独立实验环境定义（必须交付）

新增 `infra/biz_perf_w05/compose.pg17.yaml`，定义仅用于未来人工另行授权启动的**全新 PG17 数据库**（如果明确需要额外辅助服务，先在文档写缺口，本轮不增加 Worker/Scheduler/应用或自动迁移服务）。
必要特征：
- 不使用当前根目录 `docker-compose.yml`、项目 `.env`、`DOCKER_DATABASE_URL`、生产数据库凭据、已有 volumes/host path；不从既有系统服务继承环境。
- 必须显式传入**提前独立审阅的、digest-pinned PG17 镜像**；禁止 `:latest` 和仅 `postgres:17` 浮动标签。**不能编造真实 digest**；可通过 Compose `image: ${W05_PG17_PINNED_IMAGE:?missing}` 形式从未来可信输入填入。静态检查必须拒绝非 PG17 的 `@sha256:` 全长值，实际镜像真实性仍需独立核验。
- 私有网络，不映射任何宿主机端口，不使用 external:true 网络，限制服务启动为手动 profile；禁止默认应用、常驻 Worker、Scheduler、云连接、生产数据库 DNS；无 privilege/host network/docker socket/device mount。
- 专属按运行 UUID 命名的全新数据库卷和网络，禁止 bind mount、外部 volume、复用普通命名资源；但请如实说明**名字唯一并不证明资源新建/独占，未来要在启动前现场核验并确保不存在同名资源**。
- 登录信息通过未来**仓库外**的单独 secret 注入，禁止硬编码真实口令、trust auth、提交任何 secret 或 `.env`，禁止 stdout 输出密码。
- 数据库资源预算草案：PG RAM 4GiB、卷 10GiB 为拟定上限；Compose 无法保证的真实磁盘 I/O、quota、cgroup、CPU 容量必须标成 `NOT_ENFORCED`，不能把自述限额当强制。安全停止/no automatic restart；绝不包含删除资源的自动动作。
- 对参数缺失/不可信镜像、未确定 ownership 和成本时，静态准备检查应固定 `BLOCKED`。
- 既有 8 股、2025-01、900 日历日 Seed、五开关 OFF、一次 root 仍为后续实验约束；本次配置**只描述 PG 服务**，不生成 Seed、因子、业务任务或原始性能证据。

## B. 一次性静态预检脚本（小而可测）

新增 `scripts/biz_perf_p1_04_w05_lab_plan.py`（目标 <=250 行，超过需要删减功能而非抽新平台）及 `tests/unit/test_biz_perf_p1_04_w05_lab_plan.py`。使用 Python 标准库+已在锁文件中的依赖（不要装/升级），以**只读**方式加载上面**唯一固定仓库 Compose 文件**并做有限内容/变量结构检查，另接受少量显式内存传入值；严禁读生产 .env / 连接 Docker/DB/网络/子进程/文件写入。
- 显示合成资源命名方案和预算缺口，不输出密码、不展开实际 secret 内容。输出 `mode=OFFLINE_LAB_SPEC_REVIEW`，`status=BLOCKED` 或 `SPEC_REVIEWABLE_ONLY`，`live_resource_verified=false`，`root_attempts=0`，`B_GATE=NOT_APPROVED`，`TARGETED_PG17_GATE=NOT_APPROVED`，`authorization=AUTHORIZATION_PENDING`，并列出实际待核验项目。
- 只允许 `review-offline`（或只暴露纯函数+测试），如有 `execute` / `up` / `cleanup` / `--allow` / `--force` / `--permit` 等全部固定 exit 2，不执行系统命令。无入口连接 PG/启动容器/释放卷、无其他 CLI 执行子命令。
- 不允许仅自述 `new_volume=true`、`approval=true`、镜像 digest、system_identifier 就返回已验证；静态输入仅能证明格式，不能证明环境存在、镜像真实、独占或安全。
- **避免重复实现 E03–E05**：既有 evidence/authorization/lease 系统一律只读参考，不引入并行审计状态机。

## C. 离线测试与操作者手册

新增 `docs/acceptance/BIZ_PERF_P1_04_W05_LAB_PLAN.md`：简要说明从空环境到未来可测量的边界；明确仍缺（1）真实受控 Linux/PG17 资源及外部观察，（2）PG17 新建和归属证明，（3）真实执行适配及正确 root/post 采集，（4）预热/seed/迁移/root/post/cleanup 的预算签认，（5）具名责任人和单次新授权。建议准备资源步骤与人工检查项，但不得提供可以在本轮误执行生产删除/运行脚本的命令。
补充业务效果目标：未来第一次真实测试只给出 H01 输入读取/计算、H02 候选查找与写入、H03 发布前后验证的指标归因，缺失为 UNKNOWN，不能从离线夹具声称已确认瓶颈。
新增 `docs/acceptance/BIZ_PERF_P1_04_W05_LAB_CLOSEOUT.md`：真实交付的路径、RED→GREEN、测试统计、静态可做与实机不可做的明确边界、冻结文件和前次审批状态。
测试至少 20 个针对性用例，重点检查禁止 .env 引用、既有 docker-compose 未修改、无 host ports、digest 不是浮动 tag、错误镜像/UUID/秘密、外部卷/bind/docker.sock/privileged/host network/自动 restart/启动应用/worker、不可信自述、离线 CLI 拒绝、无写入及网络调用。若 Compose 变量插值或 profiles 无法保证这些安全条件，请在报告里写明，不能宣称已证明安全隔离。新脚本应有不连接数据库的安全导入测试。

只运行确认纯离线的新增用例及 W05-READY/PRETEST/E05/E04/E03/E02/冻结 diagnostic/W04A/fake PG guard；本机 Windows 不运行潜在数据库相关的全量 pytest。用 `python -B -m pytest`；`python -B -m ruff` 如本机缺包记 `ENV_BLOCKED`，不可安装/升级依赖。之后新提交的 Linux CI 验证 Ruff。检查 `git diff --check`、五冻结 blob SHA、旧跟踪文件零差异及源文件 AST。

## D. 精确白名单与历史不变量

只允许新增六份文件：
1. `docs/tasks/BIZ-PERF-P1-04-W05-LAB-01.md`（本任务书，原文保留）
2. `infra/biz_perf_w05/compose.pg17.yaml`
3. `scripts/biz_perf_p1_04_w05_lab_plan.py`
4. `tests/unit/test_biz_perf_p1_04_w05_lab_plan.py`
5. `docs/acceptance/BIZ_PERF_P1_04_W05_LAB_PLAN.md`
6. `docs/acceptance/BIZ_PERF_P1_04_W05_LAB_CLOSEOUT.md`
以上实际为**六份**，仅六份，任何新增或修改其他跟踪路径均需停止。不得更改 docker-compose.yml / Dockerfile / requirements / CI workflow / .env / backend/frontend / v14_test_database / 冻结文件 / E02–E05/W05/R1/PRD/治理历史。

五冻结 blob：
- `scripts/business_recalc_measure.py` = `782e45ba53c8de8df0d12ffa84c219855316cfda`
- `scripts/biz_perf_p1_04_diagnostic.py` = `714f78017ec252791ac6a89f9fb0e0a984333c37`
- `scripts/perf03_lnx_w04a_offline_contract.py` = `931fd4fec38551d9fac59791d2bde5ce0e6a1d48`
- `scripts/biz_perf_03_b_once.py` = `2ea473491f590893ad575b90a0ba42f932e37129`
- `scripts/business_sql_snapshot.py` = `e7532b0a0242f1e3d3b047fdc03fca7ffc3ce7c6`

## E. 交付、提交与独立审阅

使用 Codex 桌面软件归属 **GP projectId=01a15f75-2c79-7d30-9232-651a6ef4253d** 的真正持久会话，名称 `BIZ-PERF-P1-04 W05-LAB-01 隔离实验环境准备`，不可独立 `codex exec`。完成本地白名单、静态和回归校验后，尝试一次普通 git add/commit、非强制 push；若 Codex .git 写入/SSH 被拒，绝不可越权，由 ChatGPT 外层正常 PowerShell 在完成独立验证、检查 HEAD/origin/master/GitHub master 一致后安全提交推送。
ChatGPT 接收后审阅精确 SHA 的主 CI、A4-1/A4-2/Publication，检查测试、Ruff、隔离定义内容、文档明确声明的残余阻断；如失败仅给最小整改。**此阶段结论最高为 `LAB_SPEC_READY_FOR_OWNER_REVIEW`，不得宣称真实资源已创建或真实测试已获授权。**

永久红线：`ROOT_ATTEMPTS=0`，`HOTSPOT=NONE_PROVEN`，`REAL_PG17=NOT_RUN`，`REAL_WORKER=NOT_RUN`，`B_GATE=NOT_APPROVED`，`TARGETED_PG17_GATE=NOT_APPROVED`，`AUTHORIZATION=AUTHORIZATION_PENDING`，`BUDGET=DRAFT_NOT_APPROVED`。下一步必须由负责人**单独明确批准**新隔离资源创建与单次真实实验，不要自动派生新的审计阶段。
