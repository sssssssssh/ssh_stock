# 运行可靠性修复验收（2026-10-18）

基线：`master@0be92820ed077929437b8706714dbf75bea5d2e0`。
授权范围：任务轮询负载、心跳失联展示、数据库断线与失败事务恢复；不改变指标/策略/收益/身份。
保持当前 master，不回退或重写历史。UI-only 历史验收仍对应原冻结提交，本次另行冻结以上基线。

## 根因与修改

1. 旧前端每 5 秒刷新 Job 后，只要存在 RUNNING 就重复统计历史覆盖率/日历。
   慢请求可重叠，死 Worker 留下的 RUNNING 也会不断触发统计。
2. Job GET 现在仅派生 `heartbeat_stale`，不写数据库。界面保留所有入口、真实持久化状态和进度，
   心跳超时明确提示“状态待确认”，不擅自标记成功/失败。
3. JobPoller 分离轻量和统计请求，各自 single-flight；统计有进度变化且满 60 秒才刷新，
   终态额外刷新一次。统计失败节流重试、保留旧事实，卸载/退出后拒绝旧响应回写。
4. Recalculation 先回滚未提交事务，再保存 Dirty/Job 失败记录；失败记录仍不可用时保持首因，
   依原 stale recovery 对账。已提交阶段与质量证据保留，不引入自动续算或任务重放。
5. Worker 数据库轮询异常后关闭原 Session、退避重建轮询，服务心跳不重启；
   数据库异常日志仅显示 SQLAlchemy/驱动类型与合法 SQLSTATE，不输出连接信息、SQL 或参数。

## 回归证据

- RED：原始实现下新增 App 7 个用例全部失败。65 秒内覆盖统计 14 次（应为初始 1 次）；
  慢 Job 查询 20 秒内触发 5 次（应为初始 + 一个未完成请求）；四类终态均遗漏最终统计刷新。
- RED：补算断线用例由最初 OperationalError 变成 PendingRollbackError，首因被掩盖；
  Job payload 不含心跳失联信息，旧 Worker 数据库异常直接退出。
- GREEN：App/JobCenter 共 14 个新增用例通过，涵盖初始和常规 single-flight、
  不变进度、推进限频、慢统计不阻塞轻量查询、终态发生于统计中、失败重试、卸载隔离和失联提示。
- 真实 PostgreSQL 17 回归：在唯一命名的合成测试库中使真实 SQLAlchemy Connection 失效，
  断言原异常保留、Job FAILED 落库、先前提交的质量证据仍在；Dirty 失败顺序另有回归。
- 前端：`npm ci`、`npm run test:coverage`（136 passed，语句/行覆盖 86.33%）、`npm run build` 通过。
- 针对性后端：最初 40 passed；最终补验 58 passed，包含新增 PostgreSQL 断连、心跳数据库错误、
  驱动首因/SQLSTATE 保留与脱敏回归。
- 首轮完整后端回归：1908 passed、1 failed，覆盖率 87.75%；496 个集成用例全部通过。
  唯一失败为旧 prerequisites 测试桩缺少新增错误路径必需的 rollback，修正后重新执行如下完整单元回归；
  此后新增的两个集成文件用例也包含在最终 58 项补验中。首轮结果不表述为单次全绿。
- 最新完整单元回归：1420 passed；旧 prerequisites 测试桩补齐 Session.rollback，
  并新增 rollback→commit 顺序和 FAILED 断言，没有降低原有门禁断言。
- Ruff 与 `git diff --check` 通过；隔离库 Alembic current=heads=`0056_suspend_timing_text`，无新增迁移。
- 浏览器：真实 App + 全量拦截合成 API，1440/390 两宽度 × 加载/空态/失联/长失败文本/统计失败五场景，
  10 项通过；检查原操作入口、无整页横向溢出、无页面异常。截图和结果仅存 ignored coverage 目录。
  命令：`PLAYWRIGHT_MODULE=<isolated-playwright> node scripts/runtime_reliability_browser.cjs`。
  本机使用已有 Chrome，设置 `PLAYWRIGHT_CHANNEL=chrome`；CI 用已安装的独立 Chromium。

## 安全与发布边界

- 所有数据库测试显式设置 DATABASE_URL 和 TEST_DATABASE_URL 为本机隔离 PostgreSQL 17；
  不使用 `.env` 的业务连接，不访问真实行情 Provider/模型，不上传生产数据。
- 未清理业务表、未执行业务库 DDL、未部署 ECS、未重启 API/Worker/Scheduler，也未重试补算。
- 不声称修复所有计算性能问题：覆盖率统计单次仍可昂贵，因子预热重复读取与趋势逐行计算没有改动。
  参数、索引、缓存和云盘规格未调整；实际云端负载下降需在另行批准部署后复测。
- 沿用依赖的 11 项 npm 安全告警与构建大 chunk 告警未在本次升级或掩盖。
- CI 新增相同合成浏览器验收及独立 Artifact；完整 CI 结果应以推送提交 SHA 对应 Actions 为准。
