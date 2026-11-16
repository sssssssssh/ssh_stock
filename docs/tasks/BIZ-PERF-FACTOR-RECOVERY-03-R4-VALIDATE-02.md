# BIZ-PERF-FACTOR-RECOVERY-03-R4-VALIDATE-02：修复 Worker 测试夹具并在隔离 Docker 中完成原生验证

日期：2026-11-16
基线 HEAD=232baf9e13cd7b23731e59188c86e0e253c3a394。
中心目标：恢复正常因子计算；本任务只解除当前 Worker 原生测试的夹具错误，不扩展业务修改。

## 已建立的隔离验证环境（复用，不要重建）
- 设备：ssssssh。
- Docker container：ssh-stock-factor-recovery-test。
- Image：python:3.12.14-slim；Python 3.12.14。
- 已按 requirements-biz-perf-linux-py312-v1.lock 使用 pip --require-hashes --only-binary=:all: 安装完整锁定依赖，包含 fastapi/loguru/psycopg/pytest/ruff。
- 容器网络已断开：docker inspect --format '{{json .NetworkSettings.Networks}}' 返回 {}。不得重新连接网络。
- /workspace 以只读方式挂载当前仓库；/workspace/.codex_tmp 单独映射至 C:\Users\54386\AppData\Local\Temp\ssh_stock_factor_test_scratch，可写。
- PYTHONDONTWRITEBYTECODE=1；无数据库环境变量、无 .env secret。
- 不使用 docker-compose；不启动 migration/backend/worker/scheduler；不连接任何PG/数据库；不启动真实Worker服务；不执行SQL/迁移/性能实验。
- 容器测试命令使用 docker exec ssh-stock-factor-recovery-test ...，pytest -p no:cacheprovider，JUnit输出放 /tmp；Ruff使用 ruff check --no-cache。

## 已有真实测试结果（不能改写）
1. 新增 Worker 7 个参数展开用例首次执行：7 errors，全部发生在 fixture setup 第145行，尚未进入业务断言。
   根因明确：tests/unit/test_job_worker.py 的 heartbeat_dispatch fixture 执行：
   import app.services.performance_diagnostics as diagnostics
   monkeypatch.setattr(diagnostics, "get_settings", ...)
   但 performance_diagnostics 模块没有 get_settings 属性。真实 observe_worker 装饰器在函数内从 app.core.config 导入 get_settings。fixture 已经正确 patch config.get_settings，因此应移除错误的 diagnostics import 和 diagnostics.get_settings monkeypatch；不要用 raising=False 掩盖错误。
2. 既有 Worker 回归（排除上述7个新用例）：23 passed，7 deselected，exit 0。
3. 合同测试 tests/unit/test_source_contract_r1_history.py tests/unit/test_r1_reviewed_snapshot_v2.py：59 passed，185 subtests passed，exit 0。
4. 10个本轮相关Python文件 Ruff：All checks passed!
5. 上述结果均在网络断开的隔离容器内执行；没有访问数据库或真实Worker。

## 唯一代码修改白名单
- 仅允许修改 tests/unit/test_job_worker.py 中 heartbeat_dispatch fixture，移除错误 diagnostics monkeypatch；保留 config.get_settings、worker_module.get_settings 的有效patch和其他行为。
- 仅新增 docs/acceptance/BIZ_PERF_FACTOR_RECOVERY03_R4_VALIDATE02_CLOSEOUT.md。
- 不改 job_worker.py、source contract脚本、manifest、workflow、锁文件、依赖、原历史测试和其他文件。
- 保留所有既有dirty/untracked文件，不checkout/reset/clean/stash，不覆盖其他Codex工作。

## 执行步骤
1. 先检查当前Git status、HEAD、Codex活动writer。若另一个writer仍在改同一文件，停止并报告；不要并发修改。
2. 精确修复fixture，禁止改变业务实现或测试预期来让测试通过。
3. Docker网络必须保持断开，验证容器Networks为空；检查无PG/DATABASE_URL/TEST_DATABASE_URL环境变量。
4. 在容器中运行新增7个参数展开用例：
   cd /workspace && python -m pytest -q -p no:cacheprovider --junitxml=/tmp/worker-new-fixed.xml tests/unit/test_job_worker.py -k 'heartbeat_start_failure or started_heartbeat or heartbeat_cleanup'
5. 运行完整Worker文件：
   python -m pytest -q -p no:cacheprovider --junitxml=/tmp/worker-full.xml tests/unit/test_job_worker.py
6. 运行合同测试：
   python -m pytest -q -p no:cacheprovider --junitxml=/tmp/contracts-fixed.xml tests/unit/test_source_contract_r1_history.py tests/unit/test_r1_reviewed_snapshot_v2.py
7. Ruff：
   ruff check --no-cache backend/app/services/job_worker.py tests/unit/test_job_worker.py scripts/r1_integration_controller.py scripts/r1_integration_evidence.py scripts/r1_integration_seed_loader.py scripts/source_contract_governance.py scripts/source_contract_history.py scripts/source_contract_pytest.py tests/unit/test_r1_reviewed_snapshot_v2.py tests/unit/test_source_contract_r1_history.py
8. 如果新7用例仍失败，报告真正业务断言/错误，不准只报告总数。可以使用隔离临时副本进行RED验证：只在容器/tmp副本中撤销heartbeat_started guard，运行第一个start失败用例确认预期旧错误；不能修改repo工作树。若这需要改变超出本白名单，停止说明。
9. 最后验证git diff --check、唯一tracked diff只限tests/unit/test_job_worker.py、无新增意外文件（本任务closeout除外）、原本dirty文件字节未被改变；不提交、不推送。

## Closeout必须说明
- Docker镜像/Python/依赖锁版本及hash安装结果。
- 网络断开证据与无DB环境证据。
- 新7用例、完整Worker文件、合同测试、Ruff精确结果及JUnit summary。
- 说明fixture错误如何修复，不能将此前7 errors计为RED。
- RED/GREEN只有在旧实现的隔离副本确实触发原始join异常且当前代码通过时才能宣称。
- REAL_PG17=NOT_RUN；REAL_WORKER=NOT_RUN；REAL_FACTOR_RUN=NOT_RUN；B_GATE/TARGETED_PG17_GATE=NOT_APPROVED。
- 最终等待ChatGPT独立审阅，不提交不推送。
