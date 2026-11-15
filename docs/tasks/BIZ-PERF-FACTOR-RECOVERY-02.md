# BIZ-PERF-FACTOR-RECOVERY-02：候选写入真实调用链的离线性能根因定位与最小整改
日期：2026-11-16。唯一目标：使 ssh_stock 的因子重算任务正常完成，减少候选写入阶段的实际性能瓶颈。上一阶段3277c81修复默认路径取消检查；同SHA主CI、A4-1、A4-2、Publication全为success，但仍未证明真实PG17/Worker计算可用。
## 执行要求
1. 原GP线程继续。先核对HEAD=3277c81bc85382e939f58ba5d414fef3682b4de8、origin/master及工作区。前轮未跟踪 W05-GATE-01 两份文件属于保留资产，不覆盖。按AGENTS.md读取治理与业务权威文件。
2. 聚焦真实重算链路：recalculation.run_recalculation、factors/service.py、data_publication.py、repositories/replace_slice.py、Worker。找出每500行候选批次中查询已存在/已发布记录的准确调用栈、SQL形态、执行次数及事务范围。先区分因子写入与候选发布，避免错把其它阶段优化为主线。
3. 建立不连接PG17、不拉Raw、不启动Worker的可重复RED性能回归：固定S2规模或现有fixture，记录batch数、查询次数、构造参数规模、耗时（仅参考）、结果/身份/发布等价性。若离线mock不能证明数据库慢，必须标记DB_HOTSPOT=UNPROVEN，不得编造30%收益。
4. 若有确切N+1或重复查询可证明，实施一个最小优化，最多2个相关业务文件及2个测试文件，严守原事务、幂等、PIT、source hash、generation identity、并发/取消/失败回滚与发布原子性；不得新增迁移、索引、依赖或改变因子公式、阈值、策略；不得修改冻结文件/CI/安全插件。
5. 优先做RED→GREEN、受影响回归、ruff和git diff --check；完整测试如受环境限制明确报告。提供优化前后确定性查询计数和结果一致性。没有可信根因则停止代码修改，输出具体可复现缺口和下一步业务诊断，不去扩展W05工具。
6. 不连接生产PG17，不执行任何SQL/迁移/Worker/Scheduler，不修改Raw/Derived，不发起正式性能实验。B_GATE=NOT_APPROVED，TARGETED_PG17_GATE=NOT_APPROVED，ROOT_ATTEMPTS=0。
## 交付
- docs/acceptance/BIZ_PERF_FACTOR_RECOVERY02_CLOSEOUT.md：源码定位、RED/GREEN证据、精确diff、测试结果、风险与下一步。
- 不提交、不推送，等待ChatGPT独立审阅；任务书不得自行修改。完成后在GP线程回执。
