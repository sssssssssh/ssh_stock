# V1.4 A0：读路径冻结与设计核对

开始 HEAD：`c9f3b1a977c56698436d0ec4b29b6b154ed0fe55`，master 干净，
`git pull --ff-only` 已确认无更新。Python 3.12.14 / SQLAlchemy 2.0.52 /
psycopg 3.3.4 / 隔离 PG17.11；正式迁移头 `0058_data_publication`，不修改 0058。
本轮不连接云库（含只读），不启停业务 Worker/Scheduler、不处理业务任务、不重跑补算。
本机未发现运行中的项目进程；配置的业务连接不用于测试。

## 隔离与可重复入口

专用 Docker postgres:17 容器带 `purpose=ssh-stock-v14-physical-test` 标签，
仅 loopback 发布端口，与此前所有测试实例及业务实例分离。用 postgres 启动参数
`-c v14.test_instance=<random-uuid>` 记录标记，独立读取 `pg_control_system()` 的
system_identifier。`scripts/v14_test_database.py` 在任何建库/迁移/删库前校验
显式 TEST_DATABASE_URL、标记、物理 ID 和 PG17；不只依赖 localhost/_test 后缀。
每次仅建立/删除自己生成的 UUID 测试库，真实凭据、连接地址和数据不写入仓库。

使用显式环境 `TEST_DATABASE_URL / V14_TEST_INSTANCE / V14_TEST_SYSTEM_IDENTIFIER`：

```bash
python scripts/ab_read_benchmark_v14.py --variant q0 --output .codex_tmp/v14-q0.json
python -m pytest tests/integration/test_v14_calendar_guard.py tests/unit/test_v14_test_database.py
```

## 冻结 Q0

脚本通过 git show 加载冻结 SHA 的 PublicationWorkspace（不是复制后猜测旧实现），
完整源 SHA256 为 `99db843a6840df5210cfffccd032727a4337539efe6ca44118f240b1134d4657`。
Q0 使用原 TEMP VIEW / UNION ALL / NOT EXISTS，原六个因子输入列、日期/身份过滤，
真实 named cursor / FETCH 5000，全量构造一次 DataFrame。原 SQL 未规定顺序；
对照按 ts_code,trade_date 归一排序，dtype/NULL/业务字段不归一化或补零。

首次合成 smoke：A=2000、当前 B=1350、其他 root B=2800；全 FETCH 输出 1893 行，
三次摘要均为 `b8bc1c1fced39904667b38f9db91125d05e37e6fad7c1068673b8119ccfbf307`。
耗时 0.02292 / 0.01438 / 0.01381 秒。包含 NULL、错版本、同键覆盖、删除掩码、新键，
其他 root 不可见；空帧/全部业务列及异常候选由后续 PG 回归补齐。
公开表 table/index=557056/204800 bytes；候选=3407872/1122304 bytes。
cursor_tuple_fraction=0.1、work_mem=4MB、shared_buffers=128MB、effective_cache_size=4GB，
装载后显式 ANALYZE。原始收据 `.codex_tmp/v14-q0-smoke.json`（不提交生成物）。
这只是基线/隔离证据，不是百万性能或生产验收。缓存未受控，不能称冷缓存。

## 诊断边界与阶段方案

任务书的云端 57014、65k 行停顿及行规模属于用户提供的历史事实，未在本轮业务库复测。
旧 EXPLAIN 是估算，不代表实际扫描数、耗时占比或 CPU 归因。SELECT 内部执行、
服务端游标 DECLARE/FETCH、客户端解码/传输分别计量；不可分离项标 UNPROVEN。
先 A0 日历守卫，再 A1 日期双侧约束/完整键遮蔽，A2 仅 SQL 读窗口，A3 回归/性能报告。
阶段 A 不缩短预热、不修改公式/版本/hash、不增加迁移、索引或全局 planner 开关。
阶段 B 须经用户确认，Raw 修订血缘不足不得提前复用历史。C 不落地。

Q1/Q2 读事务沿用 pinned connection。设计采用共享表读锁保证单次多窗期间 A/B 不变，
不会阻塞普通读者；跨阶段公开输入保留全字段逐日摘要并在复读/最终发布前检查，
发现旁路旧写者改变输入则失败关闭。锁/摘要的净开销必须计入性能对照。
首次 base_row、候选写入/质量和根发布 CAS 不替换；300s/10m 保护预算不提高。

## A0 已执行

交易日真实 PG 回归及目标防误用单测：13 passed（JUnit：`.codex_tmp/v14-a0-junit.xml`）。
覆盖春节、周末、跨年、单一 open session、半日按 is_open、缺失/部分日历、逆序、
API 422 不入队、旧队列 Worker 在候选/ledger 创建前 FAILED。缺行情不等于休市。
后续阶段与完整 CI 仍 OPEN，不据此批准部署。
