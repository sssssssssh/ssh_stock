# A4236 未关闭方法与风险

当前结论 PARTIAL_OFFLINE_TESTED / BLOCKED；以下不是普通配置参数，不能由环境变量放行。

1. **独立 issuer/key/批准记录服务 UNRESOLVED**：未选签名算法、密钥轮换/撤销存储、可信时钟、
   审批对象 owner 与审计接口。需独立管理员审阅并安全部署；不能使用仓库密钥或自签 hash。
2. **持久消费服务 UNRESOLVED**：没有真实事务/CAS后端。须证明唯一约束、并发、掉电恢复、
   提交未知与回执丢失均不重放。内存字典快照测试不满足该要求。
3. **受信 harness UNRESOLVED**：实际运行用户、计算资源、PG17镜像摘要、网络无业务路由、
   socket归属、限额与创建权限未验证。没有编写 Docker/SQL/角色创建直连适配器。
4. **双信任域/独立销毁审计 UNRESOLVED**：Mock两个 issuer 仅模拟接口区分；没有独立签名，
   不证明物理 PG system identifier、容器归属或 absent。真实失败处置人与清理权限待明确。
5. **最终硬终止 NOT_PROVEN**：数据模型只能拒绝不终止的回执，不能回收现实驱动/进程。
   初始化、授权、cleanup、IO边界的真实强制终止需独立执行器审阅。本轮不宣称硬实时。
6. **prepared/cached plan NOT_VERIFIED**：纯 PrepareManager 不发送 libpq 协议；PG17实际权限、
   parameter_types→OID、投影自身准备污染、generic/custom 切换须未来观察，不能套 executions−5。
   无无扰动 cached 结构证明，禁止稳态/16或32预热/C0/C1 READY结论。
7. **CPU METRIC_UNAVAILABLE**：无 namespace/PID 双向可信映射与采样权限实证。
   不读取宿主/proc、授root/hostPID/pg_read_all_stats；不能以wall替代CPU。
8. **维护/统计 METHOD_UNVERIFIED**：MVCC不冻结规划器统计。四表OID、统计、索引、列、settings、
   fresh/cached/MVCC与维护须分开证明，NOT_OBSERVED不代表无autovacuum。
9. **长窗口 NEEDS_NEW_PROTOCOL_REVIEW**：三tick仅在自然 bracket 满足时模型可行；≤100ms查询
   未必对齐250ms tick。没有调度/睡眠/旧128点采集实现，也不自动修改原协议。
10. **工件信任边界**：owner-only/哈希/独立Git绑定是完整性而非独立现实签名；没有实机收据。
    write/fsync/deadline失败留下 .incomplete；进程中断可导致安全的假阴性，保留原目录审计，
    不覆盖、补签或就地“修复”为有效bundle。清理失败不覆盖首错。

普通既有 CI 的 PG17 回归仅验证现有应用/迁移，不填上述能力缺口。
不得为了关闭问题启动新增探针、申请云资源、读取业务.env或操作阿里云业务库。
需先审阅本轮代码，再单独决定基础设施与一次性 G1 预算；G2/G3 各自独立。
