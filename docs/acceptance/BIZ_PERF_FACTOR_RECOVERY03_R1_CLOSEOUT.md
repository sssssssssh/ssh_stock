# BIZ-PERF-FACTOR-RECOVERY-03-R1 closeout

日期：2026-11-16。
BASELINE_SHA=232baf9e13cd7b23731e59188c86e0e253c3a394。
STATUS=BLOCKED_BY_CONTRACT_MIGRATION_SCOPE / REVIEW_PENDING。
WORKER_FIXED=false；GREEN_FOR_WORKER_FIX=NOT_IMPLEMENTED。
CHANGED_FILES=本报告；REAL_FACTOR_RUN=NOT_RUN；NEXT=CHATGPT_REVIEW。
未暂存、未提交、未推送；旧固定hash合同与所有现有源码/测试不变。

## 基线、授权与停止位置

master，HEAD=origin/master=已认证GitHub master，均为上述完整SHA。
开始未跟踪文件为03任务书/closeout、W05两资产及本次R1任务书，无未知修改。
读取AGENTS、治理/业务边界及前轮交付，沿用原持久会话同字节治理文件。
本次任务书第2项明确：
“需要合同迁移超出白名单则停止代码修改，报告阻断和精确所需文件。”
本轮已找到可复用机制，但它不能原样适配R1，至少需修改三个白名单外的scripts文件。
因此在修改Worker和测试之前停止；没有再制造一次“代码已改、CI必红”的候选。

本轮没有新建一个已知必RED的当前Worker测试文件来破坏CI，
也没有用AST诊断替代任务要求的原生Worker单测GREEN。
任务允许在此条件下只交付具体迁移方案，本报告使用这一停止分支。

## 固定hash位置与消费者闭包

旧合同：
docs/acceptance/r1_business_compare_schema_v1.json，sources字段的
backend/app/services/job_worker.py.sha256=
91069dd58733e442831977f58ee1c37616d1ef37a271d7845856421251d6e7da，
git_blob_sha=48e6706d1178d566eeb7a9a05317005d018e9390；
同时登记worker_identity、claim_next_job、execute_claimed_job等13个函数位置/签名。
当前Worker LF摘要仍精确匹配；即使只加join保护，也会破坏整文件SHA相等。

scripts/r1_business_snapshot_contract.py:18引用schema，
:20 SCHEMA_SHA256=f6be0a5de1ce46e30758039a3ab345a308ff96cb36f6ee86ec3ccdc39759f297；
load_schema（110起）先校验schema原字节，再解析37表/520列。
只改旧schema内worker摘要也会破坏schema自身摘要，且违反本任务明确禁令。

实际运行时消费者：

| 文件 | 使用位置/作用 |
|---|---|
| scripts/r1_business_snapshot_contract.py | load_schema及compare_snapshots；加载固定定义，不自动证明当前源码合格 |
| scripts/r1_integration_evidence.py:82–96 | verify_business_sources：遍历sources，规范化工作树CRLF为LF，逐项SHA比较；不匹配INTEGRATION_BUSINESS_DRIFT |
| scripts/r1_integration_seed_loader.py:73、93–94、203 | entity_digest、original_fixture_oracle、generate_original_input；oracle先验证当前业务源码 |
| scripts/r1_integration_controller.py:75 | fake组合preflight也调用verify_business_sources |
| scripts/r1_integration_pg_export.py:54、294 | 通过schema读取列/表与合成导出定义 |
| scripts/r1_seed_snapshot_recipe.py:52、118、223 | 按schema构造/验证固定输入与快照 |
| scripts/r1_d04_decision_review.py:18 | 固定SCHEMA_REF及独立冻结摘要/字段投影；不是当前worker文件直接校验器 |

测试消费者：
- tests/unit/test_r1_real_root_protocol.py：sources()、baseline断言、
  AC31直接遍历sources读取工作树并比较摘要。
- tests/unit/test_r1_integration_seed_loader.py：10个方法间接经过oracle。
- tests/unit/test_r1_integration_controller.py：fake组合测试经过seed/preflight。
- tests/unit/test_r1_integration_pg_export.py：通过export模块schema。
- tests/unit/test_r1_business_snapshot_contract.py：通过模块别名c加载schema。
- tests/unit/test_r1_seed_snapshot_recipe.py：load_schema与SCHEMA_SHA256。
- tests/unit/test_r1_d04_decision_review.py：schema固定路径/内容投影。
- tests/unit/test_r1_reviewed_snapshot_v2.py：schema及相关R1模块原字节冻结列表。
其余间接调用沿以上模块传播；只读扫描了scripts、backend和tests的Python引用，
未发现另一个直接schema文件名或load_schema/verify_business_sources导入入口。
文档中的引用不当作执行入口。

02的CI失败原因亦由此得到解释：c690b50的publication优化将旧期望LF摘要
39d95b00afed3da308aa78a00917fad2308f9d19266cfa30268b145bd35e7e88
改为2c42b2bb750ccb73304ea22180cdefeeb8dc47715970610adc361453bbdee6e8，
触发10个seed、1个controller、1个AC31，共12项拒绝。
232baf9已恢复publication原字节；本轮不重做或重启该优化。
这类拒绝不是随机时序失败，也不证明新生产语义一定错误。

## 已有历史checkout能力与不能直接复用的原因

已完整读取：
scripts/source_contract_governance.py、source_contract_history.py、
source_contract_pytest.py、tests/unit/test_source_contract_governance.py，
及source_contract_governance_20261030.md。

现有机制提供的可复用保护：
- 显式版本、完整commit/tree双绑定，未知版本/用途拒绝；
- 当前committed与物理测试字节必须等于历史原件；
- 新建本地shared clone、detached checkout、core.autocrlf=false，无远端fetch；
- 不复制.env，清除PG/DB环境；子进程XML严格检查数量、唯一性、失败/错误/跳过；
- JUnit属性与终端公开历史SHA，不授予当前性能或执行权限。

但直接加12个节点不可行：

1. A42366路由固定为2779a2a7a7120c86f67b4991bce196c652b5ebb0，
   tree=27d9e7a9b384c063f0e7b4e5364d35b1761e6121。
   git cat-file已证明该checkout没有test_r1_integration_seed_loader.py。
2. HISTORICAL_MODULES只有7个A42366旧模块，HISTORICAL_NODES只有1个精确节点；
   verify_test_sources会拒绝R1文件，不能用目录通配或现有默认值蒙混。
3. history.run始终执行A42366验证器并预期73或1个测试，
   不能把其版本/校验器/总数静默替换成R1。
4. 更关键：source_contract_pytest仅使用pytest_pyfunc_call。
   这12个R1节点都是unittest.TestCase方法；本机pytest的
   _pytest.unittest.TestCaseFunction.runtest直接调用self._testcase(result=self)，
   不经过pytest_pyfunc_call。
   所以仅扩名单并不能真正路由这些测试。
   临时在call阶段劫持也可能已经执行当前setUpClass/fixture，不能视为完整历史执行。

## 最小可审阅迁移方案：尚未实施

建议只为本次受影响的固定R1合同增加独立版本条目，
参照已验证匹配旧sources的232baf9，而不改任何旧schema/hash。
拟绑定：
commit=232baf9e13cd7b23731e59188c86e0e253c3a394；
tree=d21c4a1d870c68177175ebee276b7c1f350345f7。
这不是把旧schema的target_sha（b6ffb7bf…）改成232baf9；
两者分别是业务定义身份与具备相应原始测试的历史执行语境。
提交/tree对象本机均已只读确认存在，不需要fetch或修改当前.git。

精确文件范围如下（均待新的独立授权）：

| 文件 | 必要改动 |
|---|---|
| scripts/source_contract_governance.py | 新增独立R1版本/commit/tree/精确节点登记；旧A42366常量及集合保持原值；拒绝未知版本与跨用途 |
| scripts/source_contract_history.py | 按显式注册版本选择允许的SHA/tree、测试文件、校验器和预期数量；复用隔离clone/XML/字节保护，不调用错误的A42366校验器验证R1 |
| scripts/source_contract_pytest.py | 对获准的unittest节点在收集阶段替换为专用历史执行Item，使原setUpClass/fixture与断言完整在子进程执行；其余节点仍走原路径，旧pytest函数路由不变 |
| tests/unit/test_source_contract_r1_history.py（新） | 路由与unittest setup/teardown隔离、双SHA/tree、测试原件篡改、节点唯一性、失败/错误/skip/缺XML/计数、未知版本、无执行权限；证明当前Worker节点绝不迁移 |
| backend/app/services/job_worker.py | 兼容前置通过后才加精确未启动join保护；当前不得改 |
| tests/unit/test_job_worker.py | 原生Worker最小故障回归，覆盖下节；保持在当前源码执行 |
| 对应独立closeout | 明确历史/当前测试各自SHA和计数，不混入当前覆盖率/性能证明 |

前三个是当前白名单外文件；新增合同测试也超出“Worker及相关单测最多2文件”。
不能在当前任务中实现这些修改。
已有tests/unit/test_source_contract_governance.py的旧集合/断言无需放宽或改写；
应通过新独立版本测试补充保护。

拟审阅的12个精确节点，不允许目录/class通配自动纳入：
- tests/unit/test_r1_real_root_protocol.py::ProtocolTests::test_AC31_source_sha_and_every_new_utf8_file
- tests/unit/test_r1_integration_controller.py::ControllerTests::test_composed_real_adapters_fake_io_not_just_callback_labels
- tests/unit/test_r1_integration_seed_loader.py::SeedLoaderTests::test_AC07_generate_once_complete_original
- tests/unit/test_r1_integration_seed_loader.py::SeedLoaderTests::test_AC08_default_timestamps_frozen
- tests/unit/test_r1_integration_seed_loader.py::SeedLoaderTests::test_AC09_sequences_and_catalog_exact
- tests/unit/test_r1_integration_seed_loader.py::SeedLoaderTests::test_AC10_independent_dual_loads_and_entity_values
- tests/unit/test_r1_integration_seed_loader.py::SeedLoaderTests::test_AC11_source_tampering_partial_duplicate_theme_type
- tests/unit/test_r1_integration_seed_loader.py::SeedLoaderTests::test_AC12_no_plan_only_proof_or_live_loading
- tests/unit/test_r1_integration_seed_loader.py::SeedLoaderTests::test_all_frozen_timestamps_and_absent_nulls_have_explicit_origins
- tests/unit/test_r1_integration_seed_loader.py::SeedLoaderTests::test_capture_callback_once_row_order_and_catalog_index_tamper
- tests/unit/test_r1_integration_seed_loader.py::SeedLoaderTests::test_capture_does_not_trust_replaced_generator
- tests/unit/test_r1_integration_seed_loader.py::SeedLoaderTests::test_independent_oracle_catches_orm_default_not_generator_self_comparison

登记名单仍需逐节点证明历史归属，特别是controller的组合适配器行为：
若其中包含应在当前执行的业务语义，必须同时保留当前等价覆盖，
不能因为它依赖旧schema就整项转历史并宣称当前业务已经验证。
当前Worker start/join/取消/失权/发布测试必须始终在当前SHA原生执行。
如审阅认为无法作这种分离，应保持阻断，而不是扩大迁移名单。

## Worker修复本身的最小方向与原生测试矩阵

尚未修改；仅供后续具体审阅。
目标位置job_worker.py finally:464–465：
对尚未成功启动的线程不join；已启动（包括已结束但ident仍存在）的线程仍正常join。
可考虑已启动状态/ident检查；不能用try/except RuntimeError整体吞join异常。
不改owner/token、失败持久化CAS、候选发布、未知Writer或队列重放策略。
不通过外层通用异常自动重试掩盖失败/恢复权限。

原生test_job_worker至少覆盖：
1. Thread.start拒绝：保留最初故障处理，不产生未启动join二次异常；不进入业务计算。
2. 正常启动：仍join原线程、传原timeout；正常join抛异常时不得静默吞掉。
3. 故障记录自身失败：保持原异常/不确定执行保护，不能伪造FAILED或放行未知Writer。
4. ContextVar与db.info、policy/observer/workspace清理；取消/失权不改成功态。
5. 单次可确认失败处理完后轮询能继续；不能自动重放旧root，终态再派发无新增动作。
6. 无候选写入/发布；正常计算结果、身份及既有取消回归仍在当前源码验证。

本轮不具备原生Worker模块依赖，不能先声称上述矩阵已经GREEN。
最短路线是先裁决窄合同兼容范围，再补上述原生RED并实施一处join保护，
随后新SHA完整CI，最后在另行获准环境回到真实Worker因子复算/候选耗时；
不扩展W05或泛用审计框架。

## 本轮实测

1. 原03报告源码隔离RED再次运行，两次独立故障注入：
   start=1、join=1、rollback=1、failure_record=1，
   Job=FAILED、逃逸RuntimeError未启动join、上下文已重置；
   终态再派发无动作，外层RuntimeError继续外抛。
   真实Thread.start被覆盖，从未启动线程/Worker/数据库。
   这是条件性故障复现，不是现场卡死根因证明；Worker修复GREEN仍NOT_IMPLEMENTED。

2. 原生pytest的历史保护边界24项通过，退出0：
   exact route/path拒绝2项、子进程失败/计数/skip拒绝6项、
   CLI非法参数拒绝4项、非执行用途拒绝8项、未知版本拒绝4项。
   命令由下方脚本给出，使用原默认安全插件，不改断言。
   退出时pytest旧临时目录pytest-current清理出现WinError5 PermissionError；
   这是atexit警告，测试报告24 passed、进程退出0，未手工清理/越权访问目录。

3. 原12项R1 unittest方法执行12、failures0、errors0；
   使用前轮诊断脚本，只在进程内给schema提供Linux LF视图，工作树文件不变。
   该脚本仍打印历史标签“OFFLINE_RED 12 failures 0 errors 0”，
   按实际0失败统计为现有合同通过，不代表Worker新修复GREEN。
   没有运行旧checkout子进程或创建.git；历史路由迁移未实现。

4. 原生安全pytest针对test_job_worker、candidate_write、replace_slice、
   factor_service_cancellation：4个收集错误，缺fastapi/loguru，退出1，ENV_BLOCKED。
   禁读.env/禁网络/Engine.connect拒绝；不安装依赖、不删测试或放松断言。
5. Ruff尝试job_worker.py/test_job_worker.py：No module named ruff，ENV_BLOCKED。
6. git diff --check通过；没有业务/测试diff，未宣称全量pytest或新SHA CI通过。

24项保护边界复现（仓库根python -X utf8 -B -）：

```python
import os,sys
from pathlib import Path
import pytest
def guard(event,args):
    if event=="open" and isinstance(args[0],(str,bytes)):
        if Path(os.fsdecode(args[0])).name==".env": raise AssertionError("NO_ENV")
    if event in {"socket.connect","socket.bind","socket.getaddrinfo","subprocess.Popen","os.system"}:
        raise AssertionError("NO_EXTERNAL")
sys.addaudithook(guard)
nodes=[
"test_history_route_is_exact_and_not_a_directory_or_version_wildcard",
"test_unregistered_historical_test_paths_are_rejected_before_git",
"test_historical_subprocess_cannot_hide_failure_skip_or_missing_cases",
"test_history_cli_rejects_unknown_execution_arguments_before_any_git",
"test_static_and_history_versions_cannot_authorize_any_high_risk_purpose",
"test_unknown_versions_never_fall_back_to_current_or_history",
]
raise SystemExit(pytest.main(["tests/unit/test_source_contract_governance.py::"+n for n in nodes]
                            +["-q","-p","no:cacheprovider"]))
```

12项原R1与Worker RED复现脚本分别保留在前轮CI_FIX和03报告，
本轮按其原脚本执行，无需新增工具。

## 保全与结论

开始/最终1646个已跟踪文件原字节映射（排序JSON SHA256）保持：
702a421ae1366d401ccccd0df2c665ac0edb45f8978907cc66241b4650898a8e。
所以旧源码、测试、schema、manifest、安全插件、CI、依赖均原字节不变。
本轮仅新增本报告。

未跟踪原件SHA256：
- R1任务书：df9fb876927dc82467729bc1290a71fa5dccfb72616cd99844b51ced3a6776d8
- 03任务书：aae3179df7d44bd28ff6912d3f1f0132514c45b690b0c23123f7a3dd7d86343f
- 03报告：d9c034fa2aff97e965bd225b9c5f9457b9b8f66ca0c893ca0ebd5fbf2ee245e3
- W05任务书：6f9f68c7028729598a0f510358798f746e0e9318e6d6926a128daa298ef915aa
- W05审计：baca21feaa6edbad2e8471db65b80166b0b8d21595550f8c70ef00f63c27d750

B_GATE=NOT_APPROVED；TARGETED_PG17_GATE=NOT_APPROVED；ROOT_ATTEMPTS=0。
没有真实DB/Worker/SQL/迁移/Raw/云端/正式性能操作，没有提交推送。
真正修复=false；CI兼容迁移=未实施；下一步为独立审阅上述精确文件范围，
不是接受当前Worker bug或把未实现内容标为通过。
