# ADR_TARGET_SESSION_GUC — 离线候选，协议批准请求

冻结输入 `a8a675ea8b93dadbba9e905a7a4af67eba163d99`；最终源码和本文由新 overlay pin绑定。
决策 NOT_APPROVED；项目owner+独立安全审批者手工批准，默认方案C继续禁用。
当前 session_method 无条件 METHOD_BLOCKED_NEEDS_PROTOCOL_DECISION；环境开关、
伪token、Mock签名、ApprovedMethodStub字符串均不构成运行权限。

方案A：将既有**四个 projection 槽全部替换**为以下同一个固定候选；不是新增SQL。
保留6×I4、6×I8，SQL总16、4projection、100ms、2s、最多8行、自然GC与旧Reviewer。
当前4槽原文/sha仍在冻结 `a42361_live_probe_worker.TEMPLATES`，本轮未改一字；
新批准应签入 old_allowlist/new_allowlist 和完整槽位表（projection前/后及最终等4个
原槽顺序不变），不得只批准某个布尔开关或“允许所有SHOW”。

候选SQL精确ASCII **406 bytes**，无参数，输出7列OID `(25, 16, 25, 1028, 16, 20, 20)`：

```sql
SELECT current_setting('statement_timeout') AS statement_timeout, current_setting('transaction_read_only')::boolean AS read_only, p.name,p.parameter_types::oid[],p.from_sql,p.generic_plans,p.custom_plans FROM (SELECT 1) AS singleton LEFT JOIN LATERAL (SELECT name,parameter_types,from_sql,generic_plans,custom_plans FROM pg_catalog.pg_prepared_statements ORDER BY name LIMIT 8) AS p ON true ORDER BY p.name
```

候选 SQL SHA256 `2f2f912b70ec0fe9c81c17c9098d8c2208a54e78ba69277bfe49c1bcf5986b56`；候选 allowlist
`9b4a128a2cfb0c2c44d7eb70ab0e6d311162c902a53a3e96fb34eb0ca130d571`；旧实际allowlist
`d0aa6b635b0eb35eb373e0b1fa003593535eac68dd07bc3445b6c80d9ef752f8`。
旧4槽原模板逐字节用原代码冻结，不在本ADR重新定义；批准前最终包应同时签入旧16个
模板逐项hash以及替换位置，以免将initSQL与probeSQL混同。新绑定版本拟
`g1.target-session-projection.candidate.v2`，旧授权不得重放，旧token不升级。

LEFT JOIN在无prepared时返回1行：timeout='100ms'、只读true，后5列全NULL。
候选 parser 严格检查7列/OID/行数，'100'、1、'true'均不当作正确GUC；空计划不得
伪造generic/custom计数。存在计划时复用原 prepared_projection 的名称、参数OID、
from_sql=false、计数上限与跨槽连续性，不放宽旧断言；异常样本完整拒绝。
parser只验证向量，不认证原始连接，所以永远返回 target_session_settings_observed=false、
qualifies=false、CACHED_PLAN_STRUCTURE_NOT_VERIFIED。将来执行器必须把结果绑定同一
backend PID/start/role/namespace/generation、prepared状态与独立Owner postconnect receipt。

方案B：libpq连接状态能证明目标db/user/socket，不能直接证明statement_timeout；
ParameterStatus只覆盖有限服务端参数，Owner另一backend的SHOW不能替代，暂无可证明
完整替代方法。依据 [PG17 libpq](https://www.postgresql.org/docs/17/libpq-status.html) 与
[PG17 timeout](https://www.postgresql.org/docs/17/runtime-config-client.html)。

方案C（当前有效）：保持禁用。不发送probe凭据、不发第一SQL、不消费真实token。
源码只有离线候选parser/测试，无新executor或额外SQL。审批人待签，版本/签名待冻结。
批准任何候选后仍需bootstrap、卷安全、受信安装和另行G1运行授权，不能自动开始实测。

## 旧模板与替换槽精确冻结附件

四个projection的1-based位置为 **6、8、14、16**。每个位置旧模板相同；全四个替换，其他12个位置不改。

### 旧 I4

参数OID `(23,)`，行数上限 1；driver bytes=18，SHA256 `91211cff1306a91b34112309539433af1641650fa4ae6b56a154cf33bfed6f71`；wire bytes=18，SHA256 `6f662bb7e0eb66fcc5c4e37998064aa5057fb9454365205078432d8d445fe9a2`。

```sql
SELECT %s::integer
```

wire精确文本：

```sql
SELECT $1::integer
```

### 旧 I8

参数OID `(20,)`，行数上限 1；driver bytes=21，SHA256 `20fb6e485e2388fe7d524bc79cc7219cc016ba0f21c32084662e74b1e35b231b`；wire bytes=21，SHA256 `47e6e307a1e0fe22b23f23a7e2a35174b2c52965b190028f9797d42d02e4b274`。

```sql
SELECT %s::bigint + 1
```

wire精确文本：

```sql
SELECT $1::bigint + 1
```

### 旧 PROJECTION

参数OID `()`，行数上限 8；driver bytes=135，SHA256 `b4b3ab3ea0b66567b406840668c3a09be73c0a9689df6ba5b65c99e4802473a4`；wire bytes=135，SHA256 `b4b3ab3ea0b66567b406840668c3a09be73c0a9689df6ba5b65c99e4802473a4`。

```sql
SELECT name, parameter_types::oid[], from_sql, generic_plans, custom_plans FROM pg_catalog.pg_prepared_statements ORDER BY name LIMIT 8
```

wire精确文本：

```sql
SELECT name, parameter_types::oid[], from_sql, generic_plans, custom_plans FROM pg_catalog.pg_prepared_statements ORDER BY name LIMIT 8
```

新projection无参数，driver/wire均为上文406bytes；结果OID有7列，旧projection结果OID为(25,1028,16,20,20)，更改parser需新协议签名。
