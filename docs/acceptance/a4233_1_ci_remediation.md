# A4233.1 验收整改（基线7bc2974）

当前状态：**PARTIAL，P0根因与定向修复完成；P1/P2及最终同SHA CI待验收**。
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

实际结果：定向2 passed/7 warnings/2.81秒/exit0；扩展15 passed/30 warnings/10.61秒/exit0。
warnings为既有Starlette与Alembic路径分隔弃用提醒。Ruff/diff exit0。
所有破坏性升降级仅新建UUID库；链恢复head=0058_data_publication；生产0051/0052等文件零改动。

## 待完成与交付边界

P1补强观测器有界停止、稳定快照、非主线程guard、首发/清理错误；CI工件区分必需/成功/失败。
最后再做同一最终SHA的主CI+专项验收，不反复提交刷完整CI，不降低覆盖率或准入。
目前不得标ACCEPTED；未授权任何新性能profile、one-shot、正式Gate或生产读取。
