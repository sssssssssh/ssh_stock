# A4-2.3.1 诊断交付：INSUFFICIENT_EVIDENCE，P2/P3 NOT_AUTHORIZED

## 结论与审批

唯一预注册实验已采集128/128样本，但**没有唯一可修复候选**。
Telemetry假设的8个预注册分块检查仅2个满足，C1没有出现generation-2 GC；
四次长generation-2 GC全部发生于C0、固定round1/position2，full/minimal均出现。
此外as_seeded阶段发生自动ANALYZE，不能当作统计环境稳定的反事实。
因此收集器COMPLETE/Job成功不等于因果成立：离线审阅标
`INCOMPLETE_ENVIRONMENT_DRIFT / INSUFFICIENT_EVIDENCE`，保留原工件及128样本，不重跑。

用户仅批准诊断分阶段提交并推送master。未批准修复、正式5/100试验、生产C1或正式L2；
P2/P3仍NOT_AUTHORIZED，capacity_ready/performance_eligible/production_read_authorized恒false。
本轮完成的是P0/P1诊断和无候选结案，不是A4-2性能关闭。

## 提交、冻结与修改范围

| 阶段 | 提交 | 内容 |
|---|---|---|
| P0 | `dedea76632a2af3752d149a6c4844b469cb2b8d8` | 原ZIP/1100样本/顺序/400控制点复算、七异常及邻近C0、H1–H5、冻结协议、四权威文档 |
| P1 | `947966dc5a33cc6d8a688431f6deb00a2dffa538` | 唯一实验工具、自然GC指标、45契约单测、PG17快照预检、独立一次性CI Job |
| 无候选结案 | 以本记录所在提交为准 | 固定ZIP离线审阅、统计漂移失败关闭测试、审阅JSON和本报告；不再次采集 |

新增`scripts/publication_tail_historical_a4231.py`、`scripts/a4231_attribution_metrics.py`、
`scripts/publication_lookup_tail_attribution_a4231.py`、`scripts/publication_tail_attribution_review_a4231.py`，
对应3个单测文件及1个快照集成测试。CI只新增独立lookup-tail-attribution Job；
没有改原audit/Core/lookup/capacity/release门禁。证据/假设/协议/报告位于docs/acceptance，
同步README、PROJECT_RULES、PRD、系统设计。backend/config/migrations/frontend及原诊断脚本相对3bdf无差异。

[冻结协议](v14_a4_2_3_1_attribution_protocol.md) SHA256：
`f2fe56c9b67376241d4c6fb55191172a4e178667fa89b983fefce81bf913d88e`。
生产C0源码仍`7708d91c831a64093f18aa4f8515789492762f464ccfe202ee0219b756f32976`；
原诊断脚本仍`2a2e1b73163ede40365941f9f0d9b9c4c4d5e31ba60b7bbf4a77e7b4f8e8d85a`。
P0提交的主CI为[run39820198404](https://github.com/sssssssssh/ssh_stock/actions/runs/39820198404)，
它与以下P1实验run严格分开，不合并成同SHA验收。

## 历史证据：HISTORICAL_NOT_ACCEPTANCE

来源44e46b0 / [run39785757520](https://github.com/sssssssssh/ssh_stock/actions/runs/39785757520) / attempt1，
artifact12429939366 ZIP SHA256：
`e2ceaf9137e0ce52c0d91201329bf0de15a4cd14ab6321aaebf74e069ba4eceb`。
1100样本、旋转顺序、全部分位数、400个C0/C1控制点完全一致。
[历史JSON](evidence/a4231_historical_replay.json)保留七异常repeat5/13/19/25/41/66/81及实际前后C0。

| 状态 | C0 P50/P95 秒 | C1 P50/P95 秒 |
|---|---|---|
| as_seeded | 0.084720 / 0.137348 | 0.065963 / 0.074127 |
| analyzed | 0.083800 / 0.088756 | 0.066162 / 0.191595 |

历史analyzed C1/C0 P95≈2.159失败保留；六个大GC相关异常及repeat81非大GC反例不删除。
这些数据不替代947966d或后续提交的正式容量收据。

## 本轮唯一实验：DIAGNOSTIC_ONLY

SHA947966d / [run39820748153](https://github.com/sssssssssh/ssh_stock/actions/runs/39820748153) / attempt1。
[归因Job119971061129](https://github.com/sssssssssh/ssh_stock/actions/runs/39820748153/job/119971061129)成功，
预检85项全部通过，采集2026-10-22 17:14:58–17:16:51 UTC（约113.27秒，含fixture准备）。
[完整工件12444391989](https://github.com/sssssssssh/ssh_stock/actions/runs/39820748153/artifacts/12444391989)：
attribution.json、四个child JSON、tests.xml；ZIP SHA256已下载复核：
`8457f553e548b4306c5d402cc86e8ea3afe3c754e1a34a80e47fc089796b9bcf`（259627字节）。
[可重复离线审阅JSON](evidence/a4231_attribution_review.json) SHA256：
`37fe47d5aa8abbe8c31cb9ce484b7198b5b69a69027ae4a1a8323ba009a2db8a`。

专用PG17.11，marker=`4dddcf52-d87f-41c3-add0-00ebf04a851b`，system ID=`7699541696851730476`；
4CPU/约16.77GB主机，容器CPU/memory限额为0（未限额），不宣称独占磁盘或受控冷缓存。
模型hash=`f8bb5cf42d3f38757eda46ff149239789638f3aabe14434cda6ed7fe9daee20f`。
正式迁移+原seed得到public603040/B503020，2000固定键hash、C0/C1模板hash、索引/settings、
同状态RR数据快照、四独立PID、全部Golden均核对；128样本原顺序保留，无补样。

下表是新诊断口径（两端同样启用tracemalloc），每格16样本；**不与历史绝对时间比较收益**。
as_seeded存在统计漂移，只作原始描述，不能参与稳定环境的因果结论。

| 状态 | 方案 | full P50/P95 秒 | minimal P50/P95 秒 |
|---|---|---|---|
| as_seeded | C0 | 0.233363 / 0.274752 | 0.233046 / 0.260228 |
| as_seeded | C1 | 0.205737 / 0.213145 | 0.206981 / 0.213050 |
| analyzed | C0 | 0.230048 / 0.256122 | 0.231267 / 0.257930 |
| analyzed | C1 | 0.204652 / 0.208486 | 0.204762 / 0.209575 |

### 机制、反例与环境缺口

四个长GC均为generation2、round1/position2，栈标签raw_decode/decode/loads/call/_json，
只代表触发点，不证明JSON或SQL是被回收对象的分配者。

| 状态/block | 方案/模式 | wall秒 | gen2秒 | execute秒 | JSON秒 | next秒 |
|---|---|---|---|---|---|---|
| as_seeded/0 | C0/full | 0.325322 | 0.095945 | 0.073928 | 0.121195 | 0.090702 |
| as_seeded/1 | C0/minimal | 0.323393 | 0.095873 | 0.071730 | 0.121648 | 0.090120 |
| analyzed/0 | C0/full | 0.323671 | 0.091222 | 0.076196 | 0.116237 | 0.091095 |
| analyzed/1 | C0/minimal | 0.326326 | 0.094343 | 0.074742 | 0.120044 | 0.091450 |

GC与JSON/next/CPU嵌套，不相加、不从wall扣除。四点client CPU约0.255–0.259秒，
backend CPU间隔约0.06–0.07秒（包含wall外采样，非精确独占成本）。
全部C1无gen2事件不证明旧C1异常不存在，只是本轮没有复现其长GC反事实。
full入场分配块中位数约352.5–371，minimal约27–28，分配差异成立但尾部方向不稳定。
H3冻结检查仅2/8满足：block0 C0满足、block1 C0方向反转，四个C1分块无长gen2。

as_seeded child0期间三张代表表被自动ANALYZE（17:15:41–17:15:44 UTC），
child1期间data_publication_row又被自动ANALYZE（17:16:08 UTC），reltuples/relpages改变。
后者502863/502508是规划器估计，**不是**B实际行数503020减少。
数据MVCC快照不冻结规划器统计；离线审阅失败关闭，不修改原COMPLETE工件。
analyzed两个child已采集统计字段一致，但H3反例仍在，不可剔除另一状态后宣称因果成立。

组件中位数：C0 execute约0.074–0.075秒、C1约0.048–0.049秒；两者next约0.090–0.092秒，
JSON约0.025–0.026秒。没有独立服务器FETCH指标，execute包含驱动传输/缓冲，不伪造FETCH拆分。
退出RSS最大252678144字节（约241MiB）；full采样无错误，前后wait blockers为0，
离散观测不证明所有瞬间均无等待。PG累计queryid/buffers/temp/WAL及CPU/RSS原值全在工件；
含observer的窗口不能推算生产独占资源消耗，进程末尾分配快照不是每样本分配归属证明。

| 假设 | 本轮判断 |
|---|---|
| H1 自然GC | 确认四个C0长gen2；不能解释旧C1六尖峰的唯一可修复来源 |
| H2 Proxy/行物化 | 两端保持不变；触发栈/分配摘要不足以给具体生产代码定因 |
| H3 Telemetry | 分配增加成立；方向/机制门槛未全部满足，不能支持唯一根因 |
| H4 顺序/共享历史 | 四长GC同round/position且模式交换是反例，尚无独立干预证实 |
| H5 execute/资源争用 | 无证据解释旧repeat81；统计漂移与不可用独占I/O仍有缺口 |

## 测试与CI（状态快照，不是发布成功）

本地Docker daemon未运行，没有启动它、服务或现有数据库。
本地单元测试禁用dotenv、显式使用不可用合成loopback URL；P1完整1849项通过，
结案工具新增8项；最终完整1857项通过（25.03秒，两个既有弃用警告），三组专项56项通过。
Ruff和diff检查通过。
PG17集成检查在CI执行，预检85/85通过；原lookup安全回归与Core全量回归不等于正式L2。

截至2026-10-22 17:23 UTC，947966d主CI归因/lookup/audit成功，Core全量测试仍运行，
capacity=SKIPPED/NOT_AUTHORIZED，release尚未运行，不能标整体PASS。
[A4-1](https://github.com/sssssssssh/ssh_stock/actions/runs/39820748132)、
[A4-2](https://github.com/sssssssssh/ssh_stock/actions/runs/39820748149)、
[Publication](https://github.com/sssssssssh/ssh_stock/actions/runs/39820748255)尚未全部完成，保持OPEN。
结案提交的新CI另绑定自身SHA；归因Job按协议跳过，不继承947966d的性能/容量准入。
旧工件、历史状态、采集成功不能补齐最新SHA正式收据。

复现命令（SOURCE.zip必须为固定工件，输出路径须不存在；审阅不连接数据库）：

```bash
python scripts/publication_tail_attribution_review_a4231.py --archive SOURCE.zip --output NEW.json
python -m pytest tests/unit/test_tail_attribution_review_a4231.py
python -m ruff check backend tests migrations scripts
git diff --check
```

本地完整单测的实际安全包装命令（禁用Settings.env_file，不能借用业务.env）：

```bash
env -u LLM_ENABLED DATABASE_URL=postgresql+psycopg://disabled:disabled@127.0.0.1:1/a4231_disabled_test TUSHARE_TOKEN=synthetic-a4231 python -c 'import sys; sys.path.insert(0,"backend"); from app.core.config import Settings; Settings.model_config["env_file"]=None; import pytest; raise SystemExit(pytest.main(["tests/unit","-q"]))'
```

T01–T13的历史复核、异常清理、隔离身份、失败关闭由现有及新增测试覆盖；
T08保留新旧GC与非GC反例；T14/T15=NOT_AUTHORIZED/OPEN，T16最新exact-SHA聚合验收仍OPEN。

## 未关闭项与后续（只一个方向）

旧正式P95仍失败；Telemetry未证明为根因；as_seeded统计漂移；分配者/顺序因果及旧execute异常未知；
新5/100、生产精确差异、正式603040行L2和聚合release均未准入，既有依赖漏洞独立保留。
唯一建议是**先审阅未来隔离实验的规划器统计稳定性契约**；本轮不改autovacuum/ANALYZE策略，
不追加采样刷过门槛，不承诺某修复必过。

未连接阿里云或业务数据库、未读取业务.env，未改生产SQL/数据/模型/公式/GC策略，
未改变300s SQL/发布保护、270min容量预算、batch500、1000万行预算，未启用A/B新读取。
