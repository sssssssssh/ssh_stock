# P0_A42331_JUNIT_SKIP_POLICY_FIX_02_GOVERNANCE_LAYOUT

日期：2026-11-10，Asia/Shanghai。状态：IMPLEMENTED / LOCAL_GOVERNANCE_PARTIAL /
NEW_SHA_CI_PENDING / INDEPENDENT_REVIEW_PENDING。未宣称完整 CI 或任务验收通过。

## 1. 基线、唯一任务与授权

- 负责人提供本任务书并明确要求“根据任务书进行修改开发，推送代码”。
- 开始时 master / HEAD / origin/master / GitHub master 均为
  `36bc8d00f70fe74884e8bd0b9dec4cebbc95c6da`，工作区干净；fetch 后无新增远端提交。
- 恢复来源仅为父提交 `35143411e696549d5aba02a8dc0658b69675cfbf` 的指定测试文件。
- 已按 AGENTS 顺序完整读取五份治理文件并核对业务权威文档相关章节。
  PROJECT_STATUS 的旧 G0/CI-OPT 指针保留历史语境，本轮唯一实施任务以本附件和最新明确请求为准。
- 原 Main CI [42740851566](https://github.com/sssssssssh/ssh_stock/actions/runs/42740851566)
  的 workflow-contracts Job129581229425 已失败，264 passed、1 failed；开始时完整 test Job 仍运行，
  不将其预填成功。根因是新增顶层函数及既有函数体改动触发 T11 冻结合同。
- 只修测试组织和指定历史测试基线，保留全部策略覆盖；不改生产 Skip 判定、认证回执、安全插件或治理门禁。

## 2. 实际修改文件与逐项差异

| 文件 | 变更 |
| --- | --- |
| tests/unit/test_a42331_ci_evidence.py | 恢复父提交原始7350字节；撤销新增常量/helper/test及旧函数内CLI断言、stdin参数改动 |
| tests/unit/test_a42331_skip_policy.py | 新增独立模块，迁移3个常量、3个helper和11个test_skip函数；另保留AC01/AC11增强断言的完整独立用例 |
| tests/unit/test_a42331_failure_evidence_regression.py | 仅将APPROVED_REASON/skip_fixture导入改为新模块，端到端子pytest/CLI及stdin=DEVNULL不变 |
| 本报告 | 新增当前范围、测试、环境局限、Git/CI交付和独立审阅索引；不改旧报告 |

逐文件完整diff、numstat、原件及迁移AST比对保存在仓库外 review.diff、migration-verification.json、
delivery-verification.json。恢复不等于删除覆盖：所有迁移函数连同装饰器、参数化数据和断言的AST
均与36bc8d0一致；两项增强用例由当时原函数完整复制，仅改独立函数名。
新模块只导入原文件稳定的ROOT、prepare、xml，没有循环导入或动态收集旁路。

受保护文件原始SHA256：
`9e82ae106032caf09f5ac410f42c6f7fde87ab62b83038fbc67616fe2c5b7e42`。
以下比较无输出，且Python原始字节比较也完全相等：

```text
git diff 35143411e696549d5aba02a8dc0658b69675cfbf -- tests/unit/test_a42331_ci_evidence.py
```

起点1552个跟踪文件中，除两份允许修改的既有测试外，1550份原始SHA256不变。
scripts/a42331_ci_evidence.py、scripts/a42331_pytest_safety.py、T11、Workflow、锁、治理文档、
W03/W04/W04-A/R1及许可/历史哈希原件均未修改。只在master操作，不建分支、不重写历史。

## 3. RED → GREEN 与完整验证证据

本机使用既有仓库外CPython3.12.0隔离venv；pytest9.1.1、pluggy1.7.0、pytest-cov7.1.0、
Ruff0.16.4、PyYAML6.0.2。保持默认source_contract_pytest；新测试、A42331/R1与T11定向命令
显式加载a42331_pytest_safety，保留原子pytest超时和所有失败断言。

| 检查 | 实际结果 |
| --- | --- |
| 修改前T11 | 1 failed、exit1，red-t11.log/xml |
| 原样恢复后T11 | 1 passed、exit0，green-t11.log/xml |
| 新模块及真实插件接线回归 | 48 passed、exit0、44.05s，new-tests.log/xml |
| 治理Job原命令 | 252 passed、13 failed、exit1、353.28s，完整governance.log/xml及command.json |
| 环境项复核 | 10 passed、exit0、1.63s，governance-env-recheck.log/xml；不能替代全组合通过 |
| A42331完整定向回归 | 66 passed、exit0、64.64s，a42331.log/xml及a42331-command.json |
| W04-A/R1指定离线回归 | 195 passed、1815 subtests passed、5条既有xunit警告，exit0、278.55s |
| Ruff、外部py_compile、diff/范围 | 全仓Ruff、3份Python编译、diff空白检查exit0；1550份原件哈希不变 |

治理Job原命令保持原选择、参数及默认插件，完整stdout/stderr及真实exit1均归档：

```text
python -m pytest tests/unit/test_a4_ci_governance.py tests/unit/test_ci_opt_01.py tests/unit/test_a4233_background_observer.py tests/unit/test_a42341_environment_guard.py::test_AT20_exact_ci_additions_no_other_workflow_or_old_step_change tests/unit/test_business_source_contract.py -q --junitxml=.codex_tmp/a4-ci-contracts.xml
```

本机13项失败逐类保留，不写成265 passed：

1. 6项外部目标拒绝单测缺SQLAlchemy、3项fake connection取消单测缺psycopg；没有实际连接请求。
2. 1项读取既有中文文档时因Windows默认GBK产生UnicodeDecodeError。
3. 2项原件严格比较，错误明确显示工作区CRLF与Git对象LF差异，包括AT20及business test adaptation。
   不在本轮转换冻结原件，不改原严格比较。
4. 1项A4235_DIRTY_TREE：当前合法未提交测试迁移不满足既有clean-tree前置；不绕过该拒绝。

已只在仓库外venv按requirements.lock补装pydantic2.13.4、SQLAlchemy2.0.52、psycopg[binary]3.3.4
及其依赖，并在后续子进程设置PYTHONUTF8=1；项目依赖文件和全局环境不变。
最初缺pydantic的收集exit4及pip不能把含extras的锁作为-c约束的失败也保留，未用其它版本fallback。
上述10项环境用例复核全通过，未改变断言或缩减原组合选择；原组合中的T11在JUnit中明确通过。
余下严格原件/clean-tree检查的最终Linux结果以新SHA自动CI为准，不以本机环境项复核冒充全绿。

新Skip回归命令（路径参数在仓库外完整命令JSON中）：

```text
python -m pytest -p scripts.a42331_pytest_safety -p no:cacheprovider --tb=short --show-capture=no -rN -q tests/unit/test_a42331_skip_policy.py tests/unit/test_a42331_failure_evidence_regression.py
python -m pytest -p scripts.a42331_pytest_safety -p no:cacheprovider --tb=short --show-capture=no -rN -q tests/unit/test_a42331_ci_evidence.py tests/unit/test_a42331_skip_policy.py tests/unit/test_a42331_failure_evidence_regression.py
python -m ruff check backend tests migrations scripts .github/actions
git diff --check
```

覆盖精确三元组、未知/重复/额外Skip、缺失/错误理由、targeted拒绝、缺少/篡改/重放证明、
相同安全字节的旧PASS复用、failure/error、计数及坏XML/实体/超限、隐私脱敏、CLI退出码与实验许可NO_GO。
真实子pytest→安全插件→独立collector CLI的批准/错误理由两条链路保持，不改成mock-only。
本机不执行需要数据库的全量pytest；完整Linux Main CI仍必须独立完成。

## 4. 提交推送与新CI验收

本轮负责人已授权普通master提交推送；只暂存上述4份文件，提交前检查完整diff、范围、原件、
迁移AST、Ruff、编译、diff空白和敏感输出。完整提交SHA、HEAD/origin/master/GitHub master对齐、
逐文件SHA256和每个Actions Run/attempt/head_sha/Job状态保存在仓库外git-ci-delivery.json并在交付对话提供。
不为追填本报告自身SHA反复提交，不手动dispatch/rerun，不调整Workflow强制绿灯。

workflow-contracts尤其T11、完整Main所有必需Job均完成且success、工件和新提交SHA对应后，
才可标记CI验收通过。未结束记PENDING；新失败保留日志和工件并单独分类，生产缺陷或范围阻断另案报告。
可选/授权实验Job的skipped不计为实验成功。交付后等待独立审阅，不自动进入后续性能阶段。

```text
TASK=P0_A42331_JUNIT_SKIP_POLICY_FIX_02_GOVERNANCE_LAYOUT
FROZEN_PARENT_BYTES=EXACT_MATCH
T11=LOCAL_PASS
MIGRATED_ASSERTIONS_AND_PARAMETERS=PRESERVED
LOCAL_FULL_GOVERNANCE=NOT_PASS
FINAL_NEW_SHA_CI=PENDING
INDEPENDENT_REVIEW=PENDING
R1=PARTIAL
HISTORICAL_AC05=PARTIAL
REAL_PG17_WORKER_OFF_ON=NO_GO
PERFORMANCE_ACCEPTANCE=NOT_MEASURED
REAL_PG17_CONNECTIONS=0
REAL_WORKER_ROOTS=0
REAL_OFF_ON_PAIRS=0
MANUAL_DISPATCH_RERUN=0
```
