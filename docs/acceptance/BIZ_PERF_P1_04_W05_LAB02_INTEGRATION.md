# W05-LAB-02 单根业务桥与尚未批准的实机接线

2026-11-15；静态源码基线 `109921758eb949b4e986b08c58b3d3f6b117bd94`。
本轮交付精确生产函数映射、共用参数桥和纯 fake 生命周期验证。
**即使所有离线测试通过，仍无可执行的一次性真实试验入口。**
`ROOT_ATTEMPTS=0 / HOTSPOT=NONE_PROVEN / REAL_PG17=NOT_RUN / REAL_WORKER=NOT_RUN`。
`B_GATE=NOT_APPROVED / TARGETED_PG17_GATE=NOT_APPROVED`，
`AUTHORIZATION=AUTHORIZATION_PENDING / BUDGET=DRAFT_NOT_APPROVED`。

## 已实现的具体映射及其可执行边界

新模块为 `scripts/biz_perf_p1_04_w05_root_bridge.py`，不修改任何旧实现。
`RootBridge` 接收 `BusinessPorts`、整数毫秒单调时钟、累计进程 CPU、可选 RSS/FETCH reader、
现有 `RootCounts` 和事件 sink。默认 `RefusedPorts` 固定拒绝 `EXECUTION_NOT_AVAILABLE`。
唯一受支持的生命周期方法是 `run_offline()`，测试仅注入内存 fake。
没有 CLI、main、执行器工厂、Session/Engine factory、连接串参数、环境读取、文件输出、
后台线程或资源创建/清理接口；没有 approved/permit/force 开关。

| 新模块映射点 | 本轮静态核对的生产函数及准确调用 |
| --- | --- |
| `LiveBusinessPort.create_claim` → `_create_claim` | 懒导入 `app.services.recalculation.create_recalculation_job`；`create_recalculation_job(db, start=date(2025,1,1), end=date(2025,1,31), evaluate_signals=False, mode="manual")`。不传 `job_id`，因为此可选参数用于 metadata 的 calc_run_id，并不是指定实际 JobRun 主键。 |
| 同上 | 懒导入 `app.services.job_worker.claim_next_job`；仅调用一次 `claim_next_job(db, WORKER_ID)`，随后严格核对返回的 native UUID 与刚创建 ID 相等；再 `db.refresh(job)`，检查 root/worker/token，绝不再次领取或取消另一个任务。 |
| `LiveBusinessPort.execute_claimed_job` → `_execute` | 懒导入 `app.services.job_worker.execute_claimed_job`；仅调用一次 `execute_claimed_job(db, claim.root_id, expected_worker=claim.worker_id, expected_token=claim.token)`。真实函数返回 None，不把返回值当成成功证明。 |
| `LiveBusinessPort.post_validate` | 固定拒绝；本轮没有真实 JobRun/Publication/来源/公开切片 reader。`PostRead` 只承载 fake reader 断言，不能认证来源。 |

`LiveBusinessPort.__new__` 无条件拒绝任意参数；其 `_session` 也无条件拒绝。
映射方法先检查接收对象类型及固定 Session 拒绝点，才抵达懒导入语句。
不支持传入 Session/Factory 激活、借任意对象调用未绑定方法或注入自述授权。
`RootBridge` 也拒绝 LiveBusinessPort、URI、dict 和普通 Session 对象作为 ports。
未来装配必须另行交付和审阅协调端代码，当前没有可把此 port 自动实例化的调用器。
Python 可执行注入是可信测试代码，不能防御恶意 Python 修改模块/私有状态；这些限制不是进程沙箱。
没有新增签名、租约或审批平台，也没有修改 E04/E05 的永久占用和人工裁决语义。

测试在内存中通过同一个 `_create_claim/_execute` 参数桥调用 fake 函数，并以 AST 对照生产签名和
懒导入目标；没有实例化真实 port，也没有导入 backend app、SQLAlchemy、psycopg 或 dotenv。
这是源码映射与调用契约验证，不是生产函数、真实事务或实机联通性验证。

## 已发现且不能掩盖的生产语义

`recalculation.py::create_recalculation_job` 委托 `job_guard.create_queued_ingestion_job`。
后者在队列 advisory lock 下按 fingerprint 去重：可能返回已有活跃根并设置
`_queue_deduplicated=True`；新建路径 commit 后 refresh，正常设置 False；特定回调路径可能 flush。
桥要求该标记**明确为 False**且 parent_job_id=None，拒绝复用已有任务，自己不追加 commit/flush。
create 发生后就消耗本桥尝试；异常、失败或未知 ACK 均不可恢复为新的尝试。

**当前生产 claim 没有按指定 ID 领取的能力。** `claim_next_job(db, worker_id)` 查队首、
锁定候选，写 worker_id/execution_token 等后 commit。桥可以核对并阻止执行误领根，
但这不能撤销已经发生的 claim，也不能证明该次 claim 没有触及另一个任务。
未来必须现场证明全新专用库、空队列且无任何其他入队者/Worker/Scheduler/并发执行者；
如果仍需 claim 前按 ID 硬约束，这是需另批的后端能力缺口，本轮不得修改后端伪造参数。
错 ID/None 后停止并交人工，不能取消误领任务、继续领取或回放 create。

生产 Worker 核对 owner/token，可能因非 RUNNING 或 ownership 不符提前返回；成功路径也只返回 None。
它还可能捕获异常并保留失败/取消/执行未知状态，所以必须独立读取终态。
其 finally 包括心跳停止/join、PublicationWorkspace close、observer/policy 清理、
worker observation 保存和 context reset；桥将整个同步调用返回作为边界。
这不证明子线程、PG backend 或外部进程已退出；后者仍需外部独立观察与硬终止机制。

## 根、Worker 与后验指标冻结

顺序为 begin → create → claim → 单次 Worker（含 finally）→ worker_return → root_freeze → post_read。
begin 带 run UUID/implementation SHA，create 后所有事件还绑定同一个 root UUID；不导出 token。
事件只含 seq、固定 event_kind、UTC 元数据、单调 elapsed、身份和有限脱敏错误码。
阶段/参数/SQL/URL/异常原文不进入事件。失败前缀尽力交 sink；sink 失败则停止，不承诺崩溃持久性。

| 指标 | 边界与缺测语义 |
| --- | --- |
| `root_elapsed_ms` | create/claim 之前启动，唯一同步 Worker 返回后第一时间读单调时钟冻结；正区间、禁止倒退/溢出。 |
| `execute_claimed_job_ms` | 调用 Worker 前至同一个返回边界，是 root 子区间，不与 root 相加。 |
| `post_root_validation_ms` | 从上述根结束时刻至后验读取返回；包括根快照封口、reader/sink 的边界处理开销，全部排除于 root。 |
| SQL | 复用 RootCounts 与原 `business_sql_snapshot.build` 的尝试计数/scope/hash；在任何后验、指标 reader、返回事件 sink 之前 freeze。无注入采集则 counts/snapshot=UNKNOWN，coverage=NOT_INSTRUMENTED；根 SQL 时长始终 UNKNOWN。 |
| CPU/RSS/FETCH | CPU 取开始和封口处累计值之差；0 合法、比率 UNDEFINED，倒退/reader失败为 UNKNOWN。RSS 为进程生命周期峰值，不是本根独占分配。RSS/FETCH 只在返回捕获处读取一次，不在 post 重读；没有 reader 不填0。reader自身必须提供本根聚合，桥不认证其覆盖。 |
| 阶段 | 只接受 E02 STAGES，区间必须落在 Worker 内；inclusive 允许重叠。同名阶段可累计，阶段总和不用于补 root/CPU/SQL/FETCH。未观测标签均 NOT_INSTRUMENTED，其数值 UNKNOWN。 |

共享 E03 `CollectorPorts` 负责 reader 值的有界验证和失败后保持 UNKNOWN；E02 常量定义合法标签与
数值一致性上界。软件时间检查只能拒绝坏证据，**不能停止卡住的调用或强制预算**。
RootCounts 存在未结束 SQL 时不能 freeze：终止本桥、不生成完整根快照；不从第二次检查拼出成功。
返回的根快照是防御性拷贝，post 改变计数/CPU、修改返回 dict 或事件不能回填根快照。

`PostRead` 必须独立绑定 job ID、publication job ID、execution token、run UUID 和 implementation SHA；
UNKNOWN_ACK/身份不符终止。Job SUCCESS 与 Publication PUBLISHED 分别检查，范围/source/row counts/
无 B 泄漏任一无法证明就 INCONCLUSIVE。只有完整 fake 正例返回 FAKE_VALIDATED，永不返回真实完成。
实际 reader 还应核对公开切片、质量、来源层级、逐表行数/摘要、原子发布及独立读者无候选泄漏；
本轮没有对应 SQL 或真实性证明。`FactorInputWindow._verify` 在五 OFF 下并非必然可达，
不新增非法 `factors.input_verify` 标签，不声称已观测热点。

本桥六个调用事件是最小内存联调证据，不是冻结 E03 原始 Replay 的新版本或可直接交付的完整 bundle。
真实协调端还缺 E02/E03 原始事件适配、有限字节持久化/完整性、实际 hooks 和覆盖/开销验证。
本轮不把 fake 事件直接送旧校验器冒称完整，也不复制原审计/准入清单。

## W05-RUN 前仍需独立批准并现场核验

LAB-01 `infra/biz_perf_w05/compose.pg17.yaml` 仅定义一个 PG 容器、私有 internal 网络、新命名卷，
**无宿主端口且无 Worker 容器**；定义尚未启动，不能从宿主默认端口连接，更不能复用现有生产端口。
未来需要单独批准的隔离 Worker 连接方案：可信固定镜像/代码、同一私有网络的专用运行域、
专用 Session factory、受控角色/最小权限和仓库外 secret 来源；不能直接使用项目 `.env` 或 DATABASE_URL。
LAB-01 secret 路径和镜像 digest 格式校验不认证真实性、权限或供应链。

| 实机阻断项 | 必须提供的证据与责任决定 |
| --- | --- |
| 全新独占资源 | 受控 Linux x86_64、可信 PG17/Worker 镜像、新 PGDATA/库/卷/网络、无同名资源与旧数据；实际 PG major、UUID marker、offline/online physical system_identifier、owner/lease/观察时间和空队列。现有 guard 会连库且不证明独占，本轮未调用。 |
| 硬时间与资源 | 外部 watchdog/cgroup 的强制停止及独立退出观察；批准 CPU 容量/累计时间、Worker 3GiB/PG 4GiB、磁盘10GiB/IO、证据10MiB、费用与失败处置。LAB-01 CPU/磁盘/IO 未强制；20min/末5min仍是未批准草案。 |
| 输入及准备计时 | 8股、2025-01、五开关 OFF、900日历日 seed；931日含两端、665 weekday×8=5320仅静态股日规则，不是所有表行数。真实逐表 seed/摘要、迁移、250交易日预热与430日历日回看耗时/预算/纳入关系均待签认。 |
| 四段退出闭环 | 准备（创建/seed/迁移预热）、root、post、cleanup 四段分别记录成功与失败退出；六个预算步骤仍单列。准备失败不得进入 root；root失败/取消/UNKNOWN_ACK 不进入重试；post失败不回 Worker；cleanup不确定标 CLEANUP_BLOCKED，保留占用与证据。 |
| 来源与原始证据 | 最终精确实施 SHA 的四条真实 CI、独立复测/审阅、冻结业务/策略/输入 fingerprint、单次 UUID、具名窗口/操作/验收/成本承担者；原始事件持久化、可信完整性和实际 SQL/FETCH/stage 覆盖。CI 通过不签发运行许可。 |
| 人工处置与清理 | 外部 watchdog/失联处理人、UNKNOWN_ACK 只读核查与人工终止流程、已证明归属资源的清理权限及结束证据；不得自动重放、释放、DROP旧库或删除不明资源。当前桥没有清理权或自动清理方法。 |

PIT、Decimal、版本/来源身份、原像、tombstone、500行候选批次、质量、取消/心跳、300秒发布预算与
原子发布语义不变。没有运行 PG、Worker、Seed、迁移、SQL、Docker/云或真实性能任务。
下一步为 ChatGPT 独立审阅与负责人决定是否批准资源和一次实验；**不是 E06，也不会自动转 W05-RUN**。
