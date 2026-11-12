# BIZ-PERF-P1-04 单次隔离合成根任务诊断

2026-11-12。设计基线 `391dca85cf9cc5b2e1858f4ea7fa19f98f52f079`。R1 已完成独立入口的离线整改，状态为 `A_GATE=OFFLINE_VALIDATED / B_GATE=NOT_APPROVED`。真实执行的接线、审批和实例校验留待单独审阅。

## W00 缺口与范围冲突

| 项目 | 基线能力 | P1-04 缺口 |
|---|---|---|
| 测量入口 | `scripts/business_recalc_measure.py` 先用 `verified_test_url` 校验，再由 `isolated_v14_database` 建库、迁移和清理。复用固定合成 Seed、create/claim/execute、终态与业务摘要。 | 默认 `overall` 包含独立 Job 和 ledger 读取，SQL/FETCH 观察也未同时冻结。旧 03-B 通道已在 Worker 返回后冻结 SQL 尝试计数，但该通道授权和 4 股协议专属。 |
| 原始证据 | 现有 `ProgressStep`、SQLAlchemy before/after/error、psycopg FETCH 和候选批计时。普通路径在 `finally` 写报告；03-B 有专属进度通道。 | 普通路径在原生崩溃或强制终止时可能无可读前缀；最终报告可覆盖、错误原文不适合直接导出。根计数、阶段、FETCH 和后验结果需要独立边界。 |
| 冻结合同 | `tests/unit/test_perf03_lnx_w04a_offline_contract.py::test_A20_four_files_original_reports_and_sources_unchanged_no_writes` 检查测量器完整字节，仅接受已签收 LF/CRLF 两个哈希。 | 任务书当前允许改动的测量器路径与 A20 直接冲突。临时副本增加注释即可复现 `W04A_FROZEN_CONTENT_MISMATCH`。 |
| 8 股规模与安全 | 历史协议按 665 开市日、4 股、2,660 股日行及固定 420 秒预算运行；现有 PG Guard 核对 PG17、UUID marker 和物理 system identifier。 | 同 Seed 规则下 8 股对应 5,320 股日行，超过旧 03-B 的 5,000 行限制。新实例、独占卷、租约、运行域、逐表行数和清理归属仍需独立证据。 |

W01 原拟议 Diff 停在冻结门禁。R1 明确授权新增独立测量入口和离线测试。旧测量器、Seed、PG17 Guard、旧 03-B 控制器及 W04-A 断言均保留原件。独立入口复用现有 SQL 快照构造器和严格 JSON 解析器。单测用现有 `RootCounts` 验证根返回后计数已冻结。普通旧测量器会建立隔离库并调用 Worker，无法作为离线子进程，因此当前入口没有调用该路径。

## R1 离线入口

```text
python -m scripts.biz_perf_p1_04_diagnostic validate --input-dir FIXTURE_DIR --output-dir NEW_OUTPUT_DIR --expected-implementation-sha EXPECTED_40_HEX_SHA
python -m scripts.biz_perf_p1_04_diagnostic execute
```

- `validate` 仅读取固定的 `preflight.json` 和 `events.jsonl`。输入须是 `OFFLINE_FIXTURE`，显式声明实施 SHA、冻结的业务源码摘要、8 股、1 月、五个 OFF 开关和预期/观察实例身份。第一个根事件绑定规范化 preflight SHA256，后续事件共享根 ID 和 run UUID。声明值的匹配只验证离线夹具契约。实例证明也来自夹具，真实实例授权仍待签发。
- `execute` 固定返回 `AUTHORIZATION_PENDING`、退出 2；无需提供配置、连接串或工作目录。旧 03-B 的 4 股、420 秒协议和历史样本均不能作为本入口的夹具或授权。
- 输出目录应位于仓库外，须新建且不存在。文件读取拒绝链接、junction、非普通文件、越界大小和路径穿越。原始事件逐条校验后原样写入 `raw_events.jsonl` 并 fsync。根快照、后验校验和摘要使用同目录临时文件及无覆盖原子发布。读回核对快照与原始事件的字节大小和 SHA256 后，再生成摘要与 `integrity.json`。完整夹具应有完整性清单且无失败回执。坏尾行保留此前已确认的前缀；卷写入失败时回执尽力保存，进程仍以失败退出。
- 摘要标记 `OFFLINE_VALIDATED` 与 `hotspot_decision=NONE_PROVEN`。夹具排行只复核 inclusive 口径，阶段可重叠。SQL execute、FETCH、CPU、RSS 分列，缺测保留 `UNKNOWN` 或 `NOT_INSTRUMENTED`。零 CPU 的派生比率为 `UNDEFINED`。`root_attempts=0` 表示本入口没有发起真实根任务。

## 真实执行后续合同（待批准）

1. 根 wall 从 create/claim 前起算，在唯一一次 Worker 返回及其清理完成后冻结；Worker 调用单独计时。随后独立读取 Job、ledger、来源和表摘要，统一归入 `post_root_validation_ms`。
2. 保留阶段 inclusive wall、SQL execute、驱动 FETCH 行数和时间、进程 CPU 及累计 RSS 的独立口径。阶段可能重叠。没有观测用 `UNKNOWN` 或 `NOT_INSTRUMENTED`，零 CPU 的派生比率标 `UNDEFINED`。
3. 根开始、阶段完成、根冻结和失败均应先写脱敏原始事件，带单调 seq、UTC 时间、相对时间和根身份。派生摘要只能在重新读回、校验完整性之后产生。快照原子发布，前缀留存，无覆盖、有限字节；拒绝截断尾行、重复键或 seq、非有限值、不可信路径和第二个 root ID。
4. 只接受同时绑定设计 SHA、实施 SHA、干净工作树、业务/策略/输入摘要、资源身份与单次 UUID 的证据。完成后必须确认 SUCCESS/PUBLISHED、来源、公开结果、无 B 泄漏和可信清理；任一关键条件缺失均为 `INCONCLUSIVE` 或任务书规定的失败码。
5. 保持因子公式和排序、PIT、250 交易日预热、430 日历日回看、500 行候选批处理、原像、tombstone、质量、取消、心跳、300 秒发布预算、原子发布及未知 ACK 边界。

## W05 单次执行待批表

本表当前为待审草案。P1-04 离线适配和审阅缺口解决后方可进入 B_GATE 裁决。

| 审批项 | 拟议值或待填凭证 |
|---|---|
| 负责人批准、操作主体及窗口 | 待填写并签认；仅一个具名执行者、一个窗口。 |
| 实施 SHA / CI / 独立审阅 | 待填写；实施精确 SHA、当前干净工作树、普通 CI SUCCESS、源码和策略一致性。 |
| 唯一 run UUID / 消耗次数 | 待签发；目前 0。根启动后计一次，失败/超时均停止。 |
| 输入 | 8 股、2025-01-01 至 2025-01-31，一个根任务，900 日历日 Seed 历史。股日行静态预期 5,320；逐表行预算和 SHA256 待审批，因子段数据实生成。 |
| 开关 | factor input reuse、Raw preflight batch、factor CPU optimization、A/B merge read、PERF_DIAGNOSTICS_ENABLED 全部 false。无 optimized/profile/candidate diagnostics/旧 03-B 模式。 |
| Linux / PG17 身份 | 待填独占 Linux x86_64、版本/镜像、隔离网络和 cgroup、独立 PGDATA 卷、PG17 major、UUID marker、offline/online system identifier 及新建 UUID 库归属。 |
| 预算 | 拟 20 分钟（末 5 分钟清理）、Worker 3 GiB、PG 4 GiB、卷 10 GiB、脱敏导出 10 MiB，须签认 CPU/磁盘/期限及终止方案。 |
| 清理权限 | 待签认；只清理所有权已确认的新建资源。身份漂移、未知 ACK、权限或清理结果不确定时，记录 `CLEANUP_BLOCKED` 并交人工处理。 |
| 停止条件 | 缺授权、身份、资源、固定封装或证据能力即拒绝。失败或已执行一次停止；不再补样、不跨根拼接。 |

验收只可报告受控 8 股样本的阶段调查方向。当前真实 PG17、Worker、OFF/ON 及容量保持未运行，R1 与 D04 状态不变。
