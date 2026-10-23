# A4233.1 验收整改（基线7bc2974）

本文是推送前封存的实现/本地实测记录：**PARTIAL，等待最终同SHA CI验收**。
最终结论须核对本文件所属提交的Checks和下述exact-SHA工件，不预写尚未发生的成功。
基线`7bc29740948742bebee65e2e2a5814553fc41934`，master，开工工作树干净。
本轮不运行开销校准/归因/P95/L2，不连接业务库，不修改生产算法、数据或正式授权。

## G0/G1：真实失败与根因 A

[原主CI39954426926](https://github.com/sssssssssh/ssh_stock/actions/runs/39954426926)
的test job120416595487已核对：1 failed/2942 passed/651 warnings，1094.77秒，
覆盖率89.28%（原70%门槛不变）；失败为M16.5预期RuntimeError未抛出。
后续两个upload因数据队列/浏览器阶段未执行而缺路径，是二次工件错误，不是新的业务根因。
原专项[39954426888](https://github.com/sssssssssh/ssh_stock/actions/runs/39954426888)273通过仍只代表专项。

本机没有运行中的Docker/现成PG17。为不启动Docker可能自动启动的业务容器，
从官方PostgreSQL17.11 tarball与sha256文件构建了忽略目录内的临时runtime；
自有新cluster仅监听127.0.0.1独立端口。编译未启用ICU/readline/zlib，
只是本地功能复现环境；最终CI仍须官方PG17容器，不能把二者当相同资源/性能环境。
首次查询对照initdb后独立pg_controldata记录的system ID及随机marker，才创建两UUID合成库。
未读取业务.env、连接业务数据库、迁移/降级用户实例或启动项目服务。

### 未修改基线测试的实际对照

[原始身份/guard计数证据](evidence/a42331_migration_reproduction.json)保留真实新合成库名、
schema、版本、物理摘要与布尔/计数，没有DSN/角色/业务值。结果：

| 情形 | Session / Alembic | 三表独立可见计数 | 0051真实guard | 结果 |
|---|---|---|---|---|
| 单跑且连接对齐 | A / A，同物理实例、public | 原测试提交归档 | 首次tool EXISTS=true时拒绝 | PASS，A仍0058 |
| 调用已有setup_runtime后 | A / B，同物理实例、public | A为1/1/1 | B三项EXISTS均false | DID NOT RAISE；A仍0058/B变0050 |

旧测试代码保持基线字节执行；仅对Connection.scalar返回的既有guard布尔作旁路记录，不消费或
改写游标/guard返回值。初始内部探针在同目标迁移DDL内尝试跨连接count而等待，已停止自有
探针并清理其两个UUID库，改为迁移前/异目标计数后完成复现；不是性能重跑或产品失败。

已证实机制：`core.db`导入时创建的全局SessionLocal固定绑定A；
既有诊断`setup_runtime()`写DATABASE_URL为显式TEST_DATABASE_URL(B)，并清get_settings缓存。
Alembic未提供connection时，env.py运行时取该Settings，故连接B。
数据在A已commit且新连接可见，B为空；0051在其实际连接上正确拒绝非空、允许空库。
排除本次复现的事务可见性/生产0051guard缺陷；**不修改任何已发布迁移**。
此为完整CI失败签名的确定复现路径，不冒称已采集原历史CI逐测试全局变量写入者追踪。

## G2：最小隔离修复

- 新`a42331_migration_contract`只从显式双验证TEST目标派生新UUID库；
  不修改环境/Settings/全局SessionLocal，ORM factory与Alembic supplied connection同一owned engine。
- 每次迁移前分别读取并比较Session与migration连接的物理/数据库/schema/revision身份，
  释放预检事务后执行Alembic；错库先拒绝，不执行DDL。新连接检查commit后的三表计数。
- M16.5主测试保留所有FK/Hash/size/immutable与非空拒降级断言；补空库、tool、
  binding+其必需tool父记录、manifest场景。binding不能在真实FK有效时脱离tool独存，
  另有不改生产的unit覆盖三个EXISTS分支，不谎称真实库构造了孤儿binding。
- M16.6相邻迁移及M16.5旧报告往返也显式绑定owned fixture；旧金融/报告不变量未变。
- 清理只删除fixture创建的随机UUID库；不force/杀连接/清共享表；清理异常固定码并使测试失败。
  原integration认证autouse fixture完整保留，未通过删除/跳过测试修复。

本地真实PG17命令（运行前显式设置合成TEST_DATABASE_URL、随机marker与独立system ID，
禁用Settings.env_file；不复制真实连接信息到仓库）：

```bash
python -m pytest tests/integration/test_m16_5_archive_migration.py tests/integration/test_m16_6_contract_migration.py -q
python -m pytest tests/integration/test_m16_5_archive_migration.py tests/integration/test_m16_6_contract_migration.py tests/integration/test_m16_5_closeout.py tests/unit/test_a42331_migration_contract.py -q --junitxml=.codex_tmp/a42331-migration-related.xml
```

实际结果：定向2 passed/7 warnings/2.81秒/exit0；扩展19 passed/30 warnings/10.50秒/exit0。
warnings为既有Starlette与Alembic路径分隔弃用提醒。Ruff/diff exit0。
所有破坏性升降级仅新建UUID库；链恢复head=0058_data_publication；生产0051/0052等文件零改动。

## G3：有界生命周期与失败关闭

observer新增严格v2收据；历史v1 schema/摘要语义保持可读，不重写历史工件。
INIT→RUNNING→STOP_REQUESTED→JOINED或STOP_TIMEOUT→RECEIPT；只有JOINED、完整ticks、
无首发/清理错误时COMPLETE_CONTRACT。worker关闭自身连接，控制线程不跨线程close。
只在物理验证后对自有真实psycopg连接使用libpq支持的cancel_safe，预算不超过剩余停止预算/.25秒；
无此能力时绝不回退可能无界的cancel()。SIGTERM handler只置事件与固定错误，不在handler内网络取消。
固定2秒stop/join，daemon只是不可杀C调用的退出兜底，不计作成功；正常路径必须关闭并join。
已完成tick与每视图进度由worker发布detached有界快照，超时读取最后已发布快照并输出失败摘要，
不是正在变动的列表；snapshot序号/摘要绑定内容，封存后即使worker稍后退出也不改旧收据。
首发错误sticky，清理码最多4项、总数与遗漏数单列；非主线程signal安装直接固定拒绝。

旧SQL白名单、100ms超时、受限角色/只读/合成UUID/双身份/128行界限原样。
真实PG17新增100ms SQL timeout（仅测试包装pg_sleep）及close异常；旧worker异常、SIGTERM恢复、
序列化/写盘错误等回归保留。有限Event阻塞用例在finally释放并join，不制造无限残留。
新增三种取消能力/身份组合断言不得调用legacy cancel。未校准快照开销，不声称性能无损。

## G4：工件分层与报告去敏

- 完整主pytest仍选择所有测试，覆盖率门槛70%不变。报告插件仅改longrepr/captured输出，
  保存固定error type/SQLSTATE/code，不改exception/outcome/断言/用例选择或GC。
- JUnit保留所有testcase、状态、计数、时间；移除SQL/参数/driver文本/hostname/本机路径，
  参数化名称摘要化；校验声明计数和实际节点一致，XML损坏/缺必备JUnit仍失败。
- 必需a42331-safe-ci-SHA-run-attempt包含安全完整JUnit与failure.json（HEAD/run/attempt/
  阶段状态/计数/固定错误），always且缺文件error；上游失败时收集成功不等于测试成功。
- 可存在的固定错误和迁移核验工件按hashFiles判断。data_queue/runtime_browser从未运行不上传；
  阶段成功时仍要求产物error，失败时只尝试保留部分产物，不添加缺目录伪失败。
  Core/JUnit后续旧工件仅在去敏完成后导出。原Release Gate与authorize/capacity的代码/条件不变。
- 精确reviewed test job摘要允许唯一授权例外，改覆盖率、跳测、continue-on-error或预算都拒绝；
  原冻结manifest不改，其余job与原五条其他workflow逐项保持。
- 故意失败的双用例子进程验证exit1、2个case/1个failure全部保留，敏感测试消息不外发；
  成功/上游失败后skipped/损坏/缺失/伪造计数均有低成本unit，不启动真实高成本负载。

## G5：本地实测与最终CI证据合同

开发中真实失败不隐藏：初版partial snapshot缺默认字段导致摘要校验失败（2失败/103通过），
改为对typed规范化投影取摘要后通过。完整unit首次暴露旧core steps字节合同拒绝本次授权的
去敏/上传差异，仅增加精确摘要验证后还原旧job再执行原全部断言；不是删除断言。
新取消测试开发中漏import time曾3失败/2157通过，补import后定向和完整unit通过。

最终本地验证（禁用.env；前者不可连接loopback，仅unit；后者先双验证自有PG17）：

| 验证 | 实际结果 |
|---|---|
| 完整tests/unit | 2160 passed，5 warnings，29.26秒，exit0 |
| M16.5/16.6相邻迁移、observer unit/PG17、证据回归 | 145 passed，39 warnings，21.28秒，exit0 |
| Ruff backend/tests/migrations/scripts/.github/actions | exit0 |
| git diff --check；生产四目录冻结 | exit0 |

warnings是既有Starlette/Alembic弃用提示；原始local JUnit在忽略目录，不提交含hostname/path的原文件。
本地没有Docker，未运行完整容器/浏览器/全部integration；交由一次最终主CI实际验收，不能冒称本地全通过。
最终同一SHA必须主CI/test（含全部pytest/Ruff/前端/容器/浏览器）和a4233 contracts成功；
核对安全JUnit总数/0失败错误跳过、覆盖率≥70、PG17身份/cleanup和普通事件昂贵jobs全部skipped。
CI链接从该提交Checks读取，原始工件名分别为：
`a42331-safe-ci-SHA-run-attempt`、`a42331-migration-SHA-run-attempt`、
`a42331-safe-errors-SHA-run-attempt`及`a4233-contract-SHA-run-attempt`。
它们绑定运行时真实HEAD，不能用上一SHA工件替代；最终交付消息列具体URL/ID/hash与结论。
为不多次触发完整CI，两个逻辑提交一次推送，只验收最终SHA，不为回填CI链接再制造文档提交。

## 变更与提交

提交A：`273e13e70ae0f554fb5a313f37dbfb67f7d68ff6`，独立迁移fixture/helper、M16.5/16.6
测试及旧报告测试工厂接线、回归unit和根因证据（共9文件）。
提交B：本报告所属最终提交（`git log -1 --format=%H -- docs/acceptance/a4233_1_ci_remediation.md`）；
observer/contract/review、CI去敏及合同helper/插件、新unit/PG17失败回归、两条workflow、
精确冻结例外合同及四权威Markdown/inventory/本报告/旧closeout追加。全部只推master，不强推。

## 未关闭项与停止边界

完整CI未实证成功前仍PARTIAL；若失败先保留安全证据和首发原因，不盲目重跑，不扩展生产修复。
旧A4231/A4232因果结论继续INSUFFICIENT_EVIDENCE；无唯一修复候选、无开销校准/P95/L2
或生产资格。本轮无性能对比数据；不会把3ticks功能耗时当正式性能证据。
Python无法强杀卡住的扩展调用，STOP_TIMEOUT只能证明最后稳定快照，不证明连接最终已关闭；
进程退出/外部runner硬杀也不能承诺一定能上传工件，缺收据按不完整处理。
原历史CI具体最后一次环境写入者未取逐测试追踪，仅证实可确定复现的同型连接漂移机制。
无阿里云/业务数据库/运行任务操作；之后校准/归因须独立任务书批准，停止等待审阅。
