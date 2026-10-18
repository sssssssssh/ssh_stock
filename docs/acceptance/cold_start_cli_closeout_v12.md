# 冷启动与安全入口 V1.2 验收

## W01 复现

冻结基线 f3158dd5317f1da2ba950522b300f66b70d9f901；完整 CI 39139452440 成功。
Pandas 3.0.5 / NumPy 2.3.3，Alembic 单头 0058_data_publication。
修复前 `tests/unit/test_cold_start_v12.py`：43 failed / 31 passed（JUnit 保存在隔离实验产物）；
完整输入黄金样本两项已通过。bool/nullable boolean 正常掩码不误报，object 负整数与部分左连接稳定复现。
机会缺失样本分别真实抛出 None 比较 TypeError 与 object NA rolling DataError。

可复现：`python scripts/cold_start_comparison.py --output .codex_tmp/cold-start-comparison.json`，
以及 `python -m pytest tests/unit/test_cold_start_v12.py`。仅使用合成内存数据。
版本决定见 ../design/cold_start_version_decision.md。后续阶段/同 SHA 门禁结果随实现补齐。

## W02–W05 已实现

Factor 严格 bool/缺失归一、有效 active 优先及上市事实降级、重复键失败；Opportunity
有限数值/真布尔与缺失 rolling 防护，保留原分数政策。87 项引擎专项通过，包含 object/bool/boolean、
None/NaN/pd.NA、IPO/退市、单日/空表/重复键、非法字符串/对象/inf、三类正常机会与评分缺失。
完整黄金样本全字段一致，真实 Trend/Signal 输出 2→2；部分缺状态的误排除恢复后信号 0→2。
因此七类派生升 v2，不改配置 Hash、PIT 或冻结金融版本；旧身份读取/当前拒绝、旧队列拒绝均有 PG 回归。

CLI 清单（先检查实际源码，不假定旧命令等价）：

| 分类 | 命令与边界 |
|---|---|
| 安全入队 | daily、sync-basic、backfill、validate-data、research-eval、显式完整 recalculate |
| 无业务写入 | check-config；check-tushare/provider-smoke-test 外部探测，只取数据不持久化 Raw/Derived |
| 只读诊断/预检 | data-job-diagnose、retention-inventory、retention-check、retention-indexes 默认 |
| 显式运维写 | retention-run（配置+confirm）、retention-indexes（apply+confirm）、reset-admin-password；不属于计算后门 |
| 默认拒绝 | recalc-factors、recalc-market、recalc-sectors、recalc-states、evaluate-signals；无强制开关 |
| 进程入口 | worker/scheduler 仍使用既有队列/所有权/候选/发布，不是同步直写替代命令 |

危险 CLI 在有效 PG17 连接且有/无活动等待队列的 10 种场景中均退出 1、零写入；
逐表校验公开值/来源/质量、Job、候选、scope、source、preimage 内容摘要不变，
额外单测证明连 Session 都不创建。显式完整 CLI 保留参数、持久入队、去重和取消。
不映射 evaluate-signals 的非等价筛选，也不静默将单表命令扩大为完整补算。

## W07 S01–S26 对照

| 场景 | 证据入口/断言 |
|---|---|
| S01–S10 | test_cold_start_v12 + 既有 factor/opportunity 单测；冻结源码对比脚本、JSON 无非有限数 |
| S11/S24 | test_cli_derived_safety + test_cold_start_cli_v12 的有效库/有无活跃任务零写入 |
| S12 | 显式 CLI 去重/取消；既有 data_queue/API/Scheduler 和真实 Worker 发布 |
| S13/S14 | 实际 FactorService 计算后取消/去除候选所需因子，真实下游失败，A 值/身份保留 |
| S15 | 完整/部分/无历史状态三种实际 Worker→因子→机会→质量→根发布，未 mock 计算/质量 |
| S16 | 真实 quality 不借 A + 缺阶段/校验/版本/Hash 的既有 publication 负例 |
| S17 | 中途断连回滚并占槽、真实 COMMIT 后回执丢失不改 FAILED |
| S18 | 原单/双 Worker 容器及双 Worker 六次原子发布，RUNNING≤1 |
| S19 | 真实 API latest/JOIN/count/分页回归 + 容量多 RR 读者，八表/信号评价仅 A 或 B |
| S20 | 原 Research/Portfolio/PAPER/账本、M16 冻结合同/报告全量回归；不改这些生产文件 |
| S21 | v1 旧行仍可读但当前过滤拒绝、旧队列不冒领；Research 新旧版本共存负例保留 |
| S22 | 三级容量脚本与 data_publication_capacity_v12.md；生产 L4 未授权 |
| S23 | 原预算/SQL 超时/剩余时间负例，整笔回滚、A 不变 |
| S25 | migrations/config/依赖无 diff，0058 非空升级回归保留，current=heads |
| S26 | 同 HEAD CI 硬验证完整/专项 JUnit、三级容量、黄金样本、容器和浏览器收据 |

五条真实 Worker 测试（含取消/失败注入）已通过；本地全单测 1530 项通过，
前端 npm ci、157 项 coverage 与 build 通过。全量/容器/最终精确 SHA 门禁以最终 CI 收据为准，
不得以此阶段记录声称生产上线。原 0058 文件不变，没有新增空迁移。
L1/L2/L3 开发容量实验均已完成，603040 / 378240 行根发布分别约 78.32 / 39.43 秒，
详细数字、受干扰 WAL 上界与增强读者/最终 SHA 区别见容量报告，不以旧脏树测量伪装最终回执。
最后补齐每层发布前的预算拒绝、真实 SQL 超时回滚、十表 A 摘要/原像/槽位状态探针；
本地 L1 已通过，完整 L2/L3 的增强故障测量必须由最终同 SHA CI 再执行，旧提交绿灯不能替代。

本地首次全量复用了旧测试库，2118 passed / 5 failed：已有 14 条风险/交易测试明细且
0057 队列触发器缺失，不能满足原测试“全表为空/正式迁移齐全”的前提。未删存量数据、未改断言/迁移；
另建空的专属 PG17 库正式 upgrade head，同一批文件 20 项全部通过（旧库触发器数 0、新库 1）。
随后在又一个新建空库重新运行全量；首次失败不计入通过证据。后续复现应始终使用全新一次性测试库，
不要复用未知历史的 stock_test 或业务连接；最终同 SHA CI 的 PG 服务也是全新空库。
新库全量实际结果：2125 passed / 0 failed，429 warnings，后端 term 覆盖率 89%，耗时约 23分54秒。
其后追加的 3 项容量脚本防误连测试单独通过（CLI 文件共 14 项），最终同 SHA CI 全量应含 2128 项。
最终本地组合专项（引擎/CLI/真实 PG 入口/发布/调度/诊断）159 项全部通过，未跳过/放宽断言。
容量脚本在导入任何 app/Settings/DB 模型前校验并覆盖显式测试 URL，拒绝远端、非测试库名及缺失 URL；
不从业务 .env 创建 Engine，探测使用合成 Token。完整历史、版本/preimage 的五条 Worker 追加断言亦全部通过。
Compose config/build、Nginx、单/双 Worker 三组、24 场景以及 M16/M17 双视口浏览器均已开发自检通过；
最终 Git 提交后的 clean HEAD 回执和精确 CI 链接优先，不用之前的 SHA 替代最终门禁。

精确 CI 入口：最终 `data-publication-reliability` Artifact 内的
`data-publication-release.json` 同时保存 `head_sha`、`ci_run_url`、完整/专项测试数量、
三级容量和容器回执；与同包黄金样本的 clean HEAD 对照。静态文档不硬写自引用最终 SHA，
避免记录 CI URL 的文档提交又变成另一未验收 SHA。最终交付消息提供该真实运行链接；
CI 失败或缺任一回执不能标记交付全绿。

## W08 部署与回退前置条件

生产操作未执行。另批只读核对 Alembic 当前/heads、全部活动 Job、所有主机旧 Writer/CLI、
公开历史血缘、磁盘/WAL/备份余量；完成备份恢复演练和指定规模/Provider 测试后才能制定维护窗口。
先停 Scheduler/所有旧 Writer，证明旧进程和 SQL 已结束；不能心跳超时就改 FAILED 解锁。
既有 Scheduler 会因新版本不就绪而识别历史缺口；其行为保持原样，不新增自动历史迁移器。
因此维护后也不能未经日期范围批准就恢复 Scheduler：先完成批准范围的手动安全补算，
核对 catchup 候选日期、旧取消意图及 Dirty 范围，再单独批准恢复自动调度。
回滚应用也要核对 0058 协议、v2 来源与旧程序兼容，不能让旧 CLI/Worker 与新程序混跑。
保留 Job/Candidate/Preimage/Artifact/审计，不降级带证据的 0058、不自动回算旧财务。
历史补算另批日期/配额/容量。npm 继承的 11 项风险（4 moderate/3 high/4 critical）未在此专项升级。

## 授权边界

不连接真实生产库、不调用真实 Provider、不部署、不重启业务服务、不自动回填；
容量实验仅在显式指定的专用 PG17 合成库进行。不得将 CI 成功解释为生产上线批准。
