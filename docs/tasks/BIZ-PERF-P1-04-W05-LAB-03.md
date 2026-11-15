# BIZ-PERF-P1-04-W05-LAB-03：专用 Worker 运行域、PG17 私有网络接线准备（纯离线）

发起：2026-11-15；项目 ssh_stock；执行方：远程 ssssssh 电脑 Codex 桌面 **GP** 项目；ChatGPT 独立复测、代码审阅、安全推送、精确 SHA CI 验收。
**W00 基线**：本地 HEAD、origin/master、GitHub master `2c1583081cc2579a8b0e73d5a2e06923fd46ce4d`，主 CI #43666985057、A4-1 #43666985003、A4-2 #43666985033、Publication #43666985068 均 SUCCESS。起点工作树必须干净，除已由 ChatGPT 下发且未跟踪的本任务书外无额外脏文件。

## 任务定位（重要）
上一阶段 LAB-01 的 `infra/biz_perf_w05/compose.pg17.yaml` 是**只有 PG17 的独立 JSON 格式 Compose**，使用显式 UUID 命名的单独卷/私有 internal network、镜像 digest、仓库外 secret，默认手动 profile；它没有 Worker，也不能从宿主端口连接。LAB-02 的 `scripts/biz_perf_p1_04_w05_root_bridge.py` 仅有真实业务函数签名映射、无可执行 LiveBusinessPort/真实后验读取、仅 fake 测试通过。根 `Dockerfile` 默认启动 Web API，根 `docker-compose.yml` 引用项目 .env 并带 Scheduler/常驻 Worker，**绝不可直接用于 W05**。
**本轮目标不是继续修 E02–E05、重复造新的签名/审计/许可系统，也不是执行 W05-RUN**；而是填平一个真实物理部署拓扑缺口：交付一个只有独立、手动激活、默认拒绝业务执行的 **一次性 W05 Worker 运行域 Compose 叠加定义**、最小安全入口和基于该真实配置的静态反例测试。输出必须承认：未提供经审阅的真实 Worker image、PG17/Worker 实际连通性、强制硬预算或真实 root。

## P0 本轮禁令与不变量
- **本轮只写代码与文档、跑纯离线指定测试**。绝不执行 docker/docker compose（包括 config/build/up）、创建或清理容器/卷/网络、连接/创建 PG17 或旧库、运行 Worker/Scheduler/业务 Root/seed/迁移/SQL/EXPLAIN/云/任何性能实验；不得读取/修改生产 .env、已有 DB、生产凭据、真实 SSH/云资源。不得以测试通过宣称部署可用。
- 不修改原 `docker-compose.yml`、`Dockerfile`、`infra/biz_perf_w05/compose.pg17.yaml`、`scripts/biz_perf_p1_04_w05_lab_plan.py`、LAB-02 根桥、E02–E05、PRETEST/W05、backend、config、migrations、任何已有测试、requirements、workflow/CI/AGENTS/项目治理文件。
- 不能增加 `execute`、`run-live`、`up`、`start`、`cleanup`、`--permit` 等可以运行真实业务/PG 的成功执行模式；默认入口即使 Compose 误启动也只报告 **EXECUTION_NOT_AVAILABLE** 并非零退出，不能导入 app、加载 DB URL、触发实际 PG/Worker 连接。
- `ROOT_ATTEMPTS=0`、`HOTSPOT=NONE_PROVEN`、`REAL_PG17=NOT_RUN`、`REAL_WORKER=NOT_RUN`、`B_GATE=NOT_APPROVED`、`TARGETED_PG17_GATE=NOT_APPROVED`、`AUTHORIZATION=AUTHORIZATION_PENDING`、`BUDGET=DRAFT_NOT_APPROVED`。

## W01 读源码后明确架构限制
按 `AGENTS.md` 顺序阅读五份治理文件、PRD、设计、PROJECT_RULES/README，重点静态阅读 LAB-01 `compose.pg17.yaml`、`scripts/biz_perf_p1_04_w05_lab_plan.py`、LAB-01 PLAN、LAB-02 ROOT BRIDGE/INTEGRATION、项目 `Dockerfile` / 根 `docker-compose.yml` 和上阶段 CI 证据。确认：`RootBridge.run_offline`、`LiveBusinessPort.__new__` 均不支持实机；生产 `claim_next_job` 没有指定 job_id 参数，错领虽然拒绝后续执行但已发生 claim。这是未来实机操作的硬阻断，不能用本轮 Compose 掩盖。Codex 沙箱 GitHub SSH 被拒绝时依赖已由外层核对的基线，不变更 SSH/沙箱/Git 配置。

## W02 交付独立 worker Compose overlay —— 核心工程产物
新增 `infra/biz_perf_w05/compose.worker.yaml`，为可用 JSON 子集的 Compose overlay，**只添加一个命名清楚的 `w05_worker` 服务**；与既有 PG17 Compose 在同一项目的 `name: w05-${W05_RUN_UUID:?missing}`、同一 `private` internal network 上运行，但 worker 不追加外部网络、不新开对外端口、不引入第二份 PG/卷。注意 Docker Compose 合并语义可能与单文件静态分析不同，不能声称已通过真正的 `docker compose config`。
- worker 需有明确且无默认值的、待未来独立供应链审阅的 digest-pinned 镜像引用 `${W05_WORKER_PINNED_IMAGE:?missing}`，例如仅要求 `@sha256:<64 lowercase hex>` 格式。**严禁虚构真实 digest**；镜像包含本次入口模块与被锁定的业务源码/依赖仍需未来独立核对，禁止在本轮安装/构建它。
- `profiles: ["w05-worker-manual"]`、`restart: "no"`、`init: true`、独立单次运行，不允许 auto restart/后台无限轮询。默认 `entrypoint` 或 `command` 只能运行本轮新增且**永久默认拒绝真实操作**的 `scripts.biz_perf_p1_04_w05_worker_gate` 的 `review-offline`（如选择无入口时说明为何不能安全触发业务；绝对不得调用 `app.cli worker`、根桥实机装配、alembic、web server）。无额外业务镜像 Dockerfile 改动。
- 运行安全约束：linux/amd64、无 privileged/host networking/cap_add/devices/docker.sock、只读 rootfs（如果程序需要 tmp 使用受限 tmpfs）、非 root 的固定 numeric UID/GID、cap_drop ALL、no-new-privileges、pids limit、PG 之外不访问公网的 `private` 内网；不提供宿主机端口/宿主 bind/生产 host volume。
- Worker 3GiB 内存草案、`memswap_limit`、不自动启动 Scheduler、没有 `depends_on` 强制触发 pg17 启动（因为即使 profile 选择也**不能**隐式创建 PG17 资源）；如果 Compose 的并网需要它显式单列，请在说明中指出无法实机证明的合并/依赖行为。
- 连接设计以**非敏感声明**为主：数据库目标只能是 Compose service `pg17` 内网主机、端口5432、测试库 `w05_lab_test`、一个将来独立创建并验证权限的 `w05_lab_worker` 角色；不能包含真实用户名密码组合 URI、`DATABASE_URL` 连接串、PGPASSWORD、项目 `.env` 或未批准的源。仅用可审阅的内部主机/库/用户字段 `W05_DB_HOST/PORT/NAME/USER` 等，不加载全局项目变量。后续运行需要独立审阅的 secret 和最小权限连接器，当前**不实现**。
- 若复用 LAB-01 的 secret，必须避免 overlay 误以为已经证明文件内容/权限/新实例身份；最好不要给尚无连接器的 worker 挂 secret。没有真实凭据时应在文档写 `CREDENTIAL_NOT_WIRED`。绝不可为了“能通过”把生产 .env 带进来。
- 不要用 `depends_on`、`profiles`、`restart:no` 声称具备看门狗、外部硬终止、资源独占或真实授权。PG 4GiB、Worker 3GiB、卷 10GiB 和 CPU/IO/成本强制均只是假设配置，不是已验收现场证据。

## W03 默认拒绝的 worker 入口与最小静态校验
新增 `scripts/biz_perf_p1_04_w05_worker_gate.py` 和 `tests/unit/test_biz_perf_p1_04_w05_worker_gate.py`。
- 提供极短、标准库为主的 `main(argv=None)`：默认、`review-offline`、任何 `execute/run/up/start/cleanup/permit/force` 参数，全部固定脱敏 JSON 返回 `EXECUTION_NOT_AVAILABLE`（exit 2），无 `app`/SQLAlchemy/psycopg/dotenv/Docker/数据库导入，无 subprocess/network/env/.env/文件写入/后端 business 调用，唯一安全用途是被动表明该 worker 镜像仍未授权运行 root。脚本不能被 `approved=True`、环境变量、注入 argv 绕过。
- 再提供 `inspect_overlay(spec:dict)` 等离线纯函数，核验 W02 的**真实结构**（最好直接复用 LAB-01 `lab_plan._read_fixed_spec` 的固定文件只读习惯或使用固定相对路径），检查仅一个 w05_worker、profile、内网、无业务执行入口、rootfs / capabilities、镜像/pinned placeholder、资源限制、无外网/宿主卷/port/生产配置、无 real Worker invocation；仅结构审核，不读 Docker/secret/DB，不联网、不执行 Compose。可保持总代码 <= 220 行，少于范围就收口，**不要另造签名、持久日志、lease 或第四套审批系统**。
- 允许的正面状态仅 `TOPOLOGY_SPEC_REVIEWABLE_ONLY` 或 `BLOCKED`，都 `execution_available=false`, `real_network_verified=false`, `root_attempts=0` 和 gates NOT_APPROVED；输入 self-declared UUID、image digest、owner、approval 等不能改变。注意即使静态配置合规，Docker Compose 环境变量插值、overlay 组合、profiles 显式选服务可绕开默认保护；这不是实机安全性证明。

## W04 安全离线测试及准确交付
至少25项**有区分度**新测试，覆盖 overlay 字段固定白名单、禁挂外网/端口/bind/根 .env、错误 UID/特权/网络/auto start/auto restart、错误 image/missing digest/错误 PG host/db role、入口参数任意变体固定拒绝、任意伪装 approval/permit、无真实app或库导入、无进程/socket/file write、无主动启动 PG/Worker/Seeder/迁移能力。用进程内 mock 与明确子进程 no-socket/no-app-import 的离线测试；拒绝恶意替换固定文件/配置。**不得调用 Docker CLI/Compose config/build/up**。
回归：LAB-02（74 个）、LAB-01（84个）、W05-READY（133个）、PRETEST、E05/E04/E03/E02/W04A/假 PG guard 的离线测试集合；仅确定纯 fake 的显式文件清单，Windows 不跑全量 pytest，建议 `python -B -m pytest`；若 Windows 缺 Ruff 记 `ENV_BLOCKED`，不装依赖，以新 SHA Linux CI Ruff 为准。
新增 `docs/acceptance/BIZ_PERF_P1_04_W05_LAB03_TOPOLOGY.md` 只写明 PG 与 Worker 网络接线和仍不可执行的缺口，明确新 image 中必须包含 entry 模块、worker image digest 与源码 fingerprint、网络/secret/least privilege/独立可用性/硬预算/clean-up 等全部未来需核对。指出：
1. Worker overlay 只提供架构说明，不证明 Docker 引擎把 overlay 同 LAB-01 合并后的实际网络；不得用本轮测试结论为已连通 PG17；
2. 当前没有可用的 Session/LiveBusinessPort 装配与真实 PostRead/Seed/PG17 的运行入口，也没有空队列现场证据；
3. **真正进入实验需要先由用户明确批准全新资源创建、成本和唯一 root**，不能在此自动执行。
新增 `docs/acceptance/BIZ_PERF_P1_04_W05_LAB03_CLOSEOUT.md` 记录 RED→GREEN、实测测试数、精确路径白名单、静态校验、未测项、冻结不变量、Git/CI 待外层结果。不能预填 CI 成功。

## 唯一允许的6个新增路径
1. `docs/tasks/BIZ-PERF-P1-04-W05-LAB-03.md`（本任务书，原文保留）
2. `infra/biz_perf_w05/compose.worker.yaml`
3. `scripts/biz_perf_p1_04_w05_worker_gate.py`
4. `tests/unit/test_biz_perf_p1_04_w05_worker_gate.py`
5. `docs/acceptance/BIZ_PERF_P1_04_W05_LAB03_TOPOLOGY.md`
6. `docs/acceptance/BIZ_PERF_P1_04_W05_LAB03_CLOSEOUT.md`

所有已有文件零修改，五份历史冻结 Git blob 必须原样：
- `scripts/business_recalc_measure.py` = `782e45ba53c8de8df0d12ffa84c219855316cfda`
- `scripts/biz_perf_p1_04_diagnostic.py` = `714f78017ec252791ac6a89f9fb0e0a984333c37`
- `scripts/perf03_lnx_w04a_offline_contract.py` = `931fd4fec38551d9fac59791d2bde5ce0e6a1d48`
- `scripts/biz_perf_03_b_once.py` = `2ea473491f590893ad575b90a0ba42f932e37129`
- `scripts/business_sql_snapshot.py` = `e7532b0a0242f1e3d3b047fdc03fca7ffc3ce7c6`

## 开发、提交、独立审阅流程
必须使用远程 Codex 桌面软件 GP projectId=`01a15f75-2c79-7d30-9232-651a6ef4253d` 真正持久会话，名称 `BIZ-PERF-P1-04 W05-LAB-03 隔离Worker拓扑`，不可独立 `codex exec`。完成离线开发与安全测试后在有权限情况下普通 `git add/commit` + 非force `git push origin master`；若 Codex sandbox `.git/index.lock` 或 SSH 拒绝，不绕过，留工作区供 ChatGPT 外层审阅后常规安全推送，外层先独立核对 HEAD/origin/master/GitHub master 精确一致、只 6 路径、`git diff --check`、五 frozen 和测试。
随后 ChatGPT 独立核对新 SHA 的主 CI/A4-1/A4-2/Publication、Linux Ruff、完整回归；发现真正缺陷就给最小整改。最高验收状态 `W05_LAB03_TOPOLOGY_OFFLINE_ACCEPTED`，**并不解除真实环境/资源授权和 Worker 运行限制**。
Codex GP 最终回执包含 `TASK=W05-LAB-03`, `BASELINE_SHA=2c1583081cc2579a8b0e73d5a2e06923fd46ce4d`, `FILES=6`, `OFFLINE_TESTS`, `FROZEN_5`, `PUSH`, `NEW_SHA`, `CI_RUN`, `ROOT_ATTEMPTS=0`, `B_GATE=NOT_APPROVED`, `REAL_PG17=NOT_RUN`, `REAL_WORKER=NOT_RUN`, `NEXT=CHATGPT_INDEPENDENT_REVIEW`。
