# A4-CI-1.0 工作流盘点

## W00 基线

2026-10-23，master HEAD / origin/master 均为
`c076fa49fdd82ea07f5939f4ec6c190b1b19785b`，工作区干净。
已完整读取 `.github/workflows/` 全部 **5** 个文件及 `a421-pg` composite action。
以下是修改前清单，不根据旧运行状态猜测，也不授权执行任何性能命令。
没有 workflow_run、schedule、repository_dispatch、workflow_call 或 pull_request_target 触发链。

## 全量触发与依赖

| 文件 / workflow | 原事件 | 主要依赖 / 并发 | 风险 |
|---|---|---|---|
| ci.yml / CI | 所有 push、PR | audit/test/lookup 独立；capacity needs lookup；release needs test/capacity/lookup/audit，always | 高：lookup 120m/无上限 PG；提交消息可启动一次性实验 |
| ab-read-a4-baseline.yml / A4-1 read baseline diagnosis | master push、全部 PR、dispatch（无输入） | 单 isolated-baseline job，120m，无 concurrency | 高：同 job 先安全回归，再自动阶梯测量 |
| ab-read-a4-2.yml / A4-2 isolated read experiments | master push、全部 PR、dispatch（无输入） | contract-and-safety -> laboratory；两者 -> always gate | 高：21 分片，max-parallel 4，fail-fast false |
| publication-v13.yml / Publication V1.3 | master push、全部 PR、dispatch（无输入） | 单 candidate-performance job，330m，PG service 在步骤前创建 | 高：多规模/多重复/范围/键负载全部自动测量 |
| a4232-statistics-tail-diagnostic.yml | master 路径 push、路径 PR | contracts 15m -> attribution 30m；后者要求 push/master/attempt1/提交消息标记 | 高：普通提交标记即能激活实验；contracts 也使用 capacity PG |

A4232 路径过滤为自身 workflow、scripts/*a4232*.py、tests/**/test_*a4232.py、
docs/acceptance/*a4_2_3_2*。其他四个 workflow 没有 paths 过滤。

## CI 每个 Job

| job | timeout / 依赖 | 资源和实际命令 | 工件 / release 关系 |
|---|---|---|---|
| dependency-audit | 15m，无依赖 | Node22 npm ci / m17_1_dependency_audit；无 PG | a421-audit-SHA-attempt；必需 |
| lookup-diagnosis | 120m，无依赖 | a421-pg resource-class=capacity（无限额主机级）；lookup 单元/小型 PG 回归；下载 artifact12429939366 并运行 publication_lookup_tail_review_a423.py 离线复核 | a421-lookup-SHA-attempt；capacity_ready 输出与 release 必需；当前不是新性能采样 |
| lookup-tail-attribution | 30m，无 needs | push/master/attempt1/[a4231-attribution-once]；capacity PG；publication_lookup_tail_attribution_a4231.py 的 128 样本 | a4231-attribution-SHA-attempt；非 release 依赖 |
| test | 未单独设置 timeout | PG17 service stock_db，加独立物理标记 v14_test；完整 pytest/cov70/Ruff/迁移/容器/前端/浏览器；小型 ab_read_benchmark_v14.py smoke；M16/M17 合同测量不作正式 L2 | core、v14-read、data-queue、M16/M17 等；原 Core 步骤与检查必须保留 |
| capacity | 300m，needs lookup，capacity_ready=true 才运行 | 三等级 [L1,L2,L3-scaled-10pct]，独立 capacity PG，软预算270m；data_publication_capacity_v12.py --confirm-synthetic --level | a421-capacity-level-SHA-attempt；release 必需，不能将 skipped 算 success |
| publication-release-gate | 30m，always，needs [test,capacity,lookup-diagnosis,dependency-audit] | 严格同 SHA/run/attempt artifact merge；ci_release_gate_v14_a4_2_1.py publication | a421-publication-release-SHA-attempt；不得弱化 |
| ui-visual-acceptance | 30m，无 needs，限 codex/ui-visual-upgrade 分支/对应 PR | Node、静态完整性、coverage/build、五宽度浏览器；无 PG | ui-visual-acceptance-SHA；非本次性能链，保留 |

## 三条原自动性能链

| job | PG / timeout | 性能命令与负载 | 工件与风险 |
|---|---|---|---|
| A4-1 isolated-baseline | 固定 a4-isolated-pg17，2 CPU/3GiB，120m | ab_read_profile_v14_a4.py：10k、100k、2570000 public；multitable/service-control/monthly，串行三组 | v14-a4-baseline-SHA；原 workflow 缺 always PG 清理，无门禁依赖 |
| A4-2 contract-and-safety | 固定 a421-pg17，read 2 CPU/3GiB，45m | matrix 静态生成，contract-only，迁移和原安全/Golden/Worker 回归 | a421-contract-SHA-attempt；可以自动保留，不能代表实验完成 |
| A4-2 laboratory | 每分片 read PG，timeout 来自 shard.timeout_minutes（最长300m） | ab_read_experiment_v14_a4_2.py --scope matrix.scope --job-id matrix.job_id；21 分片覆盖冻结1002必需组+6对照；max-parallel4 | a421-job-SHA-attempt；always status/upload/清理；普通 push/PR 原来没有 if 限制 |
| A4-2 a42-acceptance-gate | 无 PG，30m | needs contract-and-safety/laboratory，always；严格 lab merge | a421-gate-SHA-attempt；实验 skipped/缺证据应继续失败 |
| Publication candidate-performance | PG17 service publication_v13_test；未设置 CPU/memory；330m | publication_candidate_benchmark_v13.py：baseline/current，1000/100000/500000 ×3，empty/existing500000，scope500000/1000000，keys500/5000/50000；publication_v13_receipt.py | publication-v13-SHA、publication-v13-junit-SHA；前置安全检查不等于测量获准 |

原 A4-2 各分片 timeout 和所有 group 键来自 `scripts/a42_ci_contract.py`，
不是本轮可调整的性能参数。实验源、预算、规模、门槛均不修改。

## A4232 与复用 PG Action

contracts：15m，Python3.12.15，a421-pg capacity；小型四表/自然 GC/计划统计与原 A/B 合同，
只上传脱敏 a4232-contract-SHA-attempt。attribution：30m，needs contracts，
publication_tail_stability_a4232.py，冻结协议 guard；a4232-attribution-SHA-attempt。
两者均 always upload/清理；旧一次性 ID 已被历史 run39833706083 消费，不能复用。
A4231 的旧 ID 亦已由 run39820748153 消费。

a421-pg 当前默认 read，capacity 分支不设置 CPU/memory，固定名字 a421-pg17、端口55440；
purpose/stage label、marker/独立 pg_controldata system ID 与 PG17 双验证先于 DDL。
资源标签必须保留，但固定容器名和无 run/job 归属验证的 docker rm 需要治理。

## W01–W05 目标对照（不是实跑结果）

- 五条 workflow 均保留普通自动安全/合同检查；昂贵 job 必须 dispatch、确认、完整 SHA、master、attempt1 和干净 checkout。
- A4-1/Publication 拆出 contracts；A4-2 laboratory 只在授权后执行，原 always gate 保留。
- CI lookup 缩为 read 级 PG 与固定历史离线复核；capacity 保留原 readiness 前提并额外要求明确授权。
- A4231/A4232 改为显式 dispatch + 固定一次性 ID/协议 hash；旧 ID 已消费，继续拒绝，不再由 push 标记启动。
- 高成本 workflow 共享跨 workflow 串行组，活动任务不自动取消；原 A4-2 分片内并行仍是已冻结协议的明确例外。
- 每个自建 PG 唯一名字、run/job/attempt label、always 归属校验清理；未批准 Environment 不得宣称人工审批生效。
- 原 release 脚本、阈值、1002组、全部容量等级、原始协议与历史文件字节保持；本轮不 dispatch 或重跑性能实验。

实现后的精确文件/合同测试/管理员配置与回滚见
[治理与验收](a4_ci_workflow_governance.md)。此清单保留基线事实，不覆盖旧实验 closeout。
