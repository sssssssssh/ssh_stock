# A42361 未关闭方法 / 必须阻断

本轮状态 PARTIAL_OFFLINE_TESTED / BLOCKED。以下不仅是“没有实际跑”，前五项还有**源码工程缺口**。
不得标 CODE_READY，不得通过授权或 Mock 掩盖：

1. PG owner 初始化、角色ACL审计、credential lease 服务端未齐。现有两份 SQL 只是方法草案；
   不满足完整8条初始化合同。短期凭据必须绑定实际 probe backend_start/被监督PID，不能自报。
2. B 原子事务适配器/schema已有，但独立 RPC receiver/审批写入者、并发新连接提交回执服务未部署/未形成完整安装包。
   调用自己的 consumer RPC 如无独立线程/进程会死锁；不得部署单线程回调自己。
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
