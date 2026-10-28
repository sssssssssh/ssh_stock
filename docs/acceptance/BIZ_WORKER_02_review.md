# BIZ-POLICY / WORKER-02 整改记录

基线：`75076eac443d935d622bf59e12aad20ce5aba85e`，从 clean master 快进取得。
工作分支：`codex/biz-worker-02`。本轮不是可部署长补算验收，结论仍有
CONTRACT_MIGRATION_BLOCKED、HEARTBEAT_FIELD_ROOT_CAUSE_OPEN、PERFORMANCE_OPEN、FIELD_NOT_RETESTED。

## Batch A：原证据与合同审批

原始四个 Actions 实际复核：主 CI 40654653164、A4-1 40654653235、A4-2 40654653213
失败；Publication 40654653255 成功。没有运行主全量，不能引用旧 SHA 的测试数冒充本基线验收。

下载五个原 ZIP 并检查 CRC；全部 XML 的失败节点及完整调用栈保留在本地
`.codex_tmp/biz-worker-02/old-artifact-audit.json`，原 ZIP/日志未删除。

| 原工件 ID | ZIP SHA256 |
|---|---|
| 12800324553 | 7c1534b06a30ff21348c79fc7776f920f9c8acca30a71d605bbcb80430d51a4b |
| 12801217025 | a122d92b8c2c4d28cf9f38ba8b17113697db870ef5578102fb4d2a4e6e903e9c |
| 12801436000 | ff9aa2e4d47ae8b6456c0971c9345cf82ee5057ddcf3c6738ad41759d98bcb8a |
| 12801855374 | 5f7a136a835e20290f17bc832ee47e9cca08d4929542ddc272bafe175d9e6bbd |
| 12801910023 | 8a0174b2a21e0e8fc013b1d6baf50ea07666bcfcf8022333a35b6d8791c5279c |

三个 JUnit 失败：

- tests.unit.test_a4233_background_observer::test_frozen_baseline_bytes_and_old_workflows_unchanged
- tests.unit.test_ab_read_profile_v14_a4::test_a4_diagnostic_freezes_production_sources
- tests.unit.test_lookup_tail_review_a423::test_workflow_does_not_repeat_the_disallowed_100_trial_or_weaken_capacity

调用链均到 business_source_contract.verify → a42366_source_guard.verify →
`changed == stage_paths` → A4235_FROZEN_FILE_CHANGED。A4-2 的直接合同 CLI 同样退出 1，
没有 JUnit，原完整 stdout 保存，不能编造测试计数。

另在独立本地只读源码副本重验 2779a2a 原合同，完整 verify 返回摘要
`8c296818dfd1522cea16c1b952696c49b61ce5992f27d3357c0d90f3e78b5770`；
其原 11 项 guard 测试通过。在 75076ea clean 副本调用相同 verify，真实拒绝 FROZEN_FILE_CHANGED。
历史 manifest、所有旧测试、所有 workflow 和 source guard 本轮均保持原字节。

独立迁移方案见 [ADR](BIZ_WORKER_02_contract_migration_ADR.md)，尚无独立审阅者身份及签署结论。
用户选择交独立审阅者审阅不是已经签署；本轮不实施新版本分派，W01/AT04–07 未关闭。
上轮 Linux 的 4939 passed / 46 failed / 137 errors 原记录保留，不回写为成功。

## Batch B：心跳与源码身份

轻量 lease UPDATE 和 JSONB 进度合并拆成两笔独立短事务，每笔仍 owner/token/status CAS，
均保持 lock_timeout=1s / statement_timeout=3s。连接取得、事务设置、两类 UPDATE 和 COMMIT
分别记录 wall time、SQLSTATE、失败阶段；失败不释放任务，也不自动中止未知主计算。
连续失败日志记录次数、阶段、单次耗时与未确认时长；原异常、DSN、参数不打印。

真实 PG17 trigger 对进度 UPDATE 注入服务端 pg_sleep(4)：原基线在 3s 发生 57014 后心跳仍旧；
同一回归在本轮心跳已独立提交，进度失败明确保留。另有独立行锁竞争实际观测
pg_blocking_pids / Lock 并得到 55P03；连接终止保持 RUNNING、不重放。
该隔离因果实验仅证明这个失败机制，不能推出现场 57014 都由 JSONB 或锁竞争造成。

calculation_policy.py 原内容身份实现保持不变；Git-only 正例、Python/YAML/三个开关负例、
旧冻结身份不重签、pre-freeze 失败 JSONB 合并等原测试保留且重新执行。

## Batch C：人工安全对账

新增 `python -m app.cli reconcile --job-id <UUID> --dry-run`，复用既有只读诊断，
数据库强制 READ ONLY、短时限。输出 owner/token 摘要、PG 等待、其他 Writer、候选状态及
未决 prepared 数量；无匹配 SQL 不能证明所有进程退出，始终 EXECUTION_UNCONFIRMED。
没有 --apply/--force/--unlock，自动 stale recovery 仍 return 0。

新增维护原语 abort_confirmed_writer，不暴露给 CLI/API：必须有独立 authority 现场核验
所有主机执行者已终止、领取已冻结及所有提交已判定；缺该能力直接拒绝。
授权与具体 job/owner/token/审批编号/证据摘要绑定。advisory lock、原身份 CAS、子先父后、
既有 finish_publication(FAILED) ABORT/Dirty 和追加审计同一事务；保留首错/候选/公开 A。
发布进行中、未知提交、执行者存活/未知均拒绝。COMMIT 响应丢失不自动重试；独立重新读取
匹配审计和 ABORTED 事实后只返回 ALREADY_RECONCILED，不做第二次恢复。

本轮没有提供生产 authority 安装或真实退出证明。隔离 PG17 使用唯一受控子进程实际退出
及本地事务验证原语；这不能作为生产容器、所有远程 Worker 或 G1 的证明。

## Batch D：诊断能力与未完成容量

仅增加显式 opt-in ExecutionDiagnostics：有界聚合/最近32条，无 SQL、参数或行内容。
read 的 query/FETCH/DataFrame 分开；既有 ProgressStep 的 candidate/compute 等阶段计时，
trade-status 的行物化/replace/commit 单独计时。默认未安装 observer，不改变查询和金融结果。
小型真实 PG17 严格比较 DataFrame 字段、值、dtype；不把小样本当完整容量验收。

FETCH wall time包含服务器游标、传输与 Python 行物化，不能单独推定网络耗时。
当前 _lookup_batch 是一次合并 A/B SQL，lookup_candidate 包含它的总成本；后续
lookup_published 是原阶段边界，近零不代表公开查键没有成本。阶段和内含 SQL 不可相加。

只读资源预检：可用内存估算 2,217,394,176 bytes（macOS free+inactive），固定计划保留
4,294,967,296 bytes；目标仍 1,443,097 行 × 3轮，实际 0轮。判定 RESOURCE_DEFERRED，
不是实测 OOM、完整基线或性能通过。峰值预留仅规划估算，不能称为经测量证明的必要门槛。
W04/AT16–17 全规模、W05/AT18 对照及性能改造未完成；不猜测 785000 行死锁，不修改生产
_lookup_batch、索引/DDL/超时、A/B 遮蔽或 Golden，等待容量资源及实测后再选择优化。

## Batch E 与验收状态

最终同 SHA 四流程与完整 pytest 是正式门槛；审批未签时应保留真实 CI 红灯，不能使用
SOURCE_FIXED_PENDING_FIELD_VALIDATION。当前所有现场状态 FIELD_NOT_RETESTED。
完整本地回归、最终 SHA、四条原生 CI 及未关闭节点在后续证据提交/最终交付列明，
不把本段写作尚未发生的验收成功。

| 验收 | 本轮证据 / 尚缺 |
|---|---|
| AT01–03 | 精确基线、真实 RED；不加载业务 .env，不访问 TuShare/生产/G1 |
| AT04 | 历史 verify 与 11 原 guard PASS；完整新迁移审批仍 BLOCKED |
| AT05–07 | 未签署；不激活新合同、不修改历史断言 |
| AT08–11 | 真实 PG17 57014/55P03/断连、轻心跳、单调/取消/CAS、连续失败日志 |
| AT12–15 | dry-run及拒绝；本地已退出执行者的审批原语/未知ACK/幂等回归；现场证明未取得 |
| AT16–18 | RESOURCE_DEFERRED / PERFORMANCE_OPEN，未达到容量门槛 |
| AT19–20 | 原业务身份正负/Worker/旧账本回归保留执行 |
| AT21–22 | 待最终 CI，合同审批阻断；不能宣称全量通过或部署就绪 |

## 回滚

停止新版本部署，正常撤回本分支业务代码提交即可；不改 schema、无需降级迁移。
维护审计/终态是事实记录，不通过代码回滚撤销，不重签旧任务、不自动重算。
本轮无业务库、生产任务、容器或 G1 资源操作；测试 PG17 为新建独立标记/物理ID实例，
只对自有合成库通过既有 Alembic 升级，测试结束停止自有实例。
