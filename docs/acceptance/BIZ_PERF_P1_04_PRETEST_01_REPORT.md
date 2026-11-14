# PRETEST-01 只读热点调查报告

2026-11-14，源码基线 `b5207a39fd98b1508b8745fadae799ff34a3609d`。
`HOTSPOT=NONE_PROVEN / ROOT_ATTEMPTS=0 / REAL_NOT_RUN`。
三条假设的编号表示调查清单顺序，不代表耗时排名。没有真实瓶颈、提速或容量结论。

## 视图入口和证据边界

新增 `scripts/biz_perf_p1_04_pretest_report.py::summarize_offline(input_dir, expected_sha)`。
只读显式可信 fixture 目录中的 `preflight.json`、`events.jsonl`，不自动寻找其他目录。
可通过唯一读取命令输出有界 JSON：

```text
python -B -m scripts.biz_perf_p1_04_pretest_report summarize-offline --input-dir OFFLINE_FIXTURE_DIR --expected-implementation-sha EXPECTED_40_HEX_SHA
```

直接复用冻结 diagnostic 的 directory/read_file/decode/preflight/Replay/summary/encode，
以及 E02 wiring 的只读 `_hex64` 和既有常量；没有自创事件、SHA 实现、审计或审批框架。
输入是原 E02/E03 的完整原始 fixture 对，不是任意自称已验证的 summary 对象。
不调用有写入行为的 `validate_bundle`，不读取 E04/E05 账本或改变其分类与占用。
缺结束、未知根状态、质量失败、坏摘要、跨根/UUID/SHA 等均先由原 Replay 拒绝，
统一抛出 `PRETEST_EVIDENCE_REJECTED`；CLI 退出 2 且不返回部分指标。
重复键、非有限值、缺 LF、超限和不可信路径同样拒绝。输入上限沿用
preflight 64KiB、raw 8MiB、单行 64KiB、4096 事件；输出至多 2MiB。

固定输出 `source_evidence_kind=OFFLINE_FIXTURE`、`status=HYPOTHESIS_ONLY`、
`hotspot_decision=NONE_PROVEN`、`root_attempts=0`、`authorization=AUTHORIZATION_PENDING`、
`b_gate=NOT_APPROVED`、`targeted_pg17_gate=NOT_APPROVED`、`budget=DRAFT_NOT_APPROVED`。
`execute` 即使带虚拟 permit/force 参数也固定拒绝、退出 2；无文件输出、执行器或进程创建端口。
合法 fixture 可被完全伪造；本视图只验证离线自洽，不认证来源、审批或真实资源。
目录祖先须可信且稳定，沿用原读取器的文件系统信任边界，不声称线性化快照或防恶意管理员。

## 已支持指标及本次离线演示

`MEASURED_OFFLINE_FIXTURE` 表示从模拟时钟/计数构造的原始事件读得的数值，
不是实际业务运行计时。本次在系统新临时目录通过原 `wiring.emit_fixture` 生成一个完整
默认样本，再只读调用新视图；没有运行旧测量器、Worker、SQL 或性能采集。

| 字段 | 默认离线样本 | 可解释范围 |
| --- | --- | --- |
| root_elapsed_ms | 20 | create/claim 前到 mock Worker 返回，排除后验窗口 |
| execute_claimed_job_ms | 20 | root 的子区间；默认 mock create/claim 不推进时钟，所以可以相等 |
| post_root_validation_ms | 7 | 独立后验；不得加进 root |
| sql_calls / sql_snapshot.counts | 11 / SELECT=9, WITH=2 | 根冻结尝试计数；不包括后验查询 |
| sql_execute_ms（根级） | UNKNOWN | 根快照没有此字段，不能累加阶段来填补 |
| fetch_observed_ms / fetched_rows（根级） | UNKNOWN / UNKNOWN | 默认 fixture 没有 driver FETCH reader；不是 0 |
| process_cpu_ms / wall_per_cpu | 10 / 2.0 | 假时钟 CPU 差值；CPU 为 0 或 UNKNOWN 时比率 UNDEFINED |
| rss_peak_bytes | 1024 | 注入的进程生命周期峰值读数；不分摊到阶段 |
| factors.compute.stage_inclusive_ms | 20 | 默认唯一 instrumented 阶段，非真实最慢阶段 |
| factors.compute.sql_execute_ms / sql_calls | 3 / 2 | 阶段独立 fixture 指标，不等于根计数合计 |
| factors.compute.fetch_observed_ms / fetched_rows | 2 / 10 | 阶段独立 fixture 指标，不补填缺失的根 FETCH |

专属测试另将 create/claim 窗口构造成 5ms，使 root=25、Worker=20、post=7，
用非零差异检测双计；这也是模拟事件，不是新增真实测量。
`fixture_stage_top3` 完全复用原 summary 的 inclusive 排序；同名阶段可累计且阶段可重叠，
`stage_to_root_ratio` 不是全局份额，各比率不可求和。SQL 与 FETCH 也可能重叠，
不能从 Wall 减去二者得到“纯 CPU”或网络等待。视图不输出独占时间、P95/P99 或执行计划。

## 三条源码可复核假设

### H01：输入读取、窗口准备与 fingerprint 的成本归属

**CODE_OBSERVED**：`backend/app/services/factors/service.py:39` 的 `FactorService.recalc`
先取 430 日历日回看，调用五类 `_read_*`，再在第 61 行用
`run_calculation("factors.compute", calculate_stock_factors, ...)` 计算。
第 87 行还将 DataFrame 转为 records、逐行 `_clean_row` 和 metadata 合并后持久化。
`backend/app/services/factors/input_window.py:70` 的 `_prepare → verify(capture=True)`，
第 92 行 `_verify` 先 SHARE 锁五个输入表与候选表，随后五个分组 fingerprint SELECT，
再做一个候选 trade-status fingerprint scalar。逐行 to_jsonb/sha256、按 ts_code 的
string_agg 排序和历史证据对照，可能随窗口行数、表宽和重复核验次数增加成本；
不能据此推断数据库实际计划或耗时。

**关键适用条件**：`backend/app/services/recalculation.py:121` 只在
`factor_input_reuse_enabled` 为 true 时装配 FactorInputWindow。
当前拟议试验五开关全部 false，因此不能假定此 `_verify` 会运行，不能开启开关来证明假设。
源码的 `ProgressStep("factors.input_verify", "validate")` 确实存在，但冻结
diagnostic/wiring STAGES 不接收这个名字；视图对此明确 NOT_INSTRUMENTED/UNKNOWN，
不映射成 `factors.compute`，也不把五类 read 阶段冒称 fingerprint 计时。

**HYPOTHESIS / REAL_NOT_RUN**：在默认路径，读取/传输/转换与 compute 哪部分更值得调查尚未知；
条件式窗口 fingerprint 成本只保留源码假设，在本次五 OFF 试验中不能直接验证。
未来经单独授权的证据应区分 `factors.stock_daily/adj_factor/stock_basic/trade_status/index_daily`
与 `factors.compute` 的 inclusive、SQL execute、driver FETCH 和根 CPU/RSS。
现有合同若不能隔离转换或 fingerprint，就保持缺测；不能用模拟数值或残差补齐。
**MEASURED_OFFLINE_FIXTURE**：本次仅 compute=20ms；对真实 H01 无支持或排除能力。

### H02：批次查找、类型恢复、行级序列化与写入

**CODE_OBSERVED**：`backend/app/services/data_publication.py:279` 的
`PublicationWorkspace.upsert` 每次注册来源，按最多 500 行分批。
第 225 行 `_lookup_batch` 使用 input_keys JSON recordset，结合候选与 public 的两个
LATERAL probe、native composite 类型恢复，在**一次 execute** 中返回 current/base/transaction_now。
`lookup_published` 进度标签出现在该 SQL 之后，不证明另发了 public 查询。
每批若缺 SERIAL id，会额外调用 nextval/generate_series；随后按行/列准备、校验 provenance，
通过 `_json(key)`、`_json(final)` 生成 staged rows。
第 401 行 `_store_batch` 再执行 `_json(rows)`、json.dumps 和一次 JSON recordset INSERT/UPSERT；
`_json` 在第 76 行本身进行 JSON dump/load。删除路径还可能调用 public-only `_lookup`，
不能把 upsert 常见路径计数推广到所有工作负载。

**HYPOTHESIS / REAL_NOT_RUN**：批次数、列宽、Python 序列化和类型恢复，或 lookup/store
中的数据库等待都可能贡献成本。只能从代码确认上面机制，不能声称“仍是每 500 行两次查找”、
不能声称这些 probe 已用最优索引，也不能从默认 fixture 排名认定候选是瓶颈。
未来优先核对 `candidate_lookup_batch`、`candidate_store_batch` 的 inclusive/SQL/FETCH，
结合根 SQL 次数、CPU 和完整根 Wall；缺少 prepare/serialization 独立事件时应明确缺口。
业务装饰器名实际是 `candidate.query` / `candidate.write`；冻结测量器
`scripts/business_recalc_measure.py:301` 附近的 wrap 路径为 `_lookup_batch/_store_batch`
提供批次标签。这里只静态核对，没有调用该测量器或安装 wrapper。
**MEASURED_OFFLINE_FIXTURE**：默认样本未观测 lookup/store，二者均 NOT_INSTRUMENTED/UNKNOWN；
测试中的独立 lookup 观测也不能补出 store。

### H03：发布前验证、原子发布及后验读取的边界

**CODE_OBSERVED**：`backend/app/services/data_publication.py:751` 的 `finish_publication`
在 Job terminal CAS 事务中运行，不自行 commit。第 780 行 `publication.verify`
涵盖可选 A/B 证据及 `_verify_candidate`，后者从第 579 行读取 scopes/sources、逐来源核对
交易日/质量并检查各类候选身份，存在与来源数/日期数/表数有关的重复查询。
该进度阶段 complete 后，才锁 owner、检查 token/cancel/identity、开始发布预算，
并在第 821 行对已存在的 input windows 再 verify；因此不能把 `publication.verify`
当成“包含所有最终输入核验”的独占区间。
随后还有按表 count、公开原像比对、preimage、删除/UPSERT 与来源处理。
冻结测量器第 296 行将 publish mode 的进度归入 `publish_inclusive`，它与具体阶段可能重叠。

**HYPOTHESIS / REAL_NOT_RUN**：发布前检查、最终原像核验、发布写入或独立后验读取可能
各占不同成本；没有真实证据可排序。未来应分别看 `publication.verify`、`publish_inclusive`、
SQL execute、driver FETCH、根返回及 `post_root_validation_ms`。
`execute_claimed_job_ms` 包含 Worker finally，是根子区间；后验验证不计入 root，
也不能将嵌套发布阶段或 SQL+FETCH 相加推导占比。现有 root SQL 只有次数，无总 SQL 时长。
**MEASURED_OFFLINE_FIXTURE**：默认 post=7ms，publication.verify 未观测。
这些模拟数值仅验证报告边界，不能证明真实发布校验慢或安全检查可以删除。

## 结论与交接

`CODE_OBSERVED` 证明存在具体调用点；`HYPOTHESIS` 说明待区分机制；
`MEASURED_OFFLINE_FIXTURE` 只说明模拟输入经过原 Replay；所有真实性能仍为 `REAL_NOT_RUN`。
下一步仅人工审阅[隔离申请草案](BIZ_PERF_P1_04_ISOLATED_RUN_REQUEST_DRAFT.md)，
是否批准未来单次实际测量须新的明确用户请求，本任务不能切换执行。
E05/E04/E03/E02、PIT、质量、发布原子性、候选身份、排序及 frozen 五文件均不修改。
