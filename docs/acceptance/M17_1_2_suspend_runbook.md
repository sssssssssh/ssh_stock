# M17.1.2 部署与 G1 小范围验收

## 范围与审批

此文为运维步骤，不是自动执行授权。开发阶段只读核对了业务库和 Provider，
所有迁移、合成数据写入和故障注入均在隔离 PostgreSQL 17。
业务库目前只读取证版本为 0055；不要把代码、镜像构建或 CI 通过当成已完成生产升级。
不清库、不改旧迁移、不截断描述、不禁用约束/质量校验，不开启 PAPER 或 Job 删除开关。
此前其他任务的清库/不备份授权不能代替本次迁移的审批。

## 升级前

1. 核对待部署 Git SHA、同 SHA 的完整 CI SUCCESS、数据库目标及现有 revision。
   核对 .env 与外部 PostgreSQL 17 可达性，不输出连接串或 Token。
2. 等现有任务安全结束，暂停旧 Scheduler 与 Worker，停止新的手动入队；
   在批准的维护窗口停止旧 backend，避免混用新清洗与旧 VARCHAR(32)。
3. 按 `../部署与备份.md` 备份并验证恢复能力，在独立预发布结构副本演练；
   检查长事务、锁、磁盘余量和 stock_suspend_daily 当前行数。
4. 0054/0055 的线上预建索引要求仍适用。已有 0055 仅增加 0056；不要重做或改写历史迁移。

## 经审批后的升级

使用已核对的环境，在项目根目录运行；已有 Python/依赖/PYTHONPATH 时不必重复安装或设置：

```bash
export PYTHONPATH=backend
python -m alembic current
python -m alembic heads
python -m alembic upgrade head
python -m alembic current
python -m alembic heads
```

current 与 heads 均应为 `0056_suspend_timing_text`。0056 只将 nullable VARCHAR(32)
扩大为 nullable TEXT，不拉数据、不补算、不改旧记录、主键和 updated_at。
迁移锁等待上限 2 秒、语句上限 30 秒；超时应查锁后重试，不改成无限等待。

Docker 部署仍使用原 Compose 五服务和外部数据库。上述备份/停旧服务/审批完成后，
可由 `docker compose up -d --build` 的 migration 服务执行升级；不要把此命令当成只构建。
只构建且暂不启动迁移可用 `docker compose build`。前端没有功能改动，不需要改 API 地址。
若本次只批准单日 G1 验收，不要同时恢复 Scheduler，可先使用
`docker compose up -d --build backend worker frontend`，仍由 migration 依赖先升级结构。

## G1 真实小范围回填

必须先获得明确的业务库迁移和单日任务授权；源 Token、基础信息、交易日历及权限应可用。
独立 Worker 只消费已入队任务，启动前先核对没有其他不希望执行的 QUEUED 任务。
不以单层计算 CLI 冒充完整计算任务；保持自动调度/PAPER/Job 删除原开关不变。

```bash
export PYTHONPATH=backend
python -m app.cli worker
```

另一个终端提交单日任务：

```bash
export PYTHONPATH=backend
python -m app.cli backfill --start 2024-09-13 --end 2024-09-13
# 等待该 Job 真正 SUCCESS 后再执行下一条；CLI 返回 job_id 仅表示已入队。
python -m app.cli validate-data --start 2024-09-13 --end 2024-09-13
```

宿主机没有 Python 的 Docker 环境，保持 worker 容器运行，改在 backend 容器入队：

```bash
docker compose exec backend python -m app.cli backfill --start 2024-09-13 --end 2024-09-13
# 同样等待该 Job SUCCESS 后再提交校验。
docker compose exec backend python -m app.cli validate-data --start 2024-09-13 --end 2024-09-13
```

在数据页查看两个 Job 的最终状态和错误，记录真实 Job ID/范围/耗时，不伪造 SUCCESS。
backfill 会检查当天完整 Raw，不只是停牌表；其他源失败必须如实记录，不能归为本补丁已通过。
已有完整数据会按既有幂等规则跳过；若无法证明停牌记录与源一致，需要先审查具体缺口，不能清表强拉。

只读核对：

```sql
SELECT trade_date, count(*) AS rows,
       count(*) FILTER (WHERE suspend_timing IS NULL) AS null_timing,
       max(length(suspend_timing)) AS max_timing_length,
       count(*) FILTER (WHERE length(suspend_timing) > 32) AS long_timing
FROM stock_suspend_daily
WHERE trade_date = DATE '2024-09-13'
GROUP BY trade_date;

SELECT suspend_type, count(*)
FROM stock_suspend_daily WHERE trade_date = DATE '2024-09-13'
GROUP BY suspend_type;

SELECT dataset, status, actual_rows, error_count, issue_codes
FROM data_quality_daily WHERE trade_date = DATE '2024-09-13';
```

本次只读源实测 13 行、12 个空描述、1 个 35 字符描述、13 个 S。
这是特定 Token/接口在取证时的结果，不是永远固定的业务断言；源修订时以实际响应核对。
零行不是通过证据。验收需 Job SUCCESS、实际字段/NULL/分类与源一致、Raw 质量通过。
只拉 Raw 不自动补算；有 Dirty 或 Derived 依赖变化时，质量通过后按正式补算流程修复。
已有 PAPER 财务和冻结证据不得原地改写。

## 回退与最终状态

首选回滚应用并保留 TEXT，避免有损缩列。不得改写/删除长描述以通过 downgrade。
0056 downgrade 在排他锁内检查，任一 length >32 明确拒绝并回滚；无超长值才可缩回。
其他迁移原有不可变历史回退限制继续有效，不对业务库运行 CI 的降级测试。

未部署或未获得真实任务验收时，结论只能是“代码整改通过，真实业务验收待完成”。
发布记录需包含最终精确 SHA、同 SHA CI URL/回执、0056 head、真实任务 ID/范围和前后统计；
未执行项明确标为待审批，不使用隔离库合成 Job ID 替代生产 Job。
