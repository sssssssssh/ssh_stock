# FACTOR-RECOVERY-04 offline receipt

2026-11-16。STATUS=OFFLINE_DIAGNOSIS_PARTIAL / NATIVE_ENV_BLOCKED / REVIEW_PENDING。
生产修复 NOT_APPLIED；独立审阅 NOT_COMPLETED；未提交、未推送、无新 SHA/CI URL。
上一轮未产生 RECOVERY-04 交付，本轮接续同一任务，没有启动另一 writer/agent。

## 基线与实际调用链

master，HEAD=origin/master=只读 GitHub master 核对结果：
bf7b6a35a453c7d82be363dec2e0f5157221db92。
开始 tracked clean，仅有两份指定 W05 未跟踪资产。
四 workflow 通过是用户提供的基线背景；本轮 workflow-runs connector 返回空列表，
未独立重新取得四条 run 证据，没有据此推断失败或创建新 CI。
已核对 AGENTS、治理及相关业务规则；旧治理指针不覆盖本次明确离线授权。

- job_worker.py:124 claim_next_job：advisory lock、运行中 Writer 过滤、依赖终态、
  FIFO 排序，数据队头使用不带 SKIP LOCKED 的行锁；配置身份拒绝和 token claim 后 commit。
  这是故意不越过锁定数据队头的语义，未认定为可安全删除的性能冗余。
- execute_claimed_job：owner/token 校验、heartbeat、checkpoint、日历校验、私有 workspace，
  再进入 run_recalculation。上轮已修复的 start 成功标记未修改。
- recalculation → FactorService.calculate → calculate_stock_factors（带 checkpoint）→
  replace_slice_rows → upsert_rows → PublicationWorkspace.upsert。
- replace_slice_rows：记录 scope、查已有键、差集墓碑；候选 upsert 仍以 500 行分批。
- data_publication.py:228 _lookup_batch：每批一条 WITH input_keys 查询，内部含 candidate
  与 published 两个 LATERAL probe；不是两条 execute。两个 progress 标签也不是两次往返。
  实际 PostgreSQL 执行计划、I/O、锁等待及行探针成本本轮 UNKNOWN。
- finish_publication:751：终态 CAS 内验证 ledger/owner/token/cancel/identity，失败 ABORTED，
  成功路径有候选校验、SHARE 锁、预算及最终原子发布。没有执行这些 SQL 或实际发布。

## 可复现的离线重复工作与内存候选

真实 upsert 源码在每一行准备完成后都重新生成默认 updates 列表。
对 54 列 StockFactorDaily，列元数据及 conflict_columns 在同一批内不变。
最小候选是把原赋值表达式移到批内行循环外，不改查询、500 行边界、值转换、
更新列白名单、首次原像、来源身份、取消 checkpoint、事务或发布语义。

新增 tests/unit/test_factor_recovery04_candidate_preparation.py：
从当前真实源码仅编译 upsert 和纯 _json 方法，使用真实 SQLAlchemy 模型元数据，
lookup/store/progress 为假边界。试验修改仅存在于 AST 内存副本，未写生产文件。
这不是导入整个 publication 模块的原生回归，不是真实 Worker 或数据库测试。
没有伪造 fastapi/loguru 模块，也没有把假 lookup 的次数当作实测数据库延迟。

| 合成行数 | 原 primary_key 元数据检查 | 内存候选检查 | lookup/store 各次数 | 输出摘要 |
|---:|---:|---:|---:|---|
| 1 | 54 | 54 | 1 | 相等 |
| 500 | 27000 | 54 | 1 | 相等 |
| 501 | 27054 | 108 | 2 | 相等 |
| 1001 | 54054 | 162 | 3 | 相等 |
| 3450 | 186300 | 378 | 7 | 相等 |

默认列、显式列/空白名单、来源不匹配拒绝共 3 个 unittest 方法通过，退出 0，1.621 秒。
包含既有/新行、NULL 保留、首次原像假数据；源方法失败仍拒绝 PUBLICATION_SOURCE_MISMATCH。
原函数与内存候选的假 I/O 序列及输出 SHA256 逐规模相同，完整值见
[离线证据 JSON](FACTOR_RECOVERY_04_OFFLINE_EVIDENCE.json)。
3450 行单次观察时间原 0.419562 秒、候选 0.285458 秒。
计时含元数据计数代理和假 I/O，仅先原后候选各一次；未做正式交错性能实验、
分位数、数据库执行或整链测量，不能据此宣称生产提速百分比、容量或性能验收。

复现：在仓库根 Python 加 backend 至 sys.path 后，加载新增模块，运行
unittest.defaultTestLoader.loadTestsFromModule(module)。本轮安全启动另加 audit hook
拒绝 .env、socket/network、subprocess/os.system，并将 Engine.connect 替换为拒绝函数。
证据文件 scope=SOURCE_ISOLATED_FAKE_IO_MEMORY_ONLY_TRIAL、production_patch_applied=false。

## 未落生产补丁的原因与确切门禁

1. 唯一现有完整依赖断网容器 ssh-stock-factor-recovery-test 的 docker inspect 仍退出 1：
   Docker 配置读取和 docker_engine API 均 Access denied；没有提升权限、切换 daemon 或重连。
2. 宿主原生 pytest 针对 test_factor_candidate_write.py、test_job_worker.py 收集时分别缺
   loguru、fastapi，2 errors、0 测试执行；pytest 返回 2，PowerShell 管道进程退出 1。
   Ruff 退出 1，No module named ruff。未安装或更改依赖版本。
3. publication 当前字节仍由已提交 r1_current_business_sources_v2.json 的完整 SHA256 绑定。
   直接改生产文件会使当前 Controller/Seed 来源校验失败；不能更新旧摘要掩盖变更。
   候选若获审阅，应明确采用新的当前来源版本并保留旧版本历史语义，不能再次制造旧合同回归。

因此没有把内存候选伪装成已实施修复，未提交一个已知违反当前来源合同的生产修改。
需要具备正常权限的已获准断网验证执行层及独立审阅，完成原生等价/取消/发布回归、
Ruff 和当前来源版本适配，再决定是否保留此局部优化。当前没有取得独立审阅通过证据。
没有证据表明必须访问真实业务数据才能继续这一步，未申请或消耗生产/云授权。
上述条件未满足，用户的条件性提交推送许可未生效；没有尝试写 .git 或 SSH 推送。

## 文件、保全和执行状态

新增仅本报告、离线证据 JSON、上述 source-isolated 诊断测试；没有生产或 tracked 修改。
源文件原字节 SHA256 见 JSON；五冻结源、安全插件、workflow、锁和已有源码均未动。
两份 W05 保留 SHA256：
- docs/tasks/BIZ-PERF-P1-04-W05-GATE-01.md：
  6f9f68c7028729598a0f510358798f746e0e9318e6d6926a128daa298ef915aa；
- docs/acceptance/BIZ_PERF_P1_04_W05_GATE01_AUDIT.md：
  baca21feaa6edbad2e8471db65b80166b0b8d21595550f8c70ef00f63c27d750。

新测试 AST/行长/尾空白及 git diff --check 通过，不代替 Ruff。
既有 bf7b6a3 CI 不作为本轮新文件验收；全量回归和新 SHA CI NOT_RUN。
REAL_PG17=NOT_RUN；REAL_WORKER=NOT_RUN；SQL/MIGRATION=NOT_RUN；
RAW_RELOAD=NOT_RUN；FORMAL_PERFORMANCE=NOT_RUN；NEW_CLOUD_SPEND=0。
B_GATE=NOT_APPROVED；TARGETED_PG17_GATE=NOT_APPROVED。
中心线仍为 PARTIAL，等待独立审阅与离线原生验证，不声明因子计算已恢复完成。
