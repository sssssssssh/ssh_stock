# BIZ-PERF-FACTOR-RECOVERY-03-R3：版本化业务来源、保留当前覆盖并修复Worker

2026-11-16。上一轮R2 closeout为PHASE1_CLASSIFICATION_BLOCKED；已确认12个R1失败节点不全是纯历史测试。不能将12项全部历史化后宣称当前行为仍被验证。目标是实际修复心跳线程join缺陷，而非再写W05审计。

基线master=origin/master=232baf9e13cd7b23731e59188c86e0e253c3a394。首先核对AGENTS、R2 closeout、全部既有未跟踪文件及所有Git改动。保留原件，发现未知并发写入立即停下。R2新增测试tests/unit/test_source_contract_r1_history.py是本轮既有输入，不得删除以隐藏阻断。

## 允许新增的精确修改范围（R2白名单扩展）
- scripts/r1_integration_evidence.py：显式分离旧v1历史来源与新的当前来源；无自动fallback
- docs/acceptance/r1_current_business_sources_v2.json：新增当前来源完整SHA256，明确离线验证、不授权执行
- scripts/r1_integration_controller.py：仅必要的显式当前来源选择调用点
- scripts/r1_integration_seed_loader.py：仅必要的显式当前来源选择调用点
- scripts/source_contract_governance.py
- scripts/source_contract_history.py
- scripts/source_contract_pytest.py
- tests/unit/test_source_contract_r1_history.py
- tests/unit/test_r1_integration_controller.py：仅在需要当前行为等价覆盖时增补测试，原断言不可删/降
- tests/unit/test_r1_integration_seed_loader.py：同上
- backend/app/services/job_worker.py
- tests/unit/test_job_worker.py
- docs/acceptance/BIZ_PERF_FACTOR_RECOVERY03_R3_CLOSEOUT.md（新）
若还需修改其他源文件（特别是scripts/r1_integration_evidence.py的上游hash冻结链），先给出精确引用位置与影响，不越界修改。
不得修改旧schema/hash、r1_business_snapshot_contract.py、r1_integration_evidence旧版本定义语义、原A42366固定commit/tree、旧安全插件、CI、依赖、原历史测试断言或任何Raw/Derived。

## 优先级A：合同分离，避免再次被旧固定SHA阻断
1. 阅读R2报告指出的Controller和FrozenSeed当前行为。对12节点逐个分类：历史固定字节验证与当前语义行为测试。历史路由只允许真正历史性质节点；当前行为必须在当前工作树原生正反例验证，不能用历史checkout通过代替。
2. 旧schema r1_business_compare_schema_v1.json及其SHA/旧v1入口行为严格不变。新当前来源v2明确版本、固定基线、全量文件SHA、禁止执行用途。未知版本、错误摘要、符号链接、缺失文件一律拒绝。避免v2自身摘要递归、CRLF误报。新来源必须验证Worker当前字节，不能仅从Git HEAD推断。
3. 当前controller/seed在必要时显式使用v2，不可在hash失败时自动切换。旧v1入口与旧测试依然验证旧schema；当前新行为验证不能patch verify_business_sources=True。检查所有引用和冻结链；发现更深层无法在白名单内解决，报告准确阻断而不是继续造框架。
4. 如有必要只为纯历史节点新增固定232baf9/tree d21c4a1d870c68177175ebee276b7c1f350345f7历史路由，原A42366保持完全不变。unittest.TestCase须收集阶段路由，父进程不能先执行setup；子进程全套setup/body/teardown；严格JUnit节点计数，拒绝skip/error/failure、未知node/version/path。不得用历史路由掩盖当前controller/seed行为。
5. 优先解决最少必要节点，不要求一开始迁移12个节点；一旦可以安全修改Worker并保持当前语义回归，就直接推进B，不再无限扩通用审计。

## 优先级B：Worker最小真实修复
当前源码心跳Thread.start失败后finally对未启动Thread.join抛RuntimeError，可能中断轮询。只对确实成功start的线程join；正常已启动线程保持原timeout join；正常join异常不吞。保留原始失败记录、owner/token、claim、取消/失权、CAS、发布、清理、事务与fail-closed语义。
原生pytest RED/GREEN（不得AST模拟替代）覆盖start失败不join、失败记录、正常join、join异常传播、ContextVar/db.info清理、失败后下一任务可继续、取消失权和发布不变；不启动真实Worker。

## 验收
先复核新旧合同当前/历史隔离正负例及R2当前Controller反例，再跑Worker原生测试。完整可运行回归、ruff、diff check、冻结源字节映射，缺依赖明确ENV_BLOCKED不安装不绕过。禁止真实PG17、真实Worker/SQL/迁移/Raw重拉、正式性能或云资源。B_GATE/TARGETED_PG17_GATE=NOT_APPROVED。
closeout记录精确diff、每个节点归属、当前行为等价覆盖、原生Worker RED/GREEN、测试命令退出码、未解决阻断、真实执行NOT_RUN。
**本轮只实现和测试，不提交不推送**；完成交由ChatGPT独立审阅。遇到超出白名单或安全边界立即停止，不把仅29项分类测试当作Worker修复成功。
