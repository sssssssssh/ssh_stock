# W05-LAB-03 专用 Worker 与 PG17 接线准备

2026-11-15；基线 `2c1583081cc2579a8b0e73d5a2e06923fd46ce4d`。
仅交付 JSON Compose overlay、固定拒绝入口和离线结构检查；真实网络与业务执行均未验证。
`ROOT_ATTEMPTS=0 / HOTSPOT=NONE_PROVEN / REAL_PG17=NOT_RUN / REAL_WORKER=NOT_RUN`。
`B_GATE=NOT_APPROVED / TARGETED_PG17_GATE=NOT_APPROVED`，
`AUTHORIZATION=AUTHORIZATION_PENDING / BUDGET=DRAFT_NOT_APPROVED`。

## 配置接线与实际边界

| 定义 | 本次静态内容 | 尚未取得的证据 |
| --- | --- | --- |
| LAB-01 `infra/biz_perf_w05/compose.pg17.yaml` | 原字节保留；仅 `pg17`、新命名卷、`private` internal bridge、仓库外 secret 引用，无宿主端口 | PG17 镜像真实性、新实例/卷/物理身份、secret 内容/权限、真实引擎网络 |
| LAB-03 `infra/biz_perf_w05/compose.worker.yaml` | 只增加 `w05_worker`，项目名仍为 `w05-${W05_RUN_UUID:?missing}`，仅引用同一个 `private` | 两文件实际合并、插值后完整配置、DNS/连接、独占性和停止行为 |
| Worker 连接声明 | `W05_DB_HOST=pg17`、`W05_DB_PORT=5432`、`W05_DB_NAME=w05_lab_test`、`W05_DB_USER=w05_lab_worker` | 没有连接器、Session factory、真实角色或权限证明；`CREDENTIAL_NOT_WIRED` |
| Worker 镜像 | `${W05_WORKER_PINNED_IMAGE:?missing}` 无默认值；`pull_policy=never`，本轮无真实 digest、无镜像供应或构建 | 独立供应链审阅、有效 digest、linux/amd64、Python/入口/源码/锁定依赖和 fingerprint |

拟议关系是同一项目的 `w05_worker → private → pg17:5432/w05_lab_test`。
这只是配置引用关系，**没有真实连接，也没有任何 SQL**。
overlay 不重定义 network、PG 或卷，单独使用时缺少 `private` 定义；必须依赖 LAB-01 同项目定义。
本轮没有执行真正的 Compose 合并或 config，Python 字典检查不能替代引擎合并语义。
overlay 无 `depends_on`，不提供隐式启动 PG 的依赖；未来操作仍可能显式选择其他服务或资源，
不能以该字段缺失证明 Compose 从不创建网络/PG/卷。必须独立核验完整调用环境和资源计划。

`w05-worker-manual` profile、`restart=no`、`init=true` 描述手动单次运行域；
不运行常驻轮询，不启动 Scheduler。固定数字 UID/GID `10001:10001`、只读 rootfs、
`cap_drop=ALL`、`no-new-privileges:true`、64 pids、3GiB RAM/swap 同限只是声明。
程序不需临时写入，本版不挂 tmpfs、宿主目录、secret 或其他卷；没有端口、外网、设备、
特权、Docker socket、build、healthcheck 或启动 hook。
镜像实际用户/文件权限与内核隔离仍待现场证明；本次未修改任何 Dockerfile。

根 Dockerfile 默认启动 Web API，且没有 COPY 本次 scripts；根 Compose 引用项目 `.env`，
带迁移、长期 Worker 和 Scheduler，**不得直接用于 W05**。
未来独立 Worker image 必须包含 `/app/scripts/biz_perf_p1_04_w05_worker_gate.py`，
让 `/app` 下的模块可导入，并核对入口原字节与被冻结业务源码/依赖的 fingerprint。
本版不提供这样的镜像。镜像不存在、模块缺失或权限错误只会失败，不能因此改用根业务入口。

## 固定拒绝与结构检查

overlay 的 entrypoint 为 Python `-B -m scripts.biz_perf_p1_04_w05_worker_gate`，
command 为 `review-offline`；覆盖镜像默认 API 命令，但不认证镜像内部行为。
模块 `main(argv=None)` 忽略全部参数，任何模式均仅打印固定脱敏 JSON
`status=EXECUTION_NOT_AVAILABLE` 并返回2。即使传入 approved/permit/force，仍没有执行分支。
入口不读取 overlay、环境变量、secret、`.env` 或 DB URL，不导入 app/DB库，不创建进程或网络。

独立纯函数 `inspect_overlay(spec, pinned_image=...)` 做精确字段/值白名单检查，
未知字段、布尔与整数混淆、PG目标/角色变更、业务入口、挂载、外网或伪授权全部拒绝。
可选镜像参数仅检查非空引用加 `@sha256:` 与64位小写十六进制的语法，不检查 digest 存在/真实性。
不传镜像参数时只检查未插值占位符；它不是镜像已就绪的证明。
`review()` 仅显式只读固定 overlay：32KiB 上限、无重复 JSON key/NaN/YAML扩展，
拒绝链接/reparse point、多硬链接、非普通文件和可观察的读取前后身份变化。
它不读取 LAB-01、secret 或任意用户指定路径；祖先目录须可信稳定，不防御管理员替换或所有竞态。

合规结果最高为 `TOPOLOGY_SPEC_REVIEWABLE_ONLY`；其他为 `BLOCKED`。
二者始终 `execution_available=false / real_network_verified=false / root_attempts=0`，
镜像真实性为 false，两 Gate 始终 NOT_APPROVED。结果不会安装许可或自动运行能力。
CLI 始终拒绝，结构检查只能通过显式 Python 函数/本次离线测试调用。
Compose 环境插值可接受其他 UUID/镜像值；默认 `.env` 发现、额外 overlay、显式选择服务绕过 profile、
命令行覆盖 entrypoint/command 均不由本检查控制。配置合规与测试通过都不是实机安全证明。
未来必须在不加载项目 `.env` 的独立环境审阅插值输入和最终完整配置。

## 真实实验前仍阻断

1. 独立审阅的镜像 digest、入口/源码/依赖 fingerprint、真实私网合并、PG17/Worker 连通、
   仓库外 secret 与最小权限连接器；当前没有挂载凭据，也没有创建 `w05_lab_worker` 角色。
2. 新 Linux/PG17/PGDATA/卷/网络的归属、新鲜性、物理 system_identifier/marker、空队列与
   无其他入队者/Worker/Scheduler 的现场证明。UUID、名称或 owner 自述不能代替。
3. LAB-02 `RootBridge.run_offline` 只支持 fake；`LiveBusinessPort.__new__` 固定拒绝。
   没有可用 Session/LiveBusinessPort 装配、真实 PostRead/Seed/PG17 运行入口。
   `claim_next_job(db, worker_id)` 无目标 job_id 参数，错领虽能阻止后续执行，claim 已发生；
   若需 claim 前按 ID 约束，必须另批后端变更，不能用本次拓扑掩盖。
4. PG4GiB、Worker3GiB、卷10GiB、20min/末5min和证据10MiB均为未批准草案。
   CPU/IO/磁盘配额、外部 watchdog/cgroup 硬终止、资源独占、成本结束、失联/UNKNOWN_ACK
   处置、独立退出观察和已证明归属资源的 cleanup 仍缺失。profiles/init/restart 不提供这些能力。
5. 创建、seed、迁移/预热、root、post、cleanup 的预算与失败退出、真实来源/逐表数据摘要、
   实际 SQL/FETCH/stage 采集和独立终态读取需另审；不变更 E02–E05、五 OFF 和冻结业务口径。
6. **用户必须明确批准全新资源创建、成本与唯一 root**，并固定最终实施 SHA 的独立复测与
   四条 CI 证据、责任人和操作窗口，才可考虑未来实验。本次无批准、无 W05-RUN、无自动接续。

下一步仅 ChatGPT 外层独立审阅与普通交付；普通 CI 不签发现场、容量或生产资格。
