# 未来 G1 一次性申请模板（不是批准书）

状态固定 NOT_APPROVED / NOT_RUN。本文件不产生 token、密钥或执行权限。
当前真实入口不具备可启用的执行器；先关闭未配置基础设施问题，再另行人工审批。

| 申请项 | 待独立确认 |
|---|---|
| exact Git身份 | 完整40位HEAD/source/overlay、run、attempt，申请时重新读取 |
| 唯一范围 | G1_SYNTHETIC_CAPABILITY_ONLY；不能包含C0/C1/2000keys/4×500 |
| issuer | 独立服务/安全公钥源、签名版本、轮换/撤销、可信时间，UNRESOLVED |
| 审批与审计 | 审批记录ID、审计对象、token ID、TTL/nonce，一次性人工审阅 |
| 持久消费者 | 独立事务/CAS服务与提交未知策略，UNRESOLVED |
| fixture | 新建PG17 UUID/nonce/marker/system/container/image，尚未创建 |
| owner/probe | 独立owner、严格只读probe、无危险继承、所属运行用户，UNRESOLVED |
| 网络/卷 | literal loopback/独占socket，禁止公网/生产路由/敏感卷/host proc |
| 资源限额草案 | CPU1000m/RSS512MiB/PIDs32，未批准，禁止root/privileged/hostPID |
| SQL候选 | 固定allowlist摘要；总≤16含投影、每条≤100ms、窗口≤2000ms、结果≤8行 |
| 独立预算草案 | 授权≤1000ms，初始化/cleanup/写盘/最终终止各≤2000ms，均未批准 |
| 失败终止 | 无重试/无增预算；未知执行/不可回收即停止，执行器UNRESOLVED |
| 清理审计 | 精确自有fixture销毁请求/完成/独立absent签名，处置人UNRESOLVED |
| 后续 | G2 PENDING，总8次仍有效；G3 NOT_AUTHORIZED，128点NOT_RUN |

不可由Codex、CI、Git提交、配置、环境变量或本模板填写“已批准”。
未来 G1 成功也只说明具体测量能力，不允许自动转为生产/P95/L2/因果 PASS。
