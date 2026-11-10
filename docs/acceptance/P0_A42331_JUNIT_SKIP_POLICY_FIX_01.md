# P0_A42331_JUNIT_SKIP_POLICY_FIX_01

日期：2026-11-10，Asia/Shanghai。当前状态：**LOCAL_GREEN / NEW_SHA_CI_PENDING / REVIEW_PENDING**。

负责人已批准“最小接线和可信回执”。**当前实现与交付以第8节为准**。
第1～7节保留首次范围停点的历史证据，描述的是提交 `35143411e696549d5aba02a8dc0658b69675cfbf`
之前的状态，不能解读为本次批准后仍未实施。最终新提交的完整 Main CI 和独立审阅尚未完成，任务不关闭。

首次交付完成最新代码拉取、基线与历史 CI 核验、旧逻辑 RED、实际 pytest 插件链路复现和阻断论证。
**未实施 Skip 放行补丁，未完成 AC02/AC14，也未取得修复后 Main CI success；本任务不能关闭。**
只新增本报告，不修改收集器、插件、既有测试、Workflow、冻结文件或业务代码。

## 1. 基线与授权

- 任务书 BASE_SHA：`31d701f1437aa179df85a8e8f37de15581b705fa`。
- 会话开始本地 HEAD：`e7b783ee70dcf5326f5d4a7797f099308495df43`，工作区干净。
- fetch 后检查三个远端新增提交：c238dbd、60dacb8、31d701f，确认差异后按负责人要求
  `git pull --ff-only origin master`；拉取后 HEAD、origin/master、实时 GitHub master 均为 BASE_SHA。
- 开发起点全部 1551 个既有跟踪文件的原始 SHA256 已保存在仓库外；本报告交付前逐项检查。
- 五份治理文件按 AGENTS 顺序读取，核对 PRD、系统设计、PROJECT_RULES、README 的相关边界。
  PROJECT_STATUS 的旧 G0/CI-OPT 指针保留历史语境；本轮唯一任务来自当前附件和负责人请求。
- 负责人明确要求“拉取最新代码，根据任务书开发，推送代码”，授权正常 master 交付；
  这不覆盖附件明确要求的额外文件修改停点，不扩大为真实实验或 Workflow 修改授权。

## 2. 历史 Main CI 独立核验

以下为只读 GitHub GET 和既有工件下载，均是 push / attempt 1 / BASE_SHA。

| 工作流 | Run | 实际结果 |
| --- | --- | --- |
| Main CI | [42661037539](https://github.com/sssssssssh/ssh_stock/actions/runs/42661037539) | completed/failure |
| A4-2 | [42661037814](https://github.com/sssssssssh/ssh_stock/actions/runs/42661037814) | completed/success |
| A4-1 | [42661037402](https://github.com/sssssssssh/ssh_stock/actions/runs/42661037402) | completed/success |
| Publication | [42661037423](https://github.com/sssssssssh/ssh_stock/actions/runs/42661037423) | completed/success |

Main test Job `129312352798` 的 full pytest 实际日志为：
**6539 passed、1 skipped、821 warnings、3576.72s**。
安全工件 failure.json 登记 targeted/full_tests/data_queue/browser/runtime_browser 五阶段 success，
upstream_status=success，但 status=INCOMPLETE、evidence_complete=false、
first_failure_code=A42331_SAFE_EVIDENCE_INCOMPLETE。
safe_evidence Step44 和最终结果校验 Step57 均 failure；其他三条工作流 success 不覆盖这些失败。
覆盖率 90.02% 为任务书提供的既有数字；本轮没有把它当作安全策略成功或重新执行覆盖率验收。

已下载并核对 GitHub API digest 的两个工件：

| 工件 | ID / 大小 | ZIP SHA256 |
| --- | --- | --- |
| a42331-safe-ci | 13699980685 / 154424 bytes | `7a886f9fd08b1415ad719382b41fe946e454d14c3fd9771f6a9690868822c78e` |
| a42331-safe-errors | 13699591566 / 1718 bytes | `fcc1584e3c1bb040ab68f64218028cb780bf805b50cec582ce3c9fe5925283f9` |

安全 `m17_1_2-full.xml` SHA256：
`56bbbcaad9337ff78ce0665cad524cb3576ecc5f42e0c598f52b4a229aa18366`。
其声明及实际节点均为 tests=8355、failures=0、errors=0、skipped=1。
6539 个顶层 passed 与8355个含子报告的 JUnit 节点不是同一计数，不能相加。

唯一 skipped 的精确身份为：

```text
classname = tests.integration.test_r1_integration_linux_mock_domain.LinuxLabTests
name = test_linux_success_term_kill_owned_child
```

安全 XML 的 message 和 text 均已变为 `A42331_TEST_SKIPPED`。
源码中的固定理由为 `NOT_RUN/ENV_BLOCKED: no independently approved no-network Linux lab`；
**这只证明源码常量，不能证明历史原始 JUnit 的理由已经被严格核验。**
本轮未从安全 XML 反推出已不存在的原始理由。

既有 safe-errors 的回执包含 schema_version、evidence_kind、head_sha、run_id、attempt、
failures、junit_sanitized 和三项恒 false 的资格字段；没有原始 Skip 判定或其绑定证据。
不能用 `junit_sanitized=true` 代替原始理由校验。

## 3. 已确认的根因和额外阻断

第一个问题是任务书指出的判定：`collect()` 把全量 JUnit 的 failures/errors/skipped 一并要求为0。
即使所有强制阶段 success、唯一 Skip 合规，旧逻辑仍拒绝。

另一个必须同时处理的问题发生得更早：

1. `.github/workflows/ci.yml` 的 full_tests 使用 `-p scripts.a42331_pytest_safety`。
2. `scripts/a42331_pytest_safety.py::pytest_unconfigure()` 在 pytest 结束时调用
   `sanitize_junit(path)`，原地覆写 full JUnit。
3. `sanitize_junit()` 去除 Skip 的原始 message/text，只留下固定安全码。
   返回值只有 counts/sha256/bytes；该调用点没有把原始 Skip 判定保存到可信的跨进程证据链。
4. 后续独立进程 `python -m scripts.a42331_ci_evidence collect` 才遍历这份已经脱敏的 XML。

因此，仅在 `collect()` 的遍历中读取原始理由，无法覆盖真实 Main CI 链路。
若只根据脱敏后的 classname/name、skipped=1、源码常量或 pytest exit0 放行，
恰好违反本任务 AC04、AC12、AC13 与第3.4节的要求。

### 3.1 相同安全字节的反例

使用同一精确 classname/name、相同时间和计数的两个合法 JUnit fixture：

- A：message 是精确批准理由。
- B：message 是不批准的离线私密哨兵；不在本报告或公开回执中复制其原文。

旧 sanitizer 对两者生成**逐字节相同**的安全 XML：

```text
tests=1 failures=0 errors=0 skipped=1
safe_sha256=ad984c8f2932766b36f46507d450239aed2b7a954867da2858206be7b98d161f
```

从相同安全字节出发的无额外可信状态判定，不能同时做到“A通过”和“B拒绝”。
SHA256 只绑定当前安全字节，不能恢复被删除的原始理由；自行填写布尔或无认证旁路文件也不能解决可信性。
这不是放宽 `skipped==0` 的一行补丁可以安全解决的完整链路。

## 4. 已执行的 RED 与控制验证

全部样本位于仓库外自有临时目录，仅导入证据模块、标准库和现有 pytest。
未连接数据库、运行股票 Worker 或执行 Linux 进程域实验。

| 验收项 / 输入 | 实际 collect/CLI 结果 | 本轮判定 |
| --- | --- | --- |
| AC01：全量1例、skip0、五阶段success | COMPLETE；counts=1/0/0/0；CLI exit0 | 基线控制通过 |
| AC02：精确身份与精确批准理由、skip1 | INCOMPLETE；counts=1/0/0/1；CLI exit1 | **RED，未修复** |
| AC03：未知 name、skip1 | INCOMPLETE；CLI exit1 | 拒绝行为保留 |
| AC04：精确身份但错误理由、skip1 | INCOMPLETE；CLI exit1；无哨兵泄露 | 拒绝行为保留 |
| AC13：仅给已脱敏的精确身份、skip1 | INCOMPLETE；CLI exit1 | 拒绝行为保留，不能改成按ID放行 |
| AC14：五阶段success且精确批准skip1 | 仍 INCOMPLETE | **未完成** |
| AC15：真实许可与桥接 | 原文件未变、无真实调用 | NO_GO不变 |

上述 counts 顺序为 tests/failures/errors/skipped，安全 JUnit 和 failure.json 中 skip1 没有被擦除。
CLI 退出码由真实 `python -m scripts.a42331_ci_evidence collect` 子进程取得，不只根据 Python 返回值推测。

另外运行实际 pytest 插件路径：在自有临时 Python 包中生成同一精确身份、执行一次 unittest.skipTest，
显式同时加载 `scripts.source_contract_pytest` 和 `scripts.a42331_pytest_safety`。
子 pytest 为 **1 skipped / exit0**，随后 XML 已是上述安全码，原始理由已消失，现有插件回执没有 Skip 证明。
该合成包不加载仓库业务 conftest，使用 `--noconftest` 仅隔离自有 fixture；两个安全插件均明确保留。
没有更改仓库 pytest 参数、收集范围或 Linux lab 测试。

RED 总探针的最后断言要求批准 Skip 被接受，实际以
`EXPECTED_APPROVED_SKIP_ACCEPTANCE_RED`、exit1 退出，完整输出和回执已保留。
首次子探针因在仓库外无法取得 Git HEAD 而退出；第二次仅给子进程显式绑定真实仓库 Git 目录，
不创建 Git 仓库或新分支，随后完成上述复现。第一次失败证据未删除。

可复核命令（绝对解释器、argv、cwd 和实际环境值仅在仓库外私有元数据中保存）：

```text
python -B <EVIDENCE_DIR>/probe.py
# RED: exit1；包含实际collect、相同安全字节证明和实际插件子进程

python -B -m scripts.a42331_ci_evidence collect
# 分别在五份自有fixture目录运行；exit0/1/1/1/1

python -B -m pytest -p scripts.source_contract_pytest -p scripts.a42331_pytest_safety
  --noconftest --tb=no --show-capture=no -rN -q <synthetic_fixture> --junitxml=<private_target>
# 1 skipped、exit0；不是通过了真实Linux实验
```

本轮解释器为既有仓库外 CPython3.12.0 venv、pytest9.1.1；没有安装或修改依赖。
完整 AC05～AC12、新旧 A42331 GREEN/R1 回归、修复后完整 CI **NOT_RUN**：因触及任务书停点而停止实施，
不把基线控制验证或历史6539 passed冒充新修复 GREEN。

## 5. 任务书停点与具体接续建议

本轮按任务书第2.1节的明确要求停止扩展：

> 如确需修改 scripts/a42331_pytest_safety.py 或其它文件，先停止并在交付回执中提出独立论证，不能自行扩展范围。

同时遵守第3.4节和 AC13：缺少可信原始理由证明时继续拒绝，不能因为脱敏结果看起来一致而放行。
本报告没有把“可以修改 collector 文件”解释成可以未经审阅建立新的签发/信任机制。

需要独立审阅的最小接线范围如下，**尚未实施**：

1. 在首次原始 JUnit 被擦除前，做唯一固定三元组、声明/实际计数、重复节点及未知/额外 Skip 的严格判定。
   推荐审阅 `pytest_unconfigure()` 的最小调用接线，把原始检查放在 `sanitize_junit()` 之前；不改任何测试结果。
2. 判定只输出固定枚举/布尔和批准数量，不输出理由、异常、堆栈、路径、SQL、口令。
   跨进程证据至少绑定原始/安全 JUnit 摘要、可信计数、检查器版本、profile、精确 SHA/run/attempt。
3. 必须先裁决该回执的真实性、来源、生命周期和重放验证方式。
   **裸布尔、普通可伪造JSON或仅重新计算SHA都不能被当作原始理由证明。**
   若选择在现有 sanitizer 入口保存判定，也需要同样审阅该跨进程证明通道，不能只加“已批准”标签。
4. `collect()` 验证该证据链及当前安全字节；没有可信证明时拒绝。原始 Skip 计数始终保留。
   targeted 任意 Skip 继续拒绝；full failures/errors和未知/额外/重复 Skip继续拒绝。
5. 保持证据完整性与执行结果分离：失败可完整归档；未知 Skip 即使证据完整也不能 COMPLETE或exit0。
   完成全部 AC01～AC15及真实插件→收集器端到端回归后，才提交修复并验收精确SHA Main CI。

需要负责人授权的增量是上述原始判定与脱敏之间的最小接线及可信跨进程证明通道，
必要时允许修改 `scripts/a42331_pytest_safety.py`；不是授权修改 Workflow、实验许可、冻结文件或业务模块。
未获该接续裁决前，本轮不试做未经审阅的状态旁路，不推送一个会凭 ID 放行的补丁。

## 6. 文件范围、证据和 Git 交付

唯一新增：`docs/acceptance/P0_A42331_JUNIT_SKIP_POLICY_FIX_01.md`。
收集器、安全插件、原有测试、Workflow、依赖、治理、W04-A/R1原件均保持开发起点原字节。
原有1551文件 SHA256保护、git diff --check、文档新增空白检查和暂存区检查在提交前执行。
本报告的正常 master 提交推送由负责人当前请求授权；**报告交付不等于修复交付或任务完成**。

仓库外证据索引：

- baseline.json：1551原件原始SHA256和基线。
- ci-provenance.json：Main Run/Job/Step、两个安全工件ID和digest。
- safe-ci.zip、safe-errors.zip、artifact-summary.json：既有安全工件及独立计数/跳过身份核验。
- ci-safe-log-extract.txt：仅保留测试统计和固定安全错误行，未归档含环境/SQL的整份原始Job日志。
- probe.py、probe-console.log、probe-attempt02-console.log：旧逻辑RED及首轮Git定位失败。
- attempt02/baseline-probe.json：同一安全字节证明、实际插件命令/退出码/计数。
- attempt02/real-plugin.stdout.log、real-plugin.stderr.log：自有子pytest的完整输出。
- cli-probe.json：五种输入的真实CLI命令/退出码/安全回执。
- delivery-verification.json、evidence-sha256.json：最终范围、静态检查和证据哈希。

最终提交SHA、4条自动push工作流的Run/attempt/head_sha/实时状态在交付对话及仓库外回执追加，
不为追填文档自身SHA反复提交。报告推送的CI无论何种结果都不能替代尚未实施的修复验收。
若仅走文档路由，更不能称“修复后的全量Main CI通过”。

## 7. 交付裁决

```text
TASK=P0_A42331_JUNIT_SKIP_POLICY_FIX_01
BASE_SHA=31d701f1437aa179df85a8e8f37de15581b705fa
BASELINE_MAIN_CI=FAILURE
ROOT_CAUSE=skipped==0 rejects the reviewed skip; original reason is erased before collect
RED=CONFIRMED (approved skip rejected; collector CLI exit1)
RAW_REASON_PROOF_AT_COLLECT=MISSING
SAFE_XML_APPROVED_VS_UNAPPROVED=BYTE_IDENTICAL
COLLECTOR_IMPLEMENTATION=NOT_CHANGED
PLUGIN_IMPLEMENTATION=NOT_CHANGED
AC02_AC14=NOT_COMPLETE
GREEN=NOT_RUN
NEW_FULL_FIX_CI=NOT_RUN
INDEPENDENT_REVIEW_RECOMMENDATION=BLOCKED / SCOPE_REVIEW_REQUIRED
REAL_PG17_CONNECTIONS=0
REAL_WORKER_ROOTS=0
REAL_OFF_ON_PAIRS=0
MANUAL_RERUN_DISPATCH=0
R1=PARTIAL
HISTORICAL_AC05=PARTIAL
REAL_PG17_WORKER_OFF_ON=NO_GO
PERFORMANCE_ACCEPTANCE=NOT_MEASURED
```

本次停止于原始 Skip 证明链的范围审阅，不关闭任务，不进入真实 readiness、OFF/ON或性能阶段。

## 8. 获批后的最小接线与可信回执交付

### 8.1 接续授权和源码范围

负责人对第5节接续问题明确答复“批准最小接线和可信回执”。本次据此修改安全插件的
原始判定调用接线并实现可信回执；沿用“开发，推送代码”的授权，只正常提交推送 master。
未创建分支，未手工 dispatch/rerun，未改变任何 Workflow、依赖锁、冻结文件或业务实现。

任务观察基线仍为 `31d701f1437aa179df85a8e8f37de15581b705fa`。
批准后开发起点 HEAD / origin/master / 实时 GitHub master 均为
`35143411e696549d5aba02a8dc0658b69675cfbf`，它仅在 BASE_SHA 上增加第1～7节停点报告。
该版本 Main Run 42734748470 当时仍 in_progress，另外三条 push 工作流 success；均不能代替新修复 CI。

实际交付严格限于五个文件：

| 文件 | 实际变更 |
| --- | --- |
| scripts/a42331_ci_evidence.py | 固定 Skip 原始判定、私有认证回执、计数/策略/执行结果分离及安全导出 |
| scripts/a42331_pytest_safety.py | 仅替换导入与 unconfigure 的 sanitizer 调用，保持其余钩子和测试结果处理 |
| tests/unit/test_a42331_ci_evidence.py | 增加原始正负例、CLI 退出码、认证/重放/隐私回归 |
| tests/unit/test_a42331_failure_evidence_regression.py | 增加实际插件→实际 collector CLI 子进程验证 |
| 本报告 | 保留首次停点历史，追加获批实现、测试与剩余门禁 |

既有测试的断言、30秒子进程超时和安全插件保持；原有 child subprocess 仅增加 stdin=DEVNULL，
避免继承交互式输入。未删除或跳过原测试，未修改 R1 原件中的身份、哈希、许可和 NO_GO。
开发起点1552个跟踪文件中，除上述5项外1547项逐个比较原始 SHA256，全部不变。
最终 diff/numstat、五文件大小和 SHA256 在仓库外交付回执记录，避免文档自身哈希递归。

### 8.2 现在的原始判定与信任边界

固定白名单仍只有第2节的唯一三元组，使用原始 message 属性逐字比较，不 trim、不规范化、
不依赖已脱敏身份推断原始理由。唯一获批 ID 在完整输入中只能出现一次，包括同名成功节点；
不禁止 pytest 原生 unittest 非跳过子报告正常重复 ID。所有 targeted Skip 均拒绝。

插件在脱敏前调用 sanitize_junit_for_pytest。对固定 CI JUnit 源路径，先核对声明/实际计数，
再作原始策略判定，然后保留节点/计数并擦除理由。XML DTD/ENTITY、NUL/UTF16实体绕过、
非法结构、空报告、超50MB、非普通文件均拒绝。安全 XML 通过同目录临时文件 fsync/replace 原子替换；
字节已经规范化时不重写，重复导出保持摘要和文件实例身份。
未知 Skip 的 classname/name 即使形似合法标识符也摘要化，只有固定公开批准 ID 可原样保留。

认证回执采用标准库 HMAC-SHA256，绑定：检查器版本、源码 HEAD、run/attempt、仓库路径摘要、
固定 JUnit 源路径、原始和安全字节 SHA256、真实计数、策略判定/批准数量，以及安全文件的
设备/文件号/ctime/mtime/大小。最后一组绑定防止新错误输入脱敏成相同字节且签发失败时复用旧 PASS。
回执同样记录认证的 REJECT，区分“可信拒绝”和“回执缺失/无效”。

密钥和认证回执放在 runner 用户的系统临时目录，位于仓库和工件上传目录之外；不写进安全 JUnit、
failure.json 或公开日志。POSIX 目录0700、文件0600且验证 owner；Windows 密钥用当前用户 DPAPI
加密，二进制文件用 O_BINARY 读写。验证过程不创建或重建密钥；缺失、篡改、上下文改变、
安全字节/文件实例改变均 fail closed。安全 XML 没有可验证回执时仍拒绝，不能单凭 ID 放行。

信任边界为同一可信 runner OS 用户和经审阅的插件代码；不声称抵御掌握该用户权限/密钥或 root
的恶意代码。此通道只证明本次 CI 脱敏前的判定，不签发 Linux 实验许可，不跨 runner/新 run 重放。
原始含私密理由的 XML 不作为工件归档，私有密钥也不归档。

failure.json 新增固定字段 skip_policy_status、approved_skip_count、skip_policy_version 和
full_skip_proof_source。原有 qualification 字段始终 false。证据完整、策略通过和上游成功分别判断：
未知 Skip 可完整归档，但 INCOMPLETE 且 CLI exit1；上游真实失败可完整归档、保持失败计数与
INCOMPLETE，CLI沿用归档成功exit0，不伪装上游成功；五阶段success且零Skip或唯一获批Skip才可COMPLETE。

### 8.3 RED、GREEN 和 AC01～AC15

旧实现的真实 collect/CLI RED 保留于第3～4节。
批准后先运行新增原始批准 Skip 回归：1 failed、exit1（red.xml）；随后实现修复。
又以形似合法标识符的私密 Skip 名称复现2 failed、exit1，再完成对应脱敏修复，2 passed、exit0。
两个 RED 均保留安全插件，没有泄漏原始异常、密码或 SQL。

| AC | 断言及当前结果 |
| --- | --- |
| 01 | 既有零Skip全成功用例：COMPLETE，计数保留 |
| 02、14 | 精确原始三元组+五阶段success：COMPLETE、approved=1、skipped=1，CLI exit0 |
| 03、04 | 未知ID、错误/缺失/尾随空格理由：REJECT、CLI exit1 |
| 05、06 | 第二个Skip、重复批准Skip及同ID成功节点：REJECT、CLI exit1 |
| 07 | full_tests=success而实际failure/error：INCOMPLETE、计数保留、CLI exit1 |
| 08、09 | 计数不符、缺失、坏XML、DTD/ENTITY、UTF16实体、超限：固定失败回执、CLI exit1 |
| 10 | targeted任意Skip：REJECT、CLI exit1 |
| 11 | 既有失败归档和实际子pytest失败验证保留；不误报COMPLETE |
| 12 | 注入敏感理由/名称/属性/SQL：安全输出无哨兵明文；名称新增2项RED→GREEN |
| 13 | 脱敏后无证明拒绝；认证MAC/载荷篡改、缺失、SHA/run/attempt重放及安全字节变更拒绝 |
| 15 | AST核对REVIEWED_LAB_PERMIT=None；真实bridge仍抛R1_REAL_EXECUTION_NOT_AUTHORIZED |

实际子进程端到端测试使用自有无数据库 synthetic package，在原生 unittest skip 后运行两项安全插件，
再独立运行 collector CLI。批准理由：子pytest1 skipped/exit0，collectorCOMPLETE/exit0；
错误私密理由：子pytest仍1 skipped/exit0，collectorREJECT/exit1。两者安全XML均保留skipped=1，
并验证 proof_source=AUTHENTICATED_PRIOR_SANITIZER；证明没有靠修改 pytest 结果制造成功。

最终本地命令以既有隔离venv运行，原始完整参数和退出码保存在仓库外 command-results.json。
下列 $PY/$EVIDENCE 分别指该解释器和仓库外证据目录；未将本机路径写入源码或任务合同：

```powershell
& $PY -B -m pytest -p scripts.a42331_pytest_safety -p no:cacheprovider --tb=short --show-capture=no -rN -q tests/unit/test_a42331_ci_evidence.py tests/unit/test_a42331_failure_evidence_regression.py --basetemp="$EVIDENCE/final-release-temp" --junitxml="$EVIDENCE/final-release.xml"
& $PY -B -m pytest -p scripts.a42331_pytest_safety -p no:cacheprovider --tb=short --show-capture=no -rN -q tests/unit/test_perf03_lnx_w04a_offline_contract.py tests/unit/test_w04a_line_ending_integrity.py tests/unit/test_r1_*.py --basetemp="$EVIDENCE/final-r1-temp" --junitxml="$EVIDENCE/final-r1.xml"
& $PY -B -m ruff check backend tests migrations scripts
# py_compile.compile(..., cfile=<external evidence>, doraise=True): four Python files
git diff --check
```

pytest默认source_contract_pytest保持，显式a42331_pytest_safety保持；仅禁用缓存插件避免缓存产物。
R1命令中的通配在实际执行前由PowerShell展开为14份具体模块，包括W04-A、字节完整性和12份R1模块。
本机未运行需要数据库的全量 pytest，完整数据库集成只验收正常push自动CI，不使用本机用户数据库。

本机环境：CPython3.12.0、pytest9.1.1、pluggy1.7.0、pytest-cov7.1.0、Ruff0.16.4。
按既有requirements.lock仅在该仓库外venv补装PyYAML6.0.2，锁文件/项目依赖和全局环境均未修改。
首轮子pytest出现原30秒超时/中止的日志保留；同盘外部basetemp与stdin=DEVNULL后通过，未加长超时。
Windows回执诊断还发现O_BINARY缺失会损坏随机DPAPI字节，已修复；不将失败前置验证当作有效证明。

R1离线回归：**195 passed、1815 subtests passed、5 warnings，exit0，236.50s**。
5条既有record_property/xunit2兼容警告不改变测试结果。
最终A42331回归：**64 passed，exit0，50.74s**，包括各AC拒绝路径的CLI exit1断言及AC01/11 exit0断言。
全仓Ruff、4份Python外部py_compile、git diff --check均exit0。
JUnit真实节点数/摘要、编译与完整性结果见仓库外 delivery-verification.json / command-results.json。
仅本次5份允许文件统一为既有Git Blob的LF形式；未转换任何冻结原件。

### 8.4 Git、CI及独立审阅门禁

提交前核对完整diff、白空格、文件范围、1552份起点哈希及4份Python编译；只暂存上述5份文件。
完整提交SHA、HEAD/origin/master实时比对、4条自动push工作流Run/attempt/head_sha/status/conclusion
保存到仓库外 git-ci-delivery.json 并在交付对话提供，不为写入自身SHA反复制造CI。

**当前建议：REVIEW_PENDING；最终完整 Main CI 未完成前保持 CI_PENDING，不能宣称任务关闭或修复验收完成。**
若新CI出现失败、必需Job跳过、工件缺失/污染，将保留实际证据并报告，不越界修改Workflow或业务。
Windows本机测试不代表Linux完整CI，更不代表真实Linux实验资格。

```text
TASK=P0_A42331_JUNIT_SKIP_POLICY_FIX_01
APPROVED_EXTENSION=MINIMAL_PLUGIN_WIRING_AND_AUTHENTICATED_RECEIPT
R1=PARTIAL
HISTORICAL_AC05=PARTIAL
REAL_PG17_WORKER_OFF_ON=NO_GO
PERFORMANCE_ACCEPTANCE=NOT_MEASURED
REAL_PG17_CONNECTIONS=0
REAL_WORKER_ROOTS=0
REAL_OFF_ON_PAIRS=0
MANUAL_RERUN_DISPATCH=0
FINAL_NEW_SHA_MAIN_CI=PENDING
INDEPENDENT_REVIEW=PENDING
```
