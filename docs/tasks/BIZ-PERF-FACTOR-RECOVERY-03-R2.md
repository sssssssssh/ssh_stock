# BIZ-PERF-FACTOR-RECOVERY-03-R2：R1历史合同并行路由 + Worker心跳清理修复

日期：2026-11-16。
用户唯一中心目标：恢复 ssh_stock 正常因子计算，解决 Worker 可靠性和真实性能瓶颈。
原基线：master=origin/master=232baf9e13cd7b23731e59188c86e0e253c3a394。
原任务03-R1已因任务白名单过窄而停止；本任务由用户持续推进授权，明确扩展实施白名单。

## 目标与原则
本轮一次性打通历史合同阻断，并完成心跳线程启动失败后的最小Worker修复。
不修改旧合同以迁就新代码。建立并行、显式、不可互相回退的新R1历史合同路由；旧A42366路由原样保留。历史测试只能证明历史源码，不得替代当前Worker测试。
完成当前源码RED/GREEN后，等待ChatGPT独立审阅，不提交不推送。

## 先决条件
1. 重新核验HEAD、origin/master、status；保留所有既有未跟踪文件及原件。未知用户改动立即停止。
2. 读取AGENTS、治理文件、业务规则及03/03-R1报告。确认本任务白名单覆盖本次合同迁移的必要范围。
3. 历史R1路由拟绑定：
   commit=232baf9e13cd7b23731e59188c86e0e253c3a394
   tree=d21c4a1d870c68177175ebee276b7c1f350345f7
   开始前通过本地git对象再次验证二者存在且commit的tree精确匹配；不得fetch网络。
4. 旧A42366路由当前绑定的SHA、Tree、73项测试、单节点、模块集合、旧schema及断言全部保持原值。

## A. 新增独立R1历史合同路由
只迁移报告列明的12个精确历史节点，不允许目录/class通配：
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

必须先逐项审阅这些节点究竟验证历史源码还是当前业务语义。尤其controller组合适配器节点：若迁移到历史子进程会失去当前语义覆盖，则增加当前版本等价测试；不得为了让它通过而patch掉verify_business_sources、放宽源码验证或伪造seed oracle。

实现要求：
1. 在scripts/source_contract_governance.py增加独立R1历史版本标识、固定commit/tree、精确节点和精确模块登记。不得改旧HISTORICAL常量/集合/旧A42366绑定。
2. 在scripts/source_contract_history.py增加显式版本分派；原run默认A42366路径行为保持完全不变。R1路由只接受已登记版本、SHA、Tree、精确nodeid；检查原始测试文件在R1历史commit中的Git对象与当前工作树字节一致；拒绝未知版本/节点/路径。
3. R1子进程必须使用本地shared clone、detached checkout、core.autocrlf=false；验证HEAD及Tree；不fetch、不访问网络；不复制.env；剔除PG*、DATABASE_URL、TEST_DATABASE_URL、PYTEST_PLUGINS、PYTEST_ADDOPTS等数据库/pytest注入环境；禁止真实数据库连接。
4. R1子进程只执行精确nodeid，完整运行pytest/unittest的setUpClass、setUp、测试体、tearDown及原始断言。JUnit必须严格校验预期节点数量、唯一性、exit=0、failures=0、errors=0、skipped=0；缺XML/重复/缺失/多余节点均失败。
5. scripts/source_contract_pytest.py目前只使用pytest_pyfunc_call，无法截获unittest.TestCaseFunction。为R1精确节点增加收集阶段专用历史Item/等效的安全路由，必须在父进程执行unittest setup之前替换/拦截；不能在call阶段临时劫持后声称fixture没有运行。原pytest函数节点A42366路由必须保持原行为。
6. tests/unit/test_source_contract_r1_history.py新增正负例：双SHA/tree、12节点精确路由、未知node/path/version拒绝、原件篡改拒绝、父进程不执行unittest setup、子进程setup/teardown各一次、失败/error/skip/缺XML/重复/多余计数拒绝、环境变量清理、无网络/无DB、旧A42366常量/路由完全不变、新R1版本绝无执行授权。
7. 新R1历史版本只允许HISTORICAL_TEST_ONLY用途；require_purpose及相关负例必须证明DEVELOPMENT/A42366/R1-HISTORY都不能授权G1、CAPACITY、RECOVERY、PERFORMANCE、PRODUCTION_READ或真实执行。
8. 不修改docs/acceptance/r1_business_compare_schema_v1.json、其SCHEMA_SHA256、scripts/r1_business_snapshot_contract.py、scripts/r1_integration_evidence.py及原12个测试源码。它们作为被验证的历史原件保留。

## B. 当前Worker原生最小修复
仅在A的路由和保护测试可运行后，修改backend/app/services/job_worker.py及tests/unit/test_job_worker.py。
目标：execute_claimed_job中Thread.start失败后，finally不对从未成功启动的心跳线程调用join，避免二次RuntimeError掩盖原始故障并令Worker轮询退出。
要求：
- 仅跳过未成功启动线程的join；正常已启动线程（即使已自然结束）仍按原timeout join。
- 不允许try/except RuntimeError整体吞join异常；正常join异常仍按原策略传播。
- 不改owner/token、claim、失败持久化CAS、取消/失权、候选发布、事务边界、未知Writer保护或自动重放策略。
- 原生RED/GREEN测试至少覆盖：start拒绝且join未调用；原始异常/FAILED记录语义保持；正常start仍join且传原timeout；正常join异常不被吞；失败记录自身失败保持fail-closed；ContextVar/db.info/policy/observer/workspace清理；取消/失权不变；无候选写入/发布；单次可确认失败处理后Worker仍可继续轮询且不重放旧root。
- 不可用AST抽取模拟替代原生模块测试。真实Thread.start不得启动生产Worker；使用受控fake/monkeypatch。

## 精确修改白名单
允许修改：
1. scripts/source_contract_governance.py
2. scripts/source_contract_history.py
3. scripts/source_contract_pytest.py
4. tests/unit/test_source_contract_r1_history.py（新建）
5. backend/app/services/job_worker.py
6. tests/unit/test_job_worker.py
7. tests/unit/test_r1_integration_controller.py（仅当必须保留controller当前等价语义覆盖；否则不改）
8. docs/acceptance/BIZ_PERF_FACTOR_RECOVERY03_R2_CLOSEOUT.md（新建）
本任务书由外层创建，Codex不得修改。其他文件一律不改。旧schema/manifest、旧测试、CI、安全插件、依赖、策略及冻结五件不得修改。

## 验证
- 先测试A42366旧路由原有负例和正例，证明旧SHA/tree/73测试与单节点完全不变。
- 再测试R1新路由12节点在232baf9历史checkout通过，且当前Worker测试明确不在历史节点集合中。
- 再测试当前Worker原生RED/GREEN与现有取消、失权、候选发布回归。
- Ruff、git diff --check、完整白名单、所有冻结文件字节映射核对。
- 本机缺依赖可标ENV_BLOCKED，不安装依赖、不修改测试来绕过；尽可能用GitHub CI在新SHA验证，但提交推送须等ChatGPT审阅。
- 不运行真实PG17、Worker服务、SQL、迁移、Raw重拉、生产DB或正式性能实验。

## 交付与停止条件
生成docs/acceptance/BIZ_PERF_FACTOR_RECOVERY03_R2_CLOSEOUT.md，包含合同路由图、旧合同不变证据、新R1历史执行证据、12节点分类、controller当前覆盖说明、Worker RED/GREEN、精确diff、测试结果、冻结文件检查、未完成项及下一步。
若pytest自定义Item无法可靠保留报告语义/父子进程隔离，或controller当前覆盖无法保留，停止Worker修改并报告精确阻断；不得降低测试、伪造历史结果或扩大文件白名单。
不提交、不推送、不触碰生产数据。完成后向原GP会话回执BASELINE_SHA、CHANGED_FILES、OLD_A42366_UNCHANGED、R1_HISTORY_12_NODE_RESULT、WORKER_RED_GREEN、TESTS、ENV_BLOCKED、REAL_FACTOR_RUN=NOT_RUN、DB_STATUS=UNTOUCHED、NEXT=CHATGPT_REVIEW。
