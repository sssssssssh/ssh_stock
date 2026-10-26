# ADR_BOOTSTRAP_AND_BUDGET — 独立审批请求，默认拒绝

冻结输入 `a8a675ea8b93dadbba9e905a7a4af67eba163d99`；候选源码/ADR 的最终冻结字节由第七层 manifest pin 和最终 commit 绑定。
决策 NOT_APPROVED；审批人：项目 owner + 独立安全审批者；平台管理员确认供应链和安装。
未签名新版协议前旧 grant 永远不能启动新方案；本 ADR 不授权任何建库、镜像构建或安装。

推荐 A：全新动态数据库、显式成本 bootstrap。源码只有可计算规格与可行性检查，
**没有经审核可启动镜像/entrypoint 实现**，状态 ENGINEERING_BLOCKED。
B 为独占单次预构建空 fixture，尚无可审 builder，亦 NOT_IMPLEMENTED/NOT_APPROVED。
不推荐把通用、多人复用、含旧角色/数据/统计的模板冒充全新 fixture。

| 项目 | 旧冻结 | A 候选 | 未测/影响 |
|---|---|---|---|
| 初始化 SQL | 8 | 12 | 旧已有 CREATE DATABASE+8=9 即超限；补认证与审计后12 |
| 初始化命令 | 12 | 32 上限，清单26 | 现有独立 inspect 已17；不能挪到 image 隐藏 |
| 初始化窗口 | 2000ms | 30000ms | 按26×1000+12×100=27200ms 串行保守估算，非性能保证 |
| 冷启动 P95 | 未测 | NOT_MEASURED | 不编造 CPU/内存/容量；未来另批测试，不本轮运行 |
| probe SQL | 16 | 16 | 不增第17条；GUC另审批 |
| probe timeout/预算 | 100ms/2s | 不变 | 初始化与探针窗口区分，新 grant 需全部精确签入 |
| 协议版本 | 当前冻结版本 | g1.bootstrap.candidate.v2 | token/nonce/fixture/source/epoch/image+方法哈希新绑定 |

每项 SQL/OS/认证均显式入成本清单（OS列为受控操作，不是允许调用的任意 argv）：

| 操作 | 阶段 | SQL数 | 命令/认证数 | 候选单项最坏ms |
|---|---|---|---|---|
| CREATE_DATABASE | OWNER_INITIALIZATION | 1 | 0 | 100 |
| REVOKE_DATABASE | OWNER_INITIALIZATION | 1 | 0 | 100 |
| REVOKE_SCHEMA | OWNER_INITIALIZATION | 1 | 0 | 100 |
| CREATE_PROBE_ROLE | OWNER_INITIALIZATION | 1 | 0 | 100 |
| SET_SCRAM_VERIFIER | OWNER_INITIALIZATION | 1 | 0 | 100 |
| REVOKE_DEFAULT_FUNCTION | OWNER_INITIALIZATION | 1 | 0 | 100 |
| CONNECT_ONLY | OWNER_INITIALIZATION | 1 | 0 | 100 |
| READ_ONLY_DEFAULT | OWNER_INITIALIZATION | 1 | 0 | 100 |
| TIMEOUT_DEFAULT | OWNER_INITIALIZATION | 1 | 0 | 100 |
| RAW_OWNER_ROLE_AUDIT | OWNER_INITIALIZATION | 1 | 0 | 100 |
| AUTH_CONFIG_AUDIT | OWNER_INITIALIZATION | 1 | 0 | 100 |
| USER_OBJECT_PRIVILEGE_AUDIT | OWNER_INITIALIZATION | 1 | 0 | 100 |
| C_VOLUME_CREATE | BOOTSTRAP_RUNTIME | 0 | 1 | 1000 |
| C_VOLUME_INSPECT | BOOTSTRAP_RUNTIME | 0 | 1 | 1000 |
| C_SECRET_CREATE | BOOTSTRAP_RUNTIME | 0 | 1 | 1000 |
| C_SECRET_INSPECT | BOOTSTRAP_RUNTIME | 0 | 1 | 1000 |
| C_CONTAINER_CREATE | BOOTSTRAP_RUNTIME | 0 | 1 | 1000 |
| C_CONTAINER_INSPECT | BOOTSTRAP_RUNTIME | 0 | 1 | 1000 |
| C_PREPARED_INSPECT | BOOTSTRAP_RUNTIME | 0 | 1 | 1000 |
| C_BEFORE_START_INSPECT | BOOTSTRAP_RUNTIME | 0 | 1 | 1000 |
| C_START | BOOTSTRAP_RUNTIME | 0 | 1 | 1000 |
| C_RUNNING_INSPECT | BOOTSTRAP_RUNTIME | 0 | 1 | 1000 |
| C_READINESS_INSPECT | BOOTSTRAP_RUNTIME | 0 | 1 | 1000 |
| O_BEFORE_VOLUME_INSPECT | BOOTSTRAP_RUNTIME | 0 | 1 | 1000 |
| O_BEFORE_SECRET_INSPECT | BOOTSTRAP_RUNTIME | 0 | 1 | 1000 |
| O_BEFORE_CONTAINER_INSPECT | BOOTSTRAP_RUNTIME | 0 | 1 | 1000 |
| O_AFTER_VOLUME_INSPECT | BOOTSTRAP_RUNTIME | 0 | 1 | 1000 |
| O_AFTER_SECRET_INSPECT | BOOTSTRAP_RUNTIME | 0 | 1 | 1000 |
| O_AFTER_CONTAINER_INSPECT | BOOTSTRAP_RUNTIME | 0 | 1 | 1000 |
| ROOT_VERIFY_PINNED_IMAGE | BOOTSTRAP_RUNTIME | 0 | 1 | 1000 |
| ROOT_CREATE_CGROUP_SCOPE | BOOTSTRAP_RUNTIME | 0 | 1 | 1000 |
| ROOT_BIND_PRIVATE_SOCKET | BOOTSTRAP_RUNTIME | 0 | 1 | 1000 |
| ROOT_SEAL_CREDENTIALS | BOOTSTRAP_RUNTIME | 0 | 1 | 1000 |
| IMAGE_INITDB | BOOTSTRAP_RUNTIME | 0 | 1 | 1000 |
| IMAGE_WRITE_PG_HBA | BOOTSTRAP_RUNTIME | 0 | 1 | 1000 |
| IMAGE_POSTGRES_START | BOOTSTRAP_RUNTIME | 0 | 1 | 1000 |
| OWNER_AUTH_CONNECT | BOOTSTRAP_RUNTIME | 0 | 1 | 1000 |
| PROBE_AUTH_CONNECT | BOOTSTRAP_RUNTIME | 0 | 1 | 1000 |

SQL 精确候选模板如下。仅将来受信 Owner 使用 psycopg.sql.Identifier/Literal 渲染
动态 Utility DDL；`{}` 不是可执行参数化SQL，也不允许调用者提供标识符/SQL。
普通查询 %s 为固定 probe role 参数。CREATE DATABASE 在独立 autocommit 管理连接；
后续在新动态库事务执行，提交后另连接读取。不能向业务数据库路由。

### CREATE_DATABASE

```sql
CREATE DATABASE {database} OWNER postgres
```

### REVOKE_DATABASE

```sql
REVOKE ALL ON DATABASE {database} FROM PUBLIC
```

### REVOKE_SCHEMA

```sql
REVOKE ALL ON SCHEMA public FROM PUBLIC
```

### CREATE_PROBE_ROLE

```sql
CREATE ROLE {probe_role} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 1
```

### SET_SCRAM_VERIFIER

```sql
ALTER ROLE {probe_role} PASSWORD {scram_verifier_literal}
```

### REVOKE_DEFAULT_FUNCTION

```sql
ALTER DEFAULT PRIVILEGES REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC
```

### CONNECT_ONLY

```sql
GRANT CONNECT ON DATABASE {database} TO {probe_role}
```

### READ_ONLY_DEFAULT

```sql
ALTER ROLE {probe_role} SET default_transaction_read_only=on
```

### TIMEOUT_DEFAULT

```sql
ALTER ROLE {probe_role} SET statement_timeout='100ms'
```

### RAW_OWNER_ROLE_AUDIT

```sql
SELECT current_database(),current_user,current_setting('server_version_num'),system_identifier,p.rolsuper,p.rolcreatedb,p.rolcreaterole,p.rolinherit,p.rolreplication,p.rolbypassrls,p.rolconnlimit,ARRAY(SELECT roleid FROM pg_auth_members WHERE member=p.oid),has_database_privilege(p.oid,current_database(),'CREATE'),has_database_privilege(p.oid,current_database(),'TEMP'),has_schema_privilege(p.oid,'public','CREATE') FROM pg_control_system(),pg_roles p WHERE p.rolname=%s
```

### AUTH_CONFIG_AUDIT

```sql
SELECT rule_number,auth_method,error FROM pg_hba_file_rules ORDER BY rule_number
```

### USER_OBJECT_PRIVILEGE_AUDIT

```sql
SELECT c.oid,has_table_privilege(%s,c.oid,'SELECT'),has_table_privilege(%s,c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,MAINTAIN') FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' ORDER BY c.oid
```

## 认证、身份和原始元数据

安装器先验证镜像 digest、签名/SBOM/架构/固定二进制路径，再生成仅本fixture的
随机密码与 SCRAM-SHA-256 verifier；使用密封FD/Podman Secret，禁止 argv/env/日志。
pg_hba 显式 owner 的本地 peer/受信映射，probe 仅固定socket、固定角色、scram-sha-256；
拒绝 trust、网络、其他库/角色。无匹配 HBA、密码/UID/Socket、健康检查或实际登录
任一未证明，不能从 OWNER_READY 升到 ROLE_READY/SESSION_READY。
postgres 超管只在 Owner 进程，probe 无其 FD、无成员关系、无 CREATE/TEMP/DDL/DML/
TRUNCATE/MAINTAIN/复制/用户函数 execute；empty DB 中无业务表。检查序列权限和未来
对象默认权限仍需最终 bootstrap 审查，当前候选不是已落实 ACL 的物理证明。
角色默认 GUC 是配置事实；Owner 的 SHOW 不能读取另一 backend 的实际会话 GUC。

| 事实 | 独立原始来源 | 不能替代为 |
|---|---|---|
| PG17/system ID | libpq server_version + pg_control_system | scope.pg_major |
| DB/Owner/socket | connection.info dbname/user/host/port | 请求回显 |
| role flags/memberships/权限 | pg_roles/auth_members/has_*_privilege | self JSON布尔 |
| 认证规则 | pg_hba_file_rules + probe实际登录 | 容器Running/health |
| image/资源 | pin镜像+独立runtime inspect/原始C创建账本 | 名称或同标签替换 |
| 目标会话GUC | 尚待独立GUC协议 | Owner默认配置 |

PG17参考：[libpq状态](https://www.postgresql.org/docs/17/libpq-status.html)、
[SCRAM与密码](https://www.postgresql.org/docs/17/auth-password.html)、
[客户端默认值](https://www.postgresql.org/docs/17/runtime-config-client.html)。

B 方案必须单 fixture、单次、先冻结动态身份再 builder；builder 保留全部12SQL及日志/
verifier产生/原始审计成本，运行时重新核验签名、空库、ID、认证、撤销和原子领取。
不得复制相同 role/password/system ID 作为独立新实例，也不得把构建时工作记成0。
当前 prebuilt() 保留与A相同的总成本，为保守可比规格；没有 builder/runtime分别实测，
不能批准单靠镜像节省预算。若需克隆后重新身份化，增加新SQL/命令重新审批。

批准表：owner 待签；安全审批者待签；平台管理员待确认；冻结包SHA待最终交付绑定。
拒绝/无回复默认保持9>8、17>12和session_method阻断，不创建任何资源。
