# A42361 未关闭方法 / 必须阻断

本轮状态 PARTIAL_OFFLINE_TESTED / BLOCKED。以下不仅是“没有实际跑”，前五项还有**源码工程缺口**。
不得标 CODE_READY，不得通过授权或 Mock 掩盖：

1. PG owner 初始化、角色ACL审计、credential lease 服务端未齐。现有两份 SQL 只是方法草案；
   不满足完整8条初始化合同。worker现已将预连接lease与连接后session回执分离，但真实lease发行与
   backend_start/被监督PID/角色/timeout原始核验仍须独立owner实现，不能自报。
2. B 原子事务/schema与有界receiver现已写入；消费/预约提交后直接使用另一条重新核验身份的连接读回执，
   不再RPC回调自身，不依赖并发receiver才能避免死锁。独立审批写入者、受信安装/服务管理、控制库隔离
   attestation后端仍未齐；真实持久性/进程崩溃/并发及FD交付集成均NOT_RUN，不是已部署服务。
3. rootless Podman固定命令的发行版兼容、私有runtime环境、socket共享GID/userns/mount身份需独立实现审定；
   部分创建安全 reconciliation、durable逐资源ledger及socket目录回收尚未闭环。
4. 独立 E absent/namespace 原始审计服务端未齐；不能把C返回的 JSON 复述为独立原始证据。
5. 真实 worker 隔离 launcher/固定安装包验证/FD交付与 artifact fsync 的进程外 supervisor 未接成完整服务端。
   Watchdog实际TERM/KILL/reap原语已写且模型测试；后验时间校验不是硬实时保证。
6. 独立 issuer/公钥注册表/撤销/双审批/可信时钟/专用PG控制实例均 UNRESOLVED；无真实运行许可。
7. 独立双域 PG17/system/container/namespace/role身份、低权限真实连接及安全清理物理验收 NOT_RUN。
8. 后端CPU无合法无提权双向PID/startticks映射，继续 METRIC_UNAVAILABLE；RSS单位尚未归一，不能冒充bytes。
9. 真实prepared/server计划结构/自然Observer前中后tick/四表统计MVCC/维护活动未验证；不得读业务表补证据。
10. 新最终SHA CI及工件需推送后独立收集；提交时不存在的结果不预填 success。

本阶段可审阅验签、事务、固定执行器、安全命令、kill原语及证据 IO 的源码和负例；
**不代表任务书W01–W08可部署链全部完成**。下一步仍是受限源代码补齐/审阅，不是立即开启G1。
用户真实业务库、阿里云ECS、运行任务一概未触达；无G2/G3或生产资格变化。

补充：首次推送后发现的9个根文件隐藏index字节覆盖缺口，已获用户明确授权追加精确修复。
AT03新增独立全HEAD tracked树walk（不改原PROTECTED历史digest）、NUL路径、mode、no-follow FD及竞态验证，
12项先RED、补丁后21项GREEN。该源码缺口已补，最终同SHA CI待另核；不关闭上列服务端/实机阻断。

2026-10-26续作：旧追加补丁a1bd4cec7e8c4fd9d44c91b018614243a9ad119a的CI40213654303/attempt1/
job121230040204已实际核验4172 passed、coverage89.28%，四ZIP字节/摘要和内容核验完成；不是本次新增代码CI。
本次只补B接收/读回执和worker前后两阶段会话绑定，不能将其描述为C/E/完整supervisor已补齐。
特别是owner从另一backend查询pg_settings得到的是owner自身设置，不是probe的实际会话GUC；不能把角色默认值
或预连接猜测写成actual read_only/statement_timeout实测。必须先审定独立可行的证明方法及基础设施计数，
或另行申请协议决策；本次不增加第17条探针SQL、不放大8条初始化预算，也不靠提权或补跑解决。
