# BIZ-PERF-01 集中整改交付：PERFORMANCE_OPEN

本轮基线 `06b4cd6ee1783c399bdb89264c8da6190f282273`，初始 clean，经 fast-forward 拉取。
只在 master 开发；没有连接阿里云、读取业务数据库、部署、重启业务服务、启用开关或重提生产任务。
结论仍为 **CHANGES_REQUIRED / PERFORMANCE_OPEN / NOT_RELEASE_READY**。代码交付不等于性能验收通过。

## 完成的业务修复

- 真实 daily/recalculate/catchup Worker 在 Job 开始冻结三项有效开关、源码摘要、Git HEAD
  （可用时）、工作区状态和日期。子任务继承根身份并记录自身区间；计数明确为根累计。
- 常驻 Worker 保存进程开始时的源码身份，拒绝在下一 Job 偷换为新磁盘版本；运行中检查开关，
  月度因子开始及最终发布检查源码；重启后不能重冻已有 Job 的不一致身份。
  源码目录 symlink 拒绝。更新代码必须安全停止并重启 Worker，禁止热换文件。
- 同时记录 SQLAlchemy execute 的操作计数/耗时、交付分片、实际 psycopg 命名游标
  fetchmany（包括 priming、EOF、失败且返回行数未知的调用）及阶段耗时；不保存 SQL 绑定参数、
  DSN 或输入行内容。FETCH 与 execute 分开，阶段相互嵌套，不能相加。
- InputBlock 恢复 `pd.NA`、`NaT` 和所有 Decimal 的原始标量（含 NaN、小数位和零符号），再做全窗口 dtype 推断；
  日期裁剪保留其位置。修复 macOS 可用内存观测及异常去敏。free+inactive 只是估计；
  1GiB retained / 3GiB RSS 失败阈值不是物理硬限制，观测失败不静默降级。
- Job 元数据保持 owner/token CAS、发布状态与心跳的合并边界；不改变金融身份、公式、
  表结构、PIT 或生产策略参数。三项优化开关仍默认 false。

## 源码版本与 CI 边界

旧八份 manifest、原始协议、一次性授权及历史样本保持字节不变。旧源码固定
`1e510532bd140110e29b10b6e4eed30fbd573159`，当前业务源码另设精确 BIZ manifest。
原冻结清单仍核验旧 Git 对象；普通当前合同另外核验准许的实际字节、全部 HEAD、隐藏索引、
symlink/inode 与 HEAD 漂移。仅缓存固定 Git 对象，不缓存当前文件或业务数据。

只适配登记的 24 个原测试函数和 2 个辅助函数；签名、参数、旧拒绝断言及其余原字节均检查。
原基线 4,925 个 case ID 没有删除；新增缺陷回归另外计数，无 skip/xfail。
普通小型 PG 诊断通过显式、自动恢复的测试版本路由检查历史和当前源；真实 A4 CLI
仍拒绝当前业务源码，BIZ 静态指纹不能签发 G1。没有修改 workflow、正式 Gate 或历史 SQL。

实际复核原 main CI 的唯一小专项失败是
`test_a4233_background_observer::test_frozen_baseline_bytes_and_old_workflows_unchanged`；
原始去敏 JUnit 和 INCOMPLETE 回执已原字节保存。A4-2 原工件没有 JUnit，失败在
`source_contract:31`，尚未运行迁移/pytest，不能称作某个 JUnit 失败。
原 ZIP 摘要及失败工件见 baseline 和 `biz_perf_01_review/`。

## 百万行真实 SQL 证据

已按事前提交协议运行一次独立 PG17.11 诊断，物理 marker/ID 在建库、迁移前核验。
1,000 标的 × 2022–2025 工作日 = **1,043,000 StockDaily**，复权和状态同规模。
数据库实际 582,063,795 字节。源码身份固定于
`fbda8774d4a4f04b27a02a76058f90b84d907b89`，不是本轮最终 HEAD 的完整业务性能证明。

| 核验阶段 | 实际 wall 秒 | 全行指纹 SQL 数 |
|---|---:|---:|
| 初次：2022-11-27..2024-01-31 | 3.093881 | 6 |
| 扩展至 2024-03-31 | 3.425117 | 6 |
| 累计扩展至 2025-12-31 | 7.921207 | 6 |
| close 后独立最终再验 | 7.922271 | 6 |

保留全部 18 份 EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)，回放开销未混入原 wall。
累计范围计划：日线 2,918.595ms / 15,530 read blocks；复权 1,177.410ms / 8,246 read blocks；
状态 3,809.486ms / 19,592 read blocks。全行聚合随累计范围扩大重复扫描；这些计划不足以
单独证明 CPU 归因或某个优化的因果收益。最终再验仍计原七次预算检查。
完整 JSON 无损 gzip、源码身份、原始/压缩 SHA256 均已保存。

这次诊断不是十表非空布局或完整 Worker 矩阵，也不是 C1/A4/G1 性能实验。
没有据此盲改 `_lookup_batch()`、质量 SQL 或用不可靠的缓存跳过全行校验。

## 容量资源拒绝与尚未完成项

所有本轮测试结束后，在空闲本机执行一次已登记的只读资源预检：
可用内存估算 **2,235,957,248 字节（2.08GiB）**，预留要求
**4,261,412,864 字节（3.97GiB）**；磁盘可用 14,767,112,192 字节，高于原 8GiB 预留。
内存预留由原 Worker RSS 阈值及 PG 实际 shared_buffers、maintenance_work_mem、
max_connections×work_mem 推导，是保守资源预留，不是 OOM 实测或运行成功保证。
结果 **RESOURCE_DEFERRED / matrix NOT_RUN / 成功 Job 0/18**；没有换小数据补交。

| 工作包 | 实际状态 |
|---|---|
| W00 | 已锁定基线、原失败工件与历史小样本，未覆盖或冒充新结果 |
| W01 | 版本路由及拒绝回归已修复；最终 SHA 普通 CI 结果以 Actions 工件和交付消息为准 |
| W02 | Job/进程源码与开关冻结、区间、真实 FETCH/SQL/阶段证据已实现并做真实 PG 回归 |
| W03 | 输入验证百万行计划已取得；完整链及 candidate/store/quality/opportunity 计划仍缺 |
| W04 | dtype/NULL/内存与失败清理已修；可靠的跨提交分段验证优化尚未实现 |
| W05 | 未完成；缺乏所需真实布局计划，没有生产候选/质量 SQL 性能补丁 |
| W06 | 未实施；没有足够规模机会计算热点及独立完整 Golden 证据 |
| W07 | RESOURCE_DEFERRED；1/3/12 月旧新各三次、十表非空和 ≥30% 均未验收 |
| W08 | 相关 PG 回归及普通测试已执行；本机 Linux 专属边界不能替代 Ubuntu 全量 CI |
| W09 | 本报告、原始证据与运行/回滚边界已交付；等待再审阅 |

AT02/03/11/12 的源码/身份/安全修复与回归已交付；AT04/05/06/10 的完整容量和成本证明
尚未满足。AT07/08/09 已有小型真实 PG 功能/故障回归，不能提升为百万行全矩阵通过。
AT01 必须由最终同 SHA 的四条普通 Actions 核验；高成本条件跳过不算容量 PASS。
AT13/14 保持 RESOURCE_DEFERRED、PERFORMANCE_OPEN，不允许发版或生产灰度。

## 实际验证与限制

- 相关 PG17 诊断/业务：133 passed；增加真实 FETCH 后业务相关 64 passed；
  最后进程源码/Worker/FETCH 专项 39 passed。各次运行有独立 JUnit SHA，不相加冒充唯一 case 数。
- 本机全单元：4,007 passed、5 failed、0 skipped；余下是既有 macOS 下 Linux watchdog/
  OpenSSL 信任路径失败，未改其断言或平台标准。全量本机 pytest 在历史 Linux IPC 测试阻塞后
  中断，909 passed、22 failed；该早期运行还暴露测试 PG 未预加载统计扩展、40 连接耗尽、
  旧冻结路由问题。原始失败保留，随后仅修正独立测试实例为统计预加载/100 连接并回归。
- 前端 162 tests passed，coverage 87.27% statements，build 成功（已有 chunk 大小提示）。
- Ruff、diff check 通过；独立 PG17 Alembic upgrade/current/heads 均为 0058_data_publication。
- 不改 requirements、Docker/Compose、前端、模型、迁移或 config，所以未构建/启动业务镜像。

原始本机 JUnit 保存在开发输出目录，仓库记录其 SHA 与完整失败节点（去除本机路径）；
GitHub 原始工件由 Actions 保存。最终交付消息给出最新 SHA、四条同 SHA CI 链接与实际结果。
旧 8 股票报告仅作历史：1/3/12 月改善 32.8%/31.3%/21.8%，仍不能证明当前 12 月或百万行达标。

## 启用及回滚边界

生产三开关继续关闭。本轮不授权云库连接、配置启用、备份/迁移、任务重提或服务操作。
后续需资源足够的独立合成 Runner，完成十表代表性 fixture、固定快照的全部矩阵与故障验收，
以及实际热点计划，再审阅生产 SQL 补丁和收益。不能用绿色合同替代这些步骤。

生产灰度需单独授权并事先备份/核验 A 与发布账本，先通过原有取消入口安全停机，
确认 CANCELLED/ABORTED 或完成未知提交审计后再更换版本/开关。未知提交不得强制释放为成功。
回滚使用已审核源码和关闭开关；旧 Job 身份漂移会被拒绝，不自动重提或混用新旧计算。
交付结束停止本轮自建测试 PG，不改变任何已有用户服务。

补充 Decimal 表示回归：同值的 `1.100`/`1.10` 与 `-0.0`/`0.00` 不能被 Categorical
等值合并；Float 声明路径也不得把实际 Decimal 对象隐式转成 float。新增两参数 RED
均真实失败，修复后与输入/资源单元共22项通过，裁剪后仍逐一核对 Decimal.as_tuple()。
所有保留的 Decimal 对象继续计入缓存字节与原内存失败阈值；不放宽比较或资源标准。
