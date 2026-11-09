# P0_R1_W04A_HASH_COMPAT_FIX_01

日期：2026-11-10（Asia/Shanghai）。本报告为提交前的可审阅交付记录，不追填自身提交 SHA。

## 身份、授权与结论

- TASK：P0_R1_W04A_HASH_COMPAT_FIX_01。
- BASE_SHA：60dacb8f96013439ebb8490b78eaffd6a3cfbcbd。
- 修改前 HEAD / origin/master / 实时远端 master 相同；已跟踪工作区干净。
- 原两份审阅 ZIP 和一个 Patch 保留，不清理、不纳入提交。
- 负责人本轮明确请求“根据任务书修改，推送代码”，授权本轮五文件 master 交付及普通 push CI；
  不把任务书中的独立审批提示扩展为真实实验许可。
- 本地 P0 GREEN；P1 离线模拟验证通过。真实 Windows 未运行。
- 完整工程验收仍 CI_PENDING，只有精确新 SHA 的完整 Main CI 成功并经独立审阅才可关闭。
- R1=PARTIAL；HISTORICAL_AC05=PARTIAL；REAL_PG17_WORKER_OFF_ON=NO_GO；
  PERFORMANCE_ACCEPTANCE=NOT_MEASURED。

## W00：真实失败证据及固定 Blob

Main CI [42624310482](https://github.com/sssssssssh/ssh_stock/actions/runs/42624310482)，
push / attempt 1 / head_sha=60dacb8f96013439ebb8490b78eaffd6a3cfbcbd，最终 completed/failure。
test Job 129184017465：6511 passed、2 failed、1 skipped；816 warnings；2111.76s。
coverage 90.02% 保留任务书记录，不将其与测试计数或 JUnit case 数量相加。

下载并核对了安全工件 13679259293：
a42331-safe-ci-60dacb8f96013439ebb8490b78eaffd6a3cfbcbd-42624310482-1。
ZIP SHA256：
6a1713c7c5163c450598beda9795a38f77335171ef99a38335cdcb1621754151。
其完整 JUnit 为 8329 testcase / 2 failures / 0 errors / 1 skipped；
failure.json 为 evidence_complete=true / status=INCOMPLETE /
first_failure_code=A42331_UPSTREAM_NOT_SUCCESS。这是上游测试失败被完整记录，
没有据此推断 sanitizer 再次损坏。

JUnit 精确失败节点：

1. tests.unit.test_r1_real_root_protocol.ProtocolTests.test_AC01_original_six_and_baseline_preserved。
2. tests.unit.test_r1_seed_snapshot_recipe.SeedTests.test_AC29_environment_tools_and_w04a_suite_not_modified。

原日志分别为 test_r1_real_root_protocol.py 的 F....... 和 seed_snapshot_recipe.py 的 .F...。
共同首因：旧 ORIGINALS 断言要求 W04-A 测试的 f3232a88…，但获批当前文件已是 c5dd882a…。
W04-A 自身、行尾测试已经通过；error-0 不是本轮失败节点。
本轮没有修改 Worker、根诊断、sanitizer、业务事务或金融公式。

历史冻结提交：
8443b7cd524a6964b24cecd60df5be5b6c46783b。
批准当前提交：
60dacb8f96013439ebb8490b78eaffd6a3cfbcbd。
以下摘要均在修改前从这两个固定 Git Blob 独立复核；其余五文件两版本逐字节相同。

| 路径 | 历史 LF SHA256（ORIGINALS 原样保留） | 当前 LF SHA256 | 当前全 CRLF SHA256 |
| --- | --- | --- | --- |
| docs/acceptance/BIZ_PERF_03_A_R1_LNX_W03_PREFLIGHT.md | 21e9f0acc048d1724be985b13667a2cd71572992096abea9d8fbd57699455c9d | 21e9f0acc048d1724be985b13667a2cd71572992096abea9d8fbd57699455c9d | 8f2c90e4f8b56a246e8835476da7b69c11152d388440d40720b7016049acee3d |
| docs/acceptance/BIZ_PERF_03_A_R1_LNX_W04_READINESS.md | 09ac6d54828cdc085e134c5a54f91e3a1efa8933d42dea1e9bc7ae3967370f0d | 09ac6d54828cdc085e134c5a54f91e3a1efa8933d42dea1e9bc7ae3967370f0d | 39fd9206c63287106220e61f349dfabe659f0804ed6c728d09bc03e060b6bb6c |
| docs/acceptance/biz_perf_03_a_r1_lnx_w04a_contract.json | 0f464a6acc4efc651fdea798fac1b0b4b3b61069147515115afa5b9f2d91d2f8 | 0f464a6acc4efc651fdea798fac1b0b4b3b61069147515115afa5b9f2d91d2f8 | 023f36644e2c498ee70f0c5f52b6b930164fa2b58f6d23991ffbeffb97016cd5 |
| scripts/perf03_lnx_w04a_offline_contract.py | b11a4a2b8e6da6224ab8c503130073bef5ace9ec701dbf43649e116c0be6c5a0 | b11a4a2b8e6da6224ab8c503130073bef5ace9ec701dbf43649e116c0be6c5a0 | 17a09bc86be0bdbdd0b2b0e60897210ac9c31de94e0fdde16fce9ec368245add |
| tests/unit/test_perf03_lnx_w04a_offline_contract.py | f3232a88f0be68ca710ffba337e8dcfae9fa096d54a681ee8dc2eb760efce2ef | c5dd882ad80cf753a1423aba1aea7c474742886d9a20bac31807641531fb9a38 | ad6fb96689c8d25569cdb1eecd2dcf007e7e2f1cbabcaf69342ad4431a510c41 |
| docs/acceptance/BIZ_PERF_03_A_R1_LNX_W04A.md | 25bffe509c2f78473221bbb39c61bac95eec6db5e0930828205072ea46e66b20 | 25bffe509c2f78473221bbb39c61bac95eec6db5e0930828205072ea46e66b20 | 4baac2a22ac14f6f659698dcafc77b93896a60bc1f9ecb3b8a6f324004b59133 |

W04-A 历史全 CRLF 摘要：
cdfb820f1833b41a1170f4f923d4f89a39354bcfb725c2c89d816081b97f359b。
它与历史 LF 仅用于历史证明，不进入当前允许集合。
W00_BLOB_VERIFIED=PASS；四个指定 W04-A 摘要与任务书完全一致。

## W01：一个当前版本校验入口

test_r1_real_root_protocol.py 新增固定 CURRENT_APPROVED_SOURCE_VERSION、
六路径 CURRENT_APPROVED_SOURCE_HASHES 和 verify_approved_sources()。
原 ORIGINALS 六项历史 LF 映射逐字面保留，历史基线、R1 target SHA 和 12 个新增路径断言不变。
AC01 与 AC29 共用该入口；AC29 的 DECISION_REQUIRED 断言保留。

校验器不运行 Git/网络，不读取环境变量、数据库或当次 HEAD，不对真实文件字节执行
replace/strip/解码归一化。只用固定批准的完整 LF 或完整 CRLF SHA256 接受真实字节。
固定版本必须为 60dacb8f…；额外清单指纹防止允许值、路径集合或版本意外漂移，
不是运行时从用户文件生成期望。清单恰为六个路径，缺少、重复、额外或未知路径均拒绝。

在读取前验证受控根、固定路径的每级父目录和目标 lstat。
根/父目录不得为 symlink 或 junction，文件必须为普通文件且非链接；
缺失、目录、父路径穿透都以固定安全错误拒绝，不把真实路径或字节打印到失败码。
校验旧版回退时，只验证它确实等于历史摘要，然后要求当前校验拒绝；不采用 OLD/NEW 并集。

## W02：RED → GREEN 与负例

目标解释器 Python 3.12.14，pytest 9.1.1，macOS。
源代码和测试修改前先执行任务书给出的两个精确节点：
RED_AC01_AC29：2 failed，exit 1，0.06s；
原始错误明确是 c5dd882a… != f3232a88…，不是只保存 A42331_TEST_FAILURE。

P0 初次 GREEN：两原模块及新增负例 34 passed、19 subtests passed，exit 0，1.30s。
随后增加两项清单漂移负例，在最终组合中一并通过。P0 先 GREEN 后才实施 P1。

负例矩阵结果（均在离线临时目录）：

| 项目 | 结果 |
| --- | --- |
| 六文件当前完整 LF、完整 CRLF | PASS |
| W04-A 历史 LF / 历史 CRLF 回退 | REJECT |
| 任意一个文件的字符、空格、末尾换行变化 | REJECT |
| BOM、NUL、孤立 CR、混合行尾 | REJECT |
| 文件缺失、目录、符号链接、父路径符号链接穿透 | REJECT |
| 路径集合少项、多项、重复；清单少项、多项、哈希被改 | REJECT |
| 版本常量或调用方批准版本不匹配 | REJECT |
| 运行时 Git/网络/环境身份推断 | 禁止调用的边界探针通过 |
| 原 NO_GO、DECISION_REQUIRED 和监督权限 | 未提升 |

历史回退样本不要求浅 checkout 含旧 Git 对象：测试只逆向构造固定的获批 W04-A 补丁，
先核对生成样本的完整历史 SHA256，再证明当前校验拒绝；该逻辑仅为负例样本构造。
当前验收函数完全不读取历史 Git。

## 可分离 P1：合法 CRLF checkout 与 symlink 权限

P1 的 RED 探针在独立内存中载入基线 original()，对 18 路径构造合法 CRLF checkout，
旧逻辑因“输入不得含 CR”断言失败，exit 1；原始证据保留。

新 original() 先用冻结且未修改的 w.assert_frozen_file() 核实真实文件字节，
再仅对已确认的合法 CRLF 样本转换成 LF，用于构造正负测试样本。
真实校验器不进行该转换。原 W04-A 文件、本体 helper 以及 18 路径固定锚点完全不变。

Windows winerror=1314 的 symlink 创建能力不足单独记录为 UNAVAILABLE_WINDOWS_PRIVILEGE；
使用不依赖创建权限的 lstat 边界注入继续执行同一拒绝断言。其他 OS 错误不吞掉。
新增探针主动注入 1314，确认 18 路径的拒绝断言全部执行；没有 skip/xfail 或整组跳过。

原 49 个行尾测试保留，增加合法 LF/CRLF checkout 两项和权限不足语义一项，共 52 项通过。
CROSS_PLATFORM_P1=PASS_OFFLINE_SIMULATION；native Windows=NOT_RUN，不伪称 Windows 实机验收。

## W03：实际回归和范围

一次组合运行（默认 source_contract_pytest 保留，同时加载 a42331_pytest_safety）：

- 167 passed、1249 subtests passed、5 warnings，exit 0，34.10s。
- 脱敏 JUnit：1416 testcase；tests=1416、failures=0、errors=0、skipped=0。
- 顶层用例、subtest、JUnit case 是不同口径，不重复累计。
- 原 W04-A 20 项、新行尾 52 项、A42331 两模块 30 项、原 R1 source/schema/seed/adapter/
  supervisor 42 项，以及新增版本哈希负例 23 项，均包含在这一次组合中。
- 警告为既有/新增 record_property 与 xunit2 的兼容提示，没有当作测试失败节点。
- 六组 R1 integration 单元另行执行：58 passed、566 subtests passed，exit 0，41.42s，
  不与上述组合重复累计。
- 全库 Ruff：All checks passed!；四个修改/新增 Python 文件按目标解释器编译通过；
  git diff --check 通过。

仅允许的五个文件发生变化：

1. tests/unit/test_r1_real_root_protocol.py：当前批准版本清单及严格统一入口、AC01 接线。
2. tests/unit/test_r1_seed_snapshot_recipe.py：AC29 复用入口，保留 owner decision 约束。
3. tests/unit/test_r1_approved_source_hashes.py：23 项独立版本/路径/篡改负例。
4. tests/unit/test_w04a_line_ending_integrity.py：P1 样本与能力限制处理，原49项仍执行。
5. docs/acceptance/P0_R1_W04A_HASH_COMPAT_FIX_01.md：本报告。

未改 tests/unit/test_perf03_lnx_w04a_offline_contract.py，其 SHA256 仍为
c5dd882ad80cf753a1423aba1aea7c474742886d9a20bac31807641531fb9a38。
全部非白名单原件与开发起点字节对照、ORIGINALS 字面量以及 AC01/AC29 外原 R1 测试 AST 检查保留。
完整 Diff、逐文件 SHA256、固定 Blob 对照、RED/GREEN、JUnit 与编译/静态验证放在仓库外私有证据目录。

## Git、CI 与剩余边界

COMMIT_PUSH：获负责人本轮请求授权，待执行范围检查后的单次普通 master 提交推送；
最终完整 SHA、四条自动工作流 Run/attempt/head_sha 和实时状态以交付对话及仓库外回执为准。
CI 不手动 dispatch/rerun；若新 CI 出现其他失败，独立保留证据，不无依据修改 Worker 或 sanitizer。
本地通过不满足本任务 AC09 的完整新 SHA Main CI 条件，不提前关闭。

本任务 AC05 是测试负例验收项，不是历史监督门禁 AC-05。
R1=PARTIAL；历史 AC-05=PARTIAL；REAL_PG17_WORKER_OFF_ON=NO_GO；
PERFORMANCE_ACCEPTANCE=NOT_MEASURED。业务库、PG17、真实 Worker、OFF/ON、容量与部署均未执行。
停止等待独立审阅，不自动进入真实 readiness 或性能实验。
