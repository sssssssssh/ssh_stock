# A4-2.3.1 P0 假设注册表：未预设根因

起点master `3bdfc3713fea595eaf913bbc347e76510d340b60`，初始工作树干净；fetch后origin/master一致。
旧工件严格按SHA256固定，1100样本、原顺序、全部分位数重算，400控制点无剪裁。
[本轮历史复算](evidence/a4231_historical_replay.json)标HISTORICAL_NOT_ACCEPTANCE，
新增七个analyzed C1异常的同repeat及原顺序前/后C0对照；完整时间、CPU/RSS/等待指标保留。
旧P95失败仍为2.159倍；本轮尚无实测因果结论，也不授权capacity。

## 开工时CI审阅（仅基线3bdf，非未来提交验收）

| 工作流 | run / attempt | 查询结果 |
|---|---|---|
| 主CI | [39808592711](https://github.com/sssssssssh/ssh_stock/actions/runs/39808592711) /1 | completed/failure；Core/lookup/audit成功；capacity跳过；release拒绝 |
| A4-1 | [39808592652](https://github.com/sssssssssh/ssh_stock/actions/runs/39808592652) /1 | in_progress，不能标PASS |
| A4-2 | [39808592664](https://github.com/sssssssssh/ssh_stock/actions/runs/39808592664) /1 | queued，不能标PASS |
| Publication V1.3 | [39808592361](https://github.com/sssssssssh/ssh_stock/actions/runs/39808592361) /1 | in_progress，不能标PASS |

主CI物证：Core12441980987 SHA256 `8b5ad34e128fcfad4904fa330edd2b8715d0173b27d2f7b8da0fa7bf5fafb3b6`；
release12441437059 SHA256 `f00f6be31f6d262ec76f5bfff32da4828b2c43fa823a27d536d4f47afe18af7f`。
上述是GitHub返回的工件摘要，不声称未下载内容已逐字段验收；P1必须绑定其自身SHA/run/attempt。

## 竞争假设（状态均UNPROVEN）

| 假设 | 已有支持 | 反证/缺口 | 可测指标 | 拒绝/不能支持条件 | 最小诊断 |
|---|---|---|---|---|---|
| H1 GC分代/分配节奏 | 六个analyzed C1尾部伴随大GC | C0亦有尖峰；repeat81非大GC；旧gc_count16无分代 | generation、duration、collected、分配块/代计数、调用栈标签 | 无长GC或不足以解释wall；分配者仍未知则不能因果命名 | 自然GC回调，不调整策略；128快表样本记录 |
| H2 动态代理/行物化 | 临时Proxy/Rows类、JSON代理及逐行next均有分配 | C0/C1代码对称；repeat66 GC不在next主要区间 | GC栈标签、JSON/next/完整wall、受限分配来源摘要 | 相同包装下只随其他因素变化；无具体机制则不提生产修复 | 两模式保留同一原包装，作为不变控制/机制观察，不另改生成器 |
| H3 Telemetry生命周期开销 | 每样本创建engine/线程/reader，计时外分配可能触发后续自然GC | 旧数据无反事实；不能仅据静态分配断言根因 | full/minimal交叉、GC分代、阶段、allocatedblocks、CPU/RSS、PG计数 | 各独立块方向不一致或缺机制；不能以单次P95差异称因果 | 唯一干预为是否启用原Telemetry；两端C0/C1都运行 |
| H4 顺序/共享对象累积 | 原先慢后快，样本/观察器在单进程累积 | 五方案有旋转；没有分配栈，相关不等于致因 | 固定Williams交叉顺序、block/round/position、PID、进程记忆/GC史 | 改顺序或独立块后无稳定关联；不据噪声选顺序 | 每状态两个新子进程，相同重启/预热规则，两模式共用同块 |
| H5 后端execute尖峰 | repeat81 execute约0.06065s | driver execute含传输/缓冲；其他尖峰backendCPU约0.03–0.04s | execute、backendCPU、PSS calls/exec/buffers、前后wait | wall大但execute/PGCPU不大；无独占I/O证据不归因磁盘 | 相同窗口PG计数差量与采样；不执行新慢表压测 |

## 归因纪律

唯一对照因素是Telemetry的完整生命周期（构造、入退采样、后台线程、dispose）。
最小模式只不创建此对象，其余Proxy/Rows/JSON、GC记录、计时与PG前后观测完全一致。
若出现差异，最多支持该整体因素；不能自动分解成“动态Proxy已证实有错”或“生产GC必过”。
自然GC的代别/耗时可证实事件本身，但不能单靠分配栈关联给某一SQL分配对象定因。
无机制或有明显反例时保留CORRELATED_NOT_CAUSAL/MIXED/INSUFFICIENT_EVIDENCE。

本机Docker daemon未运行；本轮不擅自启动它、现有服务或业务数据库。
P1仅拟在新建双身份PG17的CI独立Job执行；无推送授权时只交付工具/测试，不冒充已有实测。
生产保持C0、AB_MERGE_READ_ENABLED=false，P2/P3未授权。
