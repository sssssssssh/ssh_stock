# BIZ-PERF-FACTOR-RECOVERY-03-R4-VALIDATE-01

2026-11-16。RESULT=ENV_BLOCKED。NEXT=CHATGPT_INDEPENDENT_REVIEW。
WORKER_NATIVE_RED=NOT_RUN；WORKER_NATIVE_GREEN=NOT_RUN；
NEW_WORKER_CASES_EXECUTED=0；REGRESSIONS=NOT_RUN。
没有把导入失败或 R4 的合同测试通过计作 Worker RED/GREEN。

## 基线及本轮范围

master，HEAD=origin/master=
232baf9e13cd7b23731e59188c86e0e253c3a394。
依任务禁止互联网，本轮没有重新联网核验 GitHub 最新 master；
上一轮认证结果见 R4 closeout，不能冒称本轮重新认证。
已读取 AGENTS、R4 closeout 和本任务书；治理及业务边界沿用本持久会话已读同版本。
没有启动另一 writer、服务或后台任务。

开始的 9 个 tracked 修改、既有未跟踪测试、v2 manifest、全部前轮任务与报告保留。
本轮唯一新增文件为本报告，没有修改 Worker、测试、manifest、路由、依赖或 workflow。
没有制作临时 RED 源码，因为未找到可运行原生测试的环境，已按步骤 1 停止执行。

## 真实离线环境探测

命令方式：对已发现的四个解释器逐一运行
`python -I -B -c <stdlib metadata probe>`，全部退出 0。
探针只调用 sys.version、importlib.metadata.version，按仓库 requirements.lock 的
22 个根发行版逐项比较；没有导入应用、构造依赖替身、运行 pip 或安装/升级。

| 环境标签 | Python | 锁定根依赖缺失数 | 版本不匹配数 | 结论 |
|---|---|---:|---:|---|
| base（当前命令行默认） | 3.12.7 | 9 | 13 | 缺核心依赖且版本不符 |
| stock（现有 Conda 环境） | 3.11.14 | 16 | 6 | 低于项目 Python 3.12，且缺依赖 |
| langchainchat（现有 Conda 环境） | 3.11.7 | 22 | 0 | 低于 Python 基线，全部根依赖缺失 |
| python311_32（另一 PATH 解释器） | 3.11.7 | 22 | 0 | 低于 Python 基线，全部根依赖缺失 |

base 精确缺失：APScheduler、fastapi、loguru、psycopg、pwdlib、pytest-cov、
ruff、tushare、uvicorn。
requirements.lock 要求 fastapi==0.141.1、loguru==0.7.3、psycopg==3.3.4、
ruff==0.16.4，均未安装。

base 其余全部 13 项不匹配（installed → required）：

| 发行版 | installed | required |
|---|---|---|
| alembic | 1.13.3 | 1.19.1 |
| httpx | 0.27.0 | 0.28.1 |
| numpy | 1.26.4 | 2.3.3 |
| pandas | 2.2.2 | 3.0.5 |
| pydantic | 2.8.2 | 2.13.4 |
| pydantic-settings | 2.6.1 | 2.11.0 |
| pytest | 7.4.4 | 9.1.1 |
| python-dotenv | 0.21.0 | 1.2.3 |
| PyYAML | 6.0.1 | 6.0.2 |
| requests | 2.32.3 | 2.32.4 |
| SQLAlchemy | 2.0.34 | 2.0.52 |
| tenacity | 8.2.3 | 9.1.4 |
| typer | 0.9.0 | 0.27.1 |

stock 精确缺失：alembic、APScheduler、fastapi、httpx、loguru、psycopg、
pydantic、pydantic-settings、pwdlib、pytest、pytest-cov、python-dotenv、
ruff、tenacity、typer、uvicorn。
其余六项 installed/required：PyYAML 6.0.3/6.0.2、SQLAlchemy 2.0.45/2.0.52、
numpy 2.4.1/2.3.3、pandas 2.3.3/3.0.5、requests 2.32.5/2.32.4、
tushare 1.4.24/1.4.29。

另外两个环境缺失 requirements.lock 全部 22 项：alembic、APScheduler、fastapi、
httpx、loguru、numpy、pandas、psycopg、pydantic、pydantic-settings、pwdlib、
pytest、pytest-cov、python-dotenv、PyYAML、requests、ruff、SQLAlchemy、
tenacity、tushare、typer、uvicorn。
以上为根发行版检查，未声称已枚举或验证完整传递依赖闭包。

仓库 wheelhouse、wheels、.venv、venv 目录不存在；已列出现有 Conda 环境及
.codex_tmp 直接目录，没有发现另一个项目虚拟环境。
本机默认 pip Cache 存在，但递归按 *.whl 查找结果为零。
没有将 HTTP 缓存、未知归档或目录名称当作完整可验 wheelhouse；
没有解包、修复缓存、下载或搜索远端。
仓库有 requirements.lock 及带 SHA256 的 requirements-biz-perf-linux-py312-v1.lock，
后者明确面向 Linux x86_64 CPython 3.12.14，不是本机 Windows wheel 集合。
锁文件存在不能代替缺失的离线安装包。

因此，已发现范围内没有兼容现成环境或完整可验证 wheelhouse。
按用户最新要求停止，不再尝试原生 pytest，不重跑 88 项合同测试掩盖阻断。

## 只读 workflow 审阅及最窄建议

仅读取本地 Git 跟踪的 workflow 定义，没有访问 GitHub、dispatch 或花费云资源。

- .github/workflows/ci.yml:43–56 的 workflow-contracts 使用 Python 3.12 和
  requirements.lock，但只执行工作流治理测试，不执行 Worker 新回归。
  该 job 通过不能作为 Worker RED/GREEN。
- 同文件:297–313 的主 test job 有 postgres:17 服务；其后还有 Docker PG、
  迁移和多组集成测试。lookup-diagnosis 在 :154 调用 a421-pg。
  即使选择 workflow_dispatch 的 experiment=none，也不是本任务要求的纯离线验证。
- publication-v13.yml:89–109 安装锁定依赖、调用 a421-pg，运行真实锁和取消集成；
  ab-read-a4-2.yml:91–114 也调用 PG action。均不作为此轮无 DB 的窄入口。

建议交独立审阅裁决：使用已经具备锁定依赖的隔离 Linux Python 3.12 runner，
新增或临时提供一个只执行以下有限验证的受审入口，固定待审源码快照摘要：

1. 安装严格 audit hook，并在导入 app.core.db 前禁止 .env 读取、socket/network、
   subprocess 和 Engine.connect；禁止真实线程/Worker 服务、SQL/迁移及任何 secrets。
2. RED 仅在隔离源码副本还原旧 join guard，不改变工作树或 manifest，
   使用当前模块及真实 pytest；确认 start 失败后的 join 错误和预期回归断言失败，
   不接受 import error 为 RED。
3. GREEN 运行未改动的 R4 快照，确认 7 个新用例，再执行既有纯离线取消、候选、
   publication 单元回归与 Ruff；不选任何 integration 文件或性能命令。
4. 保留严格退出码、JUnit、测试数、源码 SHA256 及原安全插件；
   不启用 services、a421-pg、Docker、迁移、真实发布或性能实验。

这是待独立审阅的执行路径建议，不是本轮 CI 改动或执行授权。
现有主 workflow 的 dispatch 会启动超出此任务的 job，故不建议为本验证直接 dispatch。
本轮不提交、不推送；后续 runner/CI 资源使用和交付另待审阅。

## 验证状态、保全与门禁

本轮 Worker RED/GREEN、7 个新用例、业务回归、Ruff 均 NOT_RUN。
R4 的 88 passed 是上一轮有限合同证据，不是本轮重新执行，更不是 Worker 通过。
没有测试缺陷的原生证据，因此没有擅自改测试或 Worker 补丁。

开始全部 1661 个 tracked/untracked 输入文件原字节 SHA256 排序 JSON 摘要：
28f5bcff5609fada83a4d09c9f9f9d332190c65b90ebd9030a7fdfb7805b8795。
结束排除本新增报告后摘要一致；原 R4 改动、manifest、测试及所有旧资产均未变。
git diff --check 退出 0；本新增报告另检查尾空白。
暂存区为空；HEAD 不变，没有新 SHA、提交、推送、CI dispatch 或资源创建。

无 DB 证据：实际执行的环境探针只加载标准库 metadata，未导入 app、
未读取 .env、未创建 SQLAlchemy Engine、未调用连接、SQL 或 Worker；
其它命令仅 Git/文件只读检查与新增本报告。
没有为获取依赖访问互联网、安装包、伪造模块或绕过安全插件。

B_GATE=NOT_APPROVED；TARGETED_PG17_GATE=NOT_APPROVED；
REAL_FACTOR_RUN=NOT_RUN；REAL_WORKER=NOT_RUN；REAL_PG17/SQL=NOT_RUN。
结论为 ENV_BLOCKED，仍禁止依据本轮结果提交/推送或宣称真实因子计算恢复。
