# V1.3 候选写入与长任务可靠性验收

日期：2026-10-19。冻结实现：`9a377e410516d6bf53e6d1363ec5094af88478df`。
交付区分三层：本地功能回归通过；最终 clean HEAD 的 CI 尚待结果；性能及真实云端验收未关闭。
不得将本文或旧 SHA 的 SUCCESS 解读为已部署、已批准补算或生产验收完成。

## 实现与阶段

| 项目 | 状态 | 证据与边界 |
| --- | --- | --- |
| W00 | PASS | 干净 master 冻结；旧任务只读确认为 CANCELLED/ABORTED、无残留任务 SQL；隔离 PG17 迁移与黄金样本 |
| W01 | PASS / DEFERRED | 实测旧 overlay 反关联放大、新完整 PK 点查；SQL/操作/内存/I/O 工具完成；纯网络分离、受控冷缓存及完整 key 阶梯结果待 CI/环境 |
| W02 | PASS | 精确本批键、原生类型、同事务 A/current；冻结实现逐字段黄金与完整 Worker 链路对照通过 |
| W03 | PASS / OPEN | 正常 INSERT/ON CONFLICT、500 行、原约束/触发器/首次 base；吞吐目标须按包含 W05 的最终收据判断 |
| W04 | DEFERRED | 保留原 scope 实现；50 万/100 万键已测，缺少新算法收益证据，不扩大重构 |
| W05 | PASS | 真 PG 取消锁、每批 checkpoint、错 token、心跳超时、终态、日志节流及前端回归 |
| W06 | PASS / DEFERRED | 本地全量与补充回归通过；最终 exact-SHA CI、完整容器/B3 和性能工件尚待结果 |
| W07 | PASS | [试运行与回退手册](../runbooks/publication_v13_rollout.md)；生产操作需另行授权 |

没有新增迁移/索引，没有修改 Raw/Provider、公式、策略、计算版本、PIT、首次原像、原子发布、
FIFO/CAS 或未知提交占槽规则；发布预算仍为 1000 万行/300 秒。
取消 API 使用 NO KEY UPDATE，兼容候选外键 KEY SHARE，但不提前标终态或释放执行槽。
每批 store 前的独立 checkpoint 保留安全性，也会增加最终 SQL，必须计入性能结果。

阶段提交：A `7a287e2`、B `b86edde`、C `529becb`、D `44660b3`、E `d4cd65f`；
F 为本收尾矩阵及操作手册的文档提交。以最终 F 的 HEAD 检查 CI，而非上述中间提交。

## 本地验证

- 完整 `python -m pytest`：2169 passed、445 warnings，4763.01 秒，未跳过失败用例。
- 此后新增收据/分位数测试：最终相关 unit 35 passed；新增跨月/跨年与真实完整链路 golden 3 passed。
  后补用例不冒称已包含在此前全量收集数中；最终 CI 会重新收集全部用例。
- `python -m ruff check backend tests migrations scripts` 与 `git diff --check` 通过。
- 隔离 PG17.6 `alembic upgrade head/current/heads` 通过，current=heads=`0058_data_publication`。
- 前端隔离依赖副本 `npm ci`、`test:coverage`、`build` 通过：162 tests/23 files，行覆盖率 87.27%。
  Vite 仍有既有大 chunk 警告，未通过抬高警告阈值掩盖。
- Playwright 1440/390 两宽度、14 状态共 28 场景通过；已查看取消与批次截图，展开内容不覆盖后续行。
- V1.2 容量 smoke：164 行候选，准备 1.064 秒、发布 0.359 秒，58 个 RR 读者样本、无读者错误。
  行预算与第一表后真实 SQLSTATE 57014 两探针均保持十表 A 摘要不变、root RUNNING/PREPARING 占槽，
  随后的正常发布 SUCCESS/PUBLISHED。不是 L2/L3 替代品。
- Windows 原 `resource` 导入导致的三项 CLI 失败已使用真实平台 RSS API 修复，原断言保留并通过。
- 本机无 Docker 命令，既有 VM SSH 本轮不可达；未执行本地 Compose build/容器双 Worker。
  原主 CI 强制检查保留，没有跳过或降低断言。

## 性能证据与未关闭项

以下是最终 W05 之前的探索性测量，使用相同输入且输出摘要一致，但有本机并发负载和未受控缓存。
不是最终 SHA 的验收结果，不包含新增批次取消检查，不据此宣称总体往返减半。

| 候选规模 | 冻结准备秒（3 次） | 查询/写入优化准备秒（3 次） | 早期 SQL 对照 |
| --- | --- | --- | --- |
| 1000 | 2.571 / 2.551 / 2.631 | 1.378 / 1.229 / 1.008 | 10 / 5 |
| 100000 | 171.390 / 305.769 / 198.965 | 97.769 / 54.056 / 52.698 | 840 / 420 |
| 500000 | 2208.446 / 2399.169 / 1865.724 | 587.011 / 560.369 / 531.955 | 4200 / 2100 |

包含 W05 的最新 1000 行 smoke：1.009 秒、7 SQL、2 个独立 RR 读者、无错误或 Writer 阻塞。
其 7/10 仅为单次小样本，不能代替 B1/B2 或冷/热各三次。SQL 数不是线协议网络包数。
最终脚本将输入构造与候选准备分开计时；早期值不能混入新版收据校验器。

新 CI `Publication V1.3` 保存相同 clean SHA 的 baseline/current B0/B1/B2 各三次原始 JSON，
空/非空 A、已有 50 万候选、500/5000/50000 输入（内部仍每批 500）、scope 与专项 JUnit。
收据检查 SHA、干净工作区、相同环境/设置、实际行数、确定性摘要及读者错误；
推荐 50% 耗时/SQL 目标或冷缓存证据未满足时，明确输出 `performance_closed=false` 和原因，
不能因工作流绿色就宣称性能关闭。主 CI 继续校验 L2/L3、两回滚探针和真实双 Worker。

scope 测量详见 [评估](v13_scope.md)：百万键峰值 RSS 达 586,203,136 字节；
500 条掩码只是样本，不代表百万掩码吞吐。探索性 B2 进程 RSS 约 212 至 232 MB，
全实例 WAL 受并发影响，不能直接归因单 Job；原始收据保留实际值。
目前 RSS/WAL/读者延迟预算未经运维批准，真实跨云 RTT、网络等待拆分、冷缓存及生产容量仍未验证。

## T01 至 T32

PASS 表示所列本地功能断言通过；DEFERRED 表示对应大规模/容器或最终 SHA 条件仍须验证。
测试路径前缀为 `tests/integration/`，注明 unit/frontend 的除外。

| ID | 状态 | 可追踪证据 |
| --- | --- | --- |
| T01 | PASS | `test_data_publication.py::test_missing_a_is_not_replaced_by_in_progress_b_and_cleanup_does_not_leak`；V13 empty golden |
| T02 | PASS | `test_publication_lookup_v13.py::test_all_core_candidates_match_frozen_baseline`；成功发布原像测试 |
| T03 | PASS | V13 `test_all_core_candidates_match_frozen_baseline` 比较重复写入后 base/row/key/source |
| T04 | PASS | V13 `test_tombstone_and_repeated_update_match_baseline` delete/rebuild 参数 |
| T05 | PASS | 同测试 `new_delete_rebuild`，public 不存在时 base 保持 NULL |
| T06 | PASS | V13 `test_scope_closed_boundaries_match_baseline_without_deleting_neighbors` |
| T07 | PASS | 同测试 12 月 31 日跨年及 1 月 31 日跨月，含闭区间外相邻日期 |
| T08 | PASS | V13 原生类型测试及八表全字段 golden，不按缺失值填 0 |
| T09 | PASS | 既有 `test_successful_candidate_publishes_all_tables_and_stable_signal_id` 及删除/eval 回归 |
| T10 | PASS | V13 `test_update_allowlist_null_preserve_and_json_merge` |
| T11 | PASS | 同测试，NULL 保留、JSON 合并与旧 id |
| T12 | PASS | 既有 real recalculation absent(v1) 参数、Research/PAPER 全量冻结依赖回归 |
| T13 | PASS | `test_publish_fails_closed_without_changing_a[identity]`、V13 wrong token、队列旧 owner 回归 |
| T14 | PASS | `test_publish_fails_closed_without_changing_a[changed_base]` |
| T15 | PASS | V13 cancel[lookup]，SELECT 后 STORE 前取消，0 候选写入且 A 不变 |
| T16 | PASS | V13 cancel[first_store]，首 500 行后取消，回滚后候选为 0、A 不变 |
| T17 | PASS | 两个实际取消用例，经原 checkpoint 退出而非伪改状态 |
| T18 | PASS | 真取消 API 与候选 FK 锁并存、占槽检查；heartbeat Job 锁超时不破坏业务 Session |
| T19 | PASS | 既有 `test_disconnect_mid_publication_rolls_back_a_and_holds_slot`、`test_committed_publish_response_loss_never_rewrites_success` |
| T20 | PASS / DEFERRED | 本地 smoke 第一表后真实 57014 回滚；完整 L2/L3 的同探针待最终 CI |
| T21 | PASS | 既有 budget/timeout 参数与 smoke 两探针，预算未上调 |
| T22 | PASS / DEFERRED | `test_data_queue.py::test_continuous_enqueue_dedup_fifo_and_two_workers` 通过；最终容器双 Worker 待 CI |
| T23 | PASS / DEFERRED | 既有 RR/实际 API JOIN/count/pagination，smoke RR；完整容量读者待最终 CI |
| T24 | PASS | `test_signal_delete_archives_evaluation_and_terminal_evidence_is_immutable` |
| T25 | PASS | catchup child dirty/publication 测试、队列取消恢复 dirty 及全量 dirty dependency 回归 |
| T26 | PASS | frontend 候选未发布提示、reconcile complete 区别，28 browser 场景 |
| T27 | PASS | `test_calculation_batch_progress.py::test_live_batches_visible_without_committing_candidates_or_publishing` |
| T28 | PASS | unit `test_snapshots_keep_real_advancement_separate_from_waiting_and_are_bounded`、heartbeat wait 测试 |
| T29 | PASS | `test_telemetry_rejects_wrong_owner_and_token_and_never_regresses_progress` |
| T30 | DEFERRED | RSS/WAL/TOAST/I/O、读者/锁测量工具及小样本通过；最终规模读者对照与资源预算尚未批准 |
| T31 | PASS / DEFERRED | 本地前端 162/浏览器 28 通过，原 CI 容器与 reliability 检查保留；最终 HEAD 尚待 CI |
| T32 | PASS | V13 `test_real_worker_chain_published_business_output_matches_frozen_baseline`：真实因子/趋势/机会/质量/发布，十表全部业务字段精确对照 |

T32 仅规范化两次独立执行产生的审核时间戳和 Job UUID，UUID 保留 ROOT/SEED 来源角色；
不删除或放宽数值、状态、版本、配置身份、自然键、JSON 或任何业务字段断言。
候选字节级来源/原像一致性另由八表 golden 及原像/审计测试覆盖，不用 T32 代替。

## 收据、CI 与关闭条件

本地原始证据在忽略目录 `.codex_tmp/`，不提交生成物；最终 CI 将上传可下载工件。

| 文件 | SHA256 |
| --- | --- |
| v13-full.xml | `441df525e05b1652ee14ed39f5042867ce42f99429fb29c6d3235edd1161abd5` |
| v13-baseline-B2.json | `0d8d20123d7de9e79d73fd83e9c41ab9cb46c9f7b65bb3d26c2328ed5239a846` |
| v13-current-PK.json | `f41e2a602f587a7c6c6f7d89df3e27683c0070d42b55ed3f260bf9d2ebcf25f2` |
| v13-scope-1m.json | `8efa8710243257917cc217b9efb75f737f30d85f15754dd8a49e071306ff9308` |

[最终提交工作流列表](https://github.com/sssssssssh/ssh_stock/actions?query=branch%3Amaster)：
提交推送后必须按最终 HEAD 过滤，主 CI 和 Publication V1.3 的必需 job/step 全部 SUCCESS
才可记代码整改通过。当前文档不预写未来结果；未完成/失败仍为 OPEN，不使用旧 CI 替代。
本机无法运行的 Docker/容器项依赖该结果，不能由镜像构建或单进程测试推断运行正确。

性能整改 OPEN：最终包含安全检查的 B1/B2 目标、受控冷缓存、资源预算及读者影响仍需验收。
云端真实补算 UNPROVEN：本轮无任何部署或业务库写入测试。正式试运行必须按手册另行授权。
