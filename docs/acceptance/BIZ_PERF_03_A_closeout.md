# BIZ-PERF-03-A：全链路诊断交付与验收边界

基线 `fe94bddc6cf597b3e3a48f11024993cc6c7f2b01`，master 唯一分支。
负责人已审阅 W00 并明确允许实施及最终提交推送。

## 功能与使用

`PERF_DIAGNOSTICS_ENABLED=false` 默认关闭。启用后重启 Worker，只观测后续由原入口执行的
任务；开关本身不会入队或执行任务。报告默认存于 `data/diagnostics/performance/<UTC日期>/`，
每次执行生成独立 trace UUID，task/root 保留原 Job 身份。本地目录应只允许运维人员访问。
旧 `WORKER_DIAGNOSTICS_ENABLED` 仍是独立诊断，其数据库快照机制保持原样。

配置示例：

```dotenv
PERF_DIAGNOSTICS_ENABLED=true
PERF_DIAGNOSTICS_DIRECTORY=data/diagnostics/performance
```

离线汇总只读取指定 JSON，不初始化应用、读取 dotenv、连接数据库或触发任务：

```bash
python -m scripts.performance_diagnostics_report data/diagnostics/performance/日期/TRACE.json
```

脚本输出按 Git SHA、配置摘要、数据上下文分组的中位数、最小/最大、标准差和 SQL Top N。
少于 20 份报告的 P95 明确为 null。阶段是 inclusive 时长，不能相加当整链墙钟；覆盖时间使用
区间并集，SQL/FETCH 与其父阶段不能重复累计。阶段 UTC 区间受时钟调整影响，duration 本身
来自 monotonic；覆盖比例仅辅助展示，不能作为精确独占 CPU 或网络时间。

## 实际边界

- Worker 根上下文以 ContextVar 隔离，每次尝试一个 trace；子任务不创建第二根 trace。
  来源使用现有 worker_source 启动快照，没有 Git 时明确 null，不将磁盘新 HEAD 贴给旧进程。
- 读取器保留原 execute、5000 行 partitions、检查点和构帧顺序；候选写入仍是原 500 行批次。
- SQLAlchemy cursor 事件只计数计时；指纹去字面量/注释后取 SHA256，不保存 SQL、参数或
  异常消息。复杂反斜杠/嵌套注释语句归为 unavailable，至多 128 个摘要加 overflow 桶。
- driver fetch 只借用原 policy 的 server_cursor_factory 观察点；无该路径时 fetch 统计为 null。
  execute 不是纯服务器执行时间，driver fetch/partition 同时含传输及 Python 处理成本。
  结果字节、网络分解和不可知 rowcount 保持 null，不遍历结果去猜字节数。
- 资源仅在根边界采集。CPU 是本进程区间 CPU 时间 / 本进程区间墙钟的单核百分比，可超过 100%。
  RSS 原生峰值为进程生命周期高水位；线程数和网络计数未可靠采集，明确 null。
- 当前实际插桩覆盖读取、构帧、统一 compute、候选 lookup/store、跨表质量、发布准备、
  原最终 CAS 后 commit 与收尾。queue_wait/claim 的独立时间及引擎内部纯筛选仍未单独插桩。
  未出现或未安全分离的阶段通过 coverage/coverage_reasons 明示，不能伪造零耗时 success。
- 最终 commit 收到 ACK 后才更新根诊断终态；子 Job 终态不能覆盖根状态。未知提交继续 incomplete，
  诊断不新增读库对账、不改变原未知提交恢复规则。
- 文件先写唯一 pending，再以不可覆盖的硬链接原子公开 JSON；不支持硬链接时脱敏 warning，
  原业务结果保留。硬杀进程/断电不保证存在最终报告，未实施改变退出时序的信号钩子。
- 4096 条 span 上限后保留聚合和警告，不逐只股票打印日志。全量边界及候选查询迭代的更细
  exclusive 拆分未完成；该版本不是全链路性能问题已解决的证明。

Schema、脱敏示例及汇总示例位于 [证据目录](biz_perf_03_a/schema.json)。示例身份明确为
EXAMPLE_NOT_RUNTIME_EVIDENCE，git_sha=null，不能替代真实任务、当前代码或性能证据。

## 检查记录

首次针对性命令：

```bash
python -m pytest tests/unit/test_performance_diagnostics.py tests/unit/test_calculation_frame.py -q
python -m ruff check backend tests migrations scripts
```

初轮 24 passed、0 failed、0 skipped，退出码 0；Ruff 退出码 0。
完整 pytest 已实跑，Windows 初次收集有 10 个既有 Linux fcntl/resource 错误及一个本轮测试
basename 冲突；后者已通过重命名新集成文件修复。没有跳过或修改旧测试。
最终复测结果在下方追加，不能继承基线 CI。

首次固定 CPU 计时器 OFF/ON 各 3 次（含 flush）的原始记录见
[offline_overhead.json](biz_perf_03_a/offline_overhead.json)。中位数 527.577ms -> 646.448ms，
增加 22.532%，输出一致、数据库调用 0。该观察超出 3% 目标，也不是完整 Worker 开销；
测量期间隔离 PG 测试在同机执行，资源竞争未隔离，保留原始结果，不能筛掉或冒称验收通过。
新增真实根任务 PG17 测试覆盖三对成功 OFF/ON、取消和失败配对，检查全部已发布业务表的
字段/顺序及终态等价；测试并不把诊断文件生成视为任务成功。

## 验收状态

当前保留 `PARTIAL / DIAGNOSTICS_IMPLEMENTED / OVERHEAD_OPEN / FULL_REGRESSION_OPEN`。
T01/T02/T04/T05/T07/T08/T09 有针对性单测；T03/T06/T11 还须真实 PG17 及 Linux CI 回归。
T10 根任务开销须从至少三对原始测量复算并确认不超过 3%；超出即不能 PASS。
T12 要求最终提交 Linux 完整 CI 通过。未完成项不能由普通合同绿灯、样例或旧 SHA 结果替代。
没有实施任何性能优化，没有修改生产 SQL、金融公式、迁移、发布保护或高成本工作流。

## 回滚

先将 PERF_DIAGNOSTICS_ENABLED=false，重启 Worker 后续进程以关闭新诊断；已经运行的任务
不热切换配置。报告保留本地供审阅，不需要清库或降级迁移。源码回滚用新的 revert 提交，
不得 reset、强推、覆盖历史验收或修改上轮质量优化撤回结论。
本阶段完成后等待负责人审阅，不自动开始下一项热点优化或正式性能实验。


## 第一版实测补充（保留，不覆盖）

本机 PG17.6 物理实例独立 marker/system identifier 核验后，5 个真实 Worker 配对回归通过，
0 失败/跳过，15 warnings，326.81 秒。包含三对成功任务和一对取消、一对失败，所有业务表
比较及根发布终态相同。原始时间见 [根任务记录](biz_perf_03_a/root_overhead.json)。
成功任务 OFF 中位数 37,756.230ms，ON 39,889.498ms，额外 5.6501%，超过 3%。
据此减少重复指纹解析，采用至多 128 条的 SQL 字节摘要到规范摘要缓存，不保存原文；
新一轮结果独立登记，不取两轮最有利样本，不把第一轮改写为通过。
针对性最终单测 28 passed、0 failed/skipped（6.15 秒）；Ruff 通过。
最终 Windows 全量收集仅剩 10 个既有 fcntl/resource 平台错误（13.34 秒），退出码 1。
没有降低覆盖率门槛或跳测，当前尚无完整覆盖率与 Linux 全绿结论。


## 最终本机回执与未完成项

指纹缓存修改后：针对性 28 项测试再次通过（4.32 秒），Ruff 通过。第二轮完整 PG17 复测
在因子分块收尾停滞，测试库显示连接 idle in transaction / ClientRead，不能解释为 PostgreSQL
仍在执行 SQL。该测试进程已终止，本轮记 INCOMPLETE，不纳入三对开销统计。
随后单对定位运行启用线程栈，最后记录位于 opportunity.compute 附近，栈出现 pandas take
且输出不完整，进程非零结束，未产生完整 JUnit；原因未定，不以此宣称根因已修复。
独立测试实例已停止。没有结束用户服务或操作业务库。

本机实际通过的是前一版 5 项根任务回归及当前 28 项针对性单测；不能合并冒充同一最终
SHA 的完整验收。第一版三对开销 5.6501% 未过，当前缓存版尚无有效三对结果。
离线计时器 22.532% 结果继续保留。当前不开启默认诊断，不运行新正式基准，不进入下一阶段。
所有本机结果为工作树候选，不继承 fe94bddc 的 CI；推送后的普通 CI 对最终提交独立执行。
CI 链接可从本仓库 Actions 查找该提交，尚未有通过结论。

| 验收 | 实际结果 |
| --- | --- |
| T01 生命周期 | 单测通过，前版真实根报告通过 |
| T02 异常 | 原异常保护单测通过，前版 PG 失败路径通过 |
| T03 取消 | 前版 PG 配对通过；最终缓存版完整回归未完成 |
| T04 重试/身份 | 单测 trace 不同且 task/root 保留；子终态不覆盖根 |
| T05 SQL | 受控事件计数/失败/脱敏单测通过 |
| T06 FETCH | 计数单测/原读取器测试通过；最终 PG 流式完整验收仍开放 |
| T07 资源 | 单位、null 语义单测通过；线程/网络不可用 |
| T08 Schema | 样例通过 JSON Schema 校验 |
| T09 默认关闭 | 无报告单测与前版 OFF 根报告验证通过 |
| T10 开销 | 未通过：前版 5.6501%，缓存版有效三对缺失 |
| T11 结果等价 | 前版成功/取消/失败全部表值配对通过；最终版待完整复测 |
| T12 全量回归 | Windows 10 个平台收集错误；最终 Linux CI 未通过前保持开放 |

未实现独立 claim/queue、纯筛选、可靠线程数、网络归因、无 Git 镜像精确 SHA。
本交付为可继续审阅的诊断实现，不满足全部 Definition of Done，不标 PASS/封版。


## 2026-11-03 R1 受限整改追加记录

负责人已批准阶段一方案并允许最小实现。监听器生命周期、归属及失败 FETCH 语义的
可复现缺陷已修复；有界定位 OFF 出现 Windows 0xC0000005，ON 成功，根因仍 UNKNOWN。
未形成配对等价/三对 ≤3% 结果，父任务与 R1 继续 PARTIAL；原所有记录不改写。
详见 [R1 交付与停止回执](BIZ_PERF_03_A_R1_closeout.md)。
