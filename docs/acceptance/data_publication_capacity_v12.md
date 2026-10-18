# V1.2 候选发布容量与上线判断

## 结论与实验边界

**生产容量未证实，不批准直接上线或全年回算。** 代码正确性与合成容量分开验收。
1000 万 patch 行 / 合并阶段 300 秒仍为保护上限，不是生产吞吐承诺；没有提高预算、
分段发布、自动清候选/原像、改质量阈值或新增索引/迁移。

实验只在专属 Docker PostgreSQL 17 的唯一临时合成数据库执行，非业务 .env、非真实行情。
运行脚本需显式 TEST_DATABASE_URL、loopback 且数据库名以 `_test` 结尾，并传
`--confirm-synthetic`。唯一 CI 例外是仓库隔离服务 stock_db；不接受任意远端 URL。
每级有自己的库，正式 upgrade head；退出只回收脚本自己创建的 UUID 数据库。

```bash
python scripts/data_publication_capacity_v12.py --confirm-synthetic \
  --output .codex_tmp/cold-start-capacity.json
```

脚本运行前显式设置专用测试 DATABASE_URL/TEST_DATABASE_URL，不能复制业务连接。
`--levels smoke` 仅 L1，不可据此宣称 L2/L3 完成。最终门禁必须使用默认全三级。

## 负载与采集方法

| 层级 | 股票×开市日 | 组成 |
|---|---|---|
| L1 | 10×2 | 全八类派生 + signal_forward_eval + 非 Raw 质量证据 |
| L2 | 5000×20 | 50 行业/100 题材，五类股票派生及每股信号评价 |
| L3 scaled | 500×120 | 股票维度为目标的 10%，完整 120 日；不冒充 5000×120 |
| L4 | 未执行 | 脱敏真实统计/Provider/磁盘及恢复演练必须另行批准 |

每级先有真实公开 A，再通过现有 PublicationWorkspace.upsert/检查点、正式 JSON patch、
scope、preimage 比较、根所有权 CAS 和一次 SUCCESS 提交发布 B，覆盖十类表。
性能夹具只提供结构性质量凭据，不假称运行金融引擎；真实因子/机会/质量/Worker 冷启动
与取消/失败由 test_data_publication.py 的五条真实链路另证。未替代任何原业务质量门禁。

输出 JSON 包括每阶段时间/进程峰值 RSS、写入速度、候选/原像行数与 JSON bytes、
表与索引体积、数据库总量、WAL LSN 增量、根提交耗时、三读者请求 p95/样本数、
锁等待/顶层 Writer 采样，以及候选实体索引、公开 JOIN、发布筛选的
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)。RSS 是测试进程至该阶段的高水位，非逐阶段新增量。
并发读者每个请求使用一个 RR/READ ONLY 快照：latest/count/八表来源/有序分页/JOIN、
信号与评价的值均必须全 A 或全 B，覆盖检查点及真正发布前后。
最终增强脚本每级在 B 候选完整提交后另做两个真实发布层探针：行预算设为 1 明确拒绝，
以及首表已执行合并后在第二表之前注入真实 PostgreSQL 57014 语句超时，随后完整 rollback。
逐表有序 MD5 聚合核对十表全部内容/身份仍为 A，preimage 仍为空，并记录根 RUNNING、
ledger PREPARING、执行槽位仍占用和回滚耗时；确认是已知回滚后，测试夹具再正常发布并核对
最终 SUCCESS/PUBLISHED。这是测试发布层的故障探针，不是新增 Worker 自动恢复/重试逻辑，
更不允许重放未知提交；实际 Worker 失败/取消/断连终态由独立集成故障用例验证。

WAL 是实例级 LSN 差值。本地与全量测试并行时包含同实例其他测试写入，只是受干扰上界；
以 CI 串行独占服务、同 SHA 原始 JSON 的测量优先，不能把本地受干扰值当单任务精确 WAL。
候选和原像全部保留到测量完，脚本退出时只销毁自己的合成数据库。

## 数据、计划与可复现身份

开发阶段 L1（加强后的八表/评价读者）：164 candidate / 164 preimage，写入约 0.331 秒，
根提交约 0.124 秒，读请求 p95 约 41.2ms，候选+base JSON 226954 bytes、
preimage JSON 124284 bytes，进程 RSS 高水位约 160.5MiB。
这是脏工作树开发测量，不是最终发布 SHA 回执；完整 L1/L2/L3 及实际环境优先读取
最终 CI `data-publication-reliability` Artifact 中 cold-start-capacity.json。
CI 对三层全部存在、无读者错误、RUNNING≤1、行数/提交时间未越预算做硬断言，
并绑定 clean HEAD；同包保存黄金样本 JSON、专项 JUnit、全量 JUnit 及容器证据。

开发大规模同次实验 L2 已完成：603040 candidate / 603040 preimage，写入 604.999 秒
（约 996.8 行/秒）、根发布 78.324 秒；三读者无混合，p95 118.12ms，无采样到锁等待，
最高 Writer=1。candidate+base JSON 780528676 bytes，preimage JSON 425936950 bytes；
候选表+索引约 1.023GiB，原像表+索引约 0.592GiB，DB 增长 1882537984 bytes（1.753GiB）。
进程 RSS 高水位约 189.3MiB；WAL 差值 5527061808 bytes，因并行全量测试只作受干扰上界。
该初次大实验使用三表 JOIN/count/分页与信号评价计数读者；后续增强到八表来源和评价值逐请求校验，
增强版 L1 已通过，最终 CI 三级均使用增强版。不能混称两种 p95 或源 SHA。
未改发布 Service 或索引，没有“SQL 优化前后提速”的宣称；此处交付实测瓶颈与边界，不顺带重构。

同次 L3 缩比（500 股×120 日）也完成：378240 candidate / 378240 preimage，
写入 562.552 秒、根发布 39.431 秒；读者 p95 65.63ms、零混合/零错误、Writer 最高 1，
候选+base JSON 497070803 bytes、preimage JSON 271952190 bytes，DB 增长 1193492480 bytes；
WAL 差值 3390881864 bytes 同样受并行测试污染，只作上界。
三级均未越 1000 万行/300 秒预算；实际测量没有覆盖 5000×120 或生产全年负载。
这是开发测量完成，不替代最终 clean SHA 的增强八表读者重跑与生产 L4。
上述早期本地 L1/L2/L3 数字不含这两个发布层回滚探针；最终 CI 原始 JSON 必须每级含
rollback_probes 两项，WAL/磁盘包含一次成功发布及两个测试回滚（含死元组/审计回滚开销）。
CI 明确核验每次 A 摘要不变与槽位事实，不能把早期只有成功发布的数字说成最终故障测量。

## 长期保留与容量估算

候选行包含 B JSON 和 A base JSON；preimage 又保留 A，另有索引/TOAST/膨胀和 Raw/冻结结果。
不能按一个公开行大小简单估计证据磁盘，长期未配置 GC。
以实际某层数据库增长量 D（after.database_bytes−before.database_bytes）估算：
若每天一次**同等整根范围**实验，按线性增长保守规划 30/90/365 天为 30D/90D/365D，
再加索引维护/备份/WAL/PITR/失败候选和安全余量。L2 的一次是整 20 日范围，
不能当每日单日刷新成本；失败/取消候选也会增长。
生产需测真实行宽、题材密度、修复频率和失败率，建议独立容量审批，不擅自写清理任务。
以本地 L2 D 为例，上述保留为约 52.60/157.79/639.94GiB（30/90/365 次同规模发布），
不含额外 WAL/备份/Raw；不是对真实每日数据增长的预测。
该粗算不是磁盘下界或容量承诺：public 更新及故障探针死元组可能由 VACUUM 重用，
候选/原像长期留存则持续增长；生产应分别测逻辑留存、物理膨胀与回收，不直接套用倍数上线。

## 失败保护与生产门槛

原发布回归继续覆盖超行数/剩余时间/SQL 锁超时、COMMIT 回执丢失、中途连接失效和
旧直写改变 preimage；失败保留 A，未知结果保守占槽，绝不自动 replay/分段成功。
V1.2 CLI 已默认封禁直写；管理员/旧程序仍可能越过新 CLI，故 preimage 防护继续保留，
不是任意写者的全局 fencing。双 Worker 原队列容器验收继续要求最高顶层 RUNNING=1。

上线前另行授权：生产只读 Alembic/Job/旧 Writer/血缘基线，磁盘/WAL 与备份恢复演练，
真实全市场日常及批准日期范围补算，停所有旧 Writer 后统一部署。
根本超出 300 秒/行预算则拒绝上线该规模，先做独立设计/索引/预算评审；不能拆事务绕过。
