# BIZ-PERF-P1-04-W05-LAB-03-R1：主CI唯一时序测试失败根因确认与最小整改

下发：2026-11-15。执行：ssssssh 远程电脑 Codex 桌面软件 **GP 项目持久会话**；ChatGPT 独立复测、审阅、普通提交推送和新SHA CI验收。

## 0. 事实基线：必须以本次失败证据为准

- 起始 HEAD / origin/master / GitHub master = `fc1cdc73cd6a2a4f10b55a6356953434ccf59bef`，工作区干净。W05-LAB-03 已推送、6个新文件，主 CI https://github.com/sssssssssh/ssh_stock/actions/runs/43684593024 **completed/failure**；A4-1 #43684593119、A4-2 #43684593092、Publication #43684593046 均 SUCCESS。
- 主CI test job id=132722292238：完整pytest步骤失败，`1 failed, 7647 passed, 1 skipped`，覆盖率90.02%；全量后续路由/CI-OPT判失败是上游后果，**不是**其独立根因。失败处于主CI完整 pytest，targeted测试此前成功；不能声称本次CI Ruff已经通过，因为该step并未运行。
- 从同一 run 的 `a42331-safe-ci` 工件里经脱敏的 `m17_1_2-full.xml` 已核实唯一失败条目：
  `tests.unit.test_perf03_lnx_offline_supervisor::test_rev1_synchronous_blocking_call_is_not_hard_preempted_3ea314badf5279b3`。
  failure message/type = `A42331_TEST_FAILURE`（安全脱敏），不能读出具体断言或 parametrized point；另一 safe-errors 工件仅证明 call/AssertionError，assertion_site UNKNOWN。**不可从猜测的参数、历史数据库日志、无关 SQL ERROR、其他 CI 判明根因**。
- 测试源码 `tests/unit/test_perf03_lnx_offline_supervisor.py` 约在 `test_rev1_synchronous_blocking_call_is_not_hard_preempted`：`@pytest.mark.parametrize('point',['popen','prefix_io','fsync'])`，通过真实 `time.sleep(.025)` 模拟同步阻塞，三段 `limits=(.01,.01,.01)`，断言实际耗时>=0.025、`observed==['entered','returned']`、非 COMPLETE_MOCK、first_failure 为 MOCK_START_TIMEOUT/MOCK_PHASE_TIMEOUT。
- `scripts/perf03_lnx_offline_supervisor.py::_supervise_registered` 先记录 `started=clock()`，再创建 OwnedDirectory、写 `prefix.json`，随后检查 `clock()<deadline` 才调 popen。**可检验假设**：CI机器早期 I/O 偶然超过10ms，`point=popen` 的 slow_spawn 未被调用，测试却要求一定 observe 25ms。注意这是待证明的竞争窗，不应当把它写成已确定的根因；`prefix_io` 和 `fsync` 也需逐个确认前提。
- 此时未发现业务代码/新增 LAB03 overlay 的直接失败证据；不要仅为掩盖 CI 红灯修改业务性能代码。

## 1. 必须先读与诊断

按照 AGENTS.md 顺序阅读五份治理文件及项目规则、README、W05-LAB-03任务/回执、下面两份精确源文件、A42331 pytest安全过滤与已存在的安全断言模式。先核实当前 Git 状态，仅本任务书为允许的单一未跟踪文件；若其他脏文件、HEAD/远端漂移、可疑部署进程停止并报告。
1. 研究 `test_rev1_synchronous_blocking_call_is_not_hard_preempted` 三个 point 的操作时间线：`start→OwnedDirectory/prefix→prelaunch deadline→注入阻塞→timeout→cleanup`，列出每条成功/提前拒绝路径，分析哪条断言和提前拒绝相冲突。不要修改旧 supervisor 的既有安全逻辑来迁就测试。
2. 先针对代码编写有限、**纯离线、不会连接DB/启动真实服务**的 RED 复现：固定/可控单调时钟（例如只在 injected block 到达后才开始计入经过的真实阻塞时间，使 25ms 模拟延迟仍被计入）、或利用专用合成受控构造，使在真实注入之前能确定性模拟前导 I/O>10ms，验证旧测试可产生`mock start timeout`但`observed=[]`的前提冲突。不能通过删掉错误分支或容忍任意 result 伪称修复。
3. Windows 主机旧 supervisor 的 `OwnedDirectory` 需要 Linux/macOS POSIX dirfd，Windows不可直接运行它：允许以源码 AST、mock-only、独立 Python 脚本/纯 mock 的**安全诊断**证明时序竞争，但必须在报告中注明这些不能代替 Linux 真实验证。不可启动 Docker/PG17或更改现有CI为此构建临时执行器。
4. 如证据支持上述测试竞争，首选**仅修测试时钟/注入前提**，保证所有三种point都实际进入各自 sleep，且 25ms实阻塞一定跨过10ms合成deadline，保持原强断言 `elapsed>=.025`、`observed==['entered','returned']`、非COMPLETE、原first_failure集合。特别注意以注入点为时钟推进锚点，预备阶段可用固定时钟，但注入阻塞发生后时钟必须真实前进；不要整体冻结时钟导致“未超时也通过”。对无法注入或挂起的路径必须明确失败而不是忽略。检查循环/清理阶段对时钟的依赖及当前测试其他point的影响。
5. **若不能证明测试自身竞争或发现监督器真实安全缺陷，不得盲改 supervisor；停止提交并在报告说明需要单独授权的源码修复范围和证据**。严格不要改任何生产SQL、数据、业务重算链路和根候选测量代码。

## 2. 必须交付的测试保护

- 保留该parametrize的三分支，不得 xfail/skip/deselect/删除任何断言或简单把0.01变成0.1、缩短0.025、重试直到通过、调低失败判定/coverage/关闭旧测试；不改 `scripts.a42331_pytest_safety`、GitHub CI workflow 或 requirements。
- 如果修改了测试，应增加必要的确定性负例保护：证明前导同步操作被人为拖延时**不会**导致压根未注入 slow_spawn 而产生假失败；证明25ms已被真实阻塞计时并产生fail-closed timeout；证明three points都到达并返回一次；若模拟注入完全没有发生则测试必须失败；MockConsumptionAuthority不发给失败root错误凭据。
- 目标验证：新改动在受控 RED→GREEN 中可复现；独立运行可安全执行的 AST/微型纯 mock 测试；针对性源完整性检查；需要 Linux 上的新SHA CI 才能验证原 POSIX supervisor 用例与完整测试。
- 不改历史五 frozen blobs：
  `scripts/business_recalc_measure.py` 782e45ba53c8de8df0d12ffa84c219855316cfda
  `scripts/biz_perf_p1_04_diagnostic.py` 714f78017ec252791ac6a89f9fb0e0a984333c37
  `scripts/perf03_lnx_w04a_offline_contract.py` 931fd4fec38551d9fac59791d2bde5ce0e6a1d48
  `scripts/biz_perf_03_b_once.py` 2ea473491f590893ad575b90a0ba42f932e37129
  `scripts/business_sql_snapshot.py` e7532b0a0242f1e3d3b047fdc03fca7ffc3ce7c6

## 3. 精确白名单与验收

仅允许提交以下3个路径（其中任务书由ChatGPT先下发）：
1. `docs/tasks/BIZ-PERF-P1-04-W05-LAB-03-R1.md`（本任务原文不改）
2. `tests/unit/test_perf03_lnx_offline_supervisor.py`（**仅该测试+必要紧邻测试辅助函数/负例**）
3. `docs/acceptance/BIZ_PERF_P1_04_W05_LAB03_R1_CLOSEOUT.md`（说明证据、逐point因果、RED/GREEN、验证、风险和下一步）

如证明需要其它新测试文件，优先并入同一旧测试文件；任何额外文件/脚本/CI/冻结源码改动须停止，不能扩白名单。历史旧 supervisor `scripts/perf03_lnx_offline_supervisor.py` 也不得改。
允许指定**纯离线**旧W05 LAB01/LAB02/LAB03/E02-E05/PRETEST/PG Guard等回归，不运行 Windows 上无法支持的POSIX supervisor文件；不得全量跑会连接PG的集成测试。Windows无 Ruff记 `ENV_BLOCKED_NO_RUFF`，Linux GitHub CI独立评估。
保留 `B_GATE=NOT_APPROVED`，`TARGETED_PG17_GATE=NOT_APPROVED`，`REAL_PG17=NOT_RUN`，`REAL_WORKER=NOT_RUN`，`ROOT_ATTEMPTS=0`，`HOTSPOT=NONE_PROVEN`，不得启动数据库/Worker/云/真实性能试验。

## 4. 提交与 ChatGPT 独立验收

Codex 只能在**远程 Codex 桌面软件 GP** projectId=`01a15f75-2c79-7d30-9232-651a6ef4253d` 的真持久会话中执行，名称 `BIZ-PERF-P1-04 W05-LAB-03-R1 CI时序测试整改`，不使用独立codex exec。
Codex在确认任务完成、代码/白名单/离线测试与原断言保护充分后，可尝试正常单次git add/commit及**非force** push master；如果sandbox拒绝 .git/index.lock 或 SSH，绝不越权，留给 ChatGPT 外层。
ChatGPT再通过外层设备独立检查真实精确diff、测试语义、仅3路径、旧源完整性；若合格且HEAD/origin/master/GitHub master无漂移，则安全常规提交并非force推送，之后核对新SHA主CI、A4-1、A4-2、Publication和 Linux Ruff/pytest；如 CI失败只做最小根因分析，不能宣布验收。成功最高结论 `W05_LAB03_R1_CI_VALIDATED`，不是放行实机性能实验。
GP回执字段：TASK、BASELINE_SHA、ROOT_CAUSE_STATUS(PROVEN/UNPROVEN)、CHANGED_PATHS、RED_GREEN_EVIDENCE、SAFE_TESTS、FROZEN_5、PUSH、NEW_SHA、CI、ROOT_ATTEMPTS=0、B_GATE=NOT_APPROVED、NEXT=CHATGPT_INDEPENDENT_REVIEW。
