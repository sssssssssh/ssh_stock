# V1.4 A4-2.1 执行报告：完整验收尚未关闭

## 结论

P1 设计/契约和 P2 脚本/CI 已交付；P3 已执行真实本地与远程回归，但最终 HEAD 的全部规模矩阵、
L2/L3 和两个聚合门禁尚未完成，DoD **未通过**。不得把本文件名 closeout 理解为验收已封版。

整体 `INFRASTRUCTURE_PASS=false`、`CORRECTNESS_PASS=false`（证据未齐），
`READ_PERFORMANCE_PASS=false / NOT_CLAIMED`，`production_read_authorized=false`、
`authorize_a4_3=false`，继续 `A4_2_NO_SAFE_WINNER`。没有部署或连接阿里云业务库。

## 提交与基线

基线：master `02c69c6127860f72adaf79071a9a11930b69e411`。一直保留 master，没有切分支/重写历史。

| 阶段 | 提交 | 内容 |
|---|---|---|
| P1 | `9dd81d538d0b014e683421fc6e9ffb19e4e42b6f` | 历史证据、ADR、1002 组集合契约、负向门禁测试 |
| P2 | `5593d58246f573a5d90d45416c7904c212bdc5a4` | scope/原子工件、容量拆级、严格 merger、两个 gate |
| P2 兼容性修复 | `7f5857ee08000fd77d5ddb4ce2e59146ad150008` | 冻结采样器标签、原 CLI stderr、软截止、身份与计划反例 |
| P3 | 本报告所在提交 | 工件隐私/中断证据审查、实际执行报告和剩余验收缺口 |

P3 提交 SHA 以本文件所属 Git commit 和最终 CI `head_sha` 为准（文档不能自包含自己的 commit 哈希）。
阶段 `7f5857e` 的数据仅用于本节所标诊断，不能填充 P3 新提交的 exact-SHA 矩阵。
完整文件集合可执行 `git diff --name-only 02c69c612786 HEAD` 核对。

## 修改范围

- CI：`.github/actions/a421-pg/action.yml`、`ab-read-a4-2.yml`、`ci.yml`。
- 契约/收据：`scripts/a42_ci_contract.py`、`a42_receipt_contract.py`、`a42_artifacts.py`、
  `a42_scope.py`、`a42_gate_io.py`、`ci_release_gate_v14_a4_2_1.py`、`publication_release_checks_v14_a4_2_1.py`。
- 原脚本适配：`ab_read_experiment_v14_a4_2.py`、其 summary/resources、`data_publication_capacity_v12.py`。
- 新回归：三个 unit 文件与两个 PG17 integration 文件；ADR、矩阵、证据索引及四份权威 Markdown。

backend、config、migrations、frontend、A4-1 冻结源码/原证据未改；没有新模型、索引或计算公式。
原容量 run_level 和原 release assertions 有 AST 比对；主 CI 除移出容量/提取 release 外的原步骤保留。

## 真实验证

| 验证 | 实际结果 | 身份与限制 |
|---|---|---|
| 全量 pytest + 原 coverage 门槛 | 2468 passed，0 skipped，597 warnings，2417.46 秒；89.28% ≥ 70% | 本地 `7f5857e`，专属 PG17 |
| P3 新工件/CLI/负向 unit | 129 passed | P3 工作树，非远程最终 HEAD 验收 |
| P3 PG17 实测 | 6 passed，37.52 秒 | 含真实 57014、部分命名游标 profile、全部十种 full 控制与原生计划 |
| Ruff / diff check | PASS | `backend tests migrations scripts` 全路径；未跳过错误 |
| Alembic upgrade/current/heads | PASS，current=heads=`0058_data_publication` | 仅专属 PG17，不是业务库 |
| 前端 npm ci / coverage / build | 23 文件、162 测试通过，语句/行 87.27%，build PASS | 前端源码未改 |
| Docker compose config/build | PASS | 构建不等于运行时连接已验证 |
| 远程核心 test job | success，2468 个 JUnit case 无失败/错误/跳过 | `7f5857e` 主 CI，下列链接 |
| 远程真实容器 | 三场景 success；1 Worker=6、2 Workers=6、2 Workers 原子发布=7，均 max_running=1 | 同上，真实镜像/十表协议 |
| 远程 runtime browser | 28/28 passed | 同上，桌面与窄屏原门禁 |
| 远程 L1 | success，164 行，发布 0.125932 秒，两个回滚探针通过 | 不能代替 L2/L3 |

初次本地全量因继续修复而中止的 155 项不计作全量通过；曾误并行的数据库集合比对失败没有放松断言，
之后串行复核通过。旧 `5593d58` 的两个兼容性错误已保留在 [失败索引](evidence/v14_a4_2_1_p2_ci_failure.json)。

P3 还关闭了以下工件问题：实际探针在会话内关闭 auto_explain 完整绑定参数日志，序列化再次去除参数块；
保留真实 DECLARE 文本与 rows/loops/buffers，不以 SELECT 冒充游标。
PG17 的 `log_parameter_max_length=0` 只影响参数日志，见
[PG17 auto_explain](https://www.postgresql.org/docs/17/auto-explain.html)。
中断实际计划探针时保存 `.incomplete.json.gz` 中的真实 profile 和 SQLSTATE，已完成组不覆盖；
游标没有 EOF 仍为 INCOMPLETE。另拒绝未被 manifest 引用的旧 gzip，恢复独立原文件名的 publication release JSON。

## CI 与工件索引

- [P1 A4-2](https://github.com/sssssssssh/ssh_stock/actions/runs/39641449645)、
  [P1 主 CI](https://github.com/sssssssssh/ssh_stock/actions/runs/39641449711)：设计阶段运行，不作为最终验收。
- [P2 首次 A4-2](https://github.com/sssssssssh/ssh_stock/actions/runs/39644754726)：真实失败门禁已产出
  INCOMPLETE / UPSTREAM_NOT_SUCCESS，未因上传了部分文件而通过；artifact `12368158974`，
  SHA256 `0b8f4e0be187e08b0ccf4b6d8cfbdecac0cab0ee561114bf4e086b4f1a99b832`。
- [7f5857e A4-2](https://github.com/sssssssssh/ssh_stock/actions/runs/39646797331)、
  [7f5857e 主 CI](https://github.com/sssssssssh/ssh_stock/actions/runs/39646797296)：阶段诊断，非 P3 最终 HEAD。
- 逐 job 时间、原工件 ID/下载链接/ZIP SHA256、版本化 verifier 和原始三轮样本：
  [执行快照](evidence/v14_a4_2_1_execution_progress.json)。不可把快照当动态状态。

最终新提交会自动运行同一组工作流；必须查看该提交自己的 `a421-gate-<sha>-attempt<n>` 与
`a421-publication-release-<sha>-attempt<n>`，不得拿上述旧提交/attempt 的绿色项替代。

## 分片预算与已见耗时

以下是 UTC 2026-10-21 18:51 左右的 `7f5857e` 快照；耗时为 CI job 总时长（含初始化），不是纯读取。
读取进程：10k 196.37 秒、100k 709.20 秒、百万 full .1 2943.07 秒、window .1 3060.26 秒；准备/读取/探针另在 raw/setup 收据分列。

| Job | 分钟预算 | 状态 | 完整 job 秒 |
|---|---:|---|---:|
| contract-and-safety | 45 | success（335 cases） | 441 |
| a42-small-10k | 120 | success，236/236 | 231 |
| a42-small-100k | 120 | success，236/236 | 742 |
| a42-million-full-0 | 240 | success，30/30 | 2990 |
| a42-million-window-0 | 240 | success，18 required + 3 auxiliary | 3096 |
| a42-million-plans-full-0 | 240 | success，10/10 | 1812 |
| a42-million-plans-window_matrix-0 | 240 | success，6/6 | 1329 |
| a42-million-full-1 | 240 | RUNNING | — |
| a42-million-window-1 | 240 | RUNNING | — |
| a42-million-plans-full-1 | 240 | RUNNING | — |
| a42-million-plans-window_matrix-1 | 240 | RUNNING | — |
| a42-million-monthly | 300 | QUEUED | — |
| a42-million-readers | 240 | QUEUED | — |
| a42-million-plans-monthly-0/1/2 | 各 240 | QUEUED | — |
| a42-shapes 五种 coverage | 各 120 | QUEUED | — |
| a42-event-prototype | 120 | QUEUED | — |
| test（核心） | 平台默认，原配置 | success | 2176 |
| capacity L1 | 300，软截止 270 | success | 42 |
| capacity L2 / L3-scaled-10pct | 各 300，软截止 270 | RUNNING | — |
| 两个 release gate | 各 30 | 等待依赖，不放行 | — |

21 个实验分片严格覆盖原 required 1002 组，另 6 个窗口同 job 对照。旧阶段已逐组重验 536 required + 3 auxiliary；
不是 1002/1002，更不是最终 HEAD。缺组必须失败，实际月链仅尾 T8、两档参数、三轮、15 形态、RR2、E3 仍全部必需。

## 百万级性能诊断（只限同一个 job / fraction .1）

`7f5857e` 的百万 full .1：A=2570000、当前 B=1350000、其他根 B=2800000，全部输出 3104443 行。
独立 PG17.11，2 CPU / 3 GiB，SQL 300 秒；三个原始样本保留。不能与旧 Runner 的 106/108 秒混合计算“本次提速”。

| variant | p50 秒 | p95 秒 | 保护 |
|---|---:|---:|---|
| Q0_LEGACY_RAW | 25.201 | 61.595 | NOT_EQUIVALENT，不是安全基线 |
| Q0_SERVICE_CONTROL | 23.176 | 24.603 | NOT_EQUIVALENT |
| Q0_SAFETY_EQUIVALENT | 92.549 | 93.738 | E0 + 最终复核 |
| Q1_CURRENT | 81.295 | 86.494 | E0 + 最终复核 |
| Q2_CURRENT | 93.682 | 96.378 | E0 + 最终复核 |
| S3 | 90.001 | 92.736 | E0 + 最终复核 |
| S3_INLINE | 84.843 | 85.394 | E0 + 最终复核 |
| S3_KEYS | 82.306 | 84.686 | E0 + 最终复核 |
| S4 | 81.996 | 83.984 | E0 + 最终复核 |
| S5 | 81.731 | 82.144 | E0 + 最终复核 |

S5 比同 job Q1 中位数略慢，不能宣称优化达标。Q1 的读入指纹、候选校验、最终复核中位约 20.21 / 15.22 / 22.30 秒；
这些嵌套量不能与锁持有时间重复相加。Q0 等保护 / Q1 / S5 客户端 CPU 中位 14.47 / 14.33 / 14.50 秒，
采样 RSS 下界峰值约 1.903 / 1.903 / 1.902 GB；不是逐进程独立峰值，也不是 PG 内存。
PG cgroup、DB counters、WAL、FETCH 与所有其他 variants 的原数值在 raw 收据，不能把无法归属的后台 CPU 伪装成后端 PID CPU。

窗口 .1 的六档 p50（None/1/3/5/10/20）为 108.406 / 116.593 / 115.613 / 112.584 / 112.990 / 111.991 秒；
其等保护 Q0 在该 window job 内独立测量，不能跨 runner 与上面的 full job 拼接比率。

## 未关闭项与处置

1. 最终 HEAD 的所有 required keys / 计划 / RR2 / 月链 / 形态 / E3 及两个聚合门禁未完成：OPEN，不宣称整体通过。
2. L2/L3 未完成；若超预算，保留 RESOURCE_DEFERRED，不能用 L1 代替。独立 Runner 需求及旧实测风险见
   [资源预案](v14_a4_2_1_runner_feasibility.md)。尚未取得/使用新 Runner，不操作业务云环境。
3. 性能门槛未通过：READ_PERFORMANCE_OPEN / NO_SAFE_WINNER，AB_MERGE_READ_ENABLED 默认 false。
4. 原依赖审计仍有 11 个漏洞（4 moderate / 3 high / 4 critical），本轮没有修改依赖或扩大整改范围。
5. CI 工件存在保留期限；原始下载包留在本地忽略的取证目录，Git 只提交脱敏索引和摘要，不提交归档/覆盖率产物/业务数据。

没有进入 A4-3、历史复用 B/C 或任何生产部署。后续只有最终 SHA 的必需任务全部结束并成功，且门禁和工件完整，才能关闭基础设施验收。
