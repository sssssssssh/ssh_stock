# 数据任务可靠性与安全发布 V1.1 收尾

后续 V1.2 已单独授权处理本文保留的冷启动/旧 CLI 风险，版本决定与现行验收见
[冷启动专项](cold_start_cli_closeout_v12.md)。下述内容保留为 V1.1 当时的范围和证据，
不表示当前仍允许旧 CLI 直写；生产部署/容量审批边界仍适用。

基线：master@ff3f221b4fcade5f9b8477d7df1acc66498abaf4。用户授权修改并推送，并明确日常仅网页操作。
当前记录为开发自检，最终同 SHA 证据以 GitHub CI 的 data-publication-reliability Artifact 为准；
CI 尚未通过时不得据本文件宣称可上线。没有业务数据库/阿里云迁移、停服务、补算或维护状态写入授权。

## 已实现与回滚边界

- W01：先提交血缘/主键/提交点/读者矩阵与两方案 ADR，复现旧 replace_slice 同键覆盖 A 的红灯。
- W02/W03：正式增量 0058；根任务私有候选 patch、分块检查点、内部 typed overlay、严格本来源质量、
  全请求验证日期统一发布、原像审计、终态 CAS、信号 id/评价证据、17 处来源保留；最新/JOIN/count/分页与
  多语句发现快照一致。暖启动额外日期不发布。Dirty 修复与根发布一致，子 SUCCESS 不提前认证公共结果。
- W04：管理员只读诊断与 DBA 审批/CAS runbook，无 --apply/--force、公共 HTTP 解锁或强杀。
- W05：持久唯一调度意图、容量/数据库异常证据、300 秒限速/12 次上限、就绪复核、周末/启动补偿。
  意图与 Job ID 同入队事务，丢提交响应仍能识别取消；取消不重放，超范围 skipped 不冒充完成。
- W06：现有任务中心增补候选/发布身份时间；既有取消中、待确认、完整队列与轮询不变，展示调度快照告警。
- W07：新增真实 PG17、实际完整 Service/质量链路、故障/并发/兼容测试；原会计/成交断言未降低。
  测试曾发现独立读会话破坏调用事务，已保留执行/会计原事务，24 项相关集成回归通过。

代码按发布核心、只读运维入口、Scheduler、UI、最终验收分组提交；禁止反向执行带证据的 0058 downgrade。
业务回滚须停止所有新旧 Writer、核对真实发布与未确认事务，优先保留新增结构/证据，只回滚应用；
不能让旧 Worker 消费新队列或恢复直接覆盖。详见 ADR 与 runbook。

## 自动化映射（均为合成数据，不是生产证明）

| 场景 | 可执行证据 |
|---|---|
| S01/S02 | test_data_publication 的真实 Worker 因子检查点取消，独立连接 A 不变 |
| S03/S04 | 全八表 candidate 后 CANCELLED/FAILED/PARTIAL；catchup 子成功后根取消/失败仍保留 A |
| S05 | 完整真实 run_recalculation + 原质量服务成功，无伪造凭据；跨八表发布与稳定信号 id |
| S06 | 真实质量拒绝借 A，缺校验凭据/阶段/错误 hash/预算均拒绝；候选改动使凭据失效 |
| S07 | 发布中断连回滚 A 并保守占槽；实际 commit 后丢响应仍为已提交 SUCCESS/PUBLISHED |
| S08/S09 | 缺 A、连接归池、NULL 来源兼容；不伪造旧 Job |
| S10/S11 | 调用真实 opportunities.trends 外层 SQL，JOIN/count/分页一致；候选独有日期不前移 latest |
| S12 | 发布前后多语句 RR 快照只看到完整 A 或 B |
| S13 | 原 test_data_queue 的 SQL/Provider 等待、未知执行与双 Worker 不接管；发布故障保留槽位 |
| S14/S15 | 诊断强制 READ ONLY、无进程退出证明/拒绝写参数；专有测试执行者退出后模拟审批 CAS/审计 |
| S16/S17 | 真实容量守卫、注入连接故障、计划限速/去重/重启重试、提交响应丢失、取消与限额 |
| S18 | 手工/调度混排不越序；沿用原 Research/PAPER 串行/互斥测试 |
| S19 | 既有冻结证据/PAPER/保留迁移完整回归；新增信号删除前评价审计与终态不可变 |
| S20 | JobCenter/App 单测和桌面 1440/手机 390 浏览器：断网、取消中、35 条队列、候选、发布、告警 |
| S21 | 专属非空 0057 库升级 0058，原值/Job/时间戳不变；原迁移约束/retention 兼容回归 |
| S22 | 容器单 Worker/双 Worker 队列，另加双 Worker 六次原子发布；同快照八表身份一致，RUNNING<=1 |

## 验证与复现

仅在显式确认的专属 PostgreSQL 17 测试 URL 下设置 DATABASE_URL、TEST_DATABASE_URL 和合成 Token。
新集成用例创建唯一名 m166_test_* 子库，通过正式 Alembic 迁移后使用，只清理这些自建测试库。
不得使用业务 .env 跑测试、降级或清数据。

```bash
python -m pytest tests/integration/test_data_publication.py tests/integration/test_schedule_compensation.py tests/unit
python -m pytest --cov=backend/app --cov-report=term-missing --cov-fail-under=70
python -m ruff check backend tests migrations scripts
python -m alembic upgrade head
python -m alembic current
python -m alembic heads
npm --prefix frontend ci
npm --prefix frontend run test:coverage
npm --prefix frontend run build
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example build
python scripts/data_queue_container_acceptance.py
node scripts/runtime_reliability_browser.cjs
git diff --check
```

本地已通过：全量 2008 项、0 失败、后端覆盖率 88.64%；随后补充的超时预算/skipped 调度两项纳入
最终 41 项专项回归全部通过（最终 CI 全量应包含 2010 项）。1467 项发布/调度/单元组合、24 项财务事务
相关集成和百万行 retention 原预算回归亦通过。原有财务断言未降低，早期 5 项失败不记为通过结果。
前端 157 项、覆盖率 86.79%、生产构建及 24 个桌面/手机合成浏览器场景通过，已检查截图与溢出。
专属 PG17 的 current=heads=0058_data_publication；Compose config/build、Nginx 配置检查通过。
构建曾遇到依赖下载哈希校验失败，保留校验和原依赖配置，重新下载后通过，未修改依赖锁。
单/双 Worker 各完成 6 项排队任务；另一次双 Worker 完成 6 次八表原子发布（含 1 个旧 A 共 7 个 SUCCESS），
最高顶层 RUNNING 均为 1。容器运行前核对 backend/config/迁移/依赖源文件摘要与当前 checkout 一致，
杜绝使用旧镜像；合成测试不启动用户服务。
最终 CI 生成真实 HEAD、完整 JUnit、0058 current=head、容器图像 ID 与同 SHA 浏览器收据，不硬编码自引用 SHA。

小规模候选测量：2000 行因子 candidate + ANALYZE/BUFFERS EXPLAIN，验证实体日期索引与 public 外层 JOIN
不访问候选表，写入耗时与实际计划在 targeted JUnit property。仅证明查询形状和协议，不能外推全市场全年。

## 未完成/需另行生产授权

- 已复现、未在本期修改的旧计算风险：Pandas 3.0.5 的历史交易状态左连接有缺口时，
  trade_status_present 可成为 object 列，取反得到 -2/-1；既有因子引擎会将有状态行也标记
  TRADE_STATUS_MISSING。该因子文件相对 ff3f221 未改。另有机会原因码比较 None RPS 值的旧异常路径。
  真实成功链路测试使用已有完整历史交易状态的 A 基线；它不代表无历史状态的冷启动验收。
  本期不擅自改变 eligible、指标公式或版本口径，需独立任务确定修复与版本/历史兼容策略并补回归。
  因此不能以本轮安全发布/CI 通过推断所有首次补算或历史缺口场景的计算结果已正确。
- 业务库 0058 维护迁移、备份恢复、真实 Provider、全市场/全年 JSON/WAL/磁盘与发布锁容量测量均未执行。
  默认发布 1000 万 patch 行/合并阶段 300 秒是失败保护，不是生产容量保证。证据默认长期保留，无自动 GC。
- 不恢复在 0058 前已被覆盖且没有副本的 A，不把旧 FAILED/RUNNING 中间行推断为成功来源。维护上线前
  必须另行盘点既有公共结果与旧 Writer；历史事故需人工对账，不自动回填或删除。
- 旧单表 recalc-* / evaluate-signals 按用户网页范围原样保留，未纳入候选保护；必须禁止混跑。新实现可
  在计算键原像改变时拒绝发布，但不是对任意直接写库的全面 fencing。
- 诊断不证明所有远程进程已退出；人工维护仍须 DBA/管理员审批、证据和绑定身份 CAS。没有网页解锁功能。
- npm 既有审计风险为 11 项（4 moderate/3 high/4 critical）与包体积警告，依赖未擅自升级，保留既有风险清单。

最终交付区分代码/合成验收完成与生产待批准；未完成项不应被“构建成功”掩盖。
