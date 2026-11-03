# BIZ-PERF-03-A-R1：P0 审查与预注册实施方案

> 预注册历史快照：以下状态描述为 2026-11-03 08:44 阶段一交付时点。
> 此后负责人已回复“确认，开始修改”；当前实施、停止条件和验收状态见
> [R1 交付回执](BIZ_PERF_03_A_R1_closeout.md)。保留原方案正文，不回填事后实验结果。

日期：2026-11-03，Asia/Shanghai；核查时间 08:44 +08:00。
状态：**PHASE_1_DELIVERED / IMPLEMENTATION_REVIEW_PENDING**。
本次用户指令允许按任务书推进并在完成后推送；任务书第 3、9、10 节及附录 A 另设实施前
审阅门禁。本文件先交付该门禁所需证据和方案，尚未修改运行时代码或执行测试负载。
旧 PROJECT_STATUS 的“不授权 R1”属于此前任务语境；本次明确授权覆盖 P0/静态审查，
不把它自动扩展为绕过任务书的实施前审批。治理状态变更留待负责人确认。

## 1. 基线与范围

- master、HEAD、origin/master、GitHub refs/heads/master 均为
  `32cf8f438061e95b1492fd2a5db15dd05c13e28d`，开始工作区干净。
- 业务实现最近变更为 e610a928；其后治理提交没有替换诊断代码。本文件记录修改前基线，
  不追逐文档自身最终 SHA，不创建分支、不改写旧记录。
- 已依序阅读 AGENTS、五份治理文件、相关业务权威段落、R1 任务书全文、A 阶段 closeout、
  mapping、Schema、原始开销 JSON、相关源码及测试。
- 本阶段仅新增此 Markdown；不改业务/观测器源码、测试、配置、Schema、CI 或治理执行指针。
- 无 dotenv 读取、应用初始化、Provider 请求、数据库连接、服务启动、Actions dispatch/rerun、
  百万行计算或生产操作。仅读取本机历史证据和现有 GitHub 日志。

## 2. P0：精确 SHA 工程 CI 已终结

下列均为上述完整 SHA、push、attempt 1，四个工作流均 completed/success：

| 工作流 / Run | Job ID：结论 |
| --- | --- |
| [CI 41414072689](https://github.com/sssssssssh/ssh_stock/actions/runs/41414072689) | lookup-diagnosis 125173562723：success；test 125173563138：success；dependency-audit 125173563147：success；workflow-contracts 125173563329：success |
| 同上，未执行项 | ui-visual-acceptance 125173565134、authorize 125173565226、lookup-tail-attribution 125173565456、capacity 125174047157、publication-release-gate 125201108331：全部 skipped |
| [A4-1 41414072644](https://github.com/sssssssssh/ssh_stock/actions/runs/41414072644) | contracts 125173563045：success；authorize 125173565138、isolated-baseline 125174747132：skipped |
| [A4-2 41414072701](https://github.com/sssssssssh/ssh_stock/actions/runs/41414072701) | contract-and-safety 125173563078：success；authorize 125173565005、laboratory 125175948123、a42-acceptance-gate 125175948643：skipped |
| [Publication V1.3 41414072660](https://github.com/sssssssssh/ssh_stock/actions/runs/41414072660) | contracts 125173563297：success；authorize 125173565398、candidate-performance 125174604385：skipped |

共 19 个 Job，7 success、12 skipped。主 test Job 全部实际步骤 success；步骤 23 的原命令为
完整 pytest + 原 safety 插件 + backend 覆盖率（门槛 70%）。日志结尾明确记录：
**5322 passed、816 warnings、3107.93 秒；coverage 90.00%**。
步骤 27 Ruff 为 All checks passed。步骤 7 的隔离 PG17、12–14 的测试库迁移、25–26 的迁移
核查、29–31 的 Compose/容器任务、36–38 的前端及浏览器、41 的运行可靠性均 success。
这里只复核既有运行，不重新执行这些动作。

日志包含五个 test_real_root_parity_and_local_reports 参数节点的 warning 名称，完整套件通过；
但本次未下载/解析 JUnit 或性能 artifact，不从这些名称推断逐根计时、精确身份或错误路径凭证。
此证据足以确认启动门禁中的“完整工程 CI 已终结”；不能证明 Windows 停滞根因已解决，
不能关闭三对 ≤3% 或正式容量验收，更不授权生产。新修复后仍须最终精确 SHA 的完整 CI。

## 3. 历史故障证据复核

| 证据 | 核查事实 | 结论限制 |
| --- | --- | --- |
| [root_overhead.json](biz_perf_03_a/root_overhead.json) | 3 对成功根任务，OFF 中位 37756.2296ms，ON 39889.4978ms，+5.650109%；另有取消/失败各一对 | 原工作树候选，不是当前最终源码验收；全部保留，不择优重算 |
| [offline_overhead.json](biz_perf_03_a/offline_overhead.json) | OFF/ON 各三次，+22.531557%，纯 CPU/文件 fixture | 非 PG/真实根任务；当时同机并行测试，不能作纯观测器成本归因 |
| perf03_pg_test_revision1.log | 5 passed、15 warnings、326.81 秒 | 前版结果，不覆盖缓存版 |
| perf03_pg_revision2_incomplete.log | 本机文件实际 0 字节 | 不能从空文件补造 SQL/阶段/耗时；旧连接状态仅有上一轮记录，未在本轮重新连库验证 |
| perf03_pg_debug.log | 145667 字节，最后完整业务标签位于 opportunity.compute 附近 | 只证明最后捕获位置，不证明该函数或 PostgreSQL 是根因 |
| perf03_stack.log | 868 字节：一次 45 秒 dump，心跳线程在 Event.wait；主线程在 pandas managers.take，后续栈含未知行号并截断 | 不证明进程死亡、PG 死锁、内存耗尽或仅 ON 停滞；不能用于唯一归因 |

本机历史文件位于忽略目录，不提交其完整日志、绝对路径或任何原始业务值。复核摘要：

- stack SHA256：259a4942926e4d28e37bd42ed2cdb466ff244aacee5ab9a31c1a27987605ac03。
- debug SHA256：bdafe4bcc53f98299dcd2278ee03da387f2458e515a5c685179c3301a4e34466。
- 空日志 SHA256：e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855。

**停滞根因：UNKNOWN。** CI 的 Linux 同实现可通过，支持继续区分平台、fixture、日志捕获、
pandas/驱动、心跳清理与观测器，而不是跳过定位直接更改业务 SQL。

## 4. 调用点、现有采集规模与静态风险

| 模块 / 函数 | 当前观察点与数量 | 静态发现 / 待证假设 |
| --- | --- | --- |
| performance_diagnostics.observe_worker | 每根最多一个 trace；根资源采样两次，finally 关闭/flush | setup 部分成功后的 catch 未立即撤销 token/listener，而让其存活到原函数结束；先验证故障注入 |
| performance_sql_diagnostics.SQLObserver | 每个启用根安装三个 Engine 事件；最多 128 指纹+overflow，128 个缓存项 | install 无内部回滚；close 在首个 remove 异常后可能中断；应有逐个安装/拆除失败测试 |
| SQLObserver.before/finish | before 使用 active_trace；finish 使用共享 execution_context.performance_diagnostic | finish 缺少本 observer 的归属核验，多 observer 时可能消费另一根上下文并清除；这是源码风险，不是已证明的历史停滞根因 |
| Trace.interval / span / measured_interval | 最多 4096 spans；UUID、UTC、dict；每个读取批次生成 interval | 分配/格式化与序列化可能昂贵，暂无自身 CPU 或分项耗时证据，不先认定热点 |
| Trace.report / flush | report 的 total_wall_ms 截止在序列化/写盘前；instrumentation_ms/flush_ms 为 null | 内部 total_wall_ms 不等于含 flush 的完整根任务时间；正式分母必须外部包围完整调用 |
| job_worker.execute_claimed_job | 原 decorator、bind_task、finally 中旧 policy/heartbeat/session 观测清理 | 不改变原队列/退出顺序；两套诊断应区分，不把旧心跳 SQL 计为新增性能诊断 SQL |
| calculation_policy.DriverFetchObserver.fetchmany | 原服务端游标调用前后；失败转发 rows=None | driver_fetch 累积行数在失败后仍保留成功前缀；报告需区分已知前缀与未知失败批，不能伪称完整行数 |
| calculation_frame.read_calculation_frame | 原 execute + 每 5000 行 partition + 原构帧；不额外遍历 | partition 与 driver FETCH 是嵌套；保持 Result、dtype、顺序和检查点，不为统计更换代理 |
| data_publication._lookup_batch / _store_batch / finish_publication | 原候选查询、每 500 行写入、发布准备 decorator | SQL、批次和发布预算完全不改 |
| job_run._update_owned_data_job | 原 CAS 后 commit，ACK 后 root terminal | 子任务不能发布根状态；未知 ACK/原异常必须继续保护 |
| PG 测试 / seed | 2 证券、420 自然日日历、OFF 后 ON，每组重新建隔离库 | 现有每参数成对执行，非每臂独立进程；无外层超时/原始逐根回执，比较排除全部 id，不能直接声称根身份和全部列逐项全等 |
| scripts/performance_diagnostics_overhead.measure | 3 对纯 CPU fixture，包含 setup/flush | 不能代替根任务；需先归因，不以减少样本或删除字段刷过 3% |

目前没有证明哪个点贡献了 +5.65%，也没有证明 OFF/ON 是否都能在本机稳定完成。
静态生命周期缺口具备最小回归测试设计基础，但是否实施及具体补丁仍待本方案审阅。

## 5. 预注册：先有界定位，后最小修复，最后完整对照

### 固定输入与环境

- 复用 seed(factory, include_closed=False, history_days=420)，日历从 2025-01-01 到
  2026-02-24；只用原有两个合成证券。固定请求范围 **2026-02-23～2026-02-24**，
  evaluate_signals=False，原 manual 根任务。现有退市边界和市场指数夹具保持原样。
- 不缩短原 250 交易日预热/430 自然日回看；记录实际预热起点、各 Raw 表行数、版本与配置摘要。
  此小型样本不是全市场或百万行容量，不能宣称金融研究有效性或生产提速。
- 必须使用现有 verified_test_url 的 PG17 major、随机 marker、system_identifier 双物理验证，
  与随机 UUID 合成数据库；禁止业务 DSN/dotenv。身份校验必须先于测试库写操作。
- 本机仅已核实 Python 3.12.14、SQLAlchemy 2.0.52、psycopg 3.3.4、pandas 3.0.5、
  NumPy 2.3.3、pytest 9.1.1。PG 实例与资源本轮未启动/探测；运行前登记版本、CPU/RSS、
  原生线程能力及镜像/依赖身份。不能把本机库版本写成 Linux CI 环境版本。
- OFF 与 ON 各使用独立子进程、新建同样的合成库，按同一源码、参数、数据库设置和冷启动
  规则执行；不声称 OS/PG 物理冷缓存。无并行大型 pytest/矩阵，做不到则 DEFERRED。

### 第一轮：仅定位，不计性能验收

- 顺序固定 OFF 一次 → ON 一次。每臂外层 setup 限时 180 秒；完整根函数调用限时 180 秒；
  清理限时 30 秒。父进程单调计时覆盖原函数至返回，含诊断 setup、flush、原清理。
- 测试 harness 在根调用 30 秒开始、每 30 秒输出至多 5 次当前子进程线程栈；不改生产
  信号处理、业务时间预算、原 SQL 超时或 Worker 调度。堆栈导出前去绝对路径，不采集局部变量。
- 仅受限观察本次合成任务：阶段摘要、进程自身 CPU/RSS、子进程退出码、心跳线程终态，
  必要时本测试库会话状态/等待类别；不保存 SQL/参数，不扫描其他进程或业务库。
- 180 秒根超时即 INCOMPLETE，保存已取得前缀；父进程只清理自己创建的测试子进程和
  经身份核验的专用测试资源。未知退出不得写 SUCCESS，不运行第二轮刷过。
- OFF、ON 均停滞：诊断外部阻塞，停止运行时修复，报告平台/fixture 缺口。
  仅 ON 停滞：继续对具备证据的观测器点做单因素定位；不据相关性修改金融 engine。
  缺对照、栈截断、退出不确定：根因仍 UNKNOWN，不扩范围。

### 第二轮：获批的最小生命周期修复及定向测试

先以可重复的故障注入生成 RED，再实施 GREEN。安装第 1/2/3 个事件分别失败、每个 remove
失败、业务异常、取消、未知提交、flush 失败、两根交错/并发都要验证：原异常/返回值、
token、listener、pending 文件及其余根均正确。最多修改一个有证据的缺陷组后再验证。
SQL/FETCH 不双算、失败未知行数保持 null，digest 缓存不存原文；默认 OFF 无新 SQL、
listener、文件或诊断线程。并发作用域测试不能冒充实际 Worker 并行调度能力。

成本归因单独登记，先测事件数、指纹解析/命中、span 数、分配/序列化/flush 和自身 CPU；
分项测量有观察成本，不混入正式 W04 对照。没有热点证据就不追加“优化”重构。

### 第三轮：三对真实根任务对照（前两轮成功后才可执行）

- 顺序固定 **OFF1→ON1→OFF2→ON2→OFF3→ON3**，相同 fixture、源码及隔离规则；
  每根/清理限时与第一轮相同，整个六臂执行窗口最多 45 分钟。
- 每臂独立进程；根 wall time 包含 setup/采集/flush/清理，隔离库创建、seed 及预检时间
  单独记录，不混作根任务耗时。原报告内部 wall 只能作为辅助指标，不用来计算门槛。
- 只运行这一登记批次。失败、超时、INCOMPLETE 使矩阵不完整，全部原始样本保留，不补样
  或删异常；新的测试修订必须给出新版本/理由，不拼接旧批次凑三对。
- 对比所有业务字段、dtype、自然键顺序、原因码、质量、任务与发布终态。只对随机 UUID/
  时间戳使用显式列级映射；root/job/generation 的引用闭包与从属关系必须精确验证，不能
  排除所有 id 就声称身份全等。任一差异立即停止，不改公式/数据使其“全等”。
- 额外独立用例覆盖取消、失败和未知提交。逐臂记录主执行上下文业务 SQL 次数/写入量；
  心跳 SQL 另列，其次数受墙钟调度影响不能直接归因于新诊断。计数探针 OFF/ON 对称。
- 原始摘要包含源码 SHA/工作树状态及内容 hash、root/task/trace/generation 身份、
  输入规模、环境、开始结束、退出码、wall/CPU/RSS、SQL 数、输出 hash 和完整性状态。
  私有合成回执安全导出，不依赖会删掉 properties 的通用 JUnit 作为唯一逐根证据。
- 报告全部原始值、均值、中位数、min/max、标准差；每臂仅 3 样本，P95=null。
  **(median ON / median OFF - 1) × 100% ≤3%** 且所有等价/安全检查通过才能验收。
  超标则 PARTIAL；不拿单阶段提速、纯 CPU fixture 或普通 CI 抵消失败。

## 6. 拟修改清单与需额外确认的调用点

优先允许清单：performance_diagnostics.py、performance_sql_diagnostics.py；必要的
tests/unit/test_performance_diagnostics.py、tests/integration/test_perf03_root_diagnostics.py、
scripts/performance_diagnostics_overhead.py；closeout 只追加本轮结果，不覆盖原记录。
新增证据/任务记录按批准方案登记，原 A 阶段 JSON 不覆盖。

预期最小补丁方向（尚未实施）：

1. SQLObserver 安装原子回滚、逐监听器拆除、observer 专属上下文键/归属检查。
2. observe_worker 在 setup 部分失败时立即恢复上下文和监听器，再调用原函数；收尾故障
   不掩盖原业务异常。span 开始/结束的诊断异常隔离同样先测试再决定最小修复。
3. FETCH 失败完整性与已知前缀/未知批次分清，报告与 Schema 保持一致。
4. 测试 harness 增加有界子进程、独立回执、SQL/写入量和身份全等；性能热点只在实测后选择。

job_worker.py、calculation_policy.py、calculation_frame.py、data_publication.py、job_run.py
本轮仅审阅。若上述文件需改，必须另给函数级 diff、理由并经负责人确认；本方案未提前授予许可。
金融 engine、SQL 算法、500 行批次、事务、Schema/迁移、前端、生产配置与 Actions 均禁止改动。
PROJECT_STATUS 的唯一任务/授权状态按任务书要求待负责人确认后更新，不能抹去 GOV 待最终验收事实。

## 7. R01–R12 验证与交付门禁

| 项 | 预注册验证 |
| --- | --- |
| R01 | 默认 OFF 无新 listener/文件/线程/SQL，与原返回值和副作用一致 |
| R02 | 根 trace 独立、子终态不改根、重复/重试 identity 关系与幂等不变 |
| R03 | 正常/失败/取消/未知 ACK、诊断 setup/span/cleanup 故障不改业务异常和状态 |
| R04 | 三个安装位置逐一失败回滚；拆除错误继续清理其他 listener |
| R05 | 两 observer 交错及上下文并发、关闭彼此独立，不能窃取计数或留 token |
| R06 | 参数/异常不入报告，128+overflow 和缓存有界，复杂 SQL unavailable |
| R07 | driver FETCH 与 execute、partition 分开，未知失败 rows=null，不额外消费 Result |
| R08 | 序列化/写入/link/删除失败、唯一 pending 清理与原异常保护 |
| R09 | 明确隔离 PG17 真实根结果、顺序、dtype、身份与发布全等 |
| R10 | 三对成功根任务含收尾总 wall，原始轮次不丢、≤3%、SQL/写入量等价 |
| R11 | 修复最终精确 SHA 的完整 Linux pytest/Ruff/工程 CI；当前基线绿灯不继承 |
| R12 | Schema、离线 CLI、回滚说明与原始失败/当前 PARTIAL 缺口一致 |

本轮未运行新 pytest、Ruff、PG 或开销矩阵，只做文档一致性和 git diff --check。
后续实现先定向 RED/GREEN，再完整 pytest 与 Ruff；Windows 平台限制独立披露，最终
同 SHA Linux CI 不能用跳测/改旧断言替代。仅允许普通 push CI，不 dispatch 高成本专项。
回滚继续默认 OFF；有在途任务不热更新。未授权生产部署、恢复、清库或 BIZ-PERF-03-B。

## 8. 本次审阅请求

请审阅本文件的测试预算、隔离方案、归因假设和优先修改清单。获批后进入第一轮有界定位，
再按证据进入最小实现；后续若涉及调用点或改变冻结的测量口径，另行提交具体补丁审阅。
当前 P0 的 CI 等待门禁已满足，但阶段 1 审阅尚未完成；不得把本计划交付标记为 R1 实现完成。

任务书第 3 节原文：“交负责人审阅后执行会影响行为的实现。”
附录 A 原文：“先不要修改业务代码或运行高成本测试。”
因此本次停在阶段 1，最终提交推送已获用户原则授权，待该前置审阅通过及后续验证完成后执行，
不把“完成后推送”解读为取消实施前门禁。
