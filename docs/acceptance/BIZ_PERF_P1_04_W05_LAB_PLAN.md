# W05-LAB-01 隔离 PG17 定义与未来操作边界

2026-11-15；源码起点 `80355a7fce8e165c30c67d88fc49f1386ffb10b6`。
本轮只交付独立资源描述、只读静态检查和离线测试。资源没有创建；
最高交付结论为 `LAB_SPEC_READY_FOR_OWNER_REVIEW`，独立审阅与精确提交 CI 待定。
检查器始终 `BLOCKED`；本文件、任务书、格式合规、自检与普通 CI 均不授予真实操作权限。

## 本次定义

`infra/biz_perf_w05/compose.pg17.yaml` 使用 YAML 的 JSON 子集，仅有一个 PG17 服务。
不引用根 Compose、项目 `.env`、`DOCKER_DATABASE_URL` 或应用环境；
不包含迁移、Seed、Worker、Scheduler、应用、端口映射、外部网络/卷、PGDATA bind、
设备、特权、host network、Docker socket、云连接或自动删除动作。
私有 internal bridge 网络、数据卷和项目名称均包含运行 UUID；重启策略为 `no`，
SIGINT/30s 描述数据库停止方式，不提供计时 watchdog 或自动结束能力。

| 未来显式输入 | 静态约束和现实边界 |
| --- | --- |
| `W05_RUN_UUID` | 规范小写 UUIDv4；拟议名称为 `w05-UUID`、`w05-UUID-pgdata`、`w05-UUID-private`。名称和标签不证明新建、归属或独占。启动前必须现场确认无同名项目、容器、卷、网络，不能复用已有资源。 |
| `W05_PG17_PINNED_IMAGE` | 无默认值；人工先独立审阅再提供 digest-pinned 镜像。内存校验仅接受 `docker.io/library/postgres:17@sha256:` 加64位小写十六进制；拒绝浮动标签、其他仓库/版本。格式不认证 digest 真实性、PG major、架构、入口点或供应链；仓库不提供任何声称真实的 digest。 |
| `W05_PG17_PASSWORD_SECRET_FILE` | 无默认值；未来仓库外独立 secret 文件。内存校验仅接受 `/run/w05-secrets/UUID/pg_password` 形式，不读取内容、不检查实际位置、不打印引用或口令；实际宿主路径、非链接、权限、挂载和保密来源仍需独立核验。不得提交 secret 或 `.env`。 |

数据库名为 `w05_lab_test`，初始化用户为 `w05_lab_owner`，通过
`POSTGRES_PASSWORD_FILE` 注入 secret，显式 SCRAM 本地/host 初始化认证，无 trust 配置。
PGDATA 为新命名卷中的 `pgdata` 目录，UUID marker 仅为配置声明；
物理 offline/online system_identifier 尚不存在可信观察。初始化用户权限、将来业务/采集角色
与访问方式需另审；当前没有可从宿主端口连接的客户端或真实执行适配器。
Compose file secret 在本地引擎可能以宿主文件挂载实现，不等于托管 secret 服务；
数据卷禁止 bind，secret 的挂载和权限不能由本次静态检查证明。

| 预算项 | 本轮定义 / 缺口 |
| --- | --- |
| PG RAM | 草案4GiB；`mem_limit=4g`、`memswap_limit=4g` 为配置声明，真实 cgroup、引擎行为、swap/OOM 和停止控制尚未核验。 |
| 数据卷 | 草案10GiB；`NOT_ENFORCED`，命名卷没有可移植磁盘 quota，不能称已强制限额。 |
| 磁盘 IO / CPU 容量 / cgroup | `NOT_ENFORCED`；无真实观察或批准的 CPU、IO、费用上限。累计 CPU 时间不表示配额。 |
| 时间与其他服务 | 沿用20min/末5min、Worker3GiB、证据10MiB的待签认草案；本定义仅 PG 服务，不配置 Worker。创建、seed、迁移/预热、root、post、cleanup 是否计入及各自上限/成本仍待签认。 |

所有预算保持 `DRAFT_NOT_APPROVED`。无自动重启不等于自动停止：人工停止主体、
外部超时控制、异常时的成本结束及已证明归属资源的清理均是实机前阻断项。

## 静态检查的使用和限度

唯一 CLI 是安全的只读检查：

```text
python -B -m scripts.biz_perf_p1_04_w05_lab_plan review-offline
```

CLI 不读环境变量，不接收文件路径或操作开关；缺少显式输入时报告缺项并退出2。
少量拟议值只通过 `review(values)` 内存参数传入，固定键为
`run_uuid`、`pinned_image`、`password_secret_file`；不接受 owner/approval/permit 等自述证明。
即使三项格式全部合规，仍 `status=BLOCKED / live_resource_verified=false / root_attempts=0`，
`B_GATE=NOT_APPROVED / TARGETED_PG17_GATE=NOT_APPROVED / authorization=AUTHORIZATION_PENDING`。
输出仅拟议名称、固定预算缺口与实际待核验事项，不回显镜像、secret 引用或其他输入。
execute/up/cleanup/allow/force/permit、未知子命令/参数均在读取前退出2。

检查器只读唯一固定仓库文件，拒绝重复 JSON 键、非 JSON YAML 扩展、链接/reparse point、
多硬链接、超32KiB或读取前后身份/内容属性变化；使用精确结构白名单拒绝未知字段和插值改写。
要求仓库祖先可信且稳定，不证明恶意管理员、挂载置换、文件系统竞态或实际容器隔离。
未调用 Compose 解析器；变量插值本身没有 PG major/UUID/外部 secret 路径校验能力，
用户可在未来绕过本检查提供别的值。profiles 只是手动选择约束，显式选服务可能绕过 profile；
也不能阻止 Compose 自动发现 `.env`、外部覆盖文件或运行环境注入。
因此定义和检查结果不能当成启动门禁或安全隔离证明。
未来实际渲染后的完整配置、输入来源、禁止项目 `.env` 的调用环境与精确镜像均需另行审阅；
本轮没有执行任何 Compose 命令，也没有给出启动或销毁命令。

## 从空环境到未来可测量的必要准备

负责人后续必须单独明确批准新隔离资源创建与单次真实实验。以下是准备顺序，
不构成该批准，也不新增通用审批、签名、审计、lease 平台：

1. 确定真实受控 Linux x86_64/PG17 资源、具名责任人、外部观察人、成本承担人及窗口。
   核实镜像来源与 digest、资源名称未占用、实际网络/卷/cgroup/磁盘预算和终止控制。
2. 独立取得 PG17 全新初始化、新库、独占 PGDATA、marker、offline/online 物理身份、
   owner/lease 与清理归属证明；环回、标签、名称和自述 system_identifier 均不足。
3. 另审真实执行适配与正确 root/post 采集；保留 E02 根计数在 Worker finally 返回后冻结，
   冻结后才独立核验 Job/ledger/source/逐表摘要/公开结果与无B泄漏。当前无此真实适配器，
   不可直接运行冻结测量器或把 E03 mock 换成真实 Executor。
4. 签认创建、seed、迁移/预热、root、post、cleanup 六段的纳入关系、限额、外部停止与费用；
   明确原始证据保管、结束确认、失联及 `UNKNOWN_ACK` 人工处置。失败不补样、不重试、不自动释放占用。
5. 固定最终实施 SHA、真实主CI/A4-1/A4-2/Publication run/attempt/Job/Step及独立审阅结果，
   再由负责人发出具名、具窗口、唯一 UUID 的全新单次授权。不得用本轮离线交付代替。

将来输入仍为8股、2025-01、900日历日 Seed、五开关 OFF、一次 root；5320股日仅静态规则，
真实逐表数据与摘要尚未生成。PIT、250交易日预热、430日历日回看、500行批次、300秒发布预算、
原像、质量、取消、心跳、原子发布及未知 ACK 语义不变，E05/E04/E03/E02 既有边界不变。

未来第一次真实测试只调查 H01 输入读取/计算、H02 候选查找与写入、H03 发布前后验证的
wall/SQL/FETCH/CPU/RSS 归因。未测保持 UNKNOWN/NOT_INSTRUMENTED；inclusive 重叠不求和，
root 包含 Worker、post 独立；不能从离线夹具确认瓶颈、宣称提速或报告单样本 P95/P99。
`HOTSPOT=NONE_PROVEN / REAL_PG17=NOT_RUN / REAL_WORKER=NOT_RUN`。
