# D3 TARGET_SESSION_GUC｜UNSELECTED

Disposition：**UNSELECTED**。可选 `Approve / Reject / Need changes`。

旧 TARGET_SQL 为406 bytes，输出7 OID，projection 位置6/8/14/16，固定16 SQL，natural prepare_threshold=5，GC 保持启用，G2 有效总预热8 pending。本轮不改旧模板、schedule 或 Release Gate。

新 AuditConnectionFactory 通过既有 sealed credential FD 读取 Owner 凭据；只连 FixtureIdentity 指定 Unix socket/database/role，拒绝 ambient PG*/DATABASE_URL；固定 psycopg3.3.4。B 在连接前预留 AUTH1/2，在交付连接前预留 SQL1/2。PinnedSessionSource 使用两条固定 pg_stat_activity 查询核验 actual worker backend PID/start/role/db；Owner 的另一连接默认 GUC 不作为 target 设置证据。费用单独签入 v4 D1/D3 proposal，不能偷当 probe 第17条或免费认证。

**尚未闭合**：Owner v4 server、actual worker backend generation 的 B 持久注册及完整 peer/lease 绑定、安装包与 worker 路由。AuditConnectionFactory 单独存在不能证明同一个 actual backend；当前 live broker 仍拒绝，未授权审计 SQL=0。

反降级：v4 proposal digest 包括额外审计费用、Scope、installation 和固定规格；工厂不信任 request 自选 hash。旧 session_method 继续关闭；缺任何签名、撤销、到期、代签或伪造身份均不得进入 actual SQL。所有 L1 evidence target_session_settings_observed 不能为 true。

- OWNER disposition / kid / signature：UNSELECTED / 空 / 空
- 独立 SAFETY_PLATFORM disposition / kid / signature：UNSELECTED / 空 / 空
- 外部 allowlist/proposal digest / installation identity / target connection registration：未生成
- G1_L2_EXECUTION：NOT_SIGNED；G3 NOT_AUTHORIZED
