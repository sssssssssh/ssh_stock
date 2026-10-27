# A42365 W00 基线与变更边界

开工基线、origin/master 和远端 master 均为 `2c8870f67d65e20465ad8a88affac3e1b32e9da3`；master；开工工作树 clean=true。旧 BIZ 性能验收仍为 PERFORMANCE_OPEN。

本次不运行 G1/L2，不改业务源码、配置、依赖、工作流、迁移和任何历史 manifest。新第十层 overlay 与 BIZ manifest 分离，完整 HEAD/隐藏索引/FD 校验继续生效。旧测试文件逐字节不变。

## 断点复核

| 工作包 | 基线调用断点 | 本轮新增入口 | 未关闭点 |
|---|---|---|---|
| W01 | a42364_manager.serve_installed → InstalledServiceHost(package)，backend=None | a42365_runtime_factory.build_installed_runtime；a42365_runtime.RuntimeCoordinator | 独立域服务安装与完整 server 方法仍未齐；不能 READY |
| W02 | KernelStoreCapability.verify → writer_broker=None → SAFE_DELETE_UNPROVEN | InstalledWriterBroker，BrokerResourceDriver | 全写者内核排他证明未实现；所有 live 命令拒绝 |
| W03 | PersistentBootstrapBudget 未接 native fork/exec | BudgetService，DurableJournal.reserve | native census/预算 IPC、镜像启动链未接通；prebuilt NOT_IMPLEMENTED |
| W04 | ResourceDriver._remove_attempted 是进程内集合；无 start/stop | ResourceLifecycle.perform/recover；broker 固定命令计划 | production controller 安装尚未接通 |
| W05 | ReadOnlyDelegation.verify 只接受已存在的 RO mounts | ReadOnlyProvisioner.provision/accept 传递和核验 FD | 创建 RO mount namespace、跨 UID mapping 的 root launcher 缺失 |
| W06 | RootManager 所需 cgroup/launcher/credentials 未由默认入口构造 | InstalledSupervisor；StagedPublisher.stage/finalize | 完整 root FD provisioning 和 independent Reviewer 未接通 |
| W07 | PinnedSessionSource 使用 OwnerConnections.open 重复消费同一认证 slot | AuditConnectionFactory 独立 2 AUTH/2 SQL | Owner server 和实际 target generation 注册仍未接通 |

## RED 原始证据

执行测试 `tests/unit/test_a42365_runtime_red.py`，8 failed，均为真实 ModuleNotFoundError，非正确拒绝冒充 RED。GREEN 只说明命名实现可导入，**不证明 mandatory 链路闭合**。

- 原始 `w00-red.xml` SHA256：`39b0d80e49c6382e88ece646c6d2b37b95c49034af18d9fd82d4a0adad63393f`。
- 原始 `w00-red.log` SHA256：`7b0a721f3cd2a81606cbbd83177724f5dc516213ecff56fd77610cabe3e64b7c`。

```xml
<?xml version="1.0" encoding="utf-8"?><testsuites name="pytest tests"><testsuite name="pytest" errors="0" failures="8" skipped="0" tests="8" time="0.058" timestamp="2026-10-28T02:41:04.598637+08:00" hostname="shukedeMacBook-Air.local"><testcase classname="tests.unit.test_a42365_runtime_red" name="test_W00_mandatory_runtime_implementation_exists[runtime_factory-build_installed_runtime]" time="0.001"><failure message="ModuleNotFoundError: No module named 'scripts.a42365_runtime_factory'">tests/unit/test_a42365_runtime_red.py:19: in test_W00_mandatory_runtime_implementation_exists
    value = importlib.import_module("scripts.a42365_" + module)
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
../../../.cache/codex-runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
&lt;frozen importlib._bootstrap&gt;:1387: in _gcd_import
    ???
&lt;frozen importlib._bootstrap&gt;:1360: in _find_and_load
    ???
&lt;frozen importlib._bootstrap&gt;:1324: in _find_and_load_unlocked
    ???
E   ModuleNotFoundError: No module named 'scripts.a42365_runtime_factory'</failure></testcase><testcase classname="tests.unit.test_a42365_runtime_red" name="test_W00_mandatory_runtime_implementation_exists[writer_broker-InstalledWriterBroker]" time="0.000"><failure message="ModuleNotFoundError: No module named 'scripts.a42365_writer_broker'">tests/unit/test_a42365_runtime_red.py:19: in test_W00_mandatory_runtime_implementation_exists
    value = importlib.import_module("scripts.a42365_" + module)
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
../../../.cache/codex-runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
&lt;frozen importlib._bootstrap&gt;:1387: in _gcd_import
    ???
&lt;frozen importlib._bootstrap&gt;:1360: in _find_and_load
    ???
&lt;frozen importlib._bootstrap&gt;:1324: in _find_and_load_unlocked
    ???
E   ModuleNotFoundError: No module named 'scripts.a42365_writer_broker'</failure></testcase><testcase classname="tests.unit.test_a42365_runtime_red" name="test_W00_mandatory_runtime_implementation_exists[budget-BudgetService]" time="0.000"><failure message="ModuleNotFoundError: No module named 'scripts.a42365_budget'">tests/unit/test_a42365_runtime_red.py:19: in test_W00_mandatory_runtime_implementation_exists
    value = importlib.import_module("scripts.a42365_" + module)
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
../../../.cache/codex-runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
&lt;frozen importlib._bootstrap&gt;:1387: in _gcd_import
    ???
&lt;frozen importlib._bootstrap&gt;:1360: in _find_and_load
    ???
&lt;frozen importlib._bootstrap&gt;:1324: in _find_and_load_unlocked
    ???
E   ModuleNotFoundError: No module named 'scripts.a42365_budget'</failure></testcase><testcase classname="tests.unit.test_a42365_runtime_red" name="test_W00_mandatory_runtime_implementation_exists[lifecycle-ResourceLifecycle]" time="0.000"><failure message="ModuleNotFoundError: No module named 'scripts.a42365_lifecycle'">tests/unit/test_a42365_runtime_red.py:19: in test_W00_mandatory_runtime_implementation_exists
    value = importlib.import_module("scripts.a42365_" + module)
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
../../../.cache/codex-runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
&lt;frozen importlib._bootstrap&gt;:1387: in _gcd_import
    ???
&lt;frozen importlib._bootstrap&gt;:1360: in _find_and_load
    ???
&lt;frozen importlib._bootstrap&gt;:1324: in _find_and_load_unlocked
    ???
E   ModuleNotFoundError: No module named 'scripts.a42365_lifecycle'</failure></testcase><testcase classname="tests.unit.test_a42365_runtime_red" name="test_W00_mandatory_runtime_implementation_exists[provisioner-ReadOnlyProvisioner]" time="0.000"><failure message="ModuleNotFoundError: No module named 'scripts.a42365_provisioner'">tests/unit/test_a42365_runtime_red.py:19: in test_W00_mandatory_runtime_implementation_exists
    value = importlib.import_module("scripts.a42365_" + module)
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
../../../.cache/codex-runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
&lt;frozen importlib._bootstrap&gt;:1387: in _gcd_import
    ???
&lt;frozen importlib._bootstrap&gt;:1360: in _find_and_load
    ???
&lt;frozen importlib._bootstrap&gt;:1324: in _find_and_load_unlocked
    ???
E   ModuleNotFoundError: No module named 'scripts.a42365_provisioner'</failure></testcase><testcase classname="tests.unit.test_a42365_runtime_red" name="test_W00_mandatory_runtime_implementation_exists[supervisor-InstalledSupervisor]" time="0.000"><failure message="ModuleNotFoundError: No module named 'scripts.a42365_supervisor'">tests/unit/test_a42365_runtime_red.py:19: in test_W00_mandatory_runtime_implementation_exists
    value = importlib.import_module("scripts.a42365_" + module)
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
../../../.cache/codex-runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
&lt;frozen importlib._bootstrap&gt;:1387: in _gcd_import
    ???
&lt;frozen importlib._bootstrap&gt;:1360: in _find_and_load
    ???
&lt;frozen importlib._bootstrap&gt;:1324: in _find_and_load_unlocked
    ???
E   ModuleNotFoundError: No module named 'scripts.a42365_supervisor'</failure></testcase><testcase classname="tests.unit.test_a42365_runtime_red" name="test_W00_mandatory_runtime_implementation_exists[owner-AuditConnectionFactory]" time="0.000"><failure message="ModuleNotFoundError: No module named 'scripts.a42365_owner'">tests/unit/test_a42365_runtime_red.py:19: in test_W00_mandatory_runtime_implementation_exists
    value = importlib.import_module("scripts.a42365_" + module)
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
../../../.cache/codex-runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
&lt;frozen importlib._bootstrap&gt;:1387: in _gcd_import
    ???
&lt;frozen importlib._bootstrap&gt;:1360: in _find_and_load
    ???
&lt;frozen importlib._bootstrap&gt;:1324: in _find_and_load_unlocked
    ???
E   ModuleNotFoundError: No module named 'scripts.a42365_owner'</failure></testcase><testcase classname="tests.unit.test_a42365_runtime_red" name="test_W00_mandatory_runtime_implementation_exists[runtime-RuntimeCoordinator]" time="0.000"><failure message="ModuleNotFoundError: No module named 'scripts.a42365_runtime'">tests/unit/test_a42365_runtime_red.py:19: in test_W00_mandatory_runtime_implementation_exists
    value = importlib.import_module("scripts.a42365_" + module)
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
../../../.cache/codex-runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
&lt;frozen importlib._bootstrap&gt;:1387: in _gcd_import
    ???
&lt;frozen importlib._bootstrap&gt;:1360: in _find_and_load
    ???
&lt;frozen importlib._bootstrap&gt;:1324: in _find_and_load_unlocked
    ???
E   ModuleNotFoundError: No module named 'scripts.a42365_runtime'</failure></testcase></testsuite></testsuites>
```

## 九个历史 manifest（逐字节冻结）

```json
{
  "docs/acceptance/BIZ_PERF_01_review_source_manifest.json": "47e64a62424936f9a05645453f86cd7cfaa3d216518a2b2bc55eae7243161a62",
  "docs/acceptance/a42351_reviewer_overlay_manifest.json": "ea795278e3fb84e4eebabeba737d23a92a4a0c42e6402cc828bf3801d3c9f648",
  "docs/acceptance/a42361_overlay_manifest.json": "a88d62d980751cfe182bcffc0a450c21d57195810bdce4e24c80f43c4ff1fb64",
  "docs/acceptance/a42362_overlay_manifest.json": "692b2ca9f3f1f95404a6ec953b557d6a6b510123a522b9f357163d3b016b1817",
  "docs/acceptance/a42363_complete_overlay_manifest.json": "d3f5bdce5c9a05b578eda1f599f9404f78f696170d233a3da1d105008ebbd9ff",
  "docs/acceptance/a42363_overlay_manifest.json": "92f67e70c19eee81ef2ce19283aa9969748480cbc36921df01ebba902bc64662",
  "docs/acceptance/a42363_review_overlay_manifest.json": "ec3d15819acf7c2303b1ac04771dbe9aadf78f121b0a9c00320d69d043905ba2",
  "docs/acceptance/a42364_overlay_manifest.json": "e1a594a7579ce7d79b62f828126c35f56c38df1de7f84b0b589d645e6e2c9cd7",
  "docs/acceptance/a4236_overlay_manifest.json": "d93bf795a59cb0a168f0e96f4382d58efcbdc2833bc43e22ebde3254a09c1156"
}
```

## 精确白名单

新增路径限 a42365_*.py、新 test_a42365_*.py 和本阶段验收 Markdown；最终具体路径与 SHA256 在 a42365_overlay_manifest.json 中逐文件登记，前缀匹配不代表文件自动获准。

旧路径只允许 scripts/a42364_manager.py、scripts/business_source_contract.py 两处版本接线，以及 scripts/a4235_capability_guard.py 新 digest literal。四份权威文档只追加。旧八层 manifest、BIZ manifest 和所有既有测试不修改。
