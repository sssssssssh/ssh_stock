# A4-2.3.1 阶段记录（P1工具已实现，实测尚未执行）

## 当前结论

历史结论仍为CORRELATED_NOT_CAUSAL；本轮实测为NOT_RUN，不提供因果修复承诺。
P0已提交`dedea76632a2af3752d149a6c4844b469cb2b8d8`：旧ZIP/1100样本/完整顺序复核，
七个analyzed C1异常连同同repeat和顺序相邻C0均保留，H1–H5假设及反证已注册。
[假设表](a4231_hypotheses.md) / [历史JSON](evidence/a4231_historical_replay.json)。

## 冻结协议与P1工具

[协议](v14_a4_2_3_1_attribution_protocol.md)已在P0提交冻结，SHA256：
`f2fe56c9b67376241d4c6fb55191172a4e178667fa89b983fefce81bf913d88e`。
P1入口会先验证协议等于父提交、原诊断脚本未改、生产C0及配置/模型/迁移/前端无差异、干净树。
再验证专用PG17 marker/system ID，之后才创建UUID子库并使用正式迁移与原seed。

新增`scripts/publication_lookup_tail_attribution_a4231.py`与`a4231_attribution_metrics.py`：

- 同public603040/B503020、快表2000键，两状态各两个新进程，固定Williams顺序，总128样本。
- 通过父RR导出快照保持同状态数据一致；只干预Telemetry生命周期，C0/C1对称；原lookup/JSON/next计时不改。
- 分代自然GC事件（含构造/退出阶段）、分配块/内存、CPU/RSS/PSS/buffers/等待均保留；GC嵌套不相加/不扣除。
- 限20分钟软预算、30分钟Job、每子进程300秒；异常/超限保留INCOMPLETE和已完成及失败样本证据。
- 子进程干净树/SHA/run/attempt/物理身份/协议/SQL模板/键摘要及32条原顺序均由父进程核对。
- 旧100×5矩阵与正式L2不运行；诊断Job无release准入边、无capacity_ready输出，内部授权始终false。

独立Job仅master首次push的`[a4231-attribution-once]`标记提交启用；普通提交/重复attempt不执行。
没有新试验结果时不得以工具单测或旧数据冒充P1成功。

## 验证与剩余项

本地Docker daemon未运行，本轮没有启动它或借用现有数据库。
本地仅执行不加载业务dotenv的单测/静态检查：完整单元测试1849项通过（两个既有弃用警告），
新增P1契约测试45项通过，Ruff与`git diff --check`通过。
本地未执行PG17集成测试；快照导入、候选安全预检及唯一归因采集交由隔离CI执行。
用户已明确授权本轮诊断分阶段提交并推送master；P0已推送，P1本提交准备触发唯一实验。
不存在的CI链接或尚未完成的实测结果不会标为通过。

| 阶段 | 状态 |
|---|---|
| P0历史证据/假设/协议 | 已完成并推送master |
| P1工具/自动测试 | 已实现；本地1849单元测试通过 |
| P1单轮实测 | NOT_RUN；本提交首次push后由隔离CI执行 |
| P2唯一修复候选/正式5/100复核 | NOT_AUTHORIZED，暂无实证候选 |
| P3生产C1/正式603040行L2 | NOT_AUTHORIZED |

Core/audit/A4-1/A4-2/Publication的旧3bdf状态只是P0背景，不能填充P1新SHA验收。
现有依赖风险、A4-2历史合并读取性能仍OPEN；本轮不修改npm audit、不扩大CI改造范围。
不连接阿里云、不读取业务.env、不改生产数据/SQL/GC策略/保护阈值/AB_MERGE_READ_ENABLED=false。
