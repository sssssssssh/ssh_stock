# A4235 PG17 校准能力与受控实验准备：推送前冻结交付记录

日期：2026-10-25。总体 **BLOCKED_WITH_EVIDENCE**，工具状态
**CAPABILITY_IMPLEMENTED_NOT_YET_PROVEN**。本文件不是真实性能、容量或发布收据。

## 基线与当前 Git 状态

基线 `7681b57b68aa2f402e1bac2dc59ade606700f759`：HEAD/origin/master/GitHub master 一致，开工干净。
用户本轮明确回复“允许分阶段提交并最终推送一次”，范围仅新a4235模块、测试与文档，
不修改旧Reviewer、生产或工作流，不执行真实探针。该Git授权不批准G1/G2/G3。
按文档冻结→离线工具/测试→验收文档分三提交，不改历史，最终只push一次：

1. `da72e6dd1f4fb9387caa078906ddfc48dbbb272c`：W00回执/基线与W01协议决策包冻结。
2. `6b5836c774a4486728e7c3527e8692e8d87107f1`：八个离线模块与221项新单测。
3. 本文件所在的最终文档提交（以`git rev-parse HEAD`及最终对话回执为准）。

本文件冻结于最终push之前，不能提前写“新SHA CI已成功”，也不把基线CI冒用为本轮。
最终SHA、真实CI/jobs/artifact审查在最终对话回执和独立本地审查补记中交付；
不为追写自身SHA或未来CI事实增加第四次提交/第二次push，不dispatch/rerun/cancel。

冻结定义见 a4235_baseline_freeze.md。完整 baseline 受保护 ls-tree 原文 SHA256：
`b7aecb955fb32bf285ae71ff3bdf6cfdc6aa15828e70bb46c507d31bfc1418e9`。
W01 决策包固定 SHA256：`84b572e71d1bc92ad58da105a8333d57e3d42b2d32db1102c234e63bbcea5c87`。
八个新模块已提交文件映射摘要：`694f946eda5f239c74dbbf21ee638428989ad90e807ce6be10c479251253640e`。
对应源码提交6b5836c；第三次仅文档，不改变上述源码摘要。
旧协议、两个源文件及全部生产/工作流原字节检查通过。

## W00—W08

| 包 | 状态 | 实际证据与停止线 |
|---|---|---|
| W00 | DONE（遗留问题 OPEN） | 真实日志与4个下载ZIP/hash，追加 a42342_final_review；旧Reviewer缺口如实保留 |
| W01 | DONE | A/B/C、16/32互斥固定提案、原8次、三道人审冻结；不自行批准 |
| W02 | DONE 离线 / BLOCKED 实机 | Git/static、fixture/角色/grant反例，live无条件拒绝；无真实签名/消费/harness接入 |
| W03 | DONE 模型 / BLOCKED 实机 | psycopg3.3.4纯缓存、假cursor、同session和计数检测；C0/C1/cached未证明 |
| W04 | DONE 模型 / BLOCKED 实机 | CPU身份/namespace/clock与资源scope反例；真实CPU不可用，不部署helper |
| W05 | DONE 合同 | 四表与事件漂移、v3长窗/失败前缀/短窗阻断；没有真实长窗或连续采样 |
| W06 | DONE 离线骨架 | 四typed JSON、独立expected、新目录/manifest最后、固定错误、CLI恒非零；没有128点方法 |
| W07 | PARTIAL（等待CI） | 新增221项通过；全量单元结果见下；最终SHA完整PG/前端/容器/浏览器CI待push后核对 |
| W08 | PARTIAL（等待CI） | 文档/矩阵齐备，Git授权已取得；本文件不预先宣告最终同SHA CI通过 |

## 测试命令与真实执行

全部本地测试用不可达 loopback synthetic DATABASE_URL，测试启动前将 Settings.env_file 设为 None；
不读取业务 .env、不连接真实PG、不启动服务。使用原 scripts.a42331_pytest_safety 去敏插件。

```bash
python -m pytest tests/unit/test_a4235_pg_identity.py tests/unit/test_a4235_measurement_contracts.py tests/unit/test_a4235_capability_review.py -q -p scripts.a42331_pytest_safety --tb=no --show-capture=no -rN
python -m pytest tests/unit -q -p scripts.a42331_pytest_safety --tb=no --show-capture=no -rN
python -m ruff check backend tests migrations scripts .github/actions
git diff --check
```

实际通过：新增221项（定向5.81s）；本轮重新执行全量单元2731 passed、5个既有弃用warning（78.92s），
0 failures/errors/skipped。源码提交6b5836c上验证完成，第三次仅文档。
上一轮全量2730 passed、5个既有弃用warning（77.68s），不是新增fsync反例后的最终结果。
Ruff通过。所有正式绿色定向结果均0 failed/errors/skipped。
早期214项通过；新增“冻结新增生产文件/整线程区间”2个负例先失败，修复后216项通过；
再新增“manifest后超时/cleanup-only首错/失败快照超计划及非末点partial”4个负例先失败，修复后220项通过。
授权提交后复核新增“manifest本身fsync失败”反例：先1 failed，再将manifest自有inode记录提前到
写入/同步前，使同步异常也撤销manifest，随后221项全部通过；首错收据不被覆盖。
中间全量2726 passed、5个既有弃用warning；不以该中间结果替代最终版本。
未删除或放宽原319/109/241用例；本轮不重跑任何真实实验来追求PASS。

## AT01—AT30 逐项对应

以下 PASS 仅指指定离线/Mock合同，不代表同编号物理事实已实测；G1实机项均 NOT_RUN。

| AT | 本地状态 | 用例/证据 |
|---|---|---|
| 01 | PASS | 真实基线引用/干净树、旧日志/ZIP/追加回执；遗留Reviewer OPEN |
| 02 | PASS | frozen_files、旧 definitions20文件、8次/128点/64对、两个源文件SHA |
| 03 | PASS | Decisions 禁止A/B/批准自升态 |
| 04 | PASS | 固定16/32候选、禁止动态预算/retry |
| 05 | PASS | full SHA/run/attempt/source/schema、dirty/remote/frozen反例 |
| 06 | PASS MOCK / NOT_RUN REAL | DSN/env/proxy/公网/已有库/非精确loopback/owner反例 |
| 07 | PASS MOCK / NOT_RUN REAL | marker/system/container/nonce/PGmajor/cleanup链反例 |
| 08 | PASS MOCK / NOT_RUN REAL | root/角色/创建/维护/信号/DML/DDL等13种越权 |
| 09 | PASS MOCK / NOT_RUN REAL | profile/scope/nonce/过期/consumed/预算；签名和持久单次性明确未证明 |
| 10 | PASS | 原文件完整冻结，新生产文件同样拒绝，原workflow未改 |
| 11 | PASS DRIVER MODEL | 纯PrepareManager第6次、两个SQL和OID分键，不连接 |
| 12 | PASS MOCK | exact FakeCursor、session/PID/start/generation/key |
| 13 | PASS MOCK | transaction pool/checkout/连接重建等反例 |
| 14 | PASS MOCK | 缺行/驱逐/名称/计数/模式/未知反例 |
| 15 | PASS NOT_PROVEN | 强制cached结构未验证，不从计数推导结构 |
| 16 | PASS NOT_PROVEN | synthetic白名单拒业务SQL，C0_C1_NOT_PROVEN |
| 17 | PASS MOCK / NOT_RUN REAL | PID reuse/namespace/container/clock/权限映射反例 |
| 18 | PASS MOCK / NOT_RUN REAL | 零/负/身份/分母，真实availability恒不可得 |
| 19 | PASS MOCK | 五scope/source/unit/whole-worker interval/GC阈值 |
| 20 | PASS MOCK / NOT_RUN REAL | 四表OID/统计/索引/列/设置/模型/SQL/fresh独立漂移 |
| 21 | PASS MOCK | 维护/unknown/ambiguous/churn停止，NOT_OBSERVED不证明无事件 |
| 22 | PASS MOCK | 长窗tick/250ms/100ms/25ms/join2s和OFF反例 |
| 23 | PASS MOCK | 短窗/缺后窗BRACKET_UNCOVERED，不延长lookup |
| 24 | PASS MOCK | sticky首错/清理4码+遗漏/稳定末点/manifest前后超时与fsync失败关闭 |
| 25 | PASS | 重hash伪造/错身份/独立expected/缺多文件/重复键/NaN/Inf/越界/symlink/FIFO/大小 |
| 26 | PASS | 所有准入位false，READY伪造拒绝 |
| 27 | PASS | 两CLI子进程未知execute/approve/force/token/repeat/budget等均exit1 |
| 28 | PASS NOT_RUN | 无DB/network/线程/GC导入，硬拒绝live，不创建表或执行SQL |
| 29 | PARTIAL（等待CI） | 本地原unit回归；原319含PG17集成，完整同SHA CI待唯一一次push后核对 |
| 30 | PENDING 新SHA | 旧baseline已核对，最终SHA在最终回执实际核对，不预写PASS |

## 基线 CI 与原始工件（仅基线）

[主CI40070964756](https://github.com/sssssssssh/ssh_stock/actions/runs/40070964756)：
test120804096889 / attempt1 / 3337 passed、674warnings / 89.28%。
[专项40070964706](https://github.com/sssssssssh/ssh_stock/actions/runs/40070964706)：
contracts120804096584 / attempt1 / 319、109、241 passed。
4份实际ZIP的完整命名规则、ID、SHA及核对层级见a42342_final_review.md；其他工件只metadata。
新A4235不接入正式Gate、不修改任何workflow；未来正常主CI的全量pytest会包含新unit，
专项保持原微型和旧计数，不能借新增合同自动运行实机probe。

上一轮工作树已实际生成本地纯MOCK原始工件（ignored、不提交）：`.codex_tmp/a4235-offline.EdiECy/`。
该目录的bundle是4个typed JSON；独立离线审阅实际返回exit3 / CAPABILITY_VALID_NOT_AUTHORIZED。
另有prepared_capability.json，输入为本轮单元假session/snapshot，输出DRIVER_MODEL_ONLY，不是真实prepare。
这些是run_id=local、源码摘要c5b60f7的旧工作树开发工件，保留不重签，绝不是最终新提交的GitHub工件。
最终HEAD的独立本地Mock样本将新建独立目录，仅用于合同审查，仍不是实机或GitHub采集工件。

| 文件 | 实际文件SHA256 |
|---|---|
| bundle/capability.json | 812798245638063a70ca27e3ee02b221a6c53daaadcf26393f5ee1393dae488b |
| bundle/limitations.json | 7eb444c7e49de556bb286794ec82f60f591cd12a8a42ac7a202458cf4ae13726 |
| bundle/failure.json | 0c899069c890731eadabc276a7359d01111be85c5e9e3e33619b539352a62d4b |
| bundle/manifest.json | 0f32e19f143c5bb4885822b85dd2ec63a8f123dd2cb2cc2103eb9be8e32abff4 |
| prepared_capability.json | 3dcd0bf2c9871666b141670528a1ffd6be19dadb762fca526126e9fc3d596cfc |

## 变更文件与用途

- scripts/a4235_calibration_adapter_contract.py：严格身份、安全位、状态、决策、四工件和拒绝real骨架。
- scripts/a4235_pg_identity.py：模拟fixture双身份/最小角色/独立grant合同。
- scripts/a4235_capability_guard.py：Git/packet冻结、完整SHA/dirty/ambient拒绝、静态CLI。
- scripts/a4235_prepared_probe.py：两种通用synthetic模板、假cursor安全投影、同session/计数检测。
- scripts/a4235_resource_bridge.py：模拟CPU生命周期/时钟桥及进程/整线程/RSS/GC口径。
- scripts/a4235_environment_probe.py：四表与独立数据/统计/模式/计划/维护摘要。
- scripts/a4235_observer_bridge_contract.py：新版Mock长窗、tick前缀、bracket、join/cleanup闭环。
- scripts/a4235_capability_review.py：安全新建、严格离线工件审查与非零CLI。
- tests/unit/test_a4235_pg_identity.py、test_a4235_measurement_contracts.py、test_a4235_capability_review.py：221项新回归。
- docs/acceptance/a42342_final_review.md：只追加旧CI真实回执与未关闭缺口。
- docs/acceptance/a4235_baseline_freeze.md、a4235_protocol_decision_packet.md：基线/协议冻结。
- docs/acceptance/a4235_capability_matrix.md、a4235_capability_limitations.md、a4235_observation_feasibility.md：能力/局限/可行性。
- 本文件及README/PROJECT_RULES/PRD/系统设计：本地交付状态与长期安全边界。

## 最终回执与未完成项

```text
任务：ssh_stock A4-2.3.5
基线SHA：7681b57b68aa2f402e1bac2dc59ade606700f759
最终SHA/commit列表：上述两提交+本文件所在最终文档提交，最终SHA在对话回执实际填写
主CI/专项/工件：推送前PENDING，最终在对话/独立审查补记实际核对；基线见上
PG17 synthetic capability probe：NOT_RUN，G1未授权
prepared：DRIVER_MODEL_ONLY / C0_C1_NOT_PROVEN
backend CPU：METRIC_UNAVAILABLE
cached plan结构：NOT_VERIFIED（未调用EXPLAIN EXECUTE或任何真实SQL）
G2：PENDING，A/B未批准、C默认继续停止
G3：NOT_AUTHORIZED
128点真实性能校准：NOT_RUN
生产数据/业务数据库/云环境：NOT_TOUCHED
execution_enabled/performance_eligible/capacity_ready/production_read_authorized/attribution_authorized：false
unique_repair_candidate：null
```

推送前剩余：最终提交/同SHA CI；长期未关闭：旧Reviewer独立修复授权、G1受信fixture/签发/消费/清理链和实际最小权限；
真实同session prepared、无扰动cached结构、CPU namespace/时钟映射与长窗bracket可行性。
G1/G2/G3不得互相替代。请先审阅矩阵并独立裁决A/B/C；任何真实探针仍需后续明确的小范围批准。
本轮在离线准备阶段停止，不进入C1生产优化、A4-3或阶段B/C。
