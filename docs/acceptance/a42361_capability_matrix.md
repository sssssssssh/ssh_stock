# A42361 能力矩阵

机读来源：`scripts.a42361_contract.Capability().model_dump()`。默认固定：

```json
{"implementation_status":"PARTIAL_OFFLINE_TESTED","g1_physical":"G1_PHYSICAL_NOT_RUN","real_sql_executed":0,"g2":"G2_PENDING","warmups_total":8,"g3":"G3_NOT_AUTHORIZED","physical_tests":"TRUSTED_INTEGRATION_NOT_RUN","production_read_authorized":false,"performance_eligible":false,"capacity_ready":false,"attribution_authorized":false,"unique_repair_candidate":null}
```

| 能力 | 源码/离线证据 | 现实状态 |
|---|---|---|
| Ed25519 原字节验签 | RFC8032正例/篡改负例，OpenSSL3真实密码学 | issuer/registry/审批未部署 NOT_CONFIGURED |
| 控制库消费 | 真 psycopg 事务/CAS/schema；并发/掉电协议模型 | 真实持久性/掉电 NOT_RUN |
| B接收/提交回执 | 受控监听FD、SO_PEERCRED固定ACL、绝对帧期限；新连接重验实例并读提交 | 源码/离线故障模型；安装、专用库、审批写入仍BLOCKED |
| 一次性创建预约 | append-only UNIQUE(token,event)，确认提交先于mkdir | 实际 PG17 NOT_RUN |
| rootless PG17创建/完整创建后销毁 | 固定命令/归属/隔离拒绝合同 | owner/E 服务端与部分创建回收未齐 BLOCKED |
| 16 SQL执行 | 锁定驱动真实离线 wire转换；固定6I4/6I8/4投影 | SQL实际发送0；物理身份/角色 NOT_RUN |
| 同session prepared | 只读 driver缓存/4个投影/计数和身份漂移拒绝 | NOT_PROVEN；第6次并非计划稳定证明 |
| kill/reap | 实际 OS API 原语+无进程故障注入 | 真实 supervisor launcher 未齐/OS证明 NOT_RUN |
| cached plan结构 | 明确 CACHED_PLAN_STRUCTURE_NOT_VERIFIED | NOT_PROVEN |
| 后端CPU | METRIC_UNAVAILABLE/值null，不借SQL wall | 双向PID映射方法未部署 |
| worker/Observer | unjoined CPU/elapsed null；BRACKET_UNCOVERED | 无真实tick/补睡眠/重跑 |
| GC/进程CPU/RSS | 自然callback不禁GC，不从wall扣除；RSS原生单位不冒充bytes | 仅固定worker源码；真实资源NOT_RUN |
| 四表统计/MVCC/维护 | 分离NOT_PROVEN/UNKNOWN，不读业务表 | NOT_RUN |
| 工件/Reviewer | 独占owner-only/manifest最后/首错/独立RPC交叉合同 | 外部收据未部署，最多非资格离线有效 |

G1_LIVE_CHAIN_CODE_READY_PENDING_TRUST_DEPLOY **不满足**；不能把外部客户端协议当已交付服务端。
G2总8待决，16/32未批准；G3正式128/64未授权；无C1/P95/L2/容量/因果结论。

2026-10-26：worker已取消预连接backend_start猜测；lease v2与session v2分阶段绑定，失败/过期/漂移均
在第一条探针SQL前停止。owner签发/实际会话证明仍未实现，不能将这些单元断言升级为物理OBSERVED。
