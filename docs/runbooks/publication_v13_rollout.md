# V1.3 试运行与回退手册

本手册不是生产操作授权。本轮只完成代码及隔离验收，没有部署、云端 DDL、取消、重提或补算。

## 开发验证

使用独立 PostgreSQL 17；先在当前终端显式配置 `TEST_DATABASE_URL` 和 `DATABASE_URL`，
两者均指向允许测试的 loopback 实例和以 `_test` 结尾的库。密码只在本机环境中保存，不写进 Git。
不要省略这些配置而继承项目 `.env` 中的业务地址。性能脚本还会在应用配置导入前拒绝非隔离目标。

```powershell
python -m alembic upgrade head
python -m alembic current
python -m alembic heads
python -m pytest
python -m ruff check backend tests migrations scripts
python scripts/data_publication_capacity_v12.py --confirm-synthetic --levels smoke
python scripts/publication_candidate_benchmark_v13.py --confirm-synthetic --implementation baseline --rows 1000 100000 500000 --repeats 3 --public --output .codex_tmp/v13-baseline.json
python scripts/publication_candidate_benchmark_v13.py --confirm-synthetic --implementation current --rows 1000 100000 500000 --repeats 3 --public --output .codex_tmp/v13-current.json
```

性能命令按顺序执行，不同时运行其他容量测试；固定同硬件、PG 设置、输入和读者数量。
结果包含 SHA、工作区状态、环境、操作分位数、计划、I/O/WAL/TOAST、RSS 与读者延迟。
OS 缓存未受控会明确标记，不能称作冷缓存验收。最终 clean HEAD CI 工件才用于代码验收。
完整规模、已有候选、空/非空 A、scope 和 key 数阶梯参见 `.github/workflows/publication-v13.yml`。
V1.2 L2/L3、两次真实回滚探针及容器双 Worker 继续由主 CI 强制执行。

## 生产试运行前

1. 另行获得部署与写入批准；先检查最终 HEAD 的主 CI 和 Publication V1.3 工件，不能引用旧 SHA。
2. 本地与容器配置分别检查 `DATABASE_URL`、`DOCKER_DATABASE_URL` 的预期实例，脱敏核对主机、
   端口、库名和用户，不输出密码；Docker 服务名与公网主机可能不同，不能只按字符串判断同实例。
3. 对实际目标只读运行 `python -m alembic current` 和 `heads`，确认均为 `0058_data_publication`。
   `heads` 只表示代码，不证明目标库升级。本轮无新增迁移；意外不一致时停止并单独审批。
4. 保持 Scheduler 停止；确认所有旧版 Writer、旧电脑进程、容器和手工补算均退出。
   只读核对 Job status/cancel_requested/worker/token、publication、SQL/session 和未知提交证据。
   旧任务此前收到取消请求不等于现在已退出；不能直接 SQL 改终态、删除审计或解除占槽。
5. 备份并验证恢复，记录业务表规模、WAL/磁盘余量和批准的 RSS/WAL/延迟预算。
   代码测试通过不能替代这些运维条件；不要调大 300 秒发布保护或 1000 万行预算。

## 经批准后的步骤

先运行一个 2 至 5 交易日的完整补算任务，观察 read/compute/reconcile/lookup/store/publish、
每批完成数、操作耗时、最近推进和独立心跳；等到真实 SUCCESS/PUBLISHED 后核验公开结果。
暂存数不是公开行数，范围核对 complete 不是写入完成，心跳正常不是业务已经推进。
通过后再单独批准一个月的完整任务。分段是不同根任务，不得拆开同根事务的原子发布。

慢批、锁等待或疑似卡住时，先执行既有只读诊断：

```powershell
python -m app.cli data-job-diagnose --job-id <待核对任务ID>
```

按 README 的 `PYTHONPATH`/后端环境要求执行，保存脱敏阶段与 PG 等待信息，不记录整份 SQL 参数。
通过现有取消入口请求协作退出；长 SQL 仍需等待数据库返回或现有超时，不能承诺即刻中断。
只有实际回滚、终态和执行退出已确认，且人工再次批准，才提交新任务；无自动恢复或续跑保证。
未知 COMMIT 维持占槽并人工对账，不自动重放、标 FAILED 或重建候选。

## 回退边界

先保存日志与诊断，暂停新任务，保持 Scheduler 停止，确认当前 Writer 已真实退出后再安排回退。
仅回退应用镜像/代码到已批准兼容版本；本轮没有 schema 变更，不降级 0058、不清库或删除候选。
已发布结果、preimage、Research/PAPER 和审计保留；未发布候选不得强行合并。
旧版写入问题可能重新出现，因此回退后也不能自动重放失败任务或使用不安全旧 CLI 绕过队列。
再次试运行、恢复备份、人工终态核销及生产数据处理均须单独授权。
