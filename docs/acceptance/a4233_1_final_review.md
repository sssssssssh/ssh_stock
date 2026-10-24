# A4233.1 最终审阅记录（A4234 W00）

状态：**CODE_ACCEPTED / PERFORMANCE_NOT_AUTHORIZED**。
本记录在5215145152ae732fdba2cc5104c022eb0bed2618基线上完成；开工HEAD/origin/master/远端一致、工作区干净。
2026-10-24重新读取同SHA主/专项CI及工件元数据，重新计算已下载ZIP与内部文件摘要，并以独立CI物理身份、
源码和草案指纹严格复核Observer bundle。验证级别 **OFFLINE_REVERIFIED**，不是UPLOAD_VERIFIED_ONLY。
原a4233_1_ci_remediation.md推送前PARTIAL记录保持不变；以下均为上轮构建后真实结果，不充当A4234校准证据。
本轮仅协议/工具准备，校准与归因仍未授权。

## 提交与根因

基线：`7bc29740948742bebee65e2e2a5814553fc41934`。

- A/P0：`273e13e70ae0f554fb5a313f37dbfb67f7d68ff6`，隔离迁移测试及根因证据。
- B/P1-P2/最终HEAD：`5215145152ae732fdba2cc5104c022eb0bed2618`，生命周期/快照/安全证据与文档。
- 推送分支master；本地HEAD、origin/master及远端refs/heads/master一致；工作树干净。

根因A：全局SessionLocal在导入时绑定A，而后Settings缓存/环境改变使未显式绑定connection的
Alembic连接B。复现中A提交后三个归档表为1/1/1，新连接可见；B空表真实0051 EXISTS均false。
不是0051漏保护，不修改生产迁移。新fixture仅在双验证PG17创建自有UUID库，ORM与Alembic
显式绑定同一已核验engine/connection；错库先拒绝、非空归档拒降级、空库往返、相邻约束均保留。
原历史CI具体最后环境写入者没有逐测试追踪，报告不把可复现机制冒称历史逐步轨迹。

## 最终同SHA真实结果

| 验证 | 实际结果 |
|---|---|
| [主CI39999398934](https://github.com/sssssssssh/ssh_stock/actions/runs/39999398934) | SUCCESS，attempt1，test job120571253954 |
| 主CI全量pytest | 2987 passed，0 failed/errors/skipped，674 warnings，1130.22秒，exit0 |
| 后端覆盖率 | 89.28%，原门槛70%未变 |
| 主CI新增定向 | 143 passed，34 warnings，23.43秒，exit0 |
| [A4233专项39999398924](https://github.com/sssssssssh/ssh_stock/actions/runs/39999398924) | SUCCESS，attempt1，job120571253194；319 passed，0失败/错误/跳过，34 warnings，37.02秒 |
| Ruff | 主CI与专项均exit0 |
| 迁移 | current=heads=0058_data_publication；所有生产迁移字节不变 |
| 前端 | 23个文件/162测试通过；语句覆盖率87.27%；生产构建成功 |
| 容器/浏览器 | compose config/build、队列双Worker验收、nginx校验、M16.6与桌面/窄屏可靠性浏览器检查均成功 |
| 本地（非CI替代） | 完整unit2160通过；原生PG17相关145通过；Ruff/diff通过 |

主CI lookup-diagnosis、workflow-contracts、dependency-audit、test全部SUCCESS。
authorize、lookup-tail-attribution、capacity、publication-release-gate、ui-visual-acceptance跳过。
[A4-1](https://github.com/sssssssssh/ssh_stock/actions/runs/39999398884)、
[A4-2](https://github.com/sssssssssh/ssh_stock/actions/runs/39999398974)、
[Publication](https://github.com/sssssssssh/ssh_stock/actions/runs/39999398947)普通合同均成功，昂贵任务跳过。
只进行了这一次最终SHA主CI验收，未dispatch/重跑/取消实验或改动one-shot记录。

## 原始工件与独立核验

以下ZIP已实际下载，核对GitHub API摘要并离线检查内容，非仅记录API自述。

| 工件 | ZIP SHA256 |
|---|---|
| [安全完整JUnit/失败收据12523320946](https://github.com/sssssssssh/ssh_stock/actions/runs/39999398934/artifacts/12523320946) | 9e72c19c7dd8032dca41107bad73385fded46cbe61aba98bcd120b44fe566102 |
| [迁移核验12522018938](https://github.com/sssssssssh/ssh_stock/actions/runs/39999398934/artifacts/12522018938) | 3caa72fb064e17baaf43d2fc60957bc7c9762ccb4afb6169478288e1fb208200 |
| [清理治理12521874412](https://github.com/sssssssssh/ssh_stock/actions/runs/39999398934/artifacts/12521874412) | 2ccef373c5f0e3a0a9839c7e0f373f587cf399ac0089ed1ccef7ebe6e1ee5646 |
| [固定错误元数据12522907224](https://github.com/sssssssssh/ssh_stock/actions/runs/39999398934/artifacts/12522907224) | c5564c6f6d3b180614b6ef943fe29cc1101652c786f1b886a33e4173333508ad |
| [A4233观测/迁移合同12520274461](https://github.com/sssssssssh/ssh_stock/actions/runs/39999398924/artifacts/12520274461) | 4f2d4bf98b3b945400abad093232de907f95460d7fe2f0b9c1e96be3b7350829 |

安全包含6份完整JUnit与failure.json；逐文件SHA/大小、实际XML节点与计数一致，
全量XML SHA256为5389def94eb2be4b86ed7f427392d53302ab026e2c474be42dc5801e20576e3d。
failure.json的HEAD/run/attempt均匹配，COMPLETE、evidence_complete=true，5阶段success；全部准入false。
无原始driver/SQL文本、属性、系统输出或主机信息；参数名称摘要化。主CI19个迁移fixture收据均
恢复0058并清理成功；治理收据job_status/cleanup_outcome=success、status=FINISHED。

错误包中两个实际主pytest收据的failures均为空；tests.json的1条固定错误属于刻意失败的双用例
子进程合同（证明仍exit1且完整保留JUnit），不是主CI失败，不能误报成2987用例中的失败。

专项bundle由实际CI日志中独立marker/system ID重建实例摘要，再从当前Git源码/冻结草案重建身份，
调用strict离线review校验manifest及每份文件。3ticks、JOINED_IMMUTABLE、cleanup_complete=true，
9个迁移测试库清理成功。源码摘要c72c059f1d65a3419d838188510efa3068835d67e83f4743abcdeef58b43a7ce；
协议f72e4ea46ce1c077739a5d79719ed229ecaed4904319addffd0cf5293b0fde5a；
实例bfd7a3e0bcfa824c5516e054a980b1527d510e714c8fa7ebc4dad15025156bac。
NOT_OBSERVED不证明无维护；unique_repair_candidate=null，performance_eligible/capacity_ready/
production_read_authorized全部false。

## 28个变更文件（生产四目录零改动）

- `.github/workflows/ci.yml`：定向回归、安全JUnit、失败证据及阶段化上传。
- `.github/workflows/a4233-observer-contracts.yml`：仅补低成本失败覆盖。
- `scripts/a42331_migration_contract.py`：自有UUID与Session/Alembic身份核验。
- `scripts/a42331_ci_contract.py`：精确授权test job例外，其余Gate冻结。
- `scripts/a42331_ci_evidence.py`：全量JUnit去敏与exact-SHA阶段收据。
- `scripts/a42331_pytest_safety.py`：报告去敏，测试结果不变。
- `scripts/a4233_background_observer.py`：有界停止、worker持有连接、发布稳定快照。
- `scripts/a4233_observation_contract.py`：v2生命周期，v1历史兼容。
- `scripts/a4233_observation_review.py`：v2离线复核。
- `tests/integration/conftest.py`：显式opt-in owned迁移fixture，原认证fixture保留。
- `tests/integration/test_m16_4_research_reports.py`：测试cleanup接受显式factory。
- `tests/integration/test_m16_5_archive_migration.py`：原约束/拒降级与错库/导入缓存顺序回归。
- `tests/integration/test_m16_5_closeout.py`：旧报告往返测试同库连接。
- `tests/integration/test_m16_6_contract_migration.py`：相邻迁移同库连接。
- `tests/integration/test_a4233_observer_pg17.py`：真实100ms SQL timeout、close错误。
- `tests/unit/test_a42331_migration_contract.py`：三guard分支及清理失败。
- `tests/unit/test_a42331_ci_evidence.py`：成功/失败/skipped、完整JUnit、真实失败退出码。
- `tests/unit/test_a4233_background_observer.py`：有界线程/快照/取消/guard回归。
- `tests/unit/test_a421_artifacts_and_cli.py`：精确例外后保留原全部断言。
- `tests/unit/test_a4_ci_governance.py`：同上，正式Gate不变。
- `docs/acceptance/a4233_1_ci_remediation.md`：源码级整改报告。
- `docs/acceptance/evidence/a42331_migration_reproduction.json`：原始根因证据。
- `docs/acceptance/v14_a4_2_3_3_closeout.md`：只追加，不覆盖旧失败。
- `docs/acceptance/a4_ci_workflow_inventory.md`：证据分层与例外登记。
- `README.md`、`PROJECT_RULES.md`：安全使用与冻结边界。
- `docs/股票机会发现系统_PRD_V1.0.md`、`docs/股票机会发现系统_系统设计_V1.0.md`：验收/架构边界。

## 未关闭项与停止

- 旧A4231/A4232 C1性能因果仍INSUFFICIENT_EVIDENCE，不跑P95/L2或开销校准，无性能对比可报。
- Python不可强杀卡住的C调用；STOP_TIMEOUT只提供稳定失败摘要，不证明线程/连接最终已清理。
- 快照开销未校准；未来off/on或单因素归因须新任务书及独立批准，现阶段停止等待审阅。
- 没有访问阿里云/业务数据库、修改运行任务或启动项目服务；本轮自建原生PG17已停止。
  测试cluster/编译资料与下载工件留在忽略目录便于复核，不提交或删除用户数据。

