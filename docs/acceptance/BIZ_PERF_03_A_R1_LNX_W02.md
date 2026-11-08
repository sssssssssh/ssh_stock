# P0-LNX-W02-SAFE-01：Mock-only 隔离监督

## W00_SCOPE_AND_THREAT_REVIEW（2026-11-08）

负责人最新授权为 macOS 本地开发、现有 Main CI 的 Linux pytest 专项验收。
基线 master/HEAD/origin/master/实时远端均为
`53f297430e432e9c7f018f6414556022aeda0a58`。
原七文件及两份 ZIP/一份 Patch 不变；仅新增任务书五文件。
历史指针待治理同步：PROJECT_STATUS 等仍有旧 G0/04-E 执行指针，本轮不回写治理历史。

### 冻结进程模型与威胁边界

- watchdog 固定启动同目录 hard_mock_actor.py，使用当前解释器 -I -S；
  shell=False、新 session、最小环境、stdin/stderr 为 DEVNULL。
  私有临时目录 FD 与单向有界管道 FD 仅传给 actor，不接受外部路径/命令/PID/PGID。
- actor 只执行固定 Mock 枚举；FIFO open 是真实 Linux 阻塞 syscall，其他命名阻塞为
  SIMULATED_BLOCKING，不能冒充真实 Popen/fsync/link/close 内核故障。
- 固定同组 child 也是同脚本固定角色、不再派生；TERM 时 actor 回收自己创建的 child。
  actor 内的 TERM 行为只影响此独立进程，不在调用方/pytest 安装全局 signal handler。
- watchdog 只发送有限字节、固定版本身份消息；READY/CHILD/CHILD_REAPED/DONE 有顺序合同。
  不信 actor 自报清理或成功，必须独立核对退出码、OS 归属及进程组消失。
- Linux waitid(WNOWAIT) 保留 leader 未回收身份直到信号处理完成，避免先 poll/reap 后
  将复用 PID 当成本次 actor。每次 TERM/KILL 前核对活体句柄、PID=PGID=SID。
  不接受外部 PID、不扫描系统进程、不在 leader 退出后继续对未知残留组发信号。
- 单调绝对 root deadline 从开始建立；TERM/KILL 收尾单独固定最多0.4秒，不重置 root。
  超时、坏协议、晚到 DONE、异常退出均有粘性首错，清理错误另列。
  进程/组/文件收尾不能证实则 CLEANUP_UNCERTAIN，不能继续工作项。
- 状态为 MOCK_COMPLETE/MOCK_TIMED_OUT/MOCK_FAILED/WATCHDOG_UNAVAILABLE/
  CLEANUP_UNCERTAIN；无真实执行、性能、容量、生产许可。身份不可跨 run 拼接。

### NOT_PROVEN 与保留风险

首次 watchdog/actor spawn、watchdog 自己的控制目录/pipe/信号/wait/清理系统调用仍可能
阻塞；Linux D 状态、恶意同 UID、durable trust 和真实业务接入均 NOT_PROVEN。
本实现不承诺任意阻塞可抢占，不提供内核隔离/cgroup 或真实票据。
仅测试已列场景，AC05_STATUS=PARTIAL、R1_STATUS=PARTIAL；W01 原同步缺口仍在。
Mac/Windows 的真实执行入口返回 UNSUPPORTED，不降级执行或发信号。

Linux 测试用独立 CLI 子进程和外部等待兜底，若未知收尾立即终止本次 pytest，保留失败；
不得在无法确认资源回收后继续用例。外层超时不是已证明的通用进程树清理能力。

### Main CI 接入审查

原 full_tests 无显式路径筛选，pytest testpaths=tests；新 integration_offline 文件自动收集，
不受 tests/integration/conftest.py 的 PG fixture 支配，不需要修改 Workflow。
Linux 专项必须在同 SHA 完整 JUnit 中逐节点检查，无 skip/failure/error 才可请求审阅。
本地 macOS skip 只标 LINUX_VERIFICATION_PENDING。允许一次受限 push 后取得该证据，
不 dispatch/rerun、不追加修复提交，不将旧 SHA CI 或 workflow success 代替节点证据。

## W01/W02 实现与本地验收回执

固定场景：success、block_fifo_open、block_popen_simulated、block_fsync_simulated、
block_prefix_write_simulated、block_read_simulated、block_link_simulated、
block_close_simulated、ignore_term、child_same_group、bad_receipt、nonzero、
missing_receipt、late_success。Actor 及其固定 child 不接入任何业务包或网络。
默认 Mock root 期限500毫秒，可配置范围100～1000毫秒；TERM/KILL 各固定0.2秒。
这些新 Mock 参数与旧正式180/180/30秒、45分钟和≤3%合同完全分离。

Linux 自然 FIFO 场景只在已核对的 actor PID 的 /proc/PID/wchan 观察到
wait_for_partner 时才具有“已进入实际阻塞”的证据；不可读或没有该证据时专项断言失败。
超时前 READY/DONE 只是 actor 自报，不能取代零退出码、未超期、wait 和进程组消失证据。
同组 child 不创建新 session；actor 只在自己的进程安装 TERM 行为并 wait 回收 child。
实际主动制造孤儿并遗留的测试不运行；提前退出/残留组拒绝由无真实资源的注入覆盖。

### RED/GREEN 与修订上限

- 首次新模块未实现时，纯合同测试收集 ImportError（1 error），这是开发顺序记录，
  不是旧 W01 缺陷复现，也不是 Linux syscall 证据。
- 首轮可执行合同：69 passed；Linux15 skipped，不能当作 Linux green。
- 复核发现“已拥有的 actor 在检查/信号间恰好退出”的收尾竞态，两个确定性注入均 RED；
  第一次局部修正：只在再次 no-reap 确认其已退出时停止发信号，后续仍须 wait 和组消失。
  2 passed GREEN；真实身份不符、信号失败、wait 失败或组残留仍为 CLEANUP_UNCERTAIN。
- 第二次局部修正：JSON 解析器递归耗尽异常的固定错误转换。人工 RecursionError 注入
  RED 1 failed，修复后在完整合同回归 GREEN；深层JSON和超长/重复键/坏编码负例保留。
- 初次 Ruff 两条超长行已按原规则换行；没有改变 lint 配置或削弱断言。
- 最终同一源码 macOS/Darwin arm64、CPython3.12.14：351 passed、15 skipped，5.29秒。
  73项新纯合同+278项旧W01离线测试通过；15项 Linux-only 均明确 skip。
  状态为 LINUX_VERIFICATION_PENDING，没有本地 Linux 运行、真实 PG 或 Worker。
- 新四份 Python 文件定向 Ruff 通过；五文件空白检查、旧七文件及四历史JSON SHA256
  和三份审阅工件字节核对通过。无完整仓库 pytest、依赖安装或 Workflow 修改。

精确本地命令（默认安全插件保持）：

```bash
.venv/bin/python -m pytest tests/unit/test_perf03_lnx_hard_watchdog_contract.py tests/integration_offline/test_perf03_lnx_hard_watchdog_linux.py tests/unit/test_perf03_lnx_offline_contract.py tests/unit/test_perf03_lnx_offline_supervisor.py tests/unit/test_perf03_lnx_offline_parity.py -q --tb=short
.venv/bin/python -m ruff check scripts/perf03_lnx_hard_watchdog.py scripts/perf03_lnx_hard_mock_actor.py tests/unit/test_perf03_lnx_hard_watchdog_contract.py tests/integration_offline/test_perf03_lnx_hard_watchdog_linux.py
git diff --check
```

### AC 对照（Linux 结果不得预填）

下表测试名均在两份新测试文件，Linux 项等待同 SHA Main CI 完整 JUnit。

| AC | 测试/证据 | 当前结论 |
| --- | --- | --- |
| 01 | static_and_fresh_import_guard_are_standard_library_only | 本地PASS，AST+新-I/-S导入进程 |
| 02 | unapproved_request_refused_before_io、cli_refuses_free_execution_before_io | 本地PASS |
| 03 | linux_fixed_success_requires_exit_and_os_group_confirmation | Linux PENDING |
| 04 | linux_fifo_reference_blocks_without_watchdog_and_owned_term_reaps；blocked_actor[block_fifo_open] | Linux PENDING，自然syscall证据必需 |
| 05 | blocked_actor[block_popen_simulated] | Linux PENDING，仅模拟 |
| 06 | blocked_actor[block_fsync_simulated] | Linux PENDING，仅模拟 |
| 07 | blocked_actor[prefix_write/read/link/close_simulated] | Linux PENDING，仅模拟 |
| 08 | blocked_actor[ignore_term] | Linux PENDING，须有TERM→KILL及-9退出 |
| 09 | linux_bad_or_missing_receipt_and_nonzero_never_pass | Linux PENDING |
| 10 | linux_same_group_child_is_reaped_by_actor_before_group_confirmation | Linux PENDING |
| 11 | cleanup_failures[orphan/group]、actor_cannot_skip_child_reaping_protocol | 纯注入PASS，不创建真实孤儿 |
| 12 | cleanup_failures[signal/wait/identity/group] | 纯注入PASS，无真实未回收资源 |
| 13 | equal_deadline_clock_anomalies_and_late_done_fail_closed；blocked_actor[late_success] | 合同PASS；Linux PENDING |
| 14 | equal_deadline_clock_anomalies_and_late_done_fail_closed | 本地PASS |
| 15 | spawn_is_fixed_minimal_and_failure_does_not_retry；same_run_reservation_is_single_use | 本地PASS |
| 16 | pid_reuse_or_wrong_group_never_reaches_signal；protocol_rejects_other_identity_order_and_free_fields | 本地PASS |
| 17 | receipt_cannot_upgrade_or_mix_evidence；cli_errors_never_echo_free_private_input | 本地PASS |
| 18 | non_linux_is_explicit_unsupported_without_spawn | 本地PASS；15个Linux专项skip不记PASS |
| 19 | 原test_rev1_synchronous_blocking_call_is_not_hard_preempted三参数原字节 | 旧278项回归PASS，缺口不关闭 |
| 20 | request_and_receipt_cannot_authorize_real_execution及每条Linux回执检查 | 合同PASS；Linux PENDING |

### 工程边界与交付

run_id 消费登记仅进程内防重放；不提供跨进程持久授权或恶意同UID防护。
组存在性用已知正PGID的信号0查询；不是向组0发信号；leader回收后只查询、不再杀组。
内核调度、监督者自身I/O、spawn及信号/wait系统调用最坏时延仍不具备全路径硬保证。
外层4秒测试兜底超时或CLEANUP_UNCERTAIN会立即终止本次pytest，不继续资源测试；
此失败路径不能被表述为已经证明任意残留进程均可回收。

只允许一次提交和普通 push，Linux 专项尚未执行由本轮负责人新授权明确豁免前置，
不是已满足 Linux 验收。推送后逐项检查15个Linux节点无skip/failure/error；
普通CI失败/必需节点跳过/回收不可靠即停止，不第二次提交、不 rerun/dispatch。
CI_PENDING时停止并提供真实链接，不预填最终SHA/Run成功或追填自身SHA造成二次CI。
最终完整SHA、五文件SHA256及CI取样以聊天交付报告和项目外证据清单为准。

AC05、R1始终PARTIAL；真实OFF/ON、正式六臂、≤3%开销、容量、PG17、Worker、
生产和部署均未执行、无本轮授权；Windows原生根因UNKNOWN。本实现不消费W01票据，
不把W02回执交给statistics或正式Gate。等待ChatGPT独立审阅，不自动进入真实集成。

## 提交前停止回执：同组 child 的 TERM/创建竞态

状态：LOCAL_BLOCKED / NO_COMMIT_NO_PUSH / LINUX_VERIFICATION_PENDING。
本节取代前文“下一步条件式提交”的可执行性；前面351 passed/15 skipped为该时点结果，
不能冒充当前最终绿色。提交前复核发现第三个独立问题，按两次局部修订上限停止。

新增确定性负例：
`test_term_before_same_group_child_spawn_never_leaves_child_unreaped`。
只在隔离Python探针内使用假Popen/假child/假signal/假os.write；没有实际 actor/child、
信号或FIFO。假Popen在返回child句柄之前触发 actor 自己的TERM处理器，模拟
“处理器已安装、child尚未创建/取得句柄”的窗口。actor看到停止标志后直接child.wait，
但该child没有收到之前的组TERM，故wait超时。探针固定输出HARD_MOCK_CHILD_UNREAPED，
退出3；测试预期0，实际1 failed（0.11秒）。这是有因果证据的资源收尾设计缺陷，
不是macOS调度猜测，也不是已观察到真实Linux孤儿。

本轮没有进行第三次实现修订、重跑该失败或推送取绿；没有真实未回收子进程。
建议待负责人独立审阅后限定整改：处理TERM早于创建/返回的窗口，并在actor持有的
child句柄范围内保证结束与wait，保持watchdog的独立组核验；还须测试TERM恰好发生在
创建前/创建中/创建后及wait失败。当前实现不满足“无未解决清理风险”的提交前门槛。

最终验证事实：此前完整本地351 passed/15 skipped；随后新增上述负例1 failed。
失败后未再运行完整/定向回归或Ruff，不能声称当前全部合同通过。
原W01七文件/历史JSON/三份审阅工件保持不变，所有新增内容仅留五文件白名单本地。
没有新Commit、push、CI、PG/Worker、真实OFF/ON、容量或部署。
下次是否允许第三次有界修订由负责人决定，不凭本轮持续开发授权绕过上限。

## P0-LNX-W02-RACE-01 / W00_RACE_ROOT_CAUSE（2026-11-08）

负责人独立补充授权针对上述新证据修复，允许本轮最多两次有证据的修订、一次条件式
五文件提交推送。原上轮停止事实不变，不追溯改写成通过。
基线仍为53f297430e432e9c7f018f6414556022aeda0a58；五文件与上轮停止摘要逐字节相符。
原失败节点本轮单次执行为1 failed/0.08秒、固定探针退出3：HARD_MOCK_CHILD_UNREAPED。

确切顺序：handler已安装→进入固定Popen→注入TERM，handler只设置stopped→
Popen返回句柄→旧循环因stopped退出→child.wait(.1)但child未收到此前组TERM→超时。
handler没有直接wait/exit；缺陷在句柄可用后的常规清理缺失。该证据是纯注入，不是Linux实测。

最小设计：新ChildLifecycle仅管理固定child，明确NOT_STARTED/OWNED/
OWNERSHIP_UNCONFIRMED/REAPED；创建前的TERM不启动child，创建中TERM在取得句柄后
走同一清理。创建异常但无句柄保守标记不确定，不将其当作确定未启动。
固定Popen显式process_group=actor自身正PGID、start_new_session=False，内核在exec前
完成归组；固定child不调用setpgid/setsid。发信号前还核对句柄PID、未回收状态和SID，
watchdog独立核对可见活child的实际PGID并检查最终组消失。没有外部PID/PGID接口。
child清理TERM→有界wait→KILL→有界wait总0.1秒，保持原child.wait(.1)上限；
从首次清理开始的绝对期限不重置，重复调用复用已冻结结果。信号handler始终只有布尔赋值。

有限协议区分TERM_REQUESTED、CHILD_NOT_STARTED、CHILD_UNCONFIRMED与CHILD_REAPED；
后者附固定类型的退出码，不拿actor自报替代OS组核验。缺句柄/身份/清理证据须进入
CLEANUP_UNCERTAIN；child未启动或晚到成功不允许将TERM请求伪装为MOCK_COMPLETE。
三个新增固定Linux场景将自发TERM放在创建前、返回后登记前、登记后；都是真实固定child
路径（创建前场景明确没有child），不是凭随机调度碰到窗口。Popen内部真正卡死及
actor在未登记窗口遭SIGKILL仍NOT_PROVEN，不能声称彻底回收任意未知孙进程。

## RACE-01 实现、回归与条件式交付回执

当前本地门禁：RACE01_LOCAL_VERIFIED / LINUX_VERIFICATION_PENDING。
原LOCAL_BLOCKED及两次上轮修订保持历史事实；本节仅代表负责人新补充授权后的新结果。

### 实现边界

ChildLifecycle在Popen前记录尝试且仅允许一次；TERM已到时保留NOT_STARTED。
调用被中断、抛错或没有句柄时保留OWNERSHIP_UNCONFIRMED，绝不假定无残留。
获得句柄后由统一cleanup执行wait(0)快速退出检查、身份核对、TERM/wait、KILL/wait；
TERM结束点为首次清理+0.05秒、全部结束点为+0.1秒，没有扩大原child.wait(.1)预算。
每次清理结果冻结，重复调用不再采样时钟、发信号或wait；handler仅写stopped布尔值。
包括IPC异常的常规控制流都通过finally执行已知句柄清理。无法证实则报告不确定。

child固定Popen的process_group参数来自actor自身getpgrp且start_new_session=False，
不是由CLI传入组号。内核在exec前归组，child固定分支不修改session/PGID；清理前核对
保留的句柄PID、未回收状态及SID。watchdog继续独立核对收到的活child实际PGID、
leader身份、wait和最终组消失；对已回收child不向复用PID发信号。
没有使用pthread_sigmask、全局PID扫描或任意PID/PGID入口。

有限消息新增TERM_REQUESTED、CHILD_NOT_STARTED、CHILD_UNCONFIRMED；CHILD_REAPED
必须附int退出码。不确定消息只接受固定首错与固定清理错误枚举，不能再接DONE洗成成功。
watchdog将child创建状态、退出码、TERM意图分别记录；TERM后的“actor清理退出0”仍为
MOCK_FAILED或原MOCK_TIMED_OUT，不允许MOCK_COMPLETE，已有deadline首错不会被覆盖。
没有改变W01协议或W01票据；上述仅为尚未正式交付的W02候选消息合同补齐。

### 精确验证与失败保留

环境：macOS/Darwin arm64，CPython3.12.14；默认source_contract_pytest插件未禁用。

- 原节点本轮RED：1 failed/0.08秒，探针退出3；完整配套修复后GREEN：1 passed/0.07秒。
- 串接开发中一次编辑脚本SyntaxError未写入watchdog；随后提前执行节点因缺少
  CHILD_SCENARIOS得到AttributeError、1 failed/0.08秒。该未完成候选失败另行保留，
  补齐配套常量/协议后才执行GREEN和完整回归，不将该错误冒充TERM竞态根因。
- 新W02合同文件：94 passed/0.18秒；本轮新增20个参数化合同节点，原74节点原断言未改。
- 最终同一Python源码合跑：372 passed、18 skipped，5.85秒，退出0。
  94项W02合同+278项旧W01离线回归通过，18项Linux-only均在macOS明确跳过。
- Linux专项保留原15节点，新增3个固定TERM时点节点；非Linux skip不计Linux通过。
- Ruff新四Python文件及旧W01六Python文件共10文件通过；初次新增测试辅助一条超长行
  仅换行修正，未改规则或断言。无全量仓库pytest、安装、PG/Worker或真实实验。
- 原七W01文件、原四JSON、用户两ZIP/一Patch摘要不变；新增五文件逐项空白/AST核查。
  已有W02测试函数及其参数化装饰器/断言与本轮开始副本AST一致，没有skip/xfail新规。

命令：

```bash
.venv/bin/python -m pytest tests/unit/test_perf03_lnx_hard_watchdog_contract.py tests/integration_offline/test_perf03_lnx_hard_watchdog_linux.py tests/unit/test_perf03_lnx_offline_contract.py tests/unit/test_perf03_lnx_offline_supervisor.py tests/unit/test_perf03_lnx_offline_parity.py -q --tb=short
.venv/bin/python -m ruff check scripts/perf03_lnx_hard_watchdog.py scripts/perf03_lnx_hard_mock_actor.py tests/unit/test_perf03_lnx_hard_watchdog_contract.py tests/integration_offline/test_perf03_lnx_hard_watchdog_linux.py scripts/perf03_lnx_offline_contract.py scripts/perf03_lnx_offline_supervisor.py scripts/perf03_lnx_mock_child.py tests/unit/test_perf03_lnx_offline_contract.py tests/unit/test_perf03_lnx_offline_supervisor.py tests/unit/test_perf03_lnx_offline_parity.py
```

### R01～R16 验收映射

| ID | 实际测试/证据 | 本地结论与Linux边界 |
| --- | --- | --- |
| R01 | 原test_term_before_same_group_child_spawn_never_leaves_child_unreaped不变 | RED→GREEN，纯注入 |
| R02 | race01_term_boundaries[before] | PASS，Popen零次；Linux before_spawn待执行 |
| R03 | race01_term_boundaries[during]、failed_spawn | PASS，返回句柄后清理；无句柄不确定；Linux before_registration待执行 |
| R04 | race01_term_boundaries[after] | PASS；Linux after_spawn待执行 |
| R05 | fast_exit_kill_escalation_and_repeat_term[fast] | PASS，退出码0、回收一次、不再发信号 |
| R06 | fast_exit_kill_escalation_and_repeat_term[normal/ignore] | PASS，两次TERM仅登记意图，cleanup重复调用复用结果 |
| R07 | fast_exit_kill_escalation_and_repeat_term[ignore] | PASS，模拟child TERM→KILL；既有Linux ignore_term真实组KILL待执行 |
| R08 | failed_spawn[oserror/interrupted/no_handle] | PASS，不伪造NOT_STARTED |
| R09 | wait_and_signal_failures[term_error/wait_error/kill_error/unreapable]、budget | PASS，纯假句柄，无真实未回收资源 |
| R10 | wrong_child_identity[pid/sid/reaped_handle]、既有wrong_group | PASS，拒绝向外部句柄发信号 |
| R11 | unknown_child_cannot_be_upgraded_by_actor_done、既有cleanup_failures[orphan/group] | PASS，watchdog保持不确定 |
| R12 | 平台skipif(sys.platform!='linux')、non_linux入口合同 | macOS 18 skipped明确PENDING，不是LinuxPASS |
| R13 | linux_same_group_child、blocked_actor[ignore_term]、三个新Linux TERM窗口 | 同SHA Runner PENDING，必须逐节点核查 |
| R14 | 原Linux FIFO reference与blocked_actor[FIFO]及其它边界 | 源码保留、Linux PENDING |
| R15 | 旧三组W01测试278项、SHA核验及老同步阻塞负例 | PASS，缺口仍PARTIAL |
| R16 | 所有回执合同、no_child_after_term、child_cleanup_error_preserves_prior_deadline | PASS，无真实执行许可 |

### Git/CI 与尚未证明

仅当本地门禁与基线检查通过才按本轮明确授权创建一次master提交和普通push，
获取同SHA现有Main CI full_tests中18个Linux节点的真实结果；不手动dispatch/rerun。
精确SHA、五文件摘要、Run/attempt/Job和逐节点结果由最终聊天回执及项目外工件清单提供，
不为追填本文件自身SHA再提交。若CI仍运行标CI_PENDING并停止，不预填通过。

两次创建边界均为固定Mock：Linux before_registration在真实Popen返回后、对watchdog
登记CHILD之前自发TERM，不冒充在内核Popen永久阻塞时仍能取得句柄的证明。
控制器首次spawn、watchdog自身阻塞、Linux D状态、actor在未登记窗口遭SIGKILL、
持久可信回执和恶意同UID行为仍NOT_PROVEN。单进程内run_id消费不等于持久授权。
真实Linux结果未取得前不能记W02工程通过；独立审阅前不能记CLOSED。
AC05/R1始终PARTIAL，Windows原生根因UNKNOWN，PG17、Worker、真实R1、容量与部署均未授权。
