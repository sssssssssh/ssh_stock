# A4-2.1 容量 Runner 可行性与资源缺口预案

状态：预案，未采购、未配置自建 Runner、未连接业务 ECS/数据库。
c4f7d3e 的 L3-scaled-10pct 已成功（378240 行，Job 6438 秒）；L2 在 270 分钟软截止附近退出，
完整结果未取得，发布 gate 拒绝。旧收据只有 OperationalError，预算触发按配置/时刻推断，不回填原工件；
追补新增真实定时器标记，避免 rollback 异常遮蔽预算原因，详见 [执行报告](v14_a4_2_1_closeout.md)。
用户确认暂无独立 Runner，超预算保留 RESOURCE_DEFERRED；以下规格只是预案，不采购、不配置、不借用业务 ECS。

## 实际历史证据

基线 `02c69c612786` 的主 CI 39561948002 在容量步骤取消，存活工件仅有 L1 结果。
其 `run_level` 与本次实现的 AST 完全相同，自动测试防止缩水。旧工件记录 Linux/x86_64、Python 3.12.15、4 逻辑 CPU。
原始解码日志 SHA 与 ZIP 索引见 [验收矩阵](v14_a4_2_1_matrix.md)。

| 旧 L2 完成的暂存阶段 | UTC 时间 | 累计候选行 |
|---|---|---:|
| trade status | 2026-10-21 08:03:25 | 100000 |
| stock factor | 09:08:04 | 200000 |
| market / sector / theme | 09:08:51 | 203020 |
| stock state | 10:13:43 | 303020 |
| opportunity | 12:32:13 | 403020 |
| strategy signal | 12:33:23 | 503020 |

仅 trade status 至 signal 的已见跨度约 270 分钟，尚未获得完整 L2 603040 行与正式发布/回滚结果；
L3 尚未开始。拆级消除了对前端/容器核心通道的依赖，但不改变这一真实工作负载的成本。
这只是旧运行的资源风险证据，不是新运行的完成时间或可跨 Runner 使用的性能基线。

旧百万读 fixture 的三表及索引总量约 7.88 GB（publication 约 7.04 GB、trade status 约 0.84 GB），
尚未包含 WAL、排序临时文件、系统表和镜像。数据不能缩小，不能以空 B/窄 Factor 代替。

## 若当前运行仍不能在预算内完成

1. 保留 INCOMPLETE 和已完成组，标 RESOURCE_DEFERRED；release gate 必须失败。
2. 不提高 SQL 300 秒、发布 300 秒/1000 万行预算，不裁剪 L2/L3，不修改 run_level。
3. 可申请独立测试 Runner，起始验证规格为 Linux x86_64、8 vCPU、32 GiB RAM、至少 100 GB 可用 SSD，
   Docker + Python 3.12 + PG17；这是待实测的工程规格，不是完成保证或自动采购授权。
4. CPU 单线程性能、数据库 I/O 与逐行协议成本均可能影响耗时，不能仅按核数线性外推。
   容量须标独立 resource_class，L1/L2/L3 全部重跑并保存实际配置、RSS/WAL/读者/锁/回滚证据。
5. 读取比较仍保持 PG 2 CPU/3 GiB；若客户端资源类别变化，同 job 等保护 Q0 必须重跑，不能拼接跨机器提速结论。
6. 仍保留单 job 300 分钟与容量 270 分钟软截止，先测后决定是否可完成；不因自建 Runner 放宽验收。

GitHub-hosted 单 job 当前上限为 6 小时，不能用 400～600 分钟配置规避。
参见 [Actions limits](https://docs.github.com/en/actions/reference/limits)。

## 安全前提与授权边界

公开仓库不能直接把不可信 PR 派到持久自建 Runner。若后续明确批准，必须使用可信提交的手动入口、
一次性隔离 VM/JIT Runner、只读最小权限、每 job 新物理 PG17 标记与独立 system ID，运行后销毁环境。
不携带业务 .env/SSH key/云实例身份，不与业务 ECS 共机，不接业务网段/数据库。
GitHub 明确提示自建 Runner 可被不可信代码持续攻陷，详见
[self-hosted runner hardening](https://docs.github.com/en/actions/reference/security/secure-use#hardening-for-self-hosted-runners)。

本报告不授权创建云资源、修改安全组、部署代码、重跑业务任务或进入 A4-3/B/C。
