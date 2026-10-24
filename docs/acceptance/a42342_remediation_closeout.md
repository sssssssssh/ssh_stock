# A42342 模拟证据与 Reviewer 安全整改

基线 a05ab9ffa77d54126aedbdc4fee5396359326edc，master。
本记录在最终一次推送前提交；最终40位SHA、同SHA CI run/attempt/job与下载核验工件由推送后交付回执给出，
不能提前将尚未发生的CI标通过。目标 A42342_CODE_ACCEPTED 仅指代码/模拟合同验收。

**真实校准仍禁止；BLOCKED_NEEDS_USER_PROTOCOL_DECISION 不解除。**
所有真实 execution/performance/capacity/production/attribution 准入 false，unique_repair_candidate=null。

## W00：基线与先复现

开工 HEAD==origin/master==远端 a05ab9ffa77d54126aedbdc4fee5396359326edc，工作区干净，保持当前master。
重新读取 GitHub 主CI 40061331573 与专项40061331658 jobs，均SUCCESS；未重跑旧CI。
基线主CI3253 passed/89.28%；专项319+109+157。旧冻结清单20文件校验通过。
原v3提案SHA256 065b529f759308c49630c5ce390864a7589b51fcb1be645ca420ed3575692220、
manifest SHA256 4cca8088909821371f99d8cd9dba450d2fa6ada4c6dbc462ccd8ec64498a163e 均保留。

在任何 reviewer 改动前，用纯内存 simulate 与临时工件实际复现：

| 反例 | 原实现结果 |
|---|---|
| JOIN_TIMEOUT 却伪造 joined=true | 被解析为合法 INCOMPLETE / SIMULATED_REJECT，未结构性拒绝 |
| 未 join 的 partial cleanup=true | 同上 |
| 删除已开始 block 的 warmup | 同上 |
| 删除全部 probe | 同上 |
| observed_until 超出 parent/block | 同上 |
| 有完整 partial 却改 phase=DURING_LOOKUP | 同上 |
| 真 CLI 读取完整模拟接受 bundle | exit 0，stdout/stderr为空 |

新增36项结构反例在修复前实跑：30 failed、6 passed（6项已被原实现拒绝）；保留全部断言。
复现日志和安全JUnit保存在本轮本地验收工件，未启动数据库、Observer、2000键lookup或预热。

## W01/W02：最小修复

仅 scripts/a42341_calibration_review.py：

- validate_prefix_and_timeline：两种结局均核对严格schema、独立expected、摘要、连续已完成前缀、
  block序号/串行/边界、已开始block的完整预热记录与合法探针前缀；无failed_point须完整128点。
- validate_failed_point：精确冻结schedule[len(samples)]，身份/进程/连接/backend归属、窗口与稳定
  observed_until、阶段/partial存在性、INCOMPLETE状态、已记录GC/segment/tick时间与顺序全部交叉核对。
- JOIN_TIMEOUT 必须对应未join STOP_TIMEOUT/无worker终态、partial cleanup=false；不伪造whole-worker CPU/elapsed。
- 用原始 check_sample_evidence 复核所声明的 POST_LOOKUP_VALIDATION 故障，不把partial复制成COMPLETE，
  不修改/剔除wall、ticks或GC；合法缺资源/partial tick/stop timeout仍保留已取得记录。
- validate_cleanup_consistency：首发错误不被清理码覆盖，清理码精确有序、不重复、不接受业务错误冒充清理；
  仅128点全部完成、全部边界探针齐全时可failed_point=null且只报最终cleanup失败。
- review_bundle 原返回结构与 mock.v1 模型保持；全部合法INCOMPLETE仍 SIMULATED_REJECT/UNDETERMINED。

CLI 固定JSON包含 mock_contract_validated、simulated_threshold_decision、
authorization_status=NOT_RUN_NOT_AUTHORIZED、real_performance_eligible=false 及既有安全位：

| 情况 | exit | result |
|---|---:|---|
| 合法模拟接受 | 2 | MOCK_VALID_SIMULATED_ACCEPT_NOT_AUTHORIZED |
| 合法模拟拒绝/未完成 | 3 | MOCK_VALID_NOT_QUALIFIED |
| 坏身份/schema/文件/工件 | 1 | 固定 A42341 错误码 |
| execute/approve/force/profile/token/未知参数 | 1 | A42341_EXECUTION_NOT_AUTHORIZED |

任何CLI路径不返回0，不打印异常原文、路径、连接串或参数；不将mock CLI作为CI绿色步骤或正式Gate。
CI来源仍是既有pytest/Ruff/合同核验，无工作流修改、无新增dispatch/Environment/profile/token。

## W03：T01–T20 覆盖

新增测试位于既有 test_a42341_runner_review.py、test_a42341_environment_guard.py，
现有专项三文件选择自然收集全部新用例；不新增必须修改工作流才能运行的测试文件。

| T | 回归/正反例 |
|---|---|
| T01 | 原完整128点/64对/11组正例，所有安全位不变 |
| T02 | 第3点SQL_TIMEOUT，已完成前三点与失败末点原样保留 |
| T03/T04 | 伪造joined、partial cleanup、worker终态、top cleanup拒绝 |
| T05 | 重复/跳位/跨block、错进程/连接/backend身份拒绝 |
| T06 | 窗口倒序/未来、observed倒退/越界、GC/segment/tick/backend时间不一致拒绝 |
| T07 | DURING_LOOKUP带partial或POST_LOOKUP_VALIDATION无partial拒绝 |
| T08 | 删除/重复/乱序warmup/probe/block、probe计数/时间错误拒绝；十个block首尾失败位置为合法前缀 |
| T09 | 全128点后仅cleanup失败无failed_point合法；截断点/少block/伪造first拒绝 |
| T10 | SQL_TIMEOUT为首错，CLEANUP_FAILED独立追加；伪首错/重复或错误清理码拒绝 |
| T11 | partial tick与STOP_TIMEOUT原样保留，仍未join/未清理，不补写worker CPU |
| T12 | 原始异常/DSN未知字段固定码拒绝；无原文泄漏 |
| T13/T14/T15 | 真实Python CLI子进程分别exit2/3/3，JSON明示未授权；stdout/stderr无路径或原值 |
| T16 | 独立expected错SHA/run/attempt、自报expected、坏manifest、改failure并重签manifest仍拒绝 |
| T17 | 九类非法开关和把--execute冒充路径均exit1，不读输入文件或解锁执行 |
| T18 | 多/缺文件、越界路径、symlink、改摘要、不可覆盖与原子写失败，旧/新增反例共同验证 |
| T19 | 原A4233/A4234/A42341不删/skip/xfail；schema/其他五个A42341模块/生产目录/工作流冻结 |
| T20 | 最终同SHA主CI/专项/工件由推送后实际回执核验，不能用基线结果替代 |

本地使用已验证Settings.model_config env_file=None包装与不可连接loopback假测试地址，
子进程仅导入纯脚本，并显式绑定同样不可连接的测试地址；不读业务.env或启动服务。
本地定向/全unit/Ruff/差异实际结果及最终同SHA CI在交付回执记录；任何未执行项如实NOT_RUN。

推送前最终稳定工作树实际结果：三份A42341定向241 passed（原157+新增84），exit0，38.58秒；
完整unit 2510 passed、5条原有弃用警告，exit0，72.86秒；Ruff与git diff --check均exit0。
CLI子进程已实际验证2/3/3与非法输入1，不依赖模拟返回0使pytest通过。
本地不启动PG17/Docker；完整数据库、前端、容器和浏览器验收留给最终SHA原普通CI，不能提前标完成。
开发期一次中间态定向为6失败/231通过，该轮与源码格式编辑存在重叠，不作为最终验收；
6项单独复核及最终241项定向、2510项全unit均通过，未删减/skip/放宽任何断言。
这些是纯单元调试，不是反复运行真实实验取得PASS。

## W04/W05：冻结、交付与停止线

唯一工具改动为reviewer；contract/schema/runner/environment/prepared/guard保持基线字节。
旧A4233/A4234、v2/v3、input/model/SQL/requirements、policy/consumed/evidence全部保持；
backend/config/migrations/frontend、所有.github工作流/正式Gate零改动。旧历史工件不覆盖。
旧mock.v1仍可严格解析；历史HEAD/source/attempt不能转用为当前身份，不能为兼容绕过独立expected验证。
实际核对旧ZIP12547024982的SHA256 bb1ecd4ceef864cd11bfe7214a7aabfdfe1ea7f204e085b051a5aa20a813b4f2，
其中原完整/未完成两份samples均可用未变的Bundle模型解析；未重签旧ZIP或将其当当前SHA验收。
本轮六模块source新摘要3edf9ad70bb8a0f20a3afa3078a00e5fe0fe72969a4c97aac772da12c203bdc9，
仅reviewer变化，不改冻结提案/清单的历史SHA。
四份权威Markdown仅追加本轮安全边界，原历史记录不回写；本closeout与推送后回执区分。

拟交付文件：reviewer、两份现有unit、本closeout及README/PROJECT_RULES/PRD/系统设计，共8文件。
所有修改合并后仅推送一次；不dispatch、rerun、取消或额外跑昂贵工作流。
普通CI仍会运行其自有隔离PG17既有回归/冻结cursor smoke与微型Observer，这不是新A42342测量。

预热仍总8次；v3至少16次仅必要下界，USER_APPROVAL_PENDING。真实prepare/计划稳态、backend CPU/
物理角色、长期Observer桥接与开销、C1归因/P95/L2、生产读取均未取得授权或实证。
先单独审批新协议/固定预热预算，后再单独审批真实exact SHA/profile/未消费one-shot/Environment/资源。
代码验收不改变上述状态。完成本轮后停止，等待代码审阅，不进入真实实验或生产发布。
