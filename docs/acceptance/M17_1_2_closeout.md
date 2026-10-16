# M17.1.2 验收记录

## 交付身份与结论边界

基线 master `2979be97ad0bb740d4d9632035bb609607bcdd8c`，不切换分支、不重写历史。

| 批次 | 提交 | 证据 |
|---|---|---|
| A | `0f6b4c766ff2c73bba96ef4ba517382fd443e96c` | [CI 38837049096](https://github.com/sssssssssh/ssh_stock/actions/runs/38837049096)，本机 33 项迁移/历史约束联测 |
| B | `435acb61406e0a41f836d9c24a0c06871ee3a62f` | [CI 38838039858](https://github.com/sssssssssh/ssh_stock/actions/runs/38838039858)，本机定向 88 项、全部 unit 1405 项 |
| C | 本文件所属最终提交，由同 SHA 的 CI 回执给出精确身份 | 最终全量 CI SUCCESS 才关闭代码验收；生产 G1 独立审批 |

本文件无法写入包含自身内容的 SHA。最终 Actions 的 `m17-1-2-suspend-evidence` 附件
提供 `m17_1_2-release.json`（40 位 SHA、CI URL、PG 主版本、current=heads、实际 nullable TEXT）
及 `m17_1_2-targeted.xml`、全量 `m17_1_2-full.xml`。以同次完整 Actions conclusion 为准，
早期批次绿灯不能替代最终提交。
当前没有生产迁移授权、生产回填 Job ID 或 G1 SUCCESS；这些字段不得使用合成 ID 冒充。

## 实际范围

| 文件 | 改动 |
|---|---|
| models/market_data.py | 仅 suspend_timing 改 nullable TEXT |
| 20261016_0056_suspend_timing_text.py | 0055 后增量扩容；排他锁内防有损缩列；有界锁/语句等待 |
| ingestion/normalizers.py | 仅停牌清洗：标准缺失归 NULL、原文保留、受控类型/主键错误、安全日期别名回退、聚合日志 |
| ingestion/service.py | 仅停牌清洗错误复用 ERROR 质量路径；错日快照拒绝；原对账/UPSERT/Dirty/事务边界保留 |
| test_suspend_normalization.py | 58 项清洗回归；旧实现 41 项失败，修复后全通过 |
| test_suspend_timing_schema.py | 6 项真实 PG 迁移/旧 SQLSTATE 22001/安全回退测试 |
| test_ingestion_suspend.py | 21 项真实 PG 服务/幂等/质量/回滚/TradeStatus 测试 |
| 旧迁移测试与 CI | 只更新当前 head 的精确断言；业务断言/阈值未放宽；新增本轮 JUnit 与精确回执 |
| 四份权威 Markdown 与本目录文档 | 取证、范围、部署、验收和剩余审批边界 |

0010、0054、0055 迁移不修改；未改 Provider SDK/限流、upsert_rows、reconcile_daily_snapshot、
RawCompleteness、Scheduler、Worker 架构、策略权重、Decimal、费用、T+1、PAPER 或冻结历史。

SQL 唯一业务结构变化为：

```sql
ALTER TABLE stock_suspend_daily ALTER COLUMN suspend_timing TYPE TEXT;
```

NULL 允许、自然键 trade_date+ts_code+suspend_type、索引/外键、created_at/updated_at 均不变。
不清表，不重写时间戳；降级检查与 ALTER 在同一表级排他锁下，>32 值存在就整笔拒绝。

## T00 与真实源隔离验证

[取证记录](M17_1_2_suspend_audit.md) 记录线上 READ ONLY 列定义与真实源统计。
2024-09-13 实测 13 行、12 个空值、1 个 35 字符描述，所有分类均为 S。
已找到具体超长字段，不把 NaN 错当长度超限原因；未保存完整源响应、描述原文、密钥或连接串。

额外将同日真实 Provider 响应仅存入随机临时 PostgreSQL 17.6 数据库，走真实
IngestionService 两次：13 行、12 个 SQL NULL、max_length=35、质量 PASS；
每条描述与源逐字段相等，第二次无重复行/额外 Dirty。临时库随后移除。
该验证不创建生产任务、不写业务库，不替代 T05 的真实队列回填/validate-data。

## 测试 Checklist

N = tests/unit/test_suspend_normalization.py；S = tests/integration/test_suspend_timing_schema.py；
I = tests/integration/test_ingestion_suspend.py。下表给出具体场景与断言；最终以 CI 实际 JUnit 为准。

| 项目 | 证据 |
|---|---|
| UT-01 None/缺字段 | N missing_descriptions / missing_description_field，结果严格 is None |
| UT-02 NaN/numpy.nan/pd.NA | N missing_descriptions 参数，I real_shape，PG 真实 NULL |
| UT-03 空白 | N missing_descriptions；合法非空带空格文本不 strip |
| UT-04 中文/标点 | N valid_descriptions 原样相等，I mixed 原文相等 |
| UT-05 32/33/100/500 | N valid_descriptions；S old_boundary、downgrade_refuses；I 500 字符 |
| UT-06 S/R | N types_preserve_business_identity，I TradeStatus S/R 真实计算 |
| UT-07 非法分类/复杂值 | N invalid_or_missing_type / absent_type / complex_or_nontext；I 持久 ERROR |
| UT-08 日期回退 | N missing_primary_date / date_alias / invalid_keys；无效非空日期不掩盖 |
| IT-01 空库 head | S fresh_postgresql_head，实际 nullable TEXT 与 ORM 一致 |
| IT-02 非空升级 | S nonempty_upgrade，全部字段含时间戳逐行相等 |
| IT-03 长文本插入 | S old_real_length_boundary，旧 SQLSTATE 22001、新列完整 35 字符 |
| IT-04 ON CONFLICT | I upsert_idempotency，完整长描述替换及 NULL 更新 |
| IT-05 超长拒绝降级 | S downgrade_refuses 的 33/100/500 参数，行/版本/列类型保留 |
| IT-06 短值往返 | S nonempty_upgrade，NULL/中文/32 字符全字段相等 |
| IT-07 混合批 | I real_shape，13 行、12 SQL NULL、长原文无损 |
| IT-08 中途失败 | I partial_upsert，真实 PG 第一行 UPSERT 后除零，恢复本日/前日/质量/Dirty |
| IT-09 触发日复现 | S 合成 35 字符，另有真实 Provider 响应的隔离 PG 验证；不冒充生产写入 |
| IT-10 二次拉取 | I upsert_idempotency 与真实源隔离验证，行/Dirty 不重复 |
| IT-11 Raw 质量/分类 | I invalid_snapshot、duplicate_or_truncated、trusted_empty、TradeStatus；无假 PASS |
| REG-01 Daily/Backfill/CatchUp | 全部 unit 含 backfill_resume/catchup_scheduler/raw_completeness/trade_status；最终全量 CI |
| REG-02 Retention/Dirty/PAPER | 最终 CI 原 M17.1.1 五组、Dirty、PAPER 与 M13-M16 全量回归，不改断言 |

本机已完成 33 项迁移联测、88 项定向联测、1405 项全 unit 和 Ruff；
本机全量及最终 CI 必须记录实际结果，不把 collected 1901 当成 passed 1901。
既有弃用警告与依赖安全告警不在本补丁中伪装解决。

### 本机容量限制与基线对照

本机重复全量出现既有百万行 Retention 容量失败；不能记为本机全量通过。
该用例在 `run_retention` 的第 11 条 SQL 处触发 PostgreSQL 3 秒 statement_timeout，
返回 RETENTION_RETRY_REQUIRED 并整笔回滚，独立复查耗时 3060.775ms。
另从未修改的基线 `2979be9` 导出独立快照，在同一本机临时 PG17、同等负载下重复该用例，
同一断言失败、同为第 11 条 SQL 超时回滚，耗时 3060.325ms（基线 schema 为 0055）。
原断言、3 秒预算、Retention 实现和策略配置都未修改，不用跳过/放宽来换绿灯。
此对照证明该现象在基线也存在，不将其误报为本次 TEXT/清洗修复引入的功能问题；
不等于已完成本机平台容量优化，也不豁免最终同 SHA 完整 CI 的容量门禁。

## DoD 与 G1

| 要求 | 证明与剩余边界 |
|---|---|
| 数据源真实超长 | 已取得 35 字符、具体日期/代码/类型/空值统计 |
| 单头/非空扩容 | 0056 接 0055；S 六项；最终 current=heads 回执 |
| 原文/NULL | N/I 及真实源隔离验证 |
| 非法输入不假 PASS | I 错误质量持久化、Raw/Dirty 不变 |
| 幂等/原子性 | I 真 UPSERT/故障回滚，前日保留 |
| PG/全量/Ruff/CI | 精确最终 HEAD 的完整 CI + 附件；仍需检查最终 conclusion |
| M17.1.1/财务回归 | 完整原回归；业务账本没有写入或重算 |
| 实际业务回填成功 | **待审批/未执行**；无生产 Job ID，不标记 G1 完成 |
| SHA/CI/head/前后统计 | 批次表、同 SHA CI 回执、取证及本表；生产统计待实际验收 |
| 安全与范围 | 无生产 DDL/重启/回填/删除，无真实凭据提交；合成测试仅隔离库 |

生产库现有字段不会因推送代码自行改变。按 [Runbook](M17_1_2_suspend_runbook.md)
备份、审批、升级到 0056，再运行 2024-09-13 单日 backfill 和 validate-data，
等待两个 Job 终态、核对真实值/质量和旧财务不变后，才能关闭 G1。
结论只可为“代码整改通过，真实业务验收待完成”，且“通过”仍以最终全量 CI SUCCESS 为前提。
