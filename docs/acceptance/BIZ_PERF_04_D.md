# BIZ-PERF-04-D Linux Python 完整依赖锁

2026-11-06。基线 master/HEAD/origin/master/实时远端为
c397821d45c755473bf627a40392d392bd1eab2b，clean。负责人已验收关闭04-C；本轮仅04-D。

## 审计及兼容边界

根requirements.lock固定22个直接依赖（含三个dev测试工具），不是完整闭包；没有文件hash。
pyproject.toml/requirements.txt/requirements-dev.txt保留开发范围入口；Dockerfile和七份
Workflow通过pip install -r requirements.lock安装，部分旧CI步骤会升级pip。现有a4234、
a42341及BIZ03验证器按单行name==version解析，不能承接多行hash锁；BIZ03还冻结根锁。
本轮不替换这些入口、解析器或根锁；不改既有任何Workflow及04-A/B/C源码。

新增 `requirements-biz-perf-linux-py312-v1.lock` 与 `scripts/business_dependency_contract.py`。
合同版本 `biz-perf-04-d.linux-lock.v1`，目标CPython3.12.14、Linux x86_64、glibc>=2.28。
Python3.12其他补丁版本可另行验证，但本合同不将3.12.15等安装冒充3.12.14结果。
只接受目标兼容wheel，不用sdist、不执行源码构建，PG17镜像固定策略不变。

## 解析来源与真实缺口

以历史Run41991816127/attempt1/Artifact13398532465的dependencies.json作为版本约束，
历史ZIP SHA256为251082fba565c38a831d7aec5d90fcb7628bd6c45a9411302d131e1881ea783e。
pip25.0.1在macOS下载CPython3.12/Linux目标wheel（manylinux_2_28、manylinux2014，
cp312/abi3/none）。跨平台下载最初66包，独立Linux marker闭包检查拒绝：缺greenlet。
原因是SQLAlchemy的platform_machine条件：宿主ARM的pip解析不能替代目标x86_64判断。
显式补充历史greenlet==3.5.6后，Linux环境下extras/markers依赖闭包完整为67包。
没有反复改变版本/放宽约束；这次补充修复的是可复现的目标平台缺项。
67包版本均与历史实验一致；22个原直接版本和binary/argon2/standard等extras全部保留。

分类：22直接 +45传递（含条件平台包如greenlet、uvloop、psycopg-binary）。
pytest/pytest-cov/ruff计入原锁的应用+测试闭包，不当作pip工具链。
历史68个distribution=本67包+pip；pip/setuptools/wheel不属于此业务闭包。
它们的实际版本单独记录，不要求将工具链冒充业务包；安装集合只允许这三种工具例外，
其他额外包/同名多发行/缺包/版本漂移均拒绝。pyproject的setuptools>=69、wheel是源码
构建依赖，因本路径禁止sdist/不安装项目源码，本轮不使用也不宣称完整锁定构建工具链。

## 锁与校验

每包固定版本、extras、一个批准的安装wheel SHA256；不使用URL直装或浮动specifier。
包级marker在目标环境解析后展平，最终锁不保留可以跳过校验的条件行。
读取实际wheel METADATA，绑定文件名、字节hash、METADATA hash、Requires-Python和Requires-Dist。
manifest为biz_perf_04_d_lock.json，记录目标marker环境、root/lock SHA256、直接版本、
完整67包metadata和生成Python/packaging/pip版本、宿主平台。
目标平台标签逐wheel核对；递归extras传播和目标marker评估核对版本/完整闭包/不可达多包。
未知内核版本相关marker拒绝，而不是拿宿主macOS值猜测。hash引用是内容完整性，不是签名。

真实完成：67个wheel使用pip download --no-index --find-links <wheelhouse> --require-hashes
--only-binary=:all: 加目标平台/Python参数从新目录重新下载并检查hash，退出0。
真实负例：全64位错误hash、缺失hash分别被pip拒绝，退出1。没有用--no-deps绕过此验证。
这证明目标安装文件及解析闭包，不能替代Linux加载/安装/ABI验收。

## 目标安装：NOT_VERIFIED

本机macOS ARM，Docker info确认daemon不可用。本轮不启动Docker、不更换资源或新增Runner。
没有在macOS安装Linux包；没有Linux干净venv安装回执。transitive_lock_complete保持false。
普通CI仍走旧根锁，不能把其成功视为新锁安装验证。

后续经批准并提供Linux x86_64 / CPython3.12.14资源后，复用同一锁与wheelhouse：

```text
python3.12 -m venv <new-venv>
<new-venv>/bin/python -m pip install --no-index --find-links <wheelhouse> --only-binary=:all: --require-hashes --report <install-report.json> -r requirements-biz-perf-linux-py312-v1.lock
<new-venv>/bin/python -m pip check
<new-venv>/bin/python -m scripts.business_dependency_contract <wheelhouse> --lock requirements-biz-perf-linux-py312-v1.lock --manifest docs/acceptance/biz_perf_04_d_lock.json --installed --pip-report <install-report.json>
```

命令在仓库根目录运行；预先核实解释器真实3.12.14。不得复用含业务包的旧venv；
pip report必须包含本轮全部67安装项，不能用“already satisfied”的空报告代替。
校验器先核锁/root字节、闭包、wheel hash和标签，再核report的完整目标环境、包/version/hash，
最后核实际运行解释器和installed集合，条件同时满足才派生transitive_lock_complete。
只调用validate_installed仅表示集合检查，不提供完整锁定结论。离线模拟报告不是真实验收。
工具链版本另列，manifest不会记录任何私有index URL、凭据或环境全文。

若没有合格现成资源，建议独立手动、单Job的Linux安装验证Workflow：无PG/Worker/业务Secrets，
固定Python3.12.14，干净venv、严格hash安装、集合验证、脱敏回执；不并入旧性能实验或旧授权。
这是待负责人批准的后续方案，本轮没有创建或触发该Workflow，也不申请额外权限。

## 回归、风险及交付边界

新增离线测试覆盖实际67包闭包、原直接版本、目标marker、缺项/多项/漂移、hash/marker锁篡改、
错误平台、工具链分离、模拟pip report和wheel文件篡改。相关A/B/C、BIZ03和CI合同仍执行。
准确测试统计、生成工具身份、真实pip下载/负例结果见biz_perf_04_d_validation.json。
原始wheel与日志仅在仓库外临时目录，仓库只存锁、metadata和脱敏统计，不提交安装文件。

开发/默认部署、前端、迁移入口不变；无生产DB/凭据、PG/Worker、容量或性能操作。
04-D代码与离线合同交付REVIEW_PENDING，Linux真实安装验收NOT_VERIFIED；不进入04-E/F。
没有关闭历史transitive_lock_complete=false，也没有授予正式容量/性能/生产资格。

## 2026-11-06 真实Linux安装追加记录（04-E前置归档）

上述NOT_VERIFIED/false是安装前离线快照，不再作为当前真实安装结论。
实际安装[Run 42156106471](https://github.com/sssssssssh/ssh_stock/actions/runs/42156106471)
为master/workflow_dispatch/attempt 1，target SHA
`ab5e29df5aa230076069dd587557720c2db382dc`，installation Job 127690531459，success。
Artifact 13474492280的5605字节ZIP摘要及四份JSON逐文件摘要已与任务书和GitHub原件核对。
原件见[biz_perf_04_d_runs/42156106471/artifact-index.json](biz_perf_04_d_runs/42156106471/artifact-index.json)。

原始receipt为COMPLETE、exit_code=0、七阶段PASS、target_installation=VERIFIED、
transitive_lock_complete=true；CPython3.12.14/Linux x86_64/64bit/glibc2.39、67包完整集合、
pip check、原验证器及148项合同均通过。pip25.0.1独立记录，不计入67包。
四份原JSON逐字节归档，不补造Run字段、不归档私有pip report或wheel/venv。
旧biz_perf_04_d_validation.json保留原字节和当时NOT_VERIFIED，未覆盖历史。

代码交付核验COMPLETE、真实安装VERIFIED、负责人最终验收REVIEW_PENDING三者分开，
不擅自标记04-D DONE，不授予PG/Worker/业务整链、容量、性能、生产或04-F资格。
本轮仅归档既有运行，没有重复下载67包、安装、dispatch或rerun。
