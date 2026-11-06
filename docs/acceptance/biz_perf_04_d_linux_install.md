# BIZ-PERF-04-D-LINUX-INSTALL-V1

2026-11-06；代码交付待负责人审阅，真实 Hosted Linux 安装 NOT_RUN。
开发基线：`4fe37aee77570b3377fb5ff41b85ab9e49fbbcef`，master，核查时本地/远端一致且干净。
负责人本次明确要求修改并推送，覆盖任务书默认不推送的限制；没有授权 dispatch、Actions API、
真实安装、数据库/容器/Worker、性能实验、Environment 或其他 GitHub 设置操作。

## 范围和状态

新增 `.github/workflows/biz-perf-04-d-linux-install.yml`、
`scripts/business_dependency_linux_install.py`、
`tests/unit/test_biz_perf_04_d_linux_install.py` 及本说明。
只在现有治理清单、治理说明及 test_a4_ci_governance 的原清单函数内精确登记第八份入口。
负责人额外明确批准 test_biz_perf_03_b_once.py 两个相关测试的最小适配：
保留未知工作流拒绝，剥离精确新增分类/循环后继续逐 AST 比较原历史清单断言。
原七份 Workflow、原锁、04-D manifest/validation JSON、现有验证器和业务代码均保持不变。

本轮不改全局 PROJECT_STATUS 或四份业务文档，遵守任务书限定的文件范围。
`docs/acceptance/biz_perf_04_d_validation.json` 仍为 false / NOT_VERIFIED，不关闭04-D。
只有日后获得单独许可的真实目标安装才可能生成本次运行 COMPLETE 收据；普通 CI 不提供此结论。
04-E/F、容量、性能、生产与发布资格均不随本入口获得。

## Workflow 与顺序

- 仅 workflow_dispatch，三个必填输入：target_sha、expected_lock_sha256、Boolean
  confirm_installation（默认false）。输入使用 toJSON(inputs) 经环境变量解析，不插入shell。
- 固定ubuntu-24.04，唯一installation Job，20分钟，无matrix/services/container/Environment。
- contents:read；独立并发组biz-perf-04-d-linux-install，cancel-in-progress=false。
- 初始化先写四份未完成JSON；在checkout前核验dispatch/master/repository/确认类型/完整SHA。
- checkout ref=target_sha，persist-credentials=false；随后标准库 --bind-only 检查HEAD、
  Git跟踪文件未漂移、锁/根锁/manifest摘要与数量，记录Workflow blob及文件SHA256。
- setup-python固定CPython3.12.14/x64/check-latest=false，无依赖缓存。
- 实际运行时核验CPython正式3.12.14、Linux/x86_64/64位、glibc>=2.28；新venv内再次核验。
- 只按现有manifest精确name/version/filename/hash查询官方pypi.org JSON；要求唯一bdist_wheel。
  仅HTTPS files.pythonhosted.org文件；拒绝跨主机/HTTP/凭据/查询参数重定向，下载字节再次验hash。
- 新Wheelhouse必须恰好67份批准文件，无额外文件、重复名、符号链接、路径穿越或目录复用。
- 编排器仅标准库。完整验证器依赖packaging，所以先以标准库核摘要，再从已经验hash的
  批准packaging Wheel通过子进程PYTHONPATH复用原验证器，校验67包闭包/METADATA/标签。
  此安装前校验不安装工具链，不复制验证器，也不产生完整安装证据。
- venv使用 --copies，避免解释器符号链接；不启用system site packages，不升级工具链，
  不安装项目源码。仅用下列固定离线参数安装，生成本轮真实私有pip report。
- pip check、原验证器 --installed --pip-report 和限定两份测试均通过后，再复查源文件和Wheel，
  才将运行收据置COMPLETE。没有重试、自动换源/换版本/换镜像或补装缺包路径。

## 固定命令

```bash
"$VENV/bin/python" -m pip install --no-index --find-links "$WHEELHOUSE" \
  --only-binary=:all: --require-hashes --no-cache-dir \
  --report "$PRIVATE/install-report.json" -r requirements-biz-perf-linux-py312-v1.lock
"$VENV/bin/python" -m pip check
"$VENV/bin/python" -m scripts.business_dependency_contract "$WHEELHOUSE" \
  --root requirements.lock --lock requirements-biz-perf-linux-py312-v1.lock \
  --manifest docs/acceptance/biz_perf_04_d_lock.json \
  --installed --pip-report "$PRIVATE/install-report.json"
"$VENV/bin/python" -m pytest -q --tb=no --show-capture=no -rN \
  tests/unit/test_biz_perf_04_d.py tests/unit/test_biz_perf_04_d_linux_install.py \
  --junitxml="$PRIVATE/tests.xml"
```

不使用no-deps/ignore-installed/trusted-host/extra-index-url/pre/upgrade/no-binary。
实际67包与22直接依赖必须匹配锁及manifest；pip/setuptools/wheel只作为工具链记录。
完整安装集合、报告环境/版本/hash及全部Wheel验证由原验证器负责，不能用模拟报告代替。
JUnit必须有真实testcase且failures/errors/skipped全0，缺失、损坏、空测试或跳过均拒绝。

## 来源与权限

checkout `11d5960a326750d5838078e36cf38b85af677262`、setup-python
`a26af69be951a213d495a4c3e4e4022e16d87065`、upload-artifact
`ea165f8d65b6e75b540449e92b4886f43607fa02`，2026-11-06再次通过官方Git仓库
refs/tags/v4、v5、v4核对；工作流实际固定完整commit，不使用浮动标签。
GitHub官方python-versions manifest列有3.12.14 Linux24.04 x64构建；不代表本轮已实际下载/安装。
若获取失败或运行版本不符，PYTHON_TARGET_UNAVAILABLE，停止等待人工处置，不能自动降级/升级。
https://github.com/actions/python-versions/blob/main/versions-manifest.json

编排子进程采用环境白名单，剔除业务凭据、数据库URL、GitHub Token、代理和外部PYTHONPATH，
禁用外部pytest插件自动加载；原项目显式安全插件保留。pip配置文件为os.devnull，HOME为私有目录。
无业务app、SQLAlchemy、psycopg或数据库导入，无网络安装索引参数，无shell拼接命令。
所有外部命令shell=False且有超时。HTTP每次45秒、无自动重试；总任务受20分钟平台期限约束。

## 工件与失败关闭

公开目录严格四份：receipt.json、runtime.json、dependency-verification.json、tests.json。
顶层和嵌套字段白名单、总量5MiB、原子写入、路径/链接检查；私有命令stdout/stderr、堆栈、
pip report和JUnit不上传，Wheelhouse/venv不上传。失败只公开任务书固定码；未知异常为
UNEXPECTED_INTERNAL_ERROR，原异常只写私有目录。失败时完整安装及集合成功字段撤回为false。
安装/检查命令非零、超时、缺report、合同不确认完整、测试失败、源漂移都保持INCOMPLETE。

上传步骤if:always()，retention-days=7，if-no-files-found=error，只列举四个JSON文件。
最终导出只在白名单校验通过后公布artifact_dir；失败时fallback指向无授权证据目录，不能
因校验失败仍上传原始/越界文件。普通已知失败可导出四份未完成收据，但仍保持Job失败。
平台硬取消/Runner丢失可能不能执行always或留下最终工件；缺工件永不推断成功。

## 本地验收与限制

指定安装合同、治理合同、额外获批的精确投影回归、Ruff、diff检查结果按最终交付回执记录。
首轮安装合同111 passed/1 failed：Windows CRLF checkout造成原受保护根锁/目标锁字节摘要
与Git中的LF合同不同；不修改锁/验证器/断言，使用隔离的原Git LF checkout叠加本次允许改动复验。
该副本只运行离线单测，不安装Linux依赖；不得将其结果标为真实安装通过。
本机没有检测到PATH中的actionlint；若最终未运行，交付明确记录NOT_RUN而非PASS。
本轮禁止整仓pytest、迁移、集成测试、Docker/Worker/实验以及Actions API/dispatch/rerun。

## 回滚与接续

新入口未部署、未运行、不改变旧入口；正常新revert可撤回本任务新增文件和精确清单增量，
不重写历史或修改旧七份Workflow。若将来已获批运行，先保留该run/attempt工件并等待其终结，
再由负责人决定回滚；本说明不授权取消任务或清理其他资源。
代码交付后停止等待负责人审阅；未来真实安装Workflow执行必须另行明确授权。

## 本轮交付前实证（不等于真实安装）

- 最终Git LF原始字节副本：`python -m pytest -q tests/unit/test_biz_perf_04_d.py tests/unit/test_biz_perf_04_d_linux_install.py`：148 passed，exit 0，failed/errors/skipped均0。
- 补充Wheel METADATA/平台负例及新八份清单、旧AST投影、CI-OPT T11兼容：8 passed，exit 0；其中4项与上述148项重叠，不合并冒充独立计数。
- 工作区原命令治理回归：`python -m pytest -q tests/unit/test_a4_ci_governance.py tests/unit/test_a4234_ci_governance.py`：98 passed /3 failed，exit 1，1241.33秒。
  失败分别为A4235_DIRTY_TREE（要求提交后clean）、Windows反斜杠与原POSIX字面值不等、旧read_text的Windows GBK默认解码。保留原断言，不修改范围外test_a4234文件。
- 只对旧编码用例采用Python -X utf8复核；POSIX路径用例仍需Linux执行，不伪装成本机通过。clean门禁在提交后单独复核，最终结果见交付回执，不为追填文档自身SHA追加提交。
- Ruff（新编排器、新测试、两份相关治理测试）及git diff --check通过。actionlint NOT_RUN；已执行YAML结构合同与内联Python语法检查，但不把它们冒充actionlint。
- 原七份Workflow在LF规范副本中与基线Git blob逐字节相同，五份受保护锁/manifest/validation/验证器没有差异。未修改旧CI或生产入口。
- 无整仓pytest、数据库测试、迁移、真实pip安装、容器/Worker/服务或性能实验；离线测试全部mock/临时文件。只读官方Git refs与正常Git交付涉及网络；没有PyPI下载或Actions API/dispatch/rerun。
- 当前软件交付REVIEW_PENDING；原04-D验收文件仍transitive_lock_complete=false、target_installation=NOT_VERIFIED。推送可能自动触发原普通CI，本轮不调用Actions API查询，也不将其当作新锁真实安装验收。

UTF-8专项复核实际为1 passed /1 failed（exit 1）：编码用例通过，另一个仍为Windows/POSIX路径分隔符差异。没有将其标成全绿。
