# V1.4 A4-2.1 验收矩阵

状态：P1 契约建立，P2 实现就绪，P3 完整实测 OPEN。基线 `02c69c612786`。不授权生产或下一阶段。
设计见 [ADR](../design/adr_v14_a4_2_1_ci_partition.md)；机器键定义见 `scripts/a42_ci_contract.py`。
自动测试从基线代码独立生成 1002 个 required keys，要求新分片 exact set equality；额外 6 个 auxiliary 明示。

| 编号 | 契约 / 验证 | P1 证据 | P2/P3 待完成 |
|---|---|---|---|
| T01 | 旧 CLI 默认与显式 scope/level 参数互斥 | 设计 | CLI 回归 |
| T02 | 原矩阵集合相等、无重复分配 | partition 单测 | 实际工件集合 |
| T03 | 10k、100k 各 177 read + 59 plan | partition 单测 | 两级完整实验 |
| T04 | 百万 full 10×2×3 | partition 单测 | 全读原始工件 |
| T05 | 百万窗口六档×2×3 | partition 单测 | 同 job baseline + EOF |
| T06 | 百万 monthly 9×3×3、430 天同根 | 契约检查 | 三月实际工作负载 |
| T07 | 每规模 59 actual cursor plan groups | 缺组拒绝 | 177 组全部 actual |
| T08 | 15 shapes×5×3 | partition 单测 | 225 读取 |
| T09 | E3 full 18 + monthly 27 | partition 单测 | 仍标 UNPROVEN |
| T10 | 百万 RR2 4×2×3 | partition 单测 | 实际并发读样本 |
| T11 | 物理随机 marker/ID 在 DDL 前校验 | 错身份拒绝 | 临时 PG17 负向集成 |
| T12 | schema/HEAD/baseline/attempt/model 精确 | 负向单测 | 工件集成 |
| T13 | fixture counts/recipe/resource class 精确 | 负向单测 | 百万 3,104,443 黄金 |
| T14 | 行数/自然键/hash/dtype/NULL/dup | 负向单测 | 跨 variant Golden |
| T15 | FETCH 5000、EOF、close | 负向单测 | 真游标故障 |
| T16 | E0 每次 / T8 全读或月尾 | 负向单测 | 真月链计数 |
| T17 | 完整/取消/中断/预算不足检查点 | 部分状态拒绝 | 故障注入/软截止 |
| T18 | 57014、未知提交不变成功 | SQLSTATE 拒绝 | 原安全回归 |
| T19 | 三容量级唯一、规模不降 | merger 单测 | 单级真实测量 |
| T20 | 缺/重复/错 SHA/attempt 容量拒绝 | 负向单测 | artifact merger |
| T21 | capacity A 摘要、rollback、占槽、原预算 | 负向单测 | 原 run_level 不变 |
| T22 | 上游 cancelled/skipped/failure 阻断 | 负向单测 | always release 状态 |
| T23 | 原 pytest/Ruff/Alembic/front/container 保留 | 未执行 | 最终 SHA 完整 CI |
| T24 | infrastructure/correctness/performance 分离 | 永不授权单测 | 总结/工件/开放项 |

P1 实际验证：`test_a42_ci_partition_contract.py` 与 `test_a42_receipt_gate.py`：37 passed。
这是纯契约单元验证，不等于已采集真实 PG17 / 百万 / 容量 / CI 结果。

## 旧证据冻结（仅历史诊断）

旧 A4-2 run 39561947935：primary CANCELLED，supplemental success；旧主 CI 39561948002 CANCELLED。
三种规模各 177 reads；10k/100k 各 59 plans，百万仅 6/59 plans，缺 53 组。
旧全读 protected safe-total 中位数（秒）：

| fraction | Q0 等保护 | Q1 | S5 |
|---|---:|---:|---:|
| 0.1 | 105.786832 | 108.047866 | 102.383840 |
| 1.0 | 107.151900 | 108.545931 | 104.931900 |

不能由这些部分历史数据推出新提交 PASS，不能与不同 runner 的新时间直接作优化比率。
primary 原 ZIP SHA256：`f7e7983dfe5293415f5042ea7fa66430bf69f26e8d86f740365c4b11cb93d4d1`。
已保存三份解码日志，SHA256：

- primary 119095051829：`578e334ad57a827eae123c20f4be54b9ec9c3f7e3fea2e9fe4ae5425c30832ee`
- main 119095053006：`89d9a76fdc3adede363a2e33627a8b467b22d542b3087dc8a7d2481d3ce27f68`
- supplemental 119095051479：`aa5931ee2a494efc48b35286d38ee09e114315d059a4cc4a5015780657b6c1ad`

日志/原 ZIP 留在忽略的本地取证目录，不提交潜在私有运行细节；可追溯的公开 run/job/artifact 元数据及 digest
见 [历史索引](evidence/v14_a4_2_1_history.json)。历史记录永不填补新 SHA 缺失组。

## P2 实现与本地证据

新增 `a42_scope` 复用原实验 fixture/trial，旧默认 CLI 不变；三容量级可单级调用，原 run_level AST 不变。
`a42_artifacts` 在任何实验前记录 NOT_STARTED，独立保存完整 gzip 组文件和 SHA256；
当前组失败保留 INCOMPLETE，预算不足不启动下一组；不自动恢复旧 HEAD/attempt 的结果。
`a42_gate_io` 与 `ci_release_gate_v14_a4_2_1` 检查上游状态、物理身份、完整键、Golden、实际计划和容量安全。
原主 CI 除移出容量与提取发布断言外，所有步骤保持；自动 AST 测试证明原发布断言完整保留。

本地新建的专属 PG17（不是任何业务数据库）已完成：六档窗口、三月链、完整 EOF/close、
原生游标 actual rows/loops/buffers、取消后保留先前组、L1 十表发布与两个回滚探针，以及错 marker/system ID 拒绝。
扩大定向回归 301 项通过（544.52 秒）；后增门禁控制与冻结检查另计，P3 再执行全量回归。
另一次重复集成验证曾与扩大回归误并行共用本地测试实例，因另一测试创建/移除子库而使数据库集合比对失败；
没有放松断言，改为串行复核。CI 各工作负载使用独立物理实例，不共用该本地环境。
最终 P2 定向串行复核 100 passed（24.34 秒），此前并行测试的集合比对问题未再出现。
前端 `npm ci` / coverage / build 通过：23 文件、162 测试、行/语句覆盖率 87.27%。
依赖审计仍报告 11 个既有漏洞（4 moderate / 3 high / 4 critical），本轮没有越界升级依赖。

P2 首次真实 CI 的兼容性失败与工件索引见 [失败冻结](evidence/v14_a4_2_1_p2_ci_failure.json)。
修复后新增真实容器采样、全部十种 full 变体、原 CLI 安全拒绝回归；定向 131 项通过（33.32 秒），
随后追加的 provisioning 冻结契约单测也通过。原计划 actual/loops/buffers/EOF/close 十类损坏与容量错身份六类反例均拒绝。
初次本地全量在修复过程中主动中止，仅 155 项完成，不计作全量通过；修复代码冻结后重新执行。
最终 CI 尚未成功，不能放行，也不以 L1 success 代替 L2/L3 或整个 release gate。

## P3 工件审查与执行

本地 `7f5857e` 全量 2468 passed（2417.46 秒），后端覆盖率 89.28%，原 70% 门槛未改。
该提交的远程核心也成功：真实三组单/双 Worker、十表原子发布、28 个 runtime browser 场景均完成。
实验阶段实际通过 10k/100k 各 236 组、百万 full .1 的 30 组、window .1 的 21 组及两个百万计划分片。
这些是旧阶段诊断，不能填入下一提交的最终矩阵。

P3 审查补充关闭了 auto_explain 完整参数输出、探针 57014 时丢弃可用 profile、未引用旧 gzip 混入、
原独立 publication release 文件未输出的问题。声明、实际计划计数和 EOF/close 不省略；生产 SQL 不变。
P3 增量定向验证 129 unit + 6 PG17 integration passed。完整结果、工件索引、预算及 OPEN 项见
[执行报告](v14_a4_2_1_closeout.md)；未获新 Runner，也未操作业务云环境。
Alembic 在该专属 PG17 升级成功，`current=heads=0058_data_publication`。
这些是适配器/安全回归，不替代真实百万/L2/L3 或最终 exact-SHA CI；INFRASTRUCTURE/CORRECTNESS 总体验收均 OPEN。
