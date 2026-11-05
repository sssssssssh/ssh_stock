# BIZ-PERF-04-A：SQL 终态计数一致性

2026-11-05。负责人仅批准 04-A；基线 master/HEAD/origin/master/实时远端均为
057dfe861f940a5284b594db9ef45c2257cec688，工作区 clean。允许本次提交推送和自动普通 CI，
禁止实验 dispatch/rerun、生产访问及 04-B～F。本文是交付前记录，不追填自身 SHA。

## 历史事实与根因

历史 Run 41991816127 / attempt 1 / SHA 057dfe861f940a5284b594db9ef45c2257cec688。
Artifact 13398532465，ZIP SHA256
251082fba565c38a831d7aec5d90fcb7628bd6c45a9411302d131e1881ea783e。
W00 已下载核验 manifest 六份成员的大小/哈希；原件不改写。

| 计数 | receipt.last_phase | measurement.root |
| --- | ---: | ---: |
| SELECT | 5685 | 5693 |
| UPDATE | 83 | 86 |
| DROP | 缺项 | 10 |
| 总计 | 6353 | 6374 |

ProgressStep complete 复制当时 Counter，Channel 缓存进度；Worker 返回后 measurement
另采样，最终 emit(result) 未更新计数。两份文件未核对快照身份，因此旧进度可带 result 标签。
临时视图清理提供 DROP 差异的源码解释；8 SELECT / 3 UPDATE 逐条归属仍 UNKNOWN，
不能据此推断环境或心跳问题。本轮不运行真实根任务，也不声称得到新性能数字。

## 最小实现与边界

新增 scripts/business_sql_snapshot.py，仅服务合成脚本，不安装生产观察器。
`biz-perf-04-a.sql-snapshot.v1` 是新增证据字段版本，不修改旧实验协议。

- 开始：测量器开始根生命周期，随后 create / claim / execute_claimed_job。
- 结束：execute_claimed_job 返回，包含其 Worker finally 和临时视图清理；立即冻结计数。
- 排除：随后独立 Job/ledger 状态读取、结果摘要核验、隔离数据库/容器销毁。
- 计量：SQLAlchemy before_cursor_execute 的执行尝试次数；不是成功语句数、影响行数或包数。
- 保留原 first-token 分类，包括 WITH；直接 psycopg observer 控制 SQL 单独计数，不相加。
- Engine 多连接累计使用锁；冻结时若仍有在途 cursor 调用则拒绝完整快照。冻结后不再累计。
- SQL 参数、正文、连接信息、线程身份不进入快照。保留未知查询分类问题，不伪造语义分类。

快照包含版本、固定 scope/source、head_sha、root_job_id、单调开始/结束时间、整数计数、
总计、complete 与规范 JSON SHA256 snapshot_id。构造复制原 Counter；改动任何内容都会导致
摘要校验失败。该摘要用于完整性和身份绑定，不是密码学签名或新的执行授权。

仅 SUCCESS/PUBLISHED 创建完整快照；异常/取消/清理异常保留失败进度，不发完整 result。
相同快照写入 measurement 与终态 Channel。controller 在 run_root、归档和最终安全导出
三处核对；计数、快照、SHA、根 UUID、成功状态或 phase 不一致不能进入完整证据状态。

历史无快照 JSON 仍可由原解析接口读取；新运行/完整导出不能靠删除新字段降级为旧合同。
不回写历史工件，也不宣布旧 Run 不存在。root.overall 保留原计时语义，其末端包含状态读取；
SQL 快照自身的明确边界不同，不能把二者描述为完全同一时段。默认非 once 模式仍沿用旧行为。

## 设计留项，不实施

WITH 分类后续须识别注释/引号/括号与 CTE 顶层命令；数据修改 CTE 单独标识，不支持结构
计 UNKNOWN 或拒绝完整语义统计。当前 source 明确 first_token.v1，绝不宣称完成该分类。
复杂并发阶段归属须另立连接/任务上下文合同；本次仅保证根 Counter 累计和冻结，不改共享
recent_stage、CandidateObserver 栈或生产心跳。隐式 driver COMMIT/ROLLBACK 未被计入，
不能把本计数器当作服务器所有事务语句统计。

## 验证与兼容

先增加回归测试，直接执行旧测量器的终态 emit AST（不导入应用/不连库）：
旧实现稳定失败，仍为 SELECT=5685、UPDATE=83，缺 DROP；RED 为 1 failed。
新测试验证冻结、在途拒绝、并发累计、成功对齐、失败/取消、缺失/篡改身份、历史解析、
控制 SQL 独立以及归档拒绝。现有两个测试文件仅补充成功 fixture 的必需快照字段；
原断言没有删除、跳过或降低。

最终定向回归 384 passed / 0 failed / 0 errors / 0 skipped，JUnit 6.080 秒；
Ruff 全范围和 diff 检查通过。RED 与最终 JUnit 摘要见 biz_perf_04_a_offline.json。
开发中一次旧 fixture 补充出现缩进收集错误，已修正；不删除失败记录或改低断言。
执行命令：

```text
python -m pytest tests/unit/test_biz_perf_04_a.py tests/unit/test_biz_perf_03_b_once.py tests/unit/test_biz_perf_03_b_archive.py tests/unit/test_business_recalc_measure.py tests/unit/test_business_candidate_observer.py tests/unit/test_a4_ci_governance.py tests/unit/test_ci_opt_01.py -q
python -m ruff check backend tests migrations scripts
git diff --check
```

没有本地完整 pytest、PG/容器、环境设置、业务凭据读取、数据生成或实验运行。
原七份 Workflow、历史协议、CandidateObserver、backend、模型/迁移/配置、依赖锁均不改。
自动普通 CI 只证明工程回归，不是本实验或性能通过；不追加重跑。
04-A 交付后 REVIEW_PENDING，等待审阅，禁止自动进入 04-B。
