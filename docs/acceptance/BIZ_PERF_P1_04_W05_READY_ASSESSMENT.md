# W05-READY 真实测试前缺口评估

2026-11-14；静态源码基线 `67d9b19cc19440ad91bd4562b9bc3eebf2077751`。
本轮仅完成决策准备，`ROOT_ATTEMPTS=0 / HOTSPOT=NONE_PROVEN`。
`B_GATE=NOT_APPROVED / TARGETED_PG17_GATE=NOT_APPROVED`，
`AUTHORIZATION=AUTHORIZATION_PENDING / BUDGET=DRAFT_NOT_APPROVED`。
本报告不是批准、现场核验或执行凭证。

## 一页优先级汇总

| 优先级 / 关键阻断项（五项） | 当前结论 | 负责人下一项决定 |
| --- | --- | --- |
| 1 新隔离资源及清理归属 | NOT_VERIFIED；无新实例、物理身份、独占卷/网络/cgroup/lease 的现场证据 | 是否提供全新 Linux x86_64/PG17 资源、具名归属核验人和人工结束方案 |
| 2 真实执行与测量接线 | NOT_VERIFIED；旧测量器有副作用且冻结，新入口恒拒绝真实执行 | 是否另立最小接线评审；当前不能直接复用旧入口或把 mock 换成真实 Executor |
| 3 时间、资源与成本预算 | OWNER_DECISION_REQUIRED；20min/末5min、CPU/磁盘/IO、成本及各准备步骤包含关系未定 | 明确 seed/迁移/预热/新资源创建是否计入及单列上限，不把它们藏在 root 之外 |
| 4 真实来源与单次身份 | NOT_VERIFIED；最终实施 SHA 的真实 CI、独立审阅、fingerprint、run UUID/唯一消耗尚无独立核验 | 固定精确版本、证据来源、操作人/窗口/验收人及完整原始证据留存 |
| 5 新的明确执行授权 | OWNER_DECISION_REQUIRED；本次仅离线开发，UNKNOWN_ACK 必须人工中止 | 独立审阅后由负责人决定是否另发单次真实测量请求；不得由本报告自动转执行 |

即使下面所有声明补齐，程序最多返回 `REVIEWABLE_ONLY`。这表示可供人工审阅，
仍有上述真实测试阻断项；结构通过不将任一真实事实改为 CODE_VERIFIED。

## 证据与现实缺口矩阵

每行分别记录 evidence_source、what_code_proves、what_requires_live_observation、
owner_action 和 disposition。CODE_VERIFIED 只指已静态核对的代码能力。

| evidence_source | what_code_proves | what_requires_live_observation | owner_action | disposition |
| --- | --- | --- | --- | --- |
| `scripts/biz_perf_p1_04_measure_wiring.py::OfflineRootRecorder.run_offline/_capture_root/freeze_root`；E02-R2 closeout | mock create/claim 前至 Worker 返回及 finally 后立即封闭 Wall/SQL/CPU；Worker 为 root 子区间，post 独立；后验和采集 reader 不回填根计数 | 真 Worker 的唯一返回、真实异常/取消/未知 ACK、实际原始前缀和后验边界是否接线正确 | 另审真实调用边界和失败前缀，保留唯一根，不叠加 root+Worker+post | CODE_VERIFIED |
| `scripts/biz_perf_p1_04_e03_collectors.py::CollectorPorts`；`measure_wiring.py::ProcessStats`；冻结 diagnostic 的 Replay | SQL 次数、driver FETCH、累计 CPU 差值、RSS 生命周期峰值各有离线合同；缺测 UNKNOWN/NOT_INSTRUMENTED，零 CPU 比率 UNDEFINED | 实际 reader 是否覆盖同根同进程，阶段 SQL/FETCH 的观测覆盖和成本 | 核实 reader 接线、来源和缺测，不用阶段和填补根级总 SQL 时长 | NOT_VERIFIED |
| E03 `validate_plan/OfflineGuard`；E04 `OfflineLeaseJournal/resource_decision`；E05 `audit_bundle`；各 closeout | 声明绑定、离线 receipt、文件日志/永久 UUID 占用、未知 ACK 和只读事故分类存在；mock 和默认拒绝语义可测试 | CI/审批签名来源真实性、资源所有权、跨机器唯一性和可信独立审计 | 独立核查来源、可信保存原始证据；保留 E04/E05 的人工中止，不重建审批平台 | CODE_VERIFIED |
| `scripts/biz_perf_p1_04_pretest_report.py::summarize_offline`；PRETEST-01 REPORT | 只读回放完整原始 fixture，区分 root/Worker/post，输出假设视图；合法 fixture 也能完全伪造 | 真实输入、资源和测量结果；离线自洽不证明来源可信 | 用报告定位待调查问题，不能从样本视图批准真实测试 | CODE_VERIFIED |
| `scripts/v14_test_database.py::verified_test_url` | 显式 TEST URL、环回、数据库后缀、PG17 major、UUID marker 和实际 system_identifier 一致才通过；会连接数据库，本轮未调用 | 未来实例是否全新、物理独占、没有旧/生产数据、网络/卷/权限安全及全流程归属 | 新资源须另批；不得把 loopback+marker+physical ID 当作独占和生命周期安全证明 | NOT_VERIFIED |
| E03 `_resources`；父任务 W05 及隔离申请草案 | Linux x86_64、PG17、新 PGDATA/新库、owner、卷/网络摘要、lease UUID 是 mock 必填声明 | PG 版本/镜像 digest、新 UUID marker、offline/online system_identifier、专用独占 PGDATA、卷/网络/cgroup/owner、唯一 lease 的实际观察 | 指定核验主体/观察时间、租约范围、归属证据和清理边界；不能复用既有 PG17 或旧测试库 | NOT_VERIFIED |
| 冻结 `scripts/business_recalc_measure.py::main`；`v14_test_database.py::isolated_v14_database`；W04A A20 | 旧入口调用真实 guard、CREATE、迁移、seed、create/claim/execute，最终 DROP；旧 03-B 是 4股/5000行/420秒专属协议；冻结不可改 | 与8股/20min新协议及独立新资源的接线、安全终止和后验是否相符 | 仅考虑下述静态最小插入点；不直接运行旧脚本、不修改冻结文件、不新增本轮适配器 | CODE_VERIFIED |
| 新 diagnostic/E02/E03/E04/E05 的拒绝入口与 RefusedExecutor | execute 恒 AUTHORIZATION_PENDING；默认 Executor/Inspector/Verifier 拒绝；新线无真实运行/清理接线 | watchdog/cgroup 强制、失联人工终止、真实采集、输出一致性和结束归属 | 先独立评审实际接线和失败处理；普通 CI 或离线 mock 不能补足真实执行能力 | NOT_VERIFIED |
| 父任务 W05、ISOLATED_RUN_REQUEST_DRAFT；E03 `seed_rows` | 900 **日历日**回看；start-900 至月底含两端为931日，665个合成 weekday×8=5320股日；逐表静态规则不同 | 真实生成逐表行数/摘要、benchmark_count、因子/派生及后验 quality 行数和耗时 | 不把900当真实交易日，不把5320当全部真实表行数；单独审批逐表预算 | NOT_VERIFIED |
| 草案预算；E04 `check_budget`；W05 `assess` | 固定草案20min、末5min、3GiB/4GiB/10GiB/10MiB；离线边界比较存在，无资源强制 | 新资源创建、seed、迁移和预热、root、post、cleanup 各自真实耗时；哪些纳入20min尚 UNDECIDED | 签认分段/单列限额和 CPU milli-CPU/磁盘/IO/导出/成本上限；root<15min仅是草案 | OWNER_DECISION_REQUIRED |
| 草案身份/审批项；E04 packet 来源绑定；W05 evidence/people 字段 | 检查同 SHA/run、具名字段、带时区窗口及 reference 是否存在/类型合规；不读 reference、不认证签名 | 负责人、操作人、验收人、清理人、成本承担人、真实窗口；最终实施 SHA 的主CI/A4-1/A4-2/Publication run/attempt/Job/Step、独立审阅及实际 config/strategy/dataset/business/逐表 fingerprint | 固定精确实施版本、核对真实 CI 和角色/成本/清理失败处置，制定原始证据留存；单次失败/超时/UNKNOWN_ACK 停止 | OWNER_DECISION_REQUIRED |
| PRETEST-01 H01/H02/H03；`backend/app/services/recalculation.py::run_recalculation`、factors/service、data_publication（仅静态） | 调查方向为输入读取/因子计算/候选 lookup及序列化写入/发布验证；输入复用 false 时通常不装配 FactorInputWindow，不能归因 `_verify` | 8股、2025-01、五OFF、一次真实根的 Wall/CPU/SQL/FETCH/RSS、完整输出和缺测位置 | 未测保持 UNKNOWN；inclusive 重叠不求和，无多样本不报P95/P99、优化提升、容量或生产资格 | NOT_VERIFIED |

## 未来最小接口评审点（仅静态设计）

真实接线若另获授权，应先审以下具体位置，无需另造身份、签名或审批框架：

1. 在独立真实资源建立/核验与 seed/迁移/预热结束处明确计时边界，分别提供可信来源和
   生命周期归属观察；旧 guard 是必要检查的一部分，不能单独签发执行或删除权限。
2. 围绕既有 create_recalculation_job → claim_next_job → execute_claimed_job 的一次调用，
   明确 root 起点和 Worker finally 后捕获点，复用 E02 快照合同；采集 hook、异常前缀、
   强制中止与预算强制须逐项评审，不能把 E03 MockLifecycle 替换成任意真实对象。
3. root 已冻结后独立读取终态/ledger/source/逐表摘要/公开结果及无 B 泄漏，再审已证明
   归属资源的人工结束接口。UNKNOWN_ACK/身份漂移/清理不确定时停止，不重试、不自动释放。

本轮没有实现或调用上述接口，也不提供带副作用的操作命令。五份 frozen、
E05/E04/E03/E02、PIT、250交易日预热、430日历日回看、500行批次、300秒发布预算、
原像/候选身份、质量和原子发布均保持原语义。

## 小型核验器的精确含义

`scripts/biz_perf_p1_04_w05_readiness.py::assess(request, expected_sha)` 仅接受固定键集。
申请结构由 `tests/unit/test_biz_perf_p1_04_w05_readiness.py::request_fixture` 示范：所有人名、
版本、资源 ID、摘要和来源均为内存构造的虚构数据，不交付看似已批准的实例凭证。

包括六个 timing 阶段：create、seed、migrate_warmup、root、post、cleanup。
每段显式 seconds/in_total/separate_limit_seconds；六段缺一即拒绝。准备三段可明确单列，
但须给出正的单列上限并输出 excluded_steps 和 SEPARATE_PREPARATION_BUDGET；
root/post/cleanup 必须计入。计入预算的 cleanup 前合计须<900s，cleanup≤300s，合计≤1200s；
实际可用 root 时间因此少于15min。具时区操作窗口还须覆盖1200s加单列上限。
这是保守的文书一致性约束，**并未替负责人选定真实计时方案**；实际纳入关系仍 UNDECIDED。

evidence 的 source/sha/run_uuid/reference 只作声明校验，GITHUB_ACTIONS 也是自述标签；
不查询 CI、路径、签名或资源，不能验证 CI SUCCESS、源认证或实际实例独占。
fingerprints 仅验证十六进制类型，不核对实际配置、策略或逐表内容。ACK 非 NOT_STARTED
即阻断；此纯函数没有历史状态/占用，不得用改写 ACK 声明恢复旧 run，E04/E05 的永久占用
及人工裁决语义仍有效。重复 JSON 键由有界 decode_request 拒绝，纯 dict 输入无法携带重复键。

可选唯一只读 CLI（FILE须为显式本地申请JSON）：

```text
python -B -m scripts.biz_perf_p1_04_w05_readiness review-offline --input FILE --expected-sha HEX
```

输入最多64KiB，复用原可信稳定祖先/no-follow/普通文件/单hardlink读取器；拒绝UNC、穿越、
`.env`和ADS路径。不自动寻找文件或读取环境/PG配置，不写文件，输出<64KiB的固定脱敏JSON。
不能证明恶意管理员、挂载替换或文件系统真实性；调用者负责本地、可信、稳定的祖先。
execute 或任意 --allow/--force/--permit 变体均在读取前固定退出2，授权保持待定。

下一步仅审阅[操作员待批清单](BIZ_PERF_P1_04_W05_OPERATOR_CHECKLIST.md)与
[本轮回执](BIZ_PERF_P1_04_W05_READY_CLOSEOUT.md)，由负责人独立作出批准/拒绝决定。
