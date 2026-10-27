# D1 BOOTSTRAP_AND_BUDGET｜UNSELECTED

Disposition：**UNSELECTED**。可选 `Approve / Reject / Need changes`。本文件没有执行授权。

| 方案 | 当前状态 | 成本与风险 |
|---|---|---|
| 旧动态库上限 | 8 SQL / 12 commands / 2s，保持有效 | 新建库计划超限，require_active_plan 实际拒绝 |
| 候选 FRESH_DYNAMIC | 12 SQL / 32 commands / 30s，未签 | 另计 target audit 2 SQL / 2 次认证；probe 固定16条，不能称总 SQL 只有12 |
| SINGLE_USE_PREBUILT | NOT_IMPLEMENTED | allocation/provisioner/单次消费/完整构建成本尚缺，禁止免费预热或复用 |

runtime_budget_plan 的 v4 digest 同时覆盖旧 candidate DAG、额外审计账和未实现 native census。proposal_hashes 绑定 Scope、安装 digest 和版本；工厂不接受 caller 自选 proposal digest。预算候选不是签名。29s 仍只是纸面分配，P50/P95 和真实最坏值均 NOT_RUN。

BudgetService 使用 B 独立 DurableJournal，BEGIN IMMEDIATE 下累计与 INSERT 原子预留；按固定名字防止跨进程、重启和 ACK-loss 退款。记录真实 monotonic/wall clock、boot identity、计划 hash。时钟超限后持久 STOPPED。2 个 AUTH 与2个 SQL 审计 slot 单独计数，第三个拒绝。native_exec 仅是预留接口，**没有 ptrace/seccomp/可信 image exec 中介，不能证明 initdb 的全部 fork/exec 已计数**。所有 SQL/认证/FS 路径接到同一真实 B 服务仍是工程缺口。

旧 infra/g1_pg17_image、HBA/SCRAM/bootstrap 源码和 UID999:999 配置本轮逐字节不变。没有构建或运行新 G1 镜像，没有运行 initdb。现有 OwnerInitializer 继续要求 autocommit CREATE、Identifier/Literal、原始 PG metadata、ATTEMPTED-before-DDL；本轮新增 AuditConnectionFactory，但 Owner 安装 server 仍未接通。

失败：未知 ACK 不再 CREATE、不退款；只允许原身份恢复；清理失败保留首错并隔离。回滚只关闭 v4 路由，不能删除未知 fixture 或业务数据。

审批前仍需：native 全后代计数执行中介、B budget IPC、镜像供给签名与 SBOM 安装绑定、rootless UID/GID 映射的实现审阅。审批不能补齐这些源码。

- OWNER disposition / kid / signature：UNSELECTED / 空 / 空
- 独立 SAFETY_PLATFORM disposition / kid / signature：UNSELECTED / 空 / 空
- 外部 proposal digest / installation identity / image manifest digest：待可信安装生成并独立核对
- 单独 G1_L2_EXECUTION：NOT_SIGNED；不包含在本 D1 决策中
