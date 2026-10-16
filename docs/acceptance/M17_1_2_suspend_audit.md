# M17.1.2 停复牌兼容性取证

## T00 只读取证

2026-10-16，基线 master `2979be97ad0bb740d4d9632035bb609607bcdd8c`。
业务库查询使用 READ ONLY 事务；未运行迁移、写入、重拉任务或重启业务服务。
不保存连接信息、Token、完整源响应或 SQL 参数。

- 业务 PostgreSQL 17.7，schema 为 public；数据库 revision 与仓库 head 均为
  `0055_retention_frozen_refs`。
- 实际列：trade_date 为非空 date，ts_code 为非空 VARCHAR(16)，suspend_type 为非空
  VARCHAR(8)，suspend_timing 为可空 VARCHAR(32)，created_at/updated_at 为可空 timestamptz。
- 最近失败任务的阶段为 `25 sync suspend_d 2024-09-13`，范围 2024-01-01 至 2024-11-01；
  错误包含 StringDataRightTruncation 和 INSERT INTO stock_suspend_daily。
- 使用现有 TushareProvider、现有 Token 和进程限流，只请求 2024-09-13 的 suspend_d，
  不经过写数据库的 Gateway，不保存原始响应。
- 返回 13 行：suspend_timing 类型为 float 12 行、str 1 行；标准空值 12 行，空白字符串 0 行。
  非空最大长度 35，超过 32 字符 1 行；该行股票代码 920016.BJ，日期 2024-09-13。
  仅记录长度，不保存描述原文。suspend_type 全为 S（13 行），无非法分类。

结论：已取得真实超长字段证据，不把 NaN 当成具体超长记录。描述性时间文本使用可空 TEXT，
不截断、不设替代占位文本；另修复标量缺失值和空白描述的清洗。
测试中的 35 字符时间段为合成示例，不冒充真实响应原文。

## T01 结构与风险

新增 `0056_suspend_timing_text`，父版本为 0055，只修改描述列类型。
不改 0010/0054/0055、主键、时间戳、来源外键、索引或历史数据。
升级前后：`suspend_timing VARCHAR(32) NULL` -> `suspend_timing TEXT NULL`。
迁移设置 2 秒锁等待、30 秒语句上限。降级先持有表级排他锁，再检查超长行；
任何长度大于 32 的值均拒绝回退，防止检查与缩列之间插入新长文本。
生产优先回滚应用、保留 TEXT；不得截断或删除长值以强行降级。

代码整改和隔离库验证不代表已部署；真实业务库升级及小范围回填仍需另行审批。

## A 批隔离验证

本机临时 PostgreSQL 17.6、仅 loopback、显式 TEST_DATABASE_URL；测试创建随机独立数据库，
只使用合成记录。6 项真实迁移测试全部通过：空库 head、非空短值/NULL 扩容及往返、
35 字符旧列 SQLSTATE 22001 复现/新列写入，以及 33/100/500 字符拒绝缩列并保持行和版本不变。
定向 Ruff 和 git diff --check 通过。真实接口只读复现不等于业务库回填已修复。
与旧归档/合同/PAPER foundation 迁移联测共 33 项通过，48 个既有 Alembic 配置弃用警告。
现有测试和 CI 的 head 断言仅同步到 0056，未放宽业务或不可变断言。

## B 批清洗与写入

A 提交为 `0f6b4c766ff2c73bba96ef4ba517382fd443e96c`，
[A CI](https://github.com/sssssssssh/ssh_stock/actions/runs/38837049096) 状态以实际 Actions 为准。
新 Normalizer 回归先在旧实现执行，41 failed / 17 passed，证明测试可复现旧缺口；
修复后新增 58 项与旧 7 项 Normalizer 测试全通过。
与真实 PostgreSQL Ingestion、既有质量计数测试联测共 88 passed，21 个既有 Alembic 警告。
完整后端 Ruff 通过。最终全量 CI 和上线验收另行留证，不以此定向数量替代。
另执行全部 unit 测试：1405 passed，2 个既有弃用警告；不是全量集成测试通过声明。

- None、NaN、pd.NA、缺字段、纯空白描述归为 NULL；合法文本（包括前后空格、中文、标点）原样保存。
- 非字符串复杂对象、非法/缺失 S/R、非法代码或日期明确拒绝；不再将空类型默认为 S。
  主日期只有真正缺失时才使用 suspend_date；畸形非空日期不回退掩盖错误。
- 清洗异常仅携带受控字段/错误码，Ingestion 复用现有质量 ERROR 提交路径后拒绝整个快照。
  有效记录日期若不等于请求日也拒绝，避免跨日快照对账删除。只修改停牌这一路，不改全局解析。
- 日志仅有 rows、normalized_null_count、over_32_count；没有原文、Token、SQL 参数或整份响应。
- PostgreSQL 实测 13 行合成混合批、12 个 SQL NULL、500 字符中英描述无损；重复拉取不重复行，
  描述更新/替换 NULL 正确记录 Dirty；重复键/源截断警告保守拒绝；真实空响应仍权威对账。
- 在真实 UPSERT 第一行后注入数据库除零错误：本日删除、部分写入、PASS 质量和 Dirty 整笔回滚，
  已成功提交的前一日保持不变。非法清洗则按既有设计保留 ERROR 质量，Raw/Dirty 不变。
- 真实 TradeStatusService 验证长描述或 NULL 均不改变 S 停牌、R 复牌的现有分类。

## C 批真实响应隔离写入与发布证据

再次读取当天真实接口响应，仅在随机临时 PostgreSQL 17.6 库走真实 IngestionService 两次：
13 行、12 个 SQL NULL、最长 35 字符，质量 PASS；所有描述逐字段与源相等，二次同步幂等，
Dirty 仅首次创建。临时库随后移除，没有保存源 payload，也没有生产任务或业务写入。

最终全量、精确 SHA/CI 回执和逐项映射见 `M17_1_2_closeout.md`，
部署/恢复/单日实际回填见 `M17_1_2_suspend_runbook.md`。生产列扩容与 G1 任务尚未审批执行。
