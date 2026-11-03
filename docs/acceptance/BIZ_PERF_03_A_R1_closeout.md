# BIZ-PERF-03-A-R1：最小生命周期修复及停止条件回执

日期：2026-11-03；实施前基线 32cf8f438061e95b1492fd2a5db15dd05c13e28d。
负责人已明确确认阶段一方案并要求开始修改，最终提交推送已获授权。
状态：**PARTIAL / LIFECYCLE_FIX_VERIFIED / LOCAL_NATIVE_FAILURE / OVERHEAD_OPEN**。

## 1. 实做与边界

- SQLObserver.install 在三个事件的任意安装位置失败时回滚已登记的监听器。
  登记意图先于 listen，兼容事件适配器“先安装再报错”的情况；不增加 SQL。
- close 先禁用 observer，逐项清理，单项拆除瞬时异常最多尝试两次，继续其余项。
  永久事件 API 故障的回归已验证：保留未清理列表和固定 warning，回调保持禁用，不声称已拆除；
  这只重试本地事件清理，不重放业务 SQL/事务。
- execution_context 中计时记录绑定 observer 归属；finish 同时核验归属、有效状态和
  ContextVar，避免另一根 observer 消费计数。并发/交错和关闭其中一个的场景有回归。
- 诊断 setup 部分失败时先拆除事件、恢复 ContextVar，再执行原业务函数；原返回值/异常保留。
- FETCH 失败后完整 fetched_rows=null，另提供 known_fetched_prefix_rows，保留已知成功前缀，
  不把失败批次未知行数当作 0。Schema 的 database_summary 原本允许对象内附加字段。
- 新增单次 root-arm 隔离测试入口，仅接受现有物理 marker/system_identifier 校验的测试库。
  该入口不是自动性能矩阵；需由独立父进程执行计划中的 setup/root/cleanup deadline。
  清理异常即记录 FAILED，即使 root 已成功发布，也不能将整个定位过程标为 COMPLETE。

仅改两个诊断模块、必要测试、离线诊断脚本与说明。未修改 job_worker、calculation_policy、
calculation_frame、data_publication、job_run 调用点；金融 engine、SQL、500 行批次、事务、
取消/未知提交、Provider、迁移、生产配置、前端和工作流均不变。原 A 阶段证据不覆盖。

## 2. RED → GREEN

原源码新增四个参数用例实跑：**3 failed、1 passed**。
安装第 2/3 个事件失败后原实现残留监听器；交错两个 observer 时第一根错误累计 3 次，
预期仅 1 次，第二根预期 2 次。这是独立可复现缺陷，并非 Windows 停滞根因证明。
最小修复后通过。新增测试追加于原文件，旧测试和断言不改写。

定向测试覆盖：默认 OFF、setup/flush/清理故障、并发/交错归属、部分安装、单独关闭、
SQL 脱敏及 128+overflow、已知/未知 FETCH、取消和未知提交诊断终态、原返回值保护。
这些单元级状态用例不能冒充真实 PG17 的整套失败/取消/未知提交发布验收。

## 3. 有界定位结果与停止

独立本机 PG17 测试实例复用已由本任务确认的专用目录，启动后只绑定 loopback。
每臂通过既有 major=17、marker、离线 control system_identifier 与服务器值核验，
再创建 UUID 合成库。输入与期限按[预注册计划](BIZ_PERF_03_A_R1_plan.md)执行。
运行时未并行大型 pytest；定位期间有一次轻量单测，不作为正式性能条件。

完整摘要见 [localization.json](biz_perf_03_a_r1/localization.json)：

| 臂 | 结果 |
| --- | --- |
| OFF | 原生退出码 3221225477，即 0xC0000005；没有最终 Python receipt，记 INCOMPLETE |
| ON | exit 0；SUCCESS/PUBLISHED；完整函数 wall 34673.8398ms；受控摘要记录输出 hash 与 SQL/写操作次数 |

OFF 的 30 秒 dump 有心跳线程 Event.wait 与 pandas indexers 附近的不完整主线程栈。
这是 Windows 原生访问冲突的证据，不足以归因于 pandas、faulthandler、内存、驱动或诊断代码。
尤其不是“仅 ON 停滞”，不能据此动业务 SQL。实际模块来自用户 site-packages，
PYTHONNOUSERSITE=1 的只读可用性检查显示该 conda 环境缺少本项目全部主要依赖；
这是环境隔离缺口，不是已证明的崩溃根因。本轮未修改全局依赖或安装包来刷过。

没有有效 OFF 终态，结果等价与配对开销均 UNAVAILABLE。按停止条件，**未进入 W04
三对验收**，不删除失败、重跑凑样本或将 ON 成功解释为 ≤3%。
独立测试实例已停止；未操作用户服务或业务库。未删除未知业务任务、解锁 Writer 或恢复 BIZ-PERF-02。

## 4. 验证与验收矩阵

定向命令使用隔离应用配置、禁用 dotenv 读取，数据库环境为不可连接的合成占位目标；
单测使用 SQLite/模拟事件，不连接业务 PG。完整 pytest 也通过同样的安全启动器运行。

```bash
python -m pytest tests/unit/test_performance_diagnostics.py tests/unit/test_calculation_frame.py -q
python -m pytest
python -m ruff check backend tests migrations scripts
git diff --check
```

完整本机 pytest 在收集阶段终止：10 个既有 fcntl/resource Linux 平台导入错误，
exit 2，最终复跑 11.34 秒；没有跳过/删除原测试或降低门槛。定向和 Ruff 的最终结果在交付回执中记录。
基线普通 CI 已核查 5322 passed / 90.00%，只适用于 32cf8f43；不能当修复提交的结果。
最终提交普通 Linux CI 仍待独立完成，不 dispatch 高成本实验。

| 编号 | 当前判定 |
| --- | --- |
| R01 | 单测通过；默认 OFF 不创建 Trace/监听器/文件，业务返回值不变；PG 数量对照未完成 |
| R02 | 单测通过；子终态不改根，重试 trace 独立；完整逐根发布身份待真实对照 |
| R03 | 单元状态与异常保护通过；真实 PG 失败/取消/未知 ACK 组合验收仍待验证 |
| R04 | 部分安装 RED/GREEN 与逐项清理测试通过 |
| R05 | 交错/并发和独立关闭测试通过 |
| R06 | SQL 脱敏、128+overflow 与缓存上限测试通过 |
| R07 | 单测覆盖失败总数未知及已知前缀；原读取器测试保留，真实 PG 全覆盖待验证 |
| R08 | flush/link 错误、pending 清理及原异常保护单测通过；永久 OS 拒绝清理仍有明确 warning |
| R09 | INCOMPLETE：OFF 原生崩溃，无配对完整输出 |
| R10 | NOT_RUN：停止条件触发，≤3% 仍未通过 |
| R11 | 本机全量平台受限；修复最终 SHA Linux CI 待完成 |
| R12 | 文档、CLI 和既有 Schema 兼容性定向检查；保留 PARTIAL 缺口与回滚 |

## 5. 使用、回滚与下一步

单次合成定位入口（必须先配置已验证的独立测试库，父进程按计划监督）：

```bash
python -m scripts.performance_diagnostics_overhead --root-arm off --output NEW_OFF.json
python -m scripts.performance_diagnostics_overhead --root-arm on --output NEW_ON.json
```

两个命令不能直接作为完整性能验收；现有函数不证明逐列全等或三对达标。初始持久化
INCOMPLETE 前缀可在 native crash 后保留，完整回执只在成功收尾后更新。
原默认纯 CPU fixture 保留，不能当 root 替代物。新定位 CLI 未在故障后重启实验刷结果。

PERF_DIAGNOSTICS_ENABLED 继续默认 false；回滚可关闭开关并在安全边界重启后续 Worker，
无需降级迁移或清理业务数据。源码回滚用新 revert，不覆盖旧证据。
下一步为单独审阅 Windows 原生失败/合格测试环境及有界方案，验证成功后才重启完整对照。
本轮可交付最小安全修复，但整体 R1 与父任务仍 PARTIAL，不进入 BIZ-PERF-03-B 或百万行实验。


## 最终本机验证回执

- 定向读取器/诊断回归：53 passed、0 failed/error/skipped，3.96 秒，退出码 0。
- Ruff backend tests migrations scripts：通过，退出码 0。
- root CLI 安全预检：缺少隔离 marker 时在应用配置读取与文件创建之前拒绝，已验证。
- 完整 pytest：最终复跑 11.34 秒，10 个既有平台收集错误，退出码 2；不标全量通过。
- 有界定位：OFF 原生异常 / ON SUCCESS-PUBLISHED；不能合并为配对成功。
- W04 三对、当前修复源码的真实完整配对、≤3%：NOT_RUN / OPEN。
- 当前修复最终 SHA Linux CI：推送后独立核验；尚无通过结论。

因原生失败停止继续负载；本交付为 PARTIAL 的最小修复，不宣称完整任务已验收。

补充 RED/GREEN：span 起始时钟异常、setup 失败后 cleanup 再异常分别新增复现，原实现均失败；
修复后原业务异常/返回值保留，ContextVar 恢复。该补充只涉及同一诊断文件，不修改调用点。
