# WORKER-02-R2 — 源码整改，合并仍阻断

审阅基线 b207431eb39502f3e31fb328aa03dc045895439c，master
75076eac443d935d622bf59e12aad20ce5aba85e，分支 codex/biz-worker-02，
[PR #1](https://github.com/sssssssssh/ssh_stock/pull/1) 保持 Draft。
本轮不合并、不部署，不操作业务数据库、现场 Writer 或 G1/L2 资源。

## W00 / W01：真实基线与未批准合同

[review_baseline.json](review_baseline.json) 固定父提交、原四条 PR Actions、
分支 CI、merge checkout 和原始工件摘要；[failure_inventory.md](failure_inventory.md)
逐项保留190节点实际消息。b207431 的 macOS 全量是4981/53/137/0，
4d183857 前轮是4953/53/137/0，提交前146+6是局部证据，三者不混用。
基线 full.log/XML/完整trace和30份CI ZIP的摘要均保留。原离线进程测试挂起及
人工终止只属于失败证据，不能算无人干预全量通过。

本轮没有收到独立签名、审批ID、审阅者身份/时间。
[source_inventory_PROPOSED.json](source_inventory_PROPOSED.json) 仅列26个源码/测试
精确路径的基线与当前字节摘要，沿用11份历史manifest摘要；不是已批准合同，
不实现版本分派、不启用普通CI新合同、不改历史guard、测试、manifest或工作流。
`CONTRACT_MIGRATION_BLOCKED`。历史2779a2a clean checkout 的原19项合同/篡改负例
本轮再次通过；完整Linux历史与新合同联合验收仍缺独立审批。

## W02：时间、顺序与终态保护

lease 与 progress 两短事务、owner/token/status CAS、1s锁/3sSQL限制保留。
lease时间使用数据库greatest防止迟到心跳回退；last_progress_at及JSON进度不回退。
通信确认仍必须有lease UPDATE rowcount=1和成功commit ACK，观测时间不是租约证据。

heartbeat_health 附规范化UTC微秒 observed_at；独立CAS拒绝较旧/重复健康快照。
即使性能诊断关闭或快照失败，health-only迟到观察也只能写RUNNING且不能覆盖最终
UNCONFIRMED证据。终态诊断必须与实际终态一致，不可将SUCCESS快照落入FAILED任务。
取消、首错、公开结果和计算执行状态不由这些诊断变更。

新增RED真实复现10项问题，修复后10项通过。扩展104项通过，包括原真实57014、55P03、
断连、lease/progress ACK丢失、owner/token和取消。新增连续心跳、真实进度57014、rollback
及恢复测试核对时间戳、JSON进度、失败次数、阶段与SQLSTATE。其故障注入不是现场定因。

## W03：三个实际根任务与成本观测

recalculate/daily/catchup 分别从正常队列领取，真实计算和原子发布；Provider仅重放
自有合成Raw，无网络。每类OFF/ON各用新建且相同seed的隔离PG17数据库，避免OFF完成后
改变ON的catchup工作量。十张表的财务内容、dtype与规范化摘要精确相等；仅排除显式
每次运行UUID/时间和数据库代理ID，自然键、版本、config hash及JSON内容继续比较。
空表仍报告实际0行，不能冒充非空Golden覆盖。

复用原ExecutionDiagnostics与入口，未另建计算路径。原始Raw完整性评估器只增加
opt-in计时包裹，使daily与catchup也能记录raw preflight；不改变返回值/验证/持久化逻辑。
该preflight是包含Python质量校验与相关查询的包络，不能当成纯数据库执行时间。
SQL query/FETCH/frame、compute/materialize/replace、candidate lookup/store和publish均有
实际阶段记录。未启用factor window仍NOT_INSTRUMENTED；FETCH包含游标/传输/Python，
嵌套阶段不相加。默认开关false；关闭时不生成性能诊断，独立心跳/会话事实仍保留。

snapshot的recent字典现逐项复制，dropped计数在同一锁下读取；外部消费者不能改写内部
事件。并发读写、非法标签、128组/32条边界仍有效。

[成本观测](small_input_cost_observations.json) 来自一次固定OFF→ON小输入对照，含墙钟、
进程CPU、内存高水位、SQL/写入次数与WAL增量。macOS内存是进程生命周期高水位，
不能当单任务峰值；WAL是共享合成实例LSN差额，不能作独占语句归因。心跳调度、缓存和
后台活动会影响成本；无重复统计/性能阈值/提速百分比，不代替百万行容量。

## W04 / W05：只读恢复核对及事务竞态

普通CLI继续只有reconcile --dry-run，无apply/force/unlock。名字、心跳、空PG连接列表
均不是身份认证或全端退出证明，PID/backend_start/DB OID/postmaster事实保持只读。
未安装authority时继续拒绝恢复，LocalTestAuthority不进入生产。

内部原语仍先advisory lock、root、发布账本、子任务、Dirty；root改FOR UPDATE，
同时锁发布账本，阻止原NO KEY UPDATE允许的晚到子任务FK插入竞态。外部新领取尝试
使隔离authority拒绝，原事务回滚。授权服务在提交前再次核验，避免只验证初始冻结
对象而漏掉动态撤销；有效期继续反复核对。独立authority必须保证其证明与冻结条件
持续有效，两次调用本身不证明生产全端隔离或代替原子授权消费服务。

新增内部recovery_commit_status只允许新Session，以REPEATABLE READ / READ ONLY
核对原身份、ABORTED账本、原审计及活跃子任务。未知COMMIT ACK后换连接只读确认，
不调用authority、不finish_publication、不追加审计、不commit、不自动重试恢复。
真实PG提交后客户端注入ACK丢失与未提交两种结果分别核对，不宣称物理网络抓包。

批准、撤销、未知ACK下，主/子终态、Dirty、ABORTED和审计保持原子；候选删除标记、
历史候选、已发布A与原始主/子错误保留。实际独立生产authority、双人签署/撤销/消费
账本、独立凭据、所有主机/容器退出和未决提交证明均未安装，仍
`RECOVERY_AUTHORITY_NOT_INSTALLED`。旧内部v1审批保留兼容，不成为生产权限格式。

## W06 / W07 / W08：平台、容量与现场停止线

Docker daemon不可用，/proc、Unix peer UID、pidfd、shellcheck/cc/密码工具链等原平台
问题不改断言、不skip/xfail。未经筛选本地全量仍执行；Linux完整测试依旧可能在未批准
合同门禁处被阻断，结果以最终同源码SHA的原始日志/XML与Actions为准。
四条普通工作流由正常推送触发，无手动高成本dispatch、CI重跑或取消来制造通过。

内存预检2049900544 bytes，规划预留4GiB，目标1443097行×3不缩小，实际0轮。
这是保守预检，不是实际OOM或已证明的最低需求。
`RESOURCE_DEFERRED / PERFORMANCE_OPEN`，未优化生产SQL、索引或计算公式。

现场根任务4a8c98cb-2c98-4a37-898d-c79c134da331本轮未访问。
785000行、11:32进度、11:34/11:36的57014仅为任务书提供的历史线索，未经本轮现场复核。
具体只读交接及授权边界见[运行手册](../../runbooks/WORKER_02_readonly_recovery.md)。
`FIELD_NOT_RETESTED`，不能宣告READY_FOR_FIELD_VALIDATION。

## W09 / AT01–AT24

| AT | 状态与证据 |
|---|---|
| 01–02 | 基线/PR/merge SHA及原CI/XML/hash固定；最终提交与工件在交付消息 |
| 03 | 历史19项通过，原负例/manifest不变；Linux联合验收未取得 |
| 04–05 | BLOCKED：未签署，不启用新合同或伪造负例通过 |
| 06–10 | 隔离PG17超时/锁/ACK/CAS/顺序与单调进度扩展回归通过 |
| 11–13 | 三类实际根任务OFF/ON、并发snapshot、独立Session/事务保护通过 |
| 14 | 原真实/同名伪造会话回归保留，名字或空结果均不授权 |
| 15–16 | 小输入十表等价；恢复原子性、候选删除标记/公开A/Dirty保留 |
| 17–19 | dry-run可用；生产authority/全端证明未安装，恢复BLOCKED |
| 20–21 | 隔离授权撤销/晚到child/发布/ACK/原子ABORT回归；不代表生产审批完成 |
| 22 | 最终同SHA工作流如实交付；合同红灯不能标PASS |
| 23 | Linux完整验收PLATFORM_BLOCKED / CONTRACT_MIGRATION_BLOCKED |
| 24 | RESOURCE_DEFERRED；现场操作需另外授权 |

预提交原始XML摘要见[pre_full_validation.json](pre_full_validation.json)。
最终SHA全量及CI结果在提交后形成，交付时另附原始证据包与摘要，不用这些预提交结果
冒充最终SHA验收。只有独立合同审阅、支持平台全量与运行安全门槛均满足后才建议申请
实际Worker灰度，不能自动合并/部署。

回滚需要经审阅撤回本轮应用字节，停止对应Worker并独立确认退出；不降库、不删Raw、
不抹历史审计、不重签旧任务、不自动重算。测试结束仅停止本轮自有合成PG17。
