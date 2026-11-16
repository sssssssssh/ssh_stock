# BIZ-PERF-FACTOR-RECOVERY-03-R4-VALIDATE-02

2026-11-16。RESULT=FIXTURE_FIXED / CONTAINER_ACCESS_BLOCKED。
WORKER_NATIVE_RED_GREEN=NOT_ACHIEVED；NEXT=CHATGPT_INDEPENDENT_REVIEW。
不提交、不推送。容器执行因 Docker API 权限拒绝而未完成，不能声明验收通过。

## 基线、范围与唯一修正

master，HEAD=origin/master=
232baf9e13cd7b23731e59188c86e0e253c3a394。
本轮未重新认证 GitHub 最新 master；上一轮已认证结果不冒称本轮核验。
AGENTS 和治理边界沿用本持久会话已读版本，AGENTS 摘要未变；
本轮读取 VALIDATE-02 任务书及实际 fixture。

开始已有 9 个 tracked 修改及前轮未跟踪资产，全部保留。
本轮相对开始输入唯一修改为 tests/unit/test_job_worker.py 中 heartbeat_dispatch：

```diff
-    import app.services.performance_diagnostics as diagnostics
 ...
-    monkeypatch.setattr(diagnostics, "get_settings", lambda: SimpleNamespace(
-        perf_diagnostics_enabled=False))
```

仅删除这三个物理行，CRLF 行尾保留，净删除 185 字节。
有效的 config.get_settings、worker_module.get_settings patch 保留。
没有使用 raising=False，没有改测试断言、生产实现、manifest、旧合同或其他文件。
原问题是不存在的模块属性被 monkeypatch；装饰器实际在函数内部从 config 导入设置函数。

测试文件原字节 SHA256：
fc08733336df079e8dd2ea87e40fa3e2d32c3566a62a31e8bb0e70bdf97dc792。
修正后原字节 SHA256：
75c14853bd5674a994bd1a350fb11e5feec1f847a93cf8fba24730132c3691ec。

Get-Process 可见多个 Codex/host 进程，仅凭进程名称不能判断是否为活动 writer。
没有启动另一 writer，未发现同文件并发写入证据；修改前精确比对输入摘要，
结束核对所有其他输入原字节不变，没有终止进程或越权查询命令行。

## Docker 访问拒绝：实际命令和结果

唯一 Docker 命令为只读检查：

```text
docker inspect ssh-stock-factor-recovery-test --format
  '{{json .State}} {{json .HostConfig.NetworkMode}}
   {{json .NetworkSettings.Networks}} {{json .Mounts}}'
```

实际为单行命令；退出码 1。返回两项权限错误：
- Docker CLI 无权加载用户 .docker/config.json（Access is denied）；
- 无权连接 docker_engine named pipe 的 Docker API（permission denied）。

没有获得容器 State、Networks、Mounts 或环境变量结果。
没有执行 docker exec、连接容器网络、切换 context/daemon、重建容器、
启动服务、读取 Docker 配置内容或申请/绕过沙箱权限。
本环境审批策略不允许提权，因此没有尝试提升权限重跑。

任务书提供的既有环境记录为 python:3.12.14-slim / Python 3.12.14，
已按 requirements-biz-perf-linux-py312-v1.lock 用 --require-hashes、
--only-binary=:all: 安装完整依赖，Networks={}，仓库只读挂载，scratch 可写。
上述是任务书提供的事实，本轮受 Docker API 拒绝，无法独立复核安装结果、
当前网络是否仍为空、只读挂载和 PG/DATABASE_URL/TEST_DATABASE_URL 是否仍无配置。
不能把“没有发出重连命令”写成“本轮已确认容器断网”。

## 原生验证状态

| 本轮要求 | 实际执行/结果 |
|---|---|
| 新 7 个参数展开用例 | NOT_RUN，Docker API 拒绝，未生成 worker-new-fixed.xml |
| 完整 Worker 文件 | NOT_RUN，未生成 worker-full.xml |
| 两文件合同测试 | NOT_RUN，未生成 contracts-fixed.xml |
| 容器内 10 文件 Ruff --no-cache | NOT_RUN |
| /tmp 旧 join guard 隔离副本 RED | NOT_RUN；未创建副本 |
| 当前补丁 GREEN | NOT_RUN；0 个本轮原生测试执行 |
| fixture AST、输入差异和有效 patch 保留 | 通过；不是原生行为验收 |
| git diff --check | 退出 0；新增报告另查尾空白 |

任务书的既有记录保留且不改写：新增用例 7 errors 全发生于错误 fixture setup，
不是业务缺陷 RED；旧 Worker 23 passed/7 deselected、合同 59 passed/185 subtests、
10 文件 Ruff passed 均是此前结果。本轮未取得它们的 XML/日志复核，不能计作修正后通过。
本轮没有运行宿主机 AST Worker 模拟或依赖替身来代替容器原生测试。

## 保全和交接

开始全部 1663 个输入原字节 SHA256 排序 JSON 映射摘要：
4a253a45ef2b5008673e80e15325f2a969baa1857f3b802709326c89341e5450。
排除唯一获准修改的测试文件，其余 1662 个输入开始与结束摘要相同：
ead730127d594cd4ac71044e7710ce630295da8d163b492fe82409e25e3a5e8d。
本轮唯一新增文件为本报告，暂存区为空；其他原本 dirty/untracked 文件未改。

没有 docker exec 或应用导入，没有真实 PG、Worker 服务、SQL、迁移、性能实验、
Raw/Derived 变更、容器网络重连、依赖安装、提交、推送或 CI dispatch。
REAL_PG17=NOT_RUN；REAL_WORKER=NOT_RUN；REAL_FACTOR_RUN=NOT_RUN；
B_GATE=NOT_APPROVED；TARGETED_PG17_GATE=NOT_APPROVED。

交独立审阅：fixture 修正已落地；还需由具备正常 Docker API 访问权限的获准执行层，
先重新确认指定现成容器 Networks={}、无 DB 环境及挂载，再按任务书原命令执行
7 用例、完整 Worker、合同、Ruff，并在 /tmp 副本证明旧 join 异常 RED。
不应仅凭本次静态修正宣布 Worker GREEN 或提交推送。
