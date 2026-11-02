# WORKER-02 — read-only incident review, not permission to recover

Do not run these against any business target without separate target/scope approval.
The CLI is read-only and never unlocks a Writer:

```bash
python -m app.cli reconcile --job-id <root-job-uuid> --dry-run
```

In a separately authorized incident session, obtain Docker facts with read-only
inspection (substitute a verified old container identity, not a guessed name):

```bash
docker inspect --format '{{.Id}} {{.Image}} {{.State.Pid}} {{.State.StartedAt}} {{.State.Restarting}} {{.State.OOMKilled}} {{.RestartCount}}' <verified-container-id>
docker top <verified-container-id> -eo pid,ppid,lstart,args
```

Do not publish raw inspect output, env, args or logs containing credentials. Review
every Worker host and legacy process, the restart policy and kernel PID start
identity with an independent responsible operator. A container being stopped now
does not prove that an older process committed nothing before stopping.

Only separately approved DB roles may collect bounded read-only evidence:

```sql
BEGIN READ ONLY;
SET LOCAL statement_timeout='3s';
SET LOCAL lock_timeout='1s';
SELECT id,status,parent_job_id,heartbeat_at,last_progress_at,cancel_requested
FROM job_run WHERE id=CAST(:job_id AS uuid) OR parent_job_id=CAST(:job_id AS uuid);
SELECT job_id,state,publish_started_at,published_at FROM data_publication
WHERE job_id=CAST(:job_id AS uuid);
SELECT pid,backend_start,datid,state,xact_start,wait_event_type,wait_event,
       pg_blocking_pids(pid) FROM pg_stat_activity
WHERE datname=current_database() AND pid<>pg_backend_pid() LIMIT 100;
SELECT count(*) FROM pg_prepared_xacts WHERE database=current_database();
ROLLBACK;
```

`:job_id` is a bound parameter in the chosen read-only client, not string
interpolation. No SQL text, Raw, DSN, raw token or full env should be collected.
An empty connection list is only a snapshot; it does not prove executor exit.

Approved sequence (not executed by this revision): independently freeze new
claims → inventory every old host/container/PID plus all pending commits → obtain
fresh dual approval and installed authority → normal guarded ABORT/CAS transaction
→ reconcile task, children, dirty ranges, candidate and unchanged public A → deploy
a complete reviewed Worker version → submit a new job UUID. Existing RUNNING jobs
are not silently retried or marked successful. If any prerequisite is unknown,
stop at EXECUTION_UNCONFIRMED; no UPDATE-to-FAILED workaround is provided.

Diagnostics opt-in for an independently approved future new Worker deployment:
`WORKER_DIAGNOSTICS_ENABLED=true` (default false). It is separate from the three
optimization flags and does not enable any of them. Do not hot-edit a running Worker.
Task metadata contains execution_diagnostics, heartbeat_health and database_sessions.
Missing phase = NOT_INSTRUMENTED, not zero seconds. FETCH mixes cursor/transport/Python
materialization; nested phases must not be summed. Heartbeat confirms communication
only. Unavailable diagnostic writes are logged as DIAGNOSTIC_PERSIST_UNCONFIRMED;
neither their absence nor their presence authorizes task recovery.
# WORKER-02-R2 现场交接补充（2026-10-29）

任务书指定根任务为 `4a8c98cb-2c98-4a37-898d-c79c134da331`。785000行、11:32最后
进度、11:34/11:36心跳57014是待复核历史线索，本轮没有连接现场或确认原因。
须先取得单独的只读目标授权再按下列既有命令核对所有执行端；不要把本机合成sleep
实验、进程轮询或空pg_stat_activity当现场结论。

内部恢复原语现提交前再次调用独立authority；authority必须重核有效期、撤销和
全端退出/未决提交，不能用LocalTestAuthority替代。生产服务仍未安装，普通CLI没有
执行入口。未知COMMIT ACK后只允许新连接只读核对：内部recovery_commit_status使用
可重复读快照核对原身份、ABORTED账本、审计和活跃子任务；UNCONFIRMED不准重放。
它不是新授权或Web/CLI恢复入口。现场检查/authority/恢复执行/重新部署必须分别授权。
