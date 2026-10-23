# A4233 W00：基线与观测合同

基线 `73a3273301502822dc7a881a64dfdca45db4d063`，master，工作树干净。
本轮只允许 W00–W05 新观测能力及微型功能验证，不批准任何性能测量。

## 复用与隔离

- `scripts.a42_artifacts.isolation()` / `verified_test_url()`：测试管理员在创建随机 UUID
  合成库前验证 marker 和独立 system_identifier；不使用业务 DATABASE_URL 或 dotenv。
- `a4232_stability_contract.owned()` / `statistics_snapshot()` 已审阅：前者含旧 DDL
  边界，后者访问敏感统计摘要并刷新统计快照，**新只读 observer 不调用这两者**。
- 复用 `a42_artifacts.atomic()` 的同目录临时文件、fsync 和 replace；新合同先严格校验，
  禁止依赖旧助手的字符串转换/删字段行为实现去敏；新路径拒绝覆盖。
- `a4-cleanup` 只清理当前 run/job/attempt 标签匹配的容器；`a4-finish` 仅治理状态，
  不是实验通过或 Release 凭证。新合同 workflow 仅一个 contracts job。
- 新模块 `a4233_observation_contract`、`a4233_background_observer`、
  `a4233_observation_review` 不导入应用服务，不注册 API/Worker/Scheduler。

## 权限与连接

仅双物理身份验证的本机合成 PG17；observer 独立 AUTOCOMMIT、UTC、只读连接，
固定 SELECT 白名单，启动参数 statement_timeout=100ms。测试管理员在新库预置
非超级、无创建/维护/信号/业务表权限的 observer 角色及 pg_read_all_stats、
pg_control_system() 的 EXECUTE。observer 自身绝不 GRANT/ALTER 或取超级权限。
缺权限/字段/身份立即 INCOMPLETE_OBSERVABILITY，不进行后续目录观测。
物理系统 ID 只导出摘要；用户名、库名、客户端地址、SQL/参数不进收据。

## 历史身份（只读，不重新解释）

| 来源 | SHA / run / attempt | 状态 |
|---|---|---|
| A4231 | 947966dc5a33cc6d8a688431f6deb00a2dffa538 / 39820748153 / 1 | INSUFFICIENT_EVIDENCE |
| A4232 | 3916dc4dc72f83f2470a96ff265428bd2e9549e2 / 39833706083 / 1 | INCOMPLETE_ENVIRONMENT_DRIFT / INSUFFICIENT_EVIDENCE |

A4232 ZIP SHA256 `3276cdbc12413ce2ab4a3a522a53b6d9c434dfbd19d85f7655126b8f3094ad10`；
协议 SHA256 `047db54f9ac95b1729afa30e221f0fbd7013013db5fa4bf6f6302c4645affb39`。
64/128 原始记录，parent 完整接纳 32，最后 4 条缺后置签名；仅观察 worker 0→1，
没有目标关系/PID/操作证据。四表统计/已捕获计划未见差异，不能改称自动 ANALYZE。
冻结路径和全部基线字节 hash 记录在 `evidence/a4233_frozen_manifest.json`，测试逐个对照 Git。

## 明确未授权

不改 backend/config/migrations/frontend、生产 C0、AB 开关、正式 Gate、任何旧测量源/协议/
工件、consumed one-shot policy、现有 workflow；不连接阿里云、业务库或读取业务.env。
不跑 5000×20 seed、128/1100 样本、C0/C1 P95、603040 行 L2、Publication 性能矩阵；
新实验 workflow/profile、开销校准、因果归因和生产修改均需再次任务书/审批。
本机 Docker daemon 未启动；PG17 真实微型验证交由新低成本 contracts CI，不借用业务库。

官方接口核对：[PG17 progress](https://www.postgresql.org/docs/17/progress-reporting.html)、
[统计](https://www.postgresql.org/docs/17/monitoring-stats.html)、
[角色](https://www.postgresql.org/docs/17/predefined-roles.html)。进度空不证明无维护；
累计统计有报告延迟，跨视图不是原子快照；监控时间重合不证明性能因果。
