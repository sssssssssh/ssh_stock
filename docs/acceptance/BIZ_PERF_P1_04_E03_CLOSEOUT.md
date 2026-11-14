# BIZ-PERF-P1-04 E03 离线封装回执

日期：2026-11-14（Asia/Shanghai）。状态：
`LOCAL_OFFLINE_VALIDATED / INDEPENDENT_REVIEW_PENDING / CI_PENDING`。

## W00 与范围

开始时分支 master，HEAD / origin/master 均为
`22e92d291732d4f31a0e9ba3d787ff877c20a868`。唯一 dirty 项为
`?? docs/tasks/BIZ-PERF-P1-04-E03.md`，按本任务 W00 专项例外纳入交付。
GitHub master 和起点 CI `43464657765 SUCCESS` 采用负责人本轮明确提供的外层核验；
没有把沙箱网络失败解释为版本漂移，也未再次访问 GitHub。

五份治理文件的旧阶段指针保留原有历史语境，本轮以用户明确的 E03 离线范围为准。
不修改治理基线、业务公式、配置、数据库、依赖、CI 或旧冻结合同。未发现需要解冻的冲突。

现有差距：R2 的 preflight 仅校验离线声明，缺少 CI/独立审阅凭证、完整资源归属、
逐表预算和审批接口；旧 03-B 仅适用 4 股、2660 股日、5000 行上限及 420 秒协议。
E03 没有沿用其执行通道或扩大其授权。

本次新增三个 E03 模块、三个专属测试文件及本回执，并纳入获准的任务书。
唯一既有源码改动为 E02 recorder 的可选 `fetch_reader` 公开注入参数。
五份绝对冻结文件均未修改。

## 设计与验收对应

| 项目 | 实现与证据 | 边界 |
| --- | --- | --- |
| E03-A 预检 | `validate_plan` 复用原 diagnostic preflight；精确 SHA、CLEAN、同 SHA CI SUCCESS、同 SHA 审阅及不同 reviewer/implementer digest、非零 run UUID、输入/策略/业务摘要、五开关 false、8 股/2025-01/one root；所有层使用严格键集和标量类型 | CI/审阅在输入里仍是夹具声明，格式正确不证明真实性 |
| 逐表 Seed | 显式 12 表预算和逐表内容 SHA256；按历史 Seed 的 start-900 至 2025-01-31 包含两端，共 931 日、665 个合成 weekday、5320 股日 | 不使用交易所真实日历，不生成 Raw，不代表派生输出行数预算或真实观测 |
| E03-B 端口 | Inspector / IdentityAttestor / ApprovalVerifier / BudgetGuard / ExecutorPort，全部默认 Refused；注入返回值必须是整个规范化 plan digest 绑定的 OBSERVED_OFFLINE 固定 receipt | 布尔值、跨 digest、LIVE_VERIFIED/OBSERVED_LIVE、未知字段均拒绝；没有真实验证器或 permit |
| 资源身份 | Linux x86_64、PG17、独占新 PGDATA、UUID marker、offline/online physical system identifier、新库及 owner、卷/网络/owner digest、独占 lease 和 run UUID 关联 | 仅验证 mock 的匹配/拒绝语义，不探测主机、PG、Docker 或云资源 |
| 预算 | 20min/末5min清理、Worker3GiB、PG4GiB、卷10GiB、证据10MiB 保持 DRAFT_NOT_APPROVED；CPU milli-CPU 为有界待批输入；纯函数验证 mock 用量与 root/cleanup 期限 | 无进程 watchdog 或系统资源执行器；CPU 配额不与累计 CPU 时间混用；fixture 的 2000 milli-CPU 不是批准值 |
| E03-C 采集 | 明确单调 clock、累计 CPU、RSS high-water mark、RootCounts、driver FETCH 端口；缺测/异常为 UNKNOWN，未接线 NOT_INSTRUMENTED，数值 0 保留 | RSS 是进程生命周期峰值的边界读数，不伪称 root 独占分配；inclusive 阶段和 SQL/FETCH 重叠，DO_NOT_SUM |
| R2 单次冻结 | 原 `run_offline → _capture_root → freeze_root` 保留；先固定 Wall/SQL，再读取 CPU/RSS/FETCH；后续 freeze 只发布；FETCH reader 副作用不得增加 root Wall/CPU/SQL | 无 Worker hook、后台 sampler 或真实进程；reader 为可信同步测试注入 |
| E03-D 证据 | BoundedEvidenceSink 使用 FileJsonlSink，逐事件先经原 Replay 验证，再完整 write/flush/fsync；seq、run/root、字段、64KiB 行、8MiB raw 和事件数限制；失败粘滞 | 不回显底层异常或任意日志；FileJsonlSink 的可信祖先目录及 Windows 目录项耐久性限制继续适用 |
| 失败状态机 | MockLifecycle 仅允许一次 create/claim 和一次 mock Worker；create/claim 失败、未知 ACK、Worker 失败、超时/预算、采集及 sink 故障均停止，无自动重试 | 无 cleanup/drop 方法；未知归属只分类 CLEANUP_BLOCKED；原 schema 的失败码与 E03 细分静态错误码分层保存，不改原事件格式 |
| 原 validator | 只读 mock plan → offline proof → fixture recorder/FileJsonlSink → 原 validate_bundle → execute 拒绝；失败前缀可 Replay，不产生成功 summary/integrity | 全部 OFFLINE_FIXTURE，ROOT_ATTEMPTS=0；fixture cleanup COMPLETE 只是模拟事件，没有清理动作 |

逐表 Seed 静态预算：trade_calendar=931、stock_basic=8、sector=1、sector_member=8；
stock_daily / stock_adj_factor / stock_daily_basic / stock_limit_daily 各 5320；
index_daily=665×显式 benchmark_count；stock_st_daily=0、stock_suspend_daily=0、
data_quality_daily=1330。每表都需独立 SHA256，不能以单个 5320 替代。
benchmark_count 及具体内容仍须未来独立核验，当前没有真实数据证明。

`OfflineJournal` 明确为单会话内存 replay 防护，需显式共享；复用 UUID 被拒绝。
它不提供跨进程/跨机器唯一性、持久 lease 或原子生产消费能力。即使新建 journal 或
伪造全部离线 receipts，也只能得到 OFFLINE_PROOF_ONLY；所有 execute 仍拒绝。
注入 Python 对象是可信测试代码，不是执行沙箱；本轮不提供生产适配实现。

离线 CLI：

```text
python -B -m scripts.biz_perf_p1_04_e03_guard plan --input OFFLINE_PLAN_JSON --expected-implementation-sha EXPECTED_40_HEX_SHA
python -B -m scripts.biz_perf_p1_04_e03_guard validate-offline --input OFFLINE_PLAN_JSON --expected-implementation-sha EXPECTED_40_HEX_SHA
python -B -m scripts.biz_perf_p1_04_e03_guard inspect --input OFFLINE_PLAN_JSON --expected-implementation-sha EXPECTED_40_HEX_SHA
python -B -m scripts.biz_perf_p1_04_e03_guard execute
```

plan/validate-offline 仅读取有界普通文件并输出 digest 和固定离线状态，不写文件或签发准入。
inspect 使用默认 RefusedInspector 返回拒绝；execute 固定 AUTHORIZATION_PENDING / exit 2。
旧 diagnostic execute 同样保持 AUTHORIZATION_PENDING / exit 2。
未知参数/错误输入固定拒绝，不接受环境变量、allow=true、凭据或连接串作为授权来源。

## RED → GREEN 与真实统计

基线未修改时，E03 入口存在性及 execute 拒绝两个探针 **2 failed / 51 deselected**，
退出 1：模块不存在，执行返回 1 而非合同要求的固定 exit 2。没有把缺失模块表述为
已存在真实执行漏洞；其余新增严格负例是新合同的拒绝测试。

FETCH 公开注入探针在 R2 上另有 **1 failed / 5 deselected**，退出 1：
构造器不接受 fetch_reader。增加最小公开端口后 GREEN，原 R2 58 项保留通过。
审计时将 FETCH reader 放在 CPU/RSS 之后，新增副作用测试验证不污染 root CPU/SQL/Wall。

本机 Windows / CPython 3.12.7 / pytest 7.4.4，未安装或升级依赖。

| 验证 | 实际结果 |
| --- | --- |
| E03 guard | 75 passed |
| E03 collectors | 7 passed |
| E03 evidence | 17 passed |
| 原 E02/R1/R2 wiring | 58 passed |
| 原 diagnostic | 66 passed |
| 原 W04A offline | 20 passed |
| 旧 PG identity guard（fake DB-API） | 11 passed |
| 上述核心组合 | **254 passed / 0 failed / 0 skipped**，退出 0 |
| 扩展组合，另含原 03-B once/archive | **425 passed / 9 failed**，退出 1；这是新增最终边界用例前的那一轮统计，不累计重复轮次 |
| 扩展失败原因 | 旧 03-B 的九项 POSIX API 在 Windows 缺少 getuid/getpgid/killpg/getitimer；原测试、冻结源码及断言未改，未跳过，Linux CI PENDING |
| Ruff | 已执行 `python -m ruff check backend tests migrations scripts`；退出 1，No module named ruff；未安装依赖，新 SHA CI Ruff PENDING |
| diff-check / frozen blobs | PASS |
| 本机完整 pytest / PG17 / Worker / Docker / 迁移 | NOT_RUN；本轮不授权真实连接、资源操作或本机全量回归 |

核心命令（JUnit 和临时 fixture 写入系统临时目录，不提交）：

```text
python -B -m pytest tests/unit/test_biz_perf_p1_04_e03_guard.py tests/unit/test_biz_perf_p1_04_e03_collectors.py tests/unit/test_biz_perf_p1_04_e03_evidence.py tests/unit/test_biz_perf_p1_04_measure_wiring.py tests/unit/test_biz_perf_p1_04_diagnostic.py tests/unit/test_perf03_lnx_w04a_offline_contract.py tests/unit/test_r1_integration_pg_guard.py -q --junitxml=OUT/core.xml
```

扩展命令在上述测试集合另加
`tests/unit/test_biz_perf_03_b_once.py tests/unit/test_biz_perf_03_b_archive.py`。
没有通过修改平台判断、mock 系统缺失接口、降低断言或删测来消除其九项失败。
普通 GitHub CI 才负责新 SHA 的 Linux/POSIX 和完整隔离工程回归，不能预填成功。

## 五份 frozen blob

以下 `git rev-parse HEAD:path` 与 `git hash-object path` 逐一相同，均与起点一致：

| scripts/ 文件 | Git blob SHA |
| --- | --- |
| business_recalc_measure.py | 782e45ba53c8de8df0d12ffa84c219855316cfda |
| biz_perf_p1_04_diagnostic.py | 714f78017ec252791ac6a89f9fb0e0a984333c37 |
| perf03_lnx_w04a_offline_contract.py | 931fd4fec38551d9fac59791d2bde5ce0e6a1d48 |
| biz_perf_03_b_once.py | 2ea473491f590893ad575b90a0ba42f932e37129 |
| business_sql_snapshot.py | e7532b0a0242f1e3d3b047fdc03fca7ffc3ce7c6 |

## 提交后交接

本次只允许一个 master 提交。最终 commit SHA、push 结果及 HEAD/origin/master 比较在
提交后回执报告；不为回填本文自身 SHA 再建提交。若沙箱 SSH 阻断，依 W00 说明交由
ChatGPT 使用已授权外层终端安全推送并独立审阅，不强推或手动触发 CI。

实际交付阻断：检查通过后执行仅含本轮九个路径的 `git add -- ...`，Git 返回
`Unable to create '.git/index.lock': Permission denied`，暂存失败。
环境权限明确将 `.git` 设为只读；未绕过权限或改用替代 index/refs。
因此本轮 **没有生成 commit，也没有尝试 push**。当前 HEAD / origin/master 仍为起点，
九个交付路径保留在工作区；交由已获授权的外层终端先核对 diff/范围，完成单个 master
提交及普通 push，再核对 HEAD == origin/master、精确 SHA CI 和独立审阅。

```text
BASELINE_SHA=22e92d291732d4f31a0e9ba3d787ff877c20a868
FINAL_SHA=NOT_CREATED_GIT_METADATA_READ_ONLY
CURRENT_HEAD=22e92d291732d4f31a0e9ba3d787ff877c20a868
COMMIT=BLOCKED_INDEX_LOCK_PERMISSION_DENIED
PUSH=NOT_ATTEMPTED_NO_NEW_COMMIT
MAIN_CI_RUN_URL=PENDING
MAIN_CI_ATTEMPT=PENDING
INDEPENDENT_REVIEW=PENDING
REAL_PG17=NOT_RUN
REAL_WORKER=NOT_RUN
REAL_SCHEDULER=NOT_RUN
REAL_RESOURCES_CREATED=0
REAL_RESOURCES_DELETED=0
ROOT_ATTEMPTS=0
HOTSPOT=NONE_PROVEN
B_GATE=NOT_APPROVED
TARGETED_PG17_GATE=NOT_APPROVED
AUTHORIZATION=AUTHORIZATION_PENDING
BUDGET=DRAFT_NOT_APPROVED
NEXT=CHATGPT_INDEPENDENT_REVIEW_AND_EXACT_SHA_CI
```

未测试或尚未提供：真实身份/签名验证器、跨进程持久 UUID/lease、真实资源预算强制执行、
Worker 采集 hook、系统级终止/清理、POSIX 断电耐久性和生产执行。它们不是本轮交付的
执行能力；未来需要独立授权、实现和验收，本轮没有启用入口或签发 permit。
