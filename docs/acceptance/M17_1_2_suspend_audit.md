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
