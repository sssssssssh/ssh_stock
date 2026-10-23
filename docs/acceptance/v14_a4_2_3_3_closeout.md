# A4233 W00–W05 交付记录

## A4233.1 追加说明（保留以下历史事实）

基线7bc2974主CI重复的M16.5失败已在双验证独立PG17复现：全局SessionLocal固定A而
Settings缓存重建使Alembic改连B，A提交归档在新连接可见，B空库guard正确返回false。
本轮不修改生产迁移，改用owned UUID fixture与显式Session/connection身份核验；
补observer v2稳定快照/有界停止、主线程signal限制和安全完整JUnit工件。
本轮对ci.yml test job的精确例外取代以下“原五workflow完全不变”的未来约束，
但所有正式Gate/昂贵触发/旧协议/policy/one-shot仍冻结；历史manifest原字节保留。
最终主CI与专项必须同SHA重新验收；本报告旧绿灯不能替代。
实施与实际测试、未关闭项见[a4233_1_ci_remediation.md](a4233_1_ci_remediation.md)。

状态：**OBSERVER_IMPLEMENTED_CONTRACT_PASS（仅低成本功能合同；非性能/因果/发布认证）**。
基线73a3273301502822dc7a881a64dfdca45db4d063，master；未授权性能测量。
本文件只记录新观测能力，不更新旧A4231/A4232协议、工件、报告或一次性授权记录。

## 工作项与实现

| 项 | 交付 |
|---|---|
| W00 | a4233_baseline_and_contract.md、evidence/a4233_frozen_manifest.json；历史身份/冻结hash/权限与禁区 |
| W01 | a4233_background_observer.py；独立只读连接、固定SELECT/PG17精确字段、受限权限/双身份、四表及目录索引/TOAST映射 |
| W02 | a4233_observation_contract.py；typed/extra-forbid、单调/UTC/DB时钟、PID复用/跨视图矛盾、事件分类、部分记录、清理失败关闭 |
| W03 | 新unit与微型PG17测试；不调用lookup或seed，四空关系，每个成功用例3ticks，故障可0ticks |
| W04 | v14_a4_2_3_3_observation_protocol_draft.md；DRAFT/未批准，校准与归因分开，候选预算/样本/门槛仅提案 |
| W05 | 新a4233-observer-contracts.yml，唯一contracts job；原五workflow/policy/Gate未改；补登记清单/静态测试 |

复用verified_test_url/isolation与atomic、自有容器清理；不调用旧owned/statistics_snapshot的
DDL/统计刷新行为。管理员测试fixture在新UUID库显式创建并清理受限合成角色，observer无授权能力。
代码不读取环境DATABASE_URL/.env、不导入业务服务；只读URL显式且只允许本机合成目标。

## 实际验证（开发中记录，不预写通过）

- 首轮本机目标测试收集因psutil未安装失败，已移除未声明依赖，复用原RSS helper；未改依赖文件。
- 初次unit 82 passed/1 failed：SQL静态测试把has_table_privilege的权限名字符串误识别为命令；
  改为检查SQL可执行token，仍禁止全部写/维护/控制语句；没有降低只读约束。
- 首轮相关259项/全unit2118项各有1项失败：原治理清单拒绝第六条workflow；
  仅登记新contracts-only例外并保持未知workflow仍拒绝，原昂贵workflow断言全保留。
- 修正后相关命令：`python -m pytest -q tests/unit/test_a4233_background_observer.py tests/unit/test_tail_stability_a4232.py tests/unit/test_a4_ci_governance.py`，259 passed，exit0（3.07秒，无DB）。
- `python -m ruff check backend tests migrations scripts .github/actions`：exit0。
- 本机`docker info --format '{{.ServerVersion}}'`：exit1，daemon未启动。
  本地微型PG17为NOT_RUN，未借用业务库；真实PG17结果只以本提交新contracts CI为准。
- 全unit安全包装：2118 passed、两个既有Starlette弃用警告、27.22秒、exit0，无DB。
- 全范围Ruff exit0；冻结文件逐字节/哈希检查在259项相关测试内通过；未运行本地默认全pytest/业务.env。
- 最终diff/新PG17/CI结果待推送后追加，不把本机unit当数据库或性能通过。

完整unit包装（合成不可连接loopback，只运行unit，不启动服务）：

```bash
env -u LLM_ENABLED DATABASE_URL=postgresql+psycopg://disabled:disabled@127.0.0.1:1/a4233_disabled_test TUSHARE_TOKEN=synthetic-a4233 python -c 'import sys; sys.path.insert(0,"backend"); from app.core.config import Settings; Settings.model_config["env_file"]=None; import pytest; raise SystemExit(pytest.main(["tests/unit","-q"]))'
```

## 工件与复核

新CI保存`.codex_tmp/a4233/micro/{manifest,observer-contract,ticks,review,failure}.json`，
每份绑定exact head/run/attempt/source/protocol/instance摘要，标SYNTHETIC_MICRO_SELFTEST/DIAGNOSTIC_ONLY。
manifest记录每个文件SHA256/大小、序列化wall、含重序列化的原子write wall；不可相加或冒充开销校准。
schema额外字段/哈希破坏/身份不匹配/缺tick/虚假COMPLETE/越权准入均拒绝。
合同状态仅COMPLETE_CONTRACT或INCOMPLETE_OBSERVABILITY，NOT_OBSERVED不证明无维护。
线程SQL异常、部分tick、SIGTERM、join/close/write异常保留，不上传原始driver异常或JUnit。
离线review CLI的六项身份由独立可信执行上下文提供，不能只信待审manifest自己的声明。
内容hash证明一致性，不提供对能同时重写工件与manifest的攻击者的密码学真实性担保。

## 变更范围与剩余项

新observer/contract/reviewer/test-receipt、unit/PG17测试、独立contracts workflow、W00/草案/本报告/hash清单；
更新四权威Markdown、workflow inventory及其单测。backend/config/migrations/frontend、所有旧脚本/
协议/原始证据、原workflow、governance policy/consumed记录和Release Gate保持基线。

本轮不捕获新真实autovacuum性能事件，不证明监控开销已合格、不校准、不修复C1、不做P95/L2；
未访问阿里云/ECS/RDS、业务数据库/任务/服务。旧64/128结论不变、未补样。
管理员需在未来独立受信任合成环境预置所列受限权限；无权限时INCOMPLETE而非自动GRANT。
新预算只是待审草案，后续profile、开销校准/归因/生产均NOT_AUTHORIZED。
performance_eligible/capacity_ready/production_read_authorized恒false，unique_repair_candidate=null。
完成本阶段后停止等待用户代码审阅。

## 推送后实际PG17实证（首版，不冒充最终HEAD）

实现提交 `d086e77977caa5a1dd9d39a3b7ca0ccef23b6f5e`，master，已推送。
[新contracts run39952363025](https://github.com/sssssssssh/ssh_stock/actions/runs/39952363025)
/ attempt1 / job120409676526：**269 passed、0失败/错误/跳过、12.16秒、exit0**；
包括86个新unit、7个新微型PG17用例及176个原A4232/governance合同，Ruff/自有清理成功。
PG17.11真实字段/类型、四空表与INDEX/TOAST/TOAST_INDEX映射、受限角色/缺权限/错误双身份/
超级账号拒绝均实测。成功自检3ticks，无lookup、seed或真实维护负载。

[原始工件12501265908](https://github.com/sssssssssh/ssh_stock/actions/runs/39952363025/artifacts/12501265908)
ZIP SHA256 `bc138d6f9b2b286463f73ee190fbac195d8eda8efd0f47ef7d840beaa5abae65`，
已下载比对API摘要、离线复核manifest各文件摘要/身份/typed合同，exit0。
observer-contract SHA256 `2be0a00b2c685a5e842203cf801550bbafd3d3777c7fef89828b33a4ededcdb2`；
ticks `9d87f154a7e66bc6e7e15150841c3577ddb103e4c21fd6e4b5cb4dea0da21bd1`；
review `56fde3de6c6fd1b8e1f8e335954f1a9e143b13505ae95f5ccb6746c1f8781489`。
实例摘要afac49a879d29c70292d0e93ad2e4405df74fed311ec1af258351ea7cdb45ec6；
草案摘要f72e4ea46ce1c077739a5d79719ed229ecaed4904319addffd0cf5293b0fde5a。
三个tick的SQL wall分别4.046392/3.385987/3.058868ms，总wall4.281900/3.730655/3.384199ms。
这只是空表功能自检的原始计数，**不是正式开销校准或性能对照，不能用于归因/准入**。

首版复查后最小补强：run_micro实际接入SIGTERM guard（新增回归）；
测试计数收据改用新a4233命名空间，复用旧计数解析/双身份构件但不再输出旧job_id；
测试管理员fixture的DB错误统一去敏。旧测量源/协议/policy/workflows未改。
最终复核补齐其他PG17后台进程的PID/起点/类型变动观测（不读取client会话），
类型/进程增减只标ENVIRONMENT_ACTIVITY_ONLY并停止，不猜测关系或维护操作。
补强前全unit2121 passed/25.58秒，接入SIGTERM后2122 passed/26.14秒，均exit0，两个既有警告。
新增命名空间测试后相关264 passed/3.15秒、完整unit2123 passed/26.65秒、Ruff/diff exit0；
最终提交CI仍需独立确认，不继承首版SHA资格。

首版普通push的原[主CI39952363024](https://github.com/sssssssssh/ssh_stock/actions/runs/39952363024)
仍在执行，lookup/audit/workflow合同已成功，authorize/归因/capacity跳过。
A4-1 run39952362842、A4-2 run39952362853、Publication run39952362980仅普通合同Job，
昂贵Job须dispatch，不触发新性能矩阵。最终完成情况另核，不调用dispatch/重跑/取消其他任务。

补强提交 `2e5c31a11687dd77da00570eab288083dafc0888`：
[contracts39953061434](https://github.com/sssssssssh/ssh_stock/actions/runs/39953061434)
/ attempt1，271 passed、7既有警告、8.95秒、exit0；Ruff/清理成功。
[工件12501137250](https://github.com/sssssssssh/ssh_stock/actions/runs/39953061434/artifacts/12501137250)
API ZIP摘要4cadc080d5ceb197800c67886196ec7e6f6dc1cb497dbe093f908ddbd9247128，
本处只记录API实证，不声称该ZIP已下载。
最后审阅新增后台类型变动回归、URL限定新UUID库而非任意_test库；本地相关测试和完整unit重新验证，
最终CI以该补丁所属提交为准，后续阶段仍未获授权。
该收尾代码本地相关266 passed/3.31秒、完整unit2125 passed/26.53秒（两个既有警告），
Ruff/diff均exit0；首版工件另从Git重建source/protocol hash、从测试双身份收据重建instance摘要后
独立复核全部文件hash/head/run/attempt成功（不是仅相信manifest自述）。

## 最终实现实证与 A01–A15

最终实现SHA `7d63fdbea97130a08949b6d72f49d51d7aafb3b8`，
[contracts run39953751615](https://github.com/sssssssssh/ssh_stock/actions/runs/39953751615)
/ attempt1 / job120414353827，**273 passed、0失败/错误/跳过，12.58秒，exit0**。
构成为90个新unit、7个新PG17用例、原A4232/governance176合同；Ruff和自有清理exit0。
PG17实际捕获的常驻类型有autovacuum launcher/background writer/checkpointer/
logical replication launcher/walwriter，3ticks未观察到维护进度或进程变动；不证明无维护。

[原始工件12501337815](https://github.com/sssssssssh/ssh_stock/actions/runs/39953751615/artifacts/12501337815)
ZIP SHA256 `e0b8908ef84faeb2f3722a387222f23d48c0b31b071c7f807a757b6cb42fdceb`，7046字节。
已下载、核对GitHub摘要、Git重建四源码/草案hash，独立对照测试证明的head/run/attempt/
instance摘要，全部bundle文件hash与strict离线review通过（exit0）。

| 文件 | SHA256 |
|---|---|
| observer-contract.json | c45044cd04f8c1a2b7eb51d803c2940344e0694c26d5f13103e65f4a44fbae1a |
| ticks.json | 1fa893d4924a96761d9ca196e6c5d4cd4e4320585802672974c461219f18d02c |
| review.json | 25627962ac83cd7c60065136f78ad7e0707099447a5b26de4f20958550f2c6fa |
| failure.json | fe58750842de1802ed4f246a1b5b837512e59e21f86eadd83e3fadbc97fbca67 |

新4源码聚合摘要35e0e94a30a624135e35f0b468ff476446330a505203e963d489a834584bffac；
草案摘要f72e4ea46ce1c077739a5d79719ed229ecaed4904319addffd0cf5293b0fde5a；
实例摘要49d8c165348f78256abb3d70209581fffc301315490bfbcd2501624500baa13b。

| 验收 | 证据/结果 |
|---|---|
| A01/A10/A13 | 基线、24个冻结文件hash和生产目录逐字节检查通过；原5workflow/Gate/policy/one-shot/生产未修改 |
| A02/A03/A05 | 真实PG17双身份/受限权限、明确SELECT、四空关系及其INDEX/TOAST映射合同通过 |
| A04/A06 | PID复用/跨视图矛盾/未知OID/其他数据库、monotonic/UTC/DB时钟注入回归通过 |
| A07/A08/A09 | SQL/tick/缓冲/线程/SIGTERM/首发与清理/写盘/Schema/哈希/隐私/虚假COMPLETE回归通过 |
| A11 | 本地完整unit2125；专项真实PG17合同273；Ruff/diff exit0；本地DB未运行 |
| A12 | 草案DRAFT，校准/性能/因果实验均未运行，所有准入false |
| A14 | 普通push；原授权/归因/capacity均跳过，未调用dispatch；原性能Job的事件条件字节不变 |
| A15 | 本报告列出源码/工件/CI/命令/退出码/剩余项；文档最终HEAD与远端一致性在交付时再核对 |

文档追补只记录已取得的实现SHA实证，不借旧SHA声明文档提交的CI也已完成。
截至2026-10-23 20:32（北京时间），[实现SHA主CI39953751782](https://github.com/sssssssssh/ssh_stock/actions/runs/39953751782)
完整test仍运行，lookup/audit/workflow-contracts成功；其余普通合同工作流部分仍运行。
未完成CI为NOT_VERIFIED，不是通过；最终文档SHA自己的新CI状态见最终交付，不继承旧SHA。

### 完整变更文件（仓库相对路径）

```text
.github/workflows/a4233-observer-contracts.yml
scripts/a4233_background_observer.py
scripts/a4233_observation_contract.py
scripts/a4233_observation_review.py
scripts/a4233_test_receipt.py
tests/unit/test_a4233_background_observer.py
tests/integration/test_a4233_observer_pg17.py
tests/unit/test_a4_ci_governance.py
docs/acceptance/a4233_baseline_and_contract.md
docs/acceptance/evidence/a4233_frozen_manifest.json
docs/acceptance/v14_a4_2_3_3_observation_protocol_draft.md
docs/acceptance/v14_a4_2_3_3_closeout.md
docs/acceptance/a4_ci_workflow_inventory.md
README.md
PROJECT_RULES.md
docs/股票机会发现系统_PRD_V1.0.md
docs/股票机会发现系统_系统设计_V1.0.md
```

剩余：新观测器off/on开销未校准，真实维护事件与lookup重合未测（均未授权）；
旧C1 P95失败/非GC反例/唯一修复候选仍INSUFFICIENT_EVIDENCE；完整整仓CI尚待真实终态。
没有新性能profile、Environment修改、正式实验、生产SQL/参数/数据/任务或业务库操作。
只完成W00–W05，停止等待本次代码审阅；不自动进入下一阶段。
