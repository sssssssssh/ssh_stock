# A42365 停止、恢复与后续验证

**当前不可部署**。本轮没有安装 systemd/root 服务、创建 cgroup/namespace/mount、运行 Podman/initdb/G1 SQL，未读取业务凭据或连接任何业务数据库。

停止源代码入口 RuntimeCoordinator.stop：先持久 CONSUMPTION_FROZEN，再通知 B stop，继而 D terminate、C reconcile。CONSUMED/ATTEMPTED 永久保留；若 B、D 或 C 回执未知，保持 quarantine，不能退款或重新消费。进程重启后从同一私有 journal 读取；重复不可逆动作不执行。若清理曾 ATTEMPTED 而 ACK 不明，独立核验后由下一版明确恢复协议处理，不能调用本方法盲目重试。

发布：StagedPublisher.stage 写 .incomplete、data fsync、manifest fsync。只有 held scope 清理、root 独立 committed TERMINATED、E 两轮八资源观察、Reviewer 关联 fresh receipt 后才可 finalize。L1 的 CONTROLLED_TERMINATED 明确 scope_terminated=false，不能替代 cgroup 终止。

需先完成的工程：B/O/C/D/E v4 服务端与预算固定 RPC；native initdb transitive exec 中介；跨 UID 同-store RO mount launcher；完整 root FD/cgroup/Guardian/worker 工厂；target backend generation 注册；独立 Reviewer 与原子发布提交。D2 另需不可旁路内核排他模型，不能用审批消除缺实现。

随后分别裁决 D1/D2/D3。任何实际部署和 L2 还需针对明确隔离主机、fixture、scope、安装/source/image digest、预算的一次性授权。没有该授权不能执行下面的物理清单。

| L2 清单 | 本轮状态 |
|---|---|
| PG17 实际 SCRAM/HBA/system_identifier/CREATE ACK-loss | NOT_RUN_NOT_AUTHORIZED |
| rootless Podman、同 UID/外部 API writer、ABA、daemon restart | NOT_RUN_NOT_AUTHORIZED |
| E 不同 UID、实际只读挂载、同 store、两轮间重建 | NOT_RUN_NOT_AUTHORIZED |
| cgroup v2/pidfd/Guardian、setsid/fork 后代、fsync 卡住 | NOT_RUN_NOT_AUTHORIZED |
| initdb 完整进程/认证/FS/SQL 计数及 P50/P95 | NOT_RUN_NOT_AUTHORIZED |
| 实际四资源回收与最终 independent Reviewer | NOT_RUN_NOT_AUTHORIZED |

普通 CI 只提供工程回归证据，不能替代这些物理验收。BIZ-PERF-01 PERFORMANCE_OPEN 另行保留。
