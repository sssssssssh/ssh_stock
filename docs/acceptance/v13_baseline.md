# V1.3 候选写入基线

冻结业务实现：`9a377e410516d6bf53e6d1363ec5094af88478df`，master 干净起步。
本报告只记录合成 PostgreSQL 17 测量，不是云端业务性能或生产验收。

## 隔离与黄金样本

性能入口 `scripts/publication_candidate_benchmark_v13.py` 在导入 Settings、模型和 Engine 前，
强制显式 loopback PostgreSQL、以 `_test` 结尾的数据库。内部再创建唯一测试库，正式迁移至 0058，
结束后仅移除该唯一合成库。无真实 Provider/LLM 调用，不加载业务库连接作测试参数。
冻结实现通过 `git show` 精确读取，后续与优化实现使用同一脚本、相同数据和配置。
黄金样本比较八类核心表的首次及重复写入，包含候选 JSON、原像、来源、自然键及删除标志；
时间输入固定，不将服务器默认时间差异伪装成业务差异。

旧业务任务只读核验为 CANCELLED、publication ABORTED，无残留任务 SQL；本轮不更改其状态，
不启动 Worker/Scheduler，不执行业务库迁移、回补、清理或部署。

## 初始测量

Windows、Python 3.12、独立 PostgreSQL 17.6；缓存未受控，不声称冷缓存测量。
1000 条候选、非空 public A、空候选起步，三次候选准备分别为 2.571 / 2.551 / 2.631 秒，
每次 10 条 SQL（包括每个 upsert 的来源登记/凭据失效），不是正式发布耗时。
三次候选摘要相同：`67c788943be416a505656c63d48d1cef`。

真实 EXPLAIN ANALYZE BUFFERS 显示：500 键 overlay 查询使用 Append 和反关联 Nested Loop，
候选侧先按日期扫描、实体 OR 过滤，public 分支再对已物化候选反复比较 row_key。
一个样本的反关联 Materialize 为 500 loops，平均 250 rows，查询执行约 402ms、shared read=0。
这证明小样本已有 CPU/比较放大，不能仅凭 DataFileRead 认定磁盘故障；更大规模仍须实测。

完整原始计划与各轮 SQL/操作 p50/p95/p99、RSS、WAL、表/索引大小保存在忽略目录
`.codex_tmp/v13-baseline.json`。测量进程完成后再汇总大规模结果；未完成项不得标 PASS。

## 当前边界

Commit A 不修改任何生产查询、发布、计算或取消实现。下一步优先验证精确自然键批量 join，
避免通过全局覆盖视图核对，同时保持 JSON 类型、首次 base_row 和最终原子发布协议。
50% 性能/往返目标、B2/B3、冷缓存、容器及 exact-SHA CI 均未在本基线报告中宣称通过。
