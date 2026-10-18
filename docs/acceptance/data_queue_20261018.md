# 数据任务队列与安全取消：验收与发布

范围：用户《统一数据任务队列与安全取消详细修改任务书 V1.0》T01–T10。
冻结基线：`master@7babdd2356dd3dd1dd52f60a8d8c85c84a474d22`。保持 master，不重写历史。
不重命名现有里程碑；策略/指标/财务/PIT/研究/Agent 只读边界保持，未部署业务环境。

## 设计决策与兼容

- DATA_MUTATION 的六类数据任务全局并发 1；独立 PostgreSQL 事务锁保护入队和领取，
  RUNNING 行保护整个执行周期。取消中仍 RUNNING，直到当前执行者安全退出。
- 同参数、日期和完整计算身份去重，来源/时间/随机 ID 不参与；容量只计等待，默认 100。
  部分唯一索引兜底，并发冲突回滚后返回已有 ID；终态释放指纹。
- 数据 FIFO 按 started_at/id；临时锁不越队首。依赖未结束可等待，最早可运行的后续无依赖任务可执行。
  新任务 started_at 使用过程锁内的数据库 clock_timestamp，避免认证/长事务开始时间或主机时钟偏差倒置 FIFO。
  依赖非 SUCCESS 终态标 BLOCKED。只接受既有顶层数据任务作为依赖，没有更改入口，不能创建环。
- 相邻 PAPER/回测/分析不并入新数据通道，继续自身身份/取消/恢复；非数据领取保留 SKIP LOCKED。
  Research 在持续数据队列下可能饥饿，P0 明确数据优先；已运行研究不因后来排队而退回 QUEUED。
- 数据与 RUNNING Research 心跳失联时不自动置 FAILED，也不释放执行槽位。保守阻塞是安全策略，
  不宣称进程仍活着，不宣称自动恢复。Research 的 QUEUED 过期政策仍保留，数据 QUEUED 不过期。
- 新格式任务必须携带原领取 worker/token 派发；不能从新数据库记录冒领其他执行者的凭据。
  终态与进度 CAS 校验 RUNNING/worker/token，成功还检查未取消；历史终态不可改写。
- Catch-up 内部 recalculate 是同步子任务，有 parent_job_id/execution_owner，继承父 token，不独立领取。
  取消父或运行中的子都会停止父链路；先清理子/Dirty，再结束父，不发布假 SUCCESS。
- 0057 只增字段、索引、RESTRICT FK 和非自引用约束。不改原 started_at、不补造历史执行时间。
  原历史结果与 Hash 不回填；旧排队无完整身份快照明确失败要求重提，旧运行记录留待人工确认。
- 新 Job 父子/依赖 FK 纳入保留引用清单，查询使用别名关联外层 Job，不能把自表引用误作自比较。
  数据库触发器拒绝重写链接或插入指向不存在/非顶层数据任务的链接，配合创建次序阻断环。
  BLOCKED 为已结束的历史诊断记录，保守保留，不擅自扩大既有失败日志删除口径；默认 Job 删除仍关闭。
- 取消是协作式，不是全任务回滚。已提交的完整数据保留；未提交事务回滚；Dirty 重开且不增 retry_count。
  已取消不意味着已保存结果必然可复用，仍必须走原完整性、版本、PIT 与来源门禁。
- 六类数据任务均支持运行中安全点取消。Research/回测沿用原取消能力；其他分析任务未建立本次数据通道的
  安全检查点与所有权协议，只允许原有排队取消，运行取消明确 409，不能以 UI 操作替代执行停止证明。
- 新格式 staged Derived 行在来源 Job SUCCESS 前不计入分析就绪/覆盖统计；物理数据保留，失败/取消不能
  冒充发布成功。仅对带 execution_token 的新来源生效，不重新解释旧历史或修改计算公式。
  旧 RUNNING 来源同样不能冒充已发布；旧已结束历史保留原兼容口径，不回填执行身份。

## 超时与真实性边界

Tushare 当前锁定 SDK 的 pro_api(token='', timeout=30) 将 timeout 传给 requests.post。
使用该受支持参数配置有限单次连接/读取等待，重试次数/退避有上限，重试前后查取消。
未使用线程硬杀；无法在第三方调用内部或长计算块内立即打断。请求返回成功不是停止成功。

数据任务专用 Session 在每个新事务设置 SET LOCAL SQL 超时；入队/领取/取消也设置事务内有限等待。
连接归池后不污染其他事务。数据库 SQL 超时由 PostgreSQL 取消当前语句，随后必须 rollback。
心跳单独线程只更新 heartbeat，不更新 last_progress_at；无业务进展/取消延迟只告警，不改终态。

本版不支持主动租约接管，也没有逐行数据写入 fencing。仅改 token/状态不能证明旧 SQL/SDK 已停止；
禁止据此放行下一 Writer。若旧进程可能继续运行，宁可保留 RUNNING 阻塞并人工排查。
数据库连接失效/SQL 执行结果未知时，数据任务不走普通 FAILED 释放路径：保留 RUNNING、尽力保存
execution_unconfirmed 与脱敏首因、停止本次执行心跳；诊断写入也失败时仍保留槽位并明确记录日志。
该状态取消接口返回 JOB_EXECUTION_UNCONFIRMED，不伪报安全点已退出。PostgreSQL 明确响应 57014/55P03 等
已终止语句且回滚成功的错误可正常失败收尾。最终 SUCCESS 提交响应丢失时不覆盖可能已提交的终态。

## 验证与 S01–S30 映射

测试数据库必须显式指定 DATABASE_URL/TEST_DATABASE_URL 为允许测试的 PostgreSQL 17；
集成用例只创建唯一命名的合成库，结束后只删除自身合成库。禁止以 .env 业务连接运行。

| 场景 | 自动化证据 |
|---|---|
| S01/S02/S03/S15 | test_data_queue.py：连续提交、并发去重、FIFO、排队取消和双 Session 争领 |
| S04/S05/S13/S22/S23 | 同文件：claim/cancel、success/cancel 竞态、真实退出前持槽、旧 token/派发拒绝 |
| S06/S07/S08/S09/S10 | 业务阶段回归：Backfill/补算/基础同步/日更/校验；已提交结果与 Dirty 不丢 |
| S11 | Catch-up 父/子两方向取消，有真实 parent FK/继承 token；均终态后才放行 |
| S12/S16/S21 | 依赖 BLOCKED、合法排队不超时、排队身份变化明确失败 |
| S14 | 队列为持久化记录；独立 Session 重新领取；失联 RUNNING 保守阻塞，不重放 |
| S17/S18/S19 | SDK timeout 参数/重试与取消单测；PG lock/query 超时；独立进度字段与 UI 警告 |
| S20/S27/S28 | Scheduler 在手工任务后排队/去重；运行 Research 不被新队列退回或与数据双跑 |
| S24/S26 | 完整队列不受最近 30 条挤出；前端合并服务器完整队列，无浏览器内存队列 |
| S25/S29/S30 | 未知/PAPER 404、不支持运行取消 409、终态 CAS 与 UI 禁用回归 |

前端新增 JobCenter 状态/顺序/按钮、App 确认/防双击/真实错误、队列合并/去重反馈和统计退出刷新测试。
原所有金融/研究/PAPER 回归仍在完整 pytest 门禁中。浏览器使用全量拦截合成 API，不访问 Provider 或业务服务。
执行结果以最终交付及同 SHA CI 为准；不能以旧 CI、镜像构建或合成环境替代真实生产业务验收。

本地交付前检查：1427 项后端单测通过；38 项 PostgreSQL 队列专项与 23 项 Worker 单测通过；
断连安全用例先用旧式“异常即 FAILED”路径复现失败，再恢复新实现验证通过。前端 151 项测试通过，
语句覆盖率 86.74%，构建通过；1440/390 两种宽度共 18 个合成浏览器场景通过。
完整 pytest 已执行：首次完整隔离库运行有 8 项旧迁移夹具/旧 head 断言不兼容新字段，
修正夹具后相关保留/迁移 22 项及停牌 Schema 6 项复跑通过；最终完整 1965 项以本次提交 CI 为门禁。
Ruff 与 git diff --check 通过；0057 在隔离 PostgreSQL 17 正式迁移验证，不涉及业务数据库。

Docker 验收命令：在构建 ssh-stock-app:local 后，显式设置隔离的 TEST_DATABASE_URL 与相同 DATABASE_URL，
运行 `python scripts/data_queue_container_acceptance.py`。脚本只接受 loopback 测试配置，只创建/删除
自身随机 queue_acceptance_* 合成库及有专用标签的临时容器。单/双 Worker 两套各跑 6 个带有限 SQL 延迟
的合成校验任务，按 50ms 采样顶层 RUNNING <=1；真实 claim/dispatch/CAS/heartbeat，不调用行情或金融计算。
最终本地镜像测量：单 Worker 88 个样本、双 Worker 83 个样本，两套 max RUNNING=1、6/6 成功；
最终镜像与 HEAD 回执由同 SHA CI Artifact 记录。

## 发布前与迁移

1. 确认环境及可恢复备份；先在隔离 PG17 演练非空升级、历史字段保持、索引/约束及迁移单头。
2. 维护窗口停止旧 Scheduler 入队；等待/安全收尾旧 Writer。确认所有主机/容器旧进程退出，
   PostgreSQL 中对应连接/写事务不再执行。不能仅看心跳陈旧或某个 Worker 服务 UP。
3. 0057 为事务内普通索引构建，会扫描历史任务、短暂阻塞写入；lock_timeout=5s、statement_timeout=10min。
   超时整体失败，保持旧 Schema。大库应延长维护窗口并先评估任务表规模/磁盘与查询计划，不能声称零锁在线升级。
4. 执行 alembic upgrade head/current/heads，统一部署 API/Worker/Scheduler/前端，再启动新 Worker。
   默认 Compose 一个 Worker；多实例也必须使用同一 PG 通道锁与领取实现，不允许旧 Worker 混跑。
5. 只在批准的测试日期/环境做入队/取消冒烟，核对队列数、身份、时间、终态、质量和来源记录。
   代码推送不等于生产数据库已迁移或任务已重试。

## 人工对账与回滚

失联 RUNNING 不自动改 QUEUED。先冻结所有领取/调度，确认旧执行者与写事务已停止、保存原任务与已提交结果证据，
再另行审批逐个 Job 的维护对账：核对 id/status/worker/token，内部子任务先处理，父任务最后处理；
明确记录人工确认停止原因和结束时间，保留 Dirty 与审计。没有上述证明时不得放行队列。
本次交付没有对业务库执行该操作，也不提供不经确认的“一键解锁”。

优先保留增量 Schema 回滚应用。新格式活跃队列存在时 downgrade 会拒绝，不允许删除任务来绕过。
旧应用只支持一个活跃数据任务，不能直接启动旧 Worker 消费新队列；必须冻结领取、等运行者退出、
保留待办并在隔离库演练人工恢复方案。不会为回滚清理 Raw/Derived、重写历史 Artifact 或金融账本。

## 未包含的能力与风险

- 不提供抢占式终止、自动接管、断点续算、优先级调整、重叠范围自动合并或所有类型统一调度。
- 未做业务库迁移、ECS 部署/重启、真实 Provider 拉取或实际补算。需另行授权并复测生产负载。
- 继承依赖的 npm 安全告警及大 chunk 警告不属于本次依赖升级，不能声称已消除。
