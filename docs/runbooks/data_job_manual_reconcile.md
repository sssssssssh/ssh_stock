# 数据任务失联：诊断与人工对账（不提供一键解锁）

本文件是审批后的 DBA 操作手册，不是生产执行授权。本次代码/CI 不会迁移或修复业务库。
先确认目标环境与可恢复备份；只在批准范围内操作指定 Job。心跳陈旧、Worker 服务 UP/DOWN、
没有匹配 application_name 的连接，都不能单独证明旧执行者已经退出。

## 1. 冻结与事故快照

1. 在维护窗口冻结所有 API 数据提交、Scheduler 入队和所有 Worker 领取。列举所有主机、
   容器、终端与手工执行者；同时停止使用旧 recalc-* / evaluate-signals 直写 CLI。
2. 仅管理员持有服务器/数据库凭据运行只读命令：
   `python -m app.cli data-job-diagnose --job-id <UUID>`。
   命令只 SELECT，数据库强制 READ ONLY；不输出原执行 token、连接串、IP、SQL 或原异常参数。
   保存时间、操作者、审批单、输出和冻结前后的进程清单，保存位置采用受控事故档案，不入 Git。
3. 诊断始终返回 process_exit_proven=false：服务不能通过数据库证明所有远程进程已退出。
   不存在 --apply/--force/unlock 参数，也没有公开 HTTP 状态修复接口。

## 2. 证明旧执行者与 SQL 已停止

1. 逐台核查实际 Worker/容器/手工进程，并保留明确退出证据。Provider 网络等待期间可能没有
   数据库连接，因此“数据库空闲”不代表 Python 进程已停止。不能只关闭浏览器。
2. 由有权限 DBA 核查 pg_stat_activity、pg_locks、事务和连接池。任务事务的 application_name
   为 space-data/<根 Job UUID>；旧版本可能没有该标记，必须同时核查所有可能的应用连接。
   只记录 pid/state/xact_start/wait_event 等非敏感摘要，不将原 SQL/参数放入普通日志。
3. 本手册不授权杀进程或终止数据库连接。若仍有写事务、Provider 调用、未知主机或连接不可查，
   保持 RUNNING、继续冻结，转专项审批；不能重置 token 或标 FAILED 来释放槽位。

## 3. 子任务、Dirty 与发布对账

1. 先核对根/子 job_id、父链、当前 status/worker 和执行身份指纹；实际 expected_token 仅由 DBA
   在受控数据库会话获取和绑定，不打印到终端、工单或 Git。
2. 检查 data_publication。PUBLISHED 与 SUCCESS 已同事务提交时，应承认已发布事实；不得因
   Worker 丢失提交响应把它改回 FAILED。若只一方成功，视为完整性事故，不使用下述普通恢复步骤。
3. PREPARING/ABORTED 候选不是已发布数据；保留 data_publication_row、preimage、Source 和 Scope。
   不把候选复制到业务表、不删 Raw/Derived/质量/Artifact、不重算旧账本或旧 Hash。
4. 逐条确认元数据引用的 Dirty id；主动取消重开 OPEN，不增 retry_count；故障恢复状态与原故障
   证据需要明确审批。不能对全部 Dirty 批量恢复，也不能凭 resolved_at 推断结果已经发布。

## 4. 经审批的维护事务

没有进程退出证明时禁止执行。本节由 DBA 将**明确目标和绑定参数**整理成变更单，在隔离库先演练；
不提供可直接对业务环境批量运行的清理脚本。默认先 BEGIN/SELECT/ROLLBACK dry-run。

固定顺序：取得数据通道 advisory transaction lock → 锁定指定根 Job（NO KEY UPDATE）→
按 id 核对子任务 → 明确 Dirty → 根 publication → 根 Job 最后终态；保持停止领取。
使用与服务相同的 INGESTION_ADVISORY_LOCK_KEY（由当前 job_guard 源码核对，不复制漂移值）。

每条修改必须有 CAS：id=:job_id、status=:expected_status、worker_id=:expected_worker、
execution_token=:expected_token；只允许原 RUNNING，目标仅 FAILED 或确实已完成停止的 CANCELLED。
任一 rowcount 不为 1，整笔 ROLLBACK，重新调查；不改 SUCCESS/PARTIAL/已取消的历史。
根 publication 仅允许 PREPARING→ABORTED，保留 identity、token、候选与原错误。

维护审计追加到 Job metadata.manual_reconciliations 数组，保存批准理由、操作者、UTC 时间、
旧/新 status、预期身份**指纹**、事故证据引用与“所有旧执行者/SQL 已停止”的确认，不保存实际 token。
原有 metadata/首因不能被替换；子任务先记录，父任务最后记录。终态、发布 ABORTED 与指定 Dirty
收尾在同一事务完成。COMMIT 响应未知时先重新只读核对，绝不盲目重放。

## 5. 有条件恢复

核对旧 A 仍可查、候选未外露、子任务终态、Dirty/审计真实且不增错误重试、根槽位确已合法释放。
仅启动一套新 Worker（不混旧版），先处理一个已批准合成任务，再恢复 Scheduler/API。
新请求是显式重提，不自动续算、接管或重放旧 RUNNING；未知身份继续阻塞。

生产验收需要另行审批：真实进程/数据库核查、维护事务、备份恢复与真实 Provider 负载。
隔离测试只能证明协议/事务与拒绝路径，不能替代对所有生产执行者退出的人工证明。
