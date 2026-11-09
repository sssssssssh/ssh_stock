# P0_CI_W04A_HASH_01_DELIVERY_REPORT

## 范围、身份与纠错

基线 master / HEAD / origin/master / 实时远端：
`c238dbdada044ea6c3e1d9d6a048dc4926b69c29`。修改前无已跟踪文件差异，仅保留两个审阅 ZIP
与一个 Patch；没有清理或提交这些归档。本轮负责人明确请求“根据任务书修改，推送代码”，
覆盖本次三文件交付及普通 push 自动 CI；不授权真实实验或手工 rerun/dispatch。

上一轮将 error-0 警告误判成失败节点，现撤销该分析结论。重新只读检查原始日志得到：

| Run / SHA | 根诊断模块进度 | W04-A 进度 | 真实全量统计 |
| --- | --- | --- | --- |
| [42578748521](https://github.com/sssssssssh/ssh_stock/actions/runs/42578748521) / 8443b7cd | ..... [12%] | ...................F [89%] | 6392 passed、1 failed |
| [42591472675](https://github.com/sssssssssh/ssh_stock/actions/runs/42591472675) / e7b783ee | ..... [12%] | ...................F [88%] | 6437 passed、1 failed、1 skipped |

error-0 在随后 warnings summary 的 record_property/xunit2 警告列表出现，不是失败节点。
两轮已执行的五种根诊断场景通过；本轮不因旧错误归因修业务诊断或 Worker。
旧日志/工件与历史报告原件不改写，本报告明确替代其错误的节点归因。
两轮历史 A42331_JUNIT_SANITIZATION_FAILED 与后续证据不完整是独立事实，仍保留。

## W00：基线 CI 与 18 路径核查

基线 [Main CI 42620773042](https://github.com/sssssssssh/ssh_stock/actions/runs/42620773042)，
push、attempt 1、精确 c238dbda，核查时仍 IN_PROGRESS，最终 conclusion=null，记 CI_PENDING。
test Job 129172023655 正在 Step 24 全量 pytest；Step 23 targeted 已成功，后续安全收集步骤尚未运行。
dependency-audit、workflow-contracts、lookup-diagnosis 已成功；authorize、capacity、
lookup-tail-attribution、ui-visual-acceptance 已 skipped，不作通过。
运行中的 Job 尚无可下载最终日志（只读请求返回 404），没有据此推断 sanitizer 成败。
未手动重跑、触发、取消任何工作流。新推送与基线 CI 的最终结果在交付对话/仓库外回执按真实 SHA 记录，
不通过追填本文自身 SHA 追加提交。

W04-A 保护清单首次纳入 Git 的提交为
`8443b7cd524a6964b24cecd60df5be5b6c46783b`，用作本次不可变“首次受保护 Blob”版本。
逐文件进入项目的首次提交另列如下，不将文件诞生时的旧业务版本替代 W04-A 的冻结身份。
首次受保护版本到当前 HEAD 的 18 个 Blob 均逐字节相同；无冻结后内容变更，
无 AUTHORIZED_CHANGE_REVIEW_REQUIRED 项。14 个旧工作树哈希为完整 CRLF，另 4 个为 LF。
所有首次受保护 Blob 均为 LF，因此不存在需要额外接受的原始混合/CRLF Blob 分支。

以下逐项记录历史 SHA256、固定规范 Blob SHA256、HEAD 和工作树 SHA256。
LF/CRLF 两个固定锚点同时记录在测试源码；完整 Git Blob OID 与原始对照 JSON 保存在仓库外证据目录。

| 路径 | 原历史 SHA256 | 首次保护 Blob 的 LF SHA256 | HEAD SHA256 | 工作树 SHA256 | 原记录→工作树行尾 |
| --- | --- | --- | --- | --- | --- |
| docs/acceptance/BIZ_PERF_03_A_R1_LNX_W03_PREFLIGHT.md | 21e9f0acc048d1724be985b13667a2cd71572992096abea9d8fbd57699455c9d | 21e9f0acc048d1724be985b13667a2cd71572992096abea9d8fbd57699455c9d | 21e9f0acc048d1724be985b13667a2cd71572992096abea9d8fbd57699455c9d | 21e9f0acc048d1724be985b13667a2cd71572992096abea9d8fbd57699455c9d | LF→LF |
| docs/acceptance/BIZ_PERF_03_A_R1_LNX_W04_READINESS.md | 09ac6d54828cdc085e134c5a54f91e3a1efa8933d42dea1e9bc7ae3967370f0d | 09ac6d54828cdc085e134c5a54f91e3a1efa8933d42dea1e9bc7ae3967370f0d | 09ac6d54828cdc085e134c5a54f91e3a1efa8933d42dea1e9bc7ae3967370f0d | 09ac6d54828cdc085e134c5a54f91e3a1efa8933d42dea1e9bc7ae3967370f0d | LF→LF |
| AGENTS.md | 56fc204c15a6885649ff6dc65d470e9237c0ccb1e49dd14e4f69b58907054ba5 | 6ab8120da451af72d09aebbc3ccaa512841804b98aac292f94df3e5050111b37 | 6ab8120da451af72d09aebbc3ccaa512841804b98aac292f94df3e5050111b37 | 6ab8120da451af72d09aebbc3ccaa512841804b98aac292f94df3e5050111b37 | CRLF→LF |
| PROJECT_CHARTER.md | adb7899d0b4c475e16da61cb70fb019e8aa310769eb6c35610b1f304cbc7e19f | adb7899d0b4c475e16da61cb70fb019e8aa310769eb6c35610b1f304cbc7e19f | adb7899d0b4c475e16da61cb70fb019e8aa310769eb6c35610b1f304cbc7e19f | adb7899d0b4c475e16da61cb70fb019e8aa310769eb6c35610b1f304cbc7e19f | LF→LF |
| PROJECT_STATUS.md | 0387567183f3480d2c2205244fedd081f7b9cc43566b4b0e1c262b3d82fe3029 | 68616b6f2d6450dda8f6646b3ae4ab66598db63ae4747296f0214603111e1790 | 68616b6f2d6450dda8f6646b3ae4ab66598db63ae4747296f0214603111e1790 | 68616b6f2d6450dda8f6646b3ae4ab66598db63ae4747296f0214603111e1790 | CRLF→LF |
| PROJECT_ROADMAP.md | e3dce0289ea90ce2424c6a172969f64aa8d6f6396781e05f1ada5abced1295c5 | 378f9a911ac2dac0b93c8c0e633694bcfe91b93170aa13ea42bf45e13842e0b8 | 378f9a911ac2dac0b93c8c0e633694bcfe91b93170aa13ea42bf45e13842e0b8 | 378f9a911ac2dac0b93c8c0e633694bcfe91b93170aa13ea42bf45e13842e0b8 | CRLF→LF |
| DECISION_LOG.md | a4ea4f4d6fa997821b5155cfa2af75ad6537c80cd6898c560491ab27c29094d1 | 87b4861d05b67ecb5f03ca6de44f860fa33236d3434c9a109f07b30674da481b | 87b4861d05b67ecb5f03ca6de44f860fa33236d3434c9a109f07b30674da481b | 87b4861d05b67ecb5f03ca6de44f860fa33236d3434c9a109f07b30674da481b | CRLF→LF |
| docs/tasks/README.md | fe5e71a7a73055859b8d21efbbf60fd86a5176674ee495a94a26941e22b9eed9 | 6c633a682f8fda47dfd867c22f79b4f5a054964374e5ff7dc009bea04ee72307 | 6c633a682f8fda47dfd867c22f79b4f5a054964374e5ff7dc009bea04ee72307 | 6c633a682f8fda47dfd867c22f79b4f5a054964374e5ff7dc009bea04ee72307 | CRLF→LF |
| backend/app/models/market_data.py | d798f2486ca8880e5128ba3383effa72e8d950b24f34ee543add71914955bc77 | c0207d196fb9777bfd5c83284ca9d36f5b2cbf9ea5191ca149fbce9afcee9261 | c0207d196fb9777bfd5c83284ca9d36f5b2cbf9ea5191ca149fbce9afcee9261 | c0207d196fb9777bfd5c83284ca9d36f5b2cbf9ea5191ca149fbce9afcee9261 | CRLF→LF |
| backend/app/models/job.py | dc213147ea1516797b6cae2b944cc771668263df81333ed023478669df68e950 | fc795d1d4fb92ff3b8a10d41e19898e392e236ca84c661e78dfa2b02519ecc11 | fc795d1d4fb92ff3b8a10d41e19898e392e236ca84c661e78dfa2b02519ecc11 | fc795d1d4fb92ff3b8a10d41e19898e392e236ca84c661e78dfa2b02519ecc11 | CRLF→LF |
| backend/app/models/data_publication.py | 79e8df3a75f32c0468a427e2dd78fc66162186dc27579f41d8aee421d13d129f | c9163a6e8386404d3b9faf9eaa1bf064d4a476b986e8fcc452ba9ce382aca63c | c9163a6e8386404d3b9faf9eaa1bf064d4a476b986e8fcc452ba9ce382aca63c | c9163a6e8386404d3b9faf9eaa1bf064d4a476b986e8fcc452ba9ce382aca63c | CRLF→LF |
| backend/app/models/data_schedule.py | b6c18834bf1dbc3bca50288b99889712639747d68055aee2fed0b69d8ff0ecb3 | 1c02583b6d8b455be81a3fc7f34c7aa93c167a6e516395e6688c24939fdf48c2 | 1c02583b6d8b455be81a3fc7f34c7aa93c167a6e516395e6688c24939fdf48c2 | 1c02583b6d8b455be81a3fc7f34c7aa93c167a6e516395e6688c24939fdf48c2 | CRLF→LF |
| tests/integration/test_business_recalc_performance.py | c6cc8cf4145d3dbefd259417e08c06ac7470a39adeca654ce9fe2f5483f2ba27 | c6cc8cf4145d3dbefd259417e08c06ac7470a39adeca654ce9fe2f5483f2ba27 | c6cc8cf4145d3dbefd259417e08c06ac7470a39adeca654ce9fe2f5483f2ba27 | c6cc8cf4145d3dbefd259417e08c06ac7470a39adeca654ce9fe2f5483f2ba27 | LF→LF |
| tests/integration/test_perf03_root_diagnostics.py | 5f6ac7c5c063a60cf06ac6edfbd739e548bea58c58b000f1657b43e4a5f81a4f | 7f9a5a16e19d64e7215466e8593f9fad3e1ab630a23cd036d087fba81fb9683a | 7f9a5a16e19d64e7215466e8593f9fad3e1ab630a23cd036d087fba81fb9683a | 7f9a5a16e19d64e7215466e8593f9fad3e1ab630a23cd036d087fba81fb9683a | CRLF→LF |
| scripts/business_recalc_measure.py | 49a10219c68a19406bd0cf4720400c99d82277e9db20bde411dd7bddafae2475 | edbd4b0d290fdf41ace88f2d8b15fb395c86eed2a7ae99daad5814975d114108 | edbd4b0d290fdf41ace88f2d8b15fb395c86eed2a7ae99daad5814975d114108 | edbd4b0d290fdf41ace88f2d8b15fb395c86eed2a7ae99daad5814975d114108 | CRLF→LF |
| config/strategy.yaml | bb824f8a3ef90442eafc8d0dae7796bc3d9992f671c6d06733975c7f877ce28b | 2ac50c63f3b522ae84e97dad2c9eb2eabd2206c224cea25f83d8d049e7d2864b | 2ac50c63f3b522ae84e97dad2c9eb2eabd2206c224cea25f83d8d049e7d2864b | 2ac50c63f3b522ae84e97dad2c9eb2eabd2206c224cea25f83d8d049e7d2864b | CRLF→LF |
| requirements-biz-perf-linux-py312-v1.lock | b87f3582f3d20814dd42146fde807709526764ff0d8b6713683e5645c72b7fc5 | 88549dce3164364430e20970fa10eb2125b60ff05f456d7bef4474876a98dcfc | 88549dce3164364430e20970fa10eb2125b60ff05f456d7bef4474876a98dcfc | 88549dce3164364430e20970fa10eb2125b60ff05f456d7bef4474876a98dcfc | CRLF→LF |
| scripts/perf03_lnx_hard_watchdog.py | 7216e1475612f3ef688790b65d684d0a6fd15eb6ba02bed5f0d9960f78537e6d | 02d8c6f939c694410c04fb7bc449f030e0e2c8708c1c801b08e5a2eba5940454 | 02d8c6f939c694410c04fb7bc449f030e0e2c8708c1c801b08e5a2eba5940454 | 02d8c6f939c694410c04fb7bc449f030e0e2c8708c1c801b08e5a2eba5940454 | CRLF→LF |

| 路径 | 文件首次跟踪提交 | 该首次 Blob SHA256 |
| --- | --- | --- |
| docs/acceptance/BIZ_PERF_03_A_R1_LNX_W03_PREFLIGHT.md | 8443b7cd524a6964b24cecd60df5be5b6c46783b | 21e9f0acc048d1724be985b13667a2cd71572992096abea9d8fbd57699455c9d |
| docs/acceptance/BIZ_PERF_03_A_R1_LNX_W04_READINESS.md | 8443b7cd524a6964b24cecd60df5be5b6c46783b | 09ac6d54828cdc085e134c5a54f91e3a1efa8933d42dea1e9bc7ae3967370f0d |
| AGENTS.md | 6d7bd28ed9cd5ddb3a0b44f7f5aad04fca111bf4 | 5de7215cb68fd485a52097c234b8aea334c096c7097b54fd566492ce6916cb5b |
| PROJECT_CHARTER.md | 31bf700c77b86fcb9be59787a0bde76d6f7d85bd | adb7899d0b4c475e16da61cb70fb019e8aa310769eb6c35610b1f304cbc7e19f |
| PROJECT_STATUS.md | 31bf700c77b86fcb9be59787a0bde76d6f7d85bd | 28849c7eacaf47489ac236ba972b3239a00b5b964b68bccfe76b8e33eb8e3045 |
| PROJECT_ROADMAP.md | 31bf700c77b86fcb9be59787a0bde76d6f7d85bd | bcd1e27a669b5c50d3e4edaaa9818b467f8f60a9608afbb34d0caf52665427a3 |
| DECISION_LOG.md | 31bf700c77b86fcb9be59787a0bde76d6f7d85bd | c592d828f1b302f241c2bad7202054ea491911f5696206288c1e106d1d9a9578 |
| docs/tasks/README.md | 31bf700c77b86fcb9be59787a0bde76d6f7d85bd | daff40abd68c2d4eb9db5f2399bdfe66ece440dfff9ce7b150ec7f2cebcdfff9 |
| backend/app/models/market_data.py | 78c3533ce803e95138264e94d066a103747d8013 | 8e2fb64eb37cdce5abb3a206535c64ab3bb9d4e28f3d8c64fab4e942e020dd31 |
| backend/app/models/job.py | 78c3533ce803e95138264e94d066a103747d8013 | 091e7649fb8e95f3076a498d3fcd62c0517858dfa1ca0d96e5d59003bdb29783 |
| backend/app/models/data_publication.py | 2114e47cec3d0f2f2c2d256e23e3840202c38864 | c9163a6e8386404d3b9faf9eaa1bf064d4a476b986e8fcc452ba9ce382aca63c |
| backend/app/models/data_schedule.py | 2114e47cec3d0f2f2c2d256e23e3840202c38864 | 1c02583b6d8b455be81a3fc7f34c7aa93c167a6e516395e6688c24939fdf48c2 |
| tests/integration/test_business_recalc_performance.py | 06b4cd6ee1783c399bdb89264c8da6190f282273 | c6cc8cf4145d3dbefd259417e08c06ac7470a39adeca654ce9fe2f5483f2ba27 |
| tests/integration/test_perf03_root_diagnostics.py | e610a92890d89f0b58f1de6335ae918da07d67d9 | 7f9a5a16e19d64e7215466e8593f9fad3e1ab630a23cd036d087fba81fb9683a |
| scripts/business_recalc_measure.py | 06b4cd6ee1783c399bdb89264c8da6190f282273 | d04dfcb101b599b5921db1f94eb36a07e8ec0468248b489d191cd9539eaa5811 |
| config/strategy.yaml | 78c3533ce803e95138264e94d066a103747d8013 | 5e5453f2c4c7daad2d17e8063a33c2d0dd9cb780fefd17f733c593e7a4d94d08 |
| requirements-biz-perf-linux-py312-v1.lock | 4fe37aee77570b3377fb5ff41b85ab9e49fbbcef | 88549dce3164364430e20970fa10eb2125b60ff05f456d7bef4474876a98dcfc |
| scripts/perf03_lnx_hard_watchdog.py | da15e71c9dbc206167f0551234f8b597d4bab3d6 | e52ad225e38e45dd8133d55d148e6def7bc2b1b8828aa8f1a181672e1d85f41e |

## W01：精确固定字节校验

仅修改原测试文件的 A20 文件哈希循环，并在同文件追加小型固定锚点表与校验函数。
原 PROTECTED 全部 16 个哈希保留原字面量；W03/W04 的两份 REPORTS 和原常量不变。
A20 对 18 个路径校验覆盖集合，检查历史哈希仍属于相应固定表示，再核查实际文件字节。

每个路径只有两个可接受的 SHA256：首次受保护 LF Blob，以及该 Blob 完整统一转换为 CRLF 的结果。
摘要是开发时从固定旧 Git 对象生成、逐项核对后写入的常量，不在运行时调用 Git，
不从 HEAD 或工作树反推“期望值”，不通过运行时 replace() 宽松容忍变化。
文件必须存在且 lstat 为普通文件，拒绝符号链接。混合换行、合法字符变化、空格、末尾空行、
BOM、NUL 和非预期 CR 无法匹配任一固定锚点，全部拒绝。

原 compare_plans、compare_synthetic_snapshots、read_safe 与无副作用断言保留。
其余 19 个 W04-A 用例及原辅助函数 AST 未变化。未修改原合同/业务代码/SQL/模型/迁移、
Supervisor、真实桥接、权限门禁、Workflow 或 sanitizer 严格计数算法。

## W02：RED / GREEN 与回归

本地目标 Python 3.12.14、pytest 9.1.1、macOS。命令使用原默认 source_contract_pytest，
组合回归另显式加载 a42331_pytest_safety。没有运行全量 pytest、PG17 或真实根任务。

- RED：原 A20 单节点，exit 1，1 failed；原始失败为 AGENTS.md LF 字节与 CRLF 历史摘要不符。
- GREEN：原 W04-A + 新行尾测试，exit 0，69 passed、168 subtests passed，0.81s。
- 最终组合回归，exit 0：**157 passed、734 subtests passed，43.80s**。
- 组合脱敏 JUnit：**891 testcase；tests=891、failures=0、errors=0、skipped=0**。
  顶层用例与 subtest 分开统计，不把 891 当作 891 个独立业务验收。
- 全库 Ruff：All checks passed!；目标 Python 编译两个测试文件通过；git diff --check 通过。
- 一次编译命令误用了系统 Python 3.9，因 match 语法拒绝；没有改动源码兼容旧版本，
  随后明确使用项目 Python 3.12.14 编译成功，不以系统旧版本失败作为项目目标结果。

| 组合中的模块 | 顶层用例 | subtest |
| --- | ---: | ---: |
| 原 W04-A | 20 | 168 |
| 新行尾完整性 | 49 | 0 |
| test_a42331_ci_evidence | 18 | 0 |
| test_a42331_failure_evidence_regression | 12 | 0 |
| test_r1_integration_pg_guard | 11 | 27 |
| test_r1_integration_pg_export | 12 | 530 |
| test_r1_integration_seed_loader | 10 | 7 |
| test_r1_integration_durable_owner | 8 | 0 |
| test_r1_integration_controller | 11 | 0 |
| test_r1_integration_linux_domain | 6 | 2 |
| 合计（一次组合，不与单跑相加） | 157 | 734 |

新 49 项包含每路径 LF/CRLF 两种表示（36项）、10类篡改（每类覆盖18路径）、
符号链接（18路径）、缺失/目录/未知路径，以及18项清单与无运行时 Git 依赖验证。
A01–A09 均覆盖；A10 原20项通过；A11 A42331 两模块全部通过且坏计数拒绝未变；
A12 原 R1 集成离线模块全部通过。真实 error-0 未重跑，既不需要修复也未获 PG17 运行授权。

完整命令、退出结果、原始 RED/GREEN 日志、脱敏 JUnit、完整 Diff、逐文件摘要和 Blob 对照
保存在仓库外私有 evidence 目录；本轮最终提交 SHA 与自动 CI 链接以交付时的真实 GitHub 返回为准。

## W03：范围与门禁

本轮仅三文件：

1. tests/unit/test_perf03_lnx_w04a_offline_contract.py：固定版本下的精确 LF/CRLF 字节保护。
2. tests/unit/test_w04a_line_ending_integrity.py：49 项离线正负测试。
3. docs/acceptance/P0_CI_W04A_HASH_01.md：本报告、纠错与逐项 Blob 证据。

没有修改两份旧 REPORTS、W04-A 原合同、PROTECTED 路径内容或其他历史证据。
没有改 backend/app、因子、Worker 事务、原 R1 Seed、生产 SQL、数据库 Schema、Workflow、
a42331_ci_evidence.py 或 a42331_pytest_safety.py。

本地修复状态 LOCAL_PATCH_VERIFIED；完整工程验收仍 CI_PENDING，不能以本地通过或旧工作流成功代替。
R1=PARTIAL，AC05=PARTIAL，REAL_PG17=NO_GO，REAL_WORKER=NO_GO，OFF_ON=NO_GO，
PERFORMANCE_ACCEPTANCE=NOT_MEASURED，experiment=NO_GO。
生产数据库连接、PG17 创建/连接、真实 Worker、OFF/ON、容量实验与部署均为 0。
交付后停止等待独立审阅，不自动追加修复或重跑 CI。
