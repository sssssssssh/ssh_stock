# FACTOR-RECOVERY-04-R1 — 候选准备阶段最小生产优化、来源合同版本迁移（待独立审阅）

日期：2026-11-16。基线 master HEAD=origin/master=bf7b6a35a453c7d82be363dec2e0f5157221db92，四条 GitHub CI 已 green。本任务目标是推动因子计算任务的候选写入性能恢复，不得扩大为泛用 W05 审计。

## 必须先读的证据
- docs/acceptance/FACTOR_RECOVERY_04_OFFLINE_RECEIPT.md 和同名 EVIDENCE.json
- tests/unit/test_factor_recovery04_candidate_preparation.py
- R4 的来源合同、测试、closeout
- AGENTS.md、治理文件与业务权威文档，git status（保留所有现有未跟踪文件）
- 查看真实 data_publication.py: PublicationWorkspace.upsert 的完整最新实现，不凭任务书伪造性能收益

## 背景和不可动边界
- 当前 _lookup_batch 已经是每批一条合并查询，严禁继续把进度标签算成 SQL 往返；不修改 SQL、锁/事务、批次500边界、源身份、取消、数据库模式或发布语义。
- 当前默认 update_columns 是每行对固定 model.__table__.columns 执行相同的列表推导。3,450 行诊断：186300 次列元数据判断；内存候选 378 次；假I/O和数据输出摘要相同，3 项 AST 隔离诊断通过。这不是数据库性能提升证明。
- 禁止接入业务PG17、真实Worker/SQL/迁移、Raw/Derived写入、正式性能试验或新云资源。B_GATE和TARGETED_PG17_GATE保持 NOT_APPROVED。
- 仓库中 source contract v1 和 current v2 是已固定版本：docs/acceptance/r1_business_compare_schema_v1.json及所有固定摘要不可修改；docs/acceptance/r1_current_business_sources_v2.json 不能改成接受新版本或新摘要。历史A42366不可变；R1历史AC31隔离机制不得改低安全。

## 实现任务
1. 仅在 backend/app/services/data_publication.py 的 PublicationWorkspace.upsert 内对每个 batch 预计算默认更新列集合，移到逐行 for row 之前。显式 update_columns 仍使用原对象和原迭代语义，不能无意改变 None/空列表、键缺失行为、每行合并JSON/保留NULL、首次 base_row、source_id、UUID、now、trace、checkpoint、_store 和行顺序。优先一个极小diff；若分析表明移出会改变语义，则停止并给出具体反例。
2. 不要简单替换 v2 摘要。新增独立 r1.current-business-sources.v3 完整固定manifest（仅 OFFLINE_INTEGRITY_ONLY，execution_authorized=false），校验全部现有20条来源，与真实当前 LF字节摘要一致，包括 modified data_publication.py、r1_integration_controller.py 和 r1_integration_seed_loader.py。
3. scripts/r1_integration_evidence.py 的验证器显式支持 v1/v2/v3 三个严格版本，原 v1默认不变，原 v2摘要/严格白名单/拒绝路径不变（当前代码变化后 v2 应正确拒绝已变化的源码，不能旧新任意通过）。v3 新hash必须在独立常量严格绑定。未知版本、源篡改、manifest篡改、符号链接、错误路径拒绝，不得吞异常、fallback或以 HEAD 当授权。
4. 唯一必要的 Controller / Seed 当前校验调用明确切到 v3，保证现有当前业务组合行为继续验证，不把它们迁到历史测试；同时更新 tests/unit/test_source_contract_r1_history.py 中依赖「当前v2=通过」的断言为当前v3通过且v2正确拒绝，保留旧v1/v2和历史负例。必要时只增加最窄的v3负例。
5. 用当前真实 PublicationWorkspace.upsert（而非只AST摘取）新增或扩充离线原生单元回归：基线与改动在 1、500、501、1001、3450 行、显式更新列/空更新列、NULL保留、首次原像、来源不匹配、取消检查等条件下校验等价；测试不能依赖真实PG或生产DB，不能用劣化断言来规避失败。可保留原 AST 诊断测试作为辅助，不把它当原生/整链等价测试。尽可能复用当前 tests/unit/test_factor_candidate_write.py 等已有夹具。
6. 仓库Windows检查可能由于已存v1 JSON CRLF与仓库Git LF不一致，不能更改冻结JSON或其摘要，也不能把原始路径改变为LF；必要时将当前源文件复制到纯本地、断网Linux Git checkout中验证。已就绪的容器 ssh-stock-factor-recovery-test (python:3.12.14-slim, Networks={}, /workspace只读), 但 Codex sandbox可能无法直接访问 Docker API；若拒绝，明确记录阻断而不是修改测试环境权限、跳过测试。独立ChatGPT审阅可以使用Remote Desktop Commander执行。
7. 不修改 requirements.lock、CI/workflow、数据库或测试安全插件，不运行 docker compose，不触碰两个已存在 W05 未跟踪文件。

## 允许修改的有限文件
- backend/app/services/data_publication.py
- scripts/r1_integration_evidence.py
- scripts/r1_integration_controller.py
- scripts/r1_integration_seed_loader.py
- docs/acceptance/r1_current_business_sources_v3.json（新增）
- tests/unit/test_source_contract_r1_history.py
- tests/unit/test_factor_recovery04_candidate_preparation.py（仅为保留原诊断或新增验证而有必要）
- tests/unit/test_factor_candidate_write.py 或新增 tests/unit/test_factor_recovery04_native.py（二选一，最窄）
- 新增 docs/acceptance/FACTOR_RECOVERY_04_R1_CLOSEOUT.md
- 若需要超出白名单，先停下并在closeout给出精准理由，不擅自改。

## 必须通过的离线验收与交付
- 原生 Worker 30项、Controller/Seed/Protocol/R1当前历史组合、旧source contract治理、候选写入/取消/发布单元回归、全项目Ruff和git diff --check。
- 独立v3验证与旧v1/v2拒绝语义；精准比较当前业务来源，不能放宽合同。
- 验收包括伪I/O输出等价与真实SQLAlchemy模型元数据语义，不得承诺生产性能百分比；若无法运行原生测试，closeout注明 NOT_RUN。
- 完整具体diff、文件SHA/原固定摘要、测试数/JUnit、潜在风险、尚未验证的真实PG17/Worker/候选写入性能。
- 禁止提交、推送或触发 CI，先提交给ChatGPT独立审阅，再决定非force push和CI。
