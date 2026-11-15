# FACTOR-RECOVERY-02 紧急 CI 诊断与最小修复

日期：2026-11-16。STATUS=PARTIAL / REVIEW_PENDING。
FACTOR-RECOVERY-03=STOPPED；NEXT=CHATGPT_INDEPENDENT_REVIEW。
未暂存、未提交、未推送、未触发/重跑工作流；未连接真实PG、未运行Worker/Scheduler、
未读取.env或业务数据、未执行SQL/迁移、未扩展性能工具。

## 基线与当前交付

master，HEAD=origin/master=已认证GitHub master：
c690b5006bb6f50d069eba80a4f5b446b46cba53。
父提交3277c81bc85382e939f58ba5d414fef3682b4de8。
开始仅有前轮W05任务书及审计两个未跟踪文件，均原字节保留。
已核对AGENTS；五治理及相关业务权威文件沿用本持久会话前轮已读版本，
本次git diff确认相对前轮没有变化。此次授权是紧急诊断，不进入03。

实际修改仅 tests/unit/test_factor_candidate_write.py 的长行拆分；新增本报告。
生产 publication、历史R1合同/schema/工具、workflow、安全脱敏插件均不改。
CI恢复尚未完成：E501已做等AST修复；当前源码下12项历史合同失败仍未关闭，
不能宣称全部GREEN或新SHA CI已通过。

## GitHub 认证日志及XML证据

四个指定run均为c690b50对应执行，工件绑定完整SHA、attempt1。
只读取已有jobs/logs/artifacts，没有dispatch、rerun、取消或设置变更。

| Run / Job | 实际首要失败及已完成检查 |
|---|---|
| 主CI [43753378192](https://github.com/sssssssssh/ssh_stock/actions/runs/43753378192)，test 132932047866 | 全量日志：12 failed、7661 passed、1 skipped、821 warnings，2798.41秒；后续Ruff/构建等skipped |
| 同run，workflow-contracts 132932048121 | pytest **265 passed**；失败是下一步Ruff E501，不是workflow合同pytest失败 |
| A4-1 [43753378141](https://github.com/sssssssssh/ssh_stock/actions/runs/43753378141)，contracts 132932047865 | 49 passed；同一步命令后续Ruff E501，致整个step failure |
| A4-2 [43753378121](https://github.com/sssssssssh/ssh_stock/actions/runs/43753378121)，contract-and-safety 132932048138 | 342 passed；Ruff E501 |
| Publication [43753378110](https://github.com/sssssssssh/ssh_stock/actions/runs/43753378110)，contracts 132932047750 | 候选等价/锁/取消阶段85 passed；Ruff E501 |

四处Ruff均明确指向：
tests/unit/test_factor_candidate_write.py:138:101，
E501 Line too long (101 > 100)，Found 1 error。
主CI test的Ruff步骤未运行，不能把它记作已经观察到E501。
后续CI-OPT汇总job拒绝mandatory failure是正常级联，非另一独立根因。
依赖审计与lookup-diagnosis成功；高成本专项skipped不是性能验收。

实际读取两个ZIP，内存解压XML，没有把原始日志/临时下载URL写入仓库：

| Artifact | SHA256 / 核对结果 |
|---|---|
| [14179012812](https://github.com/sssssssssh/ssh_stock/actions/runs/43753378192/artifacts/14179012812)，a42331-safe-ci | 802aede8d4ff23ed97408f9355b808853ec9368236c5eea2bf1188d26b4e4c0c，与GitHub digest相等 |
| [14177281838](https://github.com/sssssssssh/ssh_stock/actions/runs/43753378192/artifacts/14177281838)，a4-ci-contracts | e6f2ddadfe4dc7c0629b19dc2f5375f131c180b0ec167362a4b7df427c508064，与GitHub digest相等；a4-ci-contracts.xml为265 tests、0 failure/error/skip |

safe-ci包含a42331-targeted.xml、data-publication-targeted.xml、cold-start-targeted.xml、
m17_1_2-full.xml、m17_1_2-targeted.xml、v14-targeted.xml及failure.json。
目标m17_1_2-full.xml有12个failure，全部仅有
A42331_TEST_FAILURE，不含参数、栈或底层异常；不据此猜测具体错误。
其suite tests属性为9667，与全量终端统计分开记录，不用它推算passed或覆盖率；
本轮未进一步归因这两种计数口径差异。
其它读取XML的failure/error均0：143、45、114、85、51 tests。
安全脱敏继续保持；没有移除或改变a42331插件以获取CI秘密。

XML定位的12个精确节点：

- tests.unit.test_r1_integration_controller.ControllerTests.test_composed_real_adapters_fake_io_not_just_callback_labels
- tests.unit.test_r1_integration_seed_loader.SeedLoaderTests.test_AC07_generate_once_complete_original
- tests.unit.test_r1_integration_seed_loader.SeedLoaderTests.test_AC08_default_timestamps_frozen
- tests.unit.test_r1_integration_seed_loader.SeedLoaderTests.test_AC09_sequences_and_catalog_exact
- tests.unit.test_r1_integration_seed_loader.SeedLoaderTests.test_AC10_independent_dual_loads_and_entity_values
- tests.unit.test_r1_integration_seed_loader.SeedLoaderTests.test_AC11_source_tampering_partial_duplicate_theme_type
- tests.unit.test_r1_integration_seed_loader.SeedLoaderTests.test_AC12_no_plan_only_proof_or_live_loading
- tests.unit.test_r1_integration_seed_loader.SeedLoaderTests.test_all_frozen_timestamps_and_absent_nulls_have_explicit_origins
- tests.unit.test_r1_integration_seed_loader.SeedLoaderTests.test_capture_callback_once_row_order_and_catalog_index_tamper
- tests.unit.test_r1_integration_seed_loader.SeedLoaderTests.test_capture_does_not_trust_replaced_generator
- tests.unit.test_r1_integration_seed_loader.SeedLoaderTests.test_independent_oracle_catches_orm_default_not_generator_self_comparison
- tests.unit.test_r1_real_root_protocol.ProtocolTests.test_AC31_source_sha_and_every_new_utf8_file

## 共同根因与历史不稳定的区分

这是两个问题，不能用一个解释替代另一个。

1. c690b50新增测试存在101字符长行，确定性引入E501，四个工作流共因。
2. c690b50生产变更碰到旧R1固定源码合同；不是批次SQL、真实PG锁或Worker故障。

精确链：
seed loader original_fixture_oracle/FrozenSeed→
scripts/r1_integration_evidence.py verify_business_sources→
load_schema()['sources']与工作树规范化LF字节逐项SHA256比较。
controller的fake组合也创建FrozenSeed，因而同样拒绝。
ProtocolTests.AC31直接执行相同的逐文件摘要相等断言。

旧schema为docs/acceptance/r1_business_compare_schema_v1.json，
schema_version=r1.business-compare.v1，
target_sha=b6ffb7bf8ec7d26f771d9b89923e4f7e926edbed，
authority=NO_GO，schema自身摘要由SCHEMA_SHA256钉住。
在其全部sources中，本轮唯一不匹配是backend/app/services/data_publication.py：

- 旧schema期望：39d95b00afed3da308aa78a00917fad2308f9d19266cfa30268b145bd35e7e88
- 父3277c81实际LF摘要：相同
- c690b50实际LF摘要：2c42b2bb750ccb73304ea22180cdefeeb8dc47715970610adc361453bbdee6e8

唯一生产delta正是record_scope复用register_source(invalidate=True)。
这里确认的是**本次引入的源码合同兼容性回归**，不是证明生产计算语义回归。
Publication真实CI的85项通过也是有限工程证据，不能反向证明所有业务/性能条件。

没有证据把这12项归为历史flaky；同一源码视图的确定性拒绝、单文件父视图对照支持归因。
此前supervisor deadline时序竞争不在这12个节点，不顺带修改或重跑。

## 离线RED与父视图反事实对照

执行的是原有12个unittest方法，不是只抽取源码AST。
导入范围为标准库/R1离线模块及原fake适配器；audithook拒绝.env读取、网络、
子进程和shell。没有调用真实loader/PG/Worker。parent git show在安装guard前只读取得，
临时目录只由原fake测试按其正常生命周期使用/清理。

初次Windows原字节运行遇到额外环境阻断：
schema原始CRLF摘要e023206e7209ff96ebeb0417dbd516a061c9dc58aee4bf98e9f63fc84e04ea47，
LF摘要f6be0a5de1ce46e30758039a3ab345a308ff96cb36f6ee86ec3ccdc39759f297，
后者正好等于合同常量。原字节会在setUpClass先R1_SOURCE_CONTRACT_DRIFT，
不能冒充CI底层异常。
另有unittest相对pytest的tests/unit导入路径差异，诊断只补sys.path，不改文件。

为模拟Linux现有checkout，仅在诊断进程给schema.read_bytes提供LF内存视图，
其余当前业务源码仍真实读取；没有写文件或改schema/hash。结果：

- 当前c690b50视图：12运行，2 assertion failure、10 error。
  9个seed方法及controller为INTEGRATION_BUSINESS_DRIFT；
  replaced-generator负例因预期SEED_ENTITY_MISMATCH却先遇该drift而assertion失败；
  AC31为源码摘要相等assertion失败。
  pytest将这些归为failed，而unittest区分error/failure，不混淆计数。
- 仅把publication的read_bytes换成git show 3277c81原字节，schema仍用LF视图：
  **12运行、0 failure、0 error**。全部原断言保留。
  这是父源码的只读因果对照，不是当前补丁GREEN，也不是历史完整CI重新验收。

当前代码仍会按旧合同拒绝；本报告明确保留这个RED，不用诊断替身修饰最终状态。

## 已完成的最小修复及验证

仅拆分test_factor_candidate_write.py第138行的scope_filters列表：

```diff
-            scope_filters=[StockFactorDaily.trade_date >= start, StockFactorDaily.trade_date <= end],
+            scope_filters=[
+                StockFactorDaily.trade_date >= start,
+                StockFactorDaily.trade_date <= end,
+            ],
```

受控RED：HEAD精确只有一条>100字符行，(138,101)。
GREEN：当前文件所有行≤100；完整ast.dump(old)==ast.dump(new)，所有断言/条件/SQL表达式不变。
AST摘要两侧相同：
3e6b2a9f6190bbada0d8cf3a854060fe376a2ec30fe7d8099000c6302dcb6e3f。
这足以证明该E501长行已消除，不等于完整Ruff已运行通过。
python -B -m ruff check tests/unit/test_factor_candidate_write.py：
No module named ruff，ENV_BLOCKED，未安装依赖。
git diff --check通过。没有放宽断言、加skip/重试/容差或改a42331脱敏。

## 停止合同层修改的依据与具体交接

[PROJECT_RULES.md](../../PROJECT_RULES.md)第76、84–90行要求：
“历史源码合同、manifest、原正反例及旧验收记录不改写”，历史合同只在对应源码适用，
逐节点登记历史路由，不能通配迁移当前安全测试。
第97行仍记载“先做业务优化，暂不适配旧冻结合同”。
本次用户另要求“不扩展性能工具”“若需要越界先停止报告”。

因此没有直接更新schema摘要、接受双摘要、忽略publication源、修改seed guard，
也没有把12个节点skip或转到旧checkout冒充当前业务通过。
关闭这组失败需要对旧合同/历史路由作明确版本适配裁决，超出本次保守最小格式修复。
这里是依据仓库规则与用户停止条件的范围判断，不是自动审批拒绝。

独立审阅可据以下具体范围裁决，不需要继续开发泛用性能框架：
- 是否批准仅对这12个历史合同节点逐一登记历史源码执行语境；
- 若批准，复用既有source_contract_pytest的历史独立checkout机制，
  为每个节点证明归属/旧正反例完整性，原hash/manifest保留；
- 必须保留当前业务publication/取消/身份/候选安全回归在当前SHA执行，
  不能目录通配转移测试、混入当前覆盖率或授予性能权限；
- 或明确要求其他独立版本化方案，但不能直接给旧schema换上新生产hash。

本轮只提供上述方案，未修改路由、合同或工具。
RECOVERY-03继续停止，等待ChatGPT独立审阅；不提交不推送。
当前剩余风险：12项仍RED、完整Ruff本机不可运行、新SHA Linux CI未验收。
B_GATE=NOT_APPROVED；TARGETED_PG17_GATE=NOT_APPROVED；ROOT_ATTEMPTS=0。

## 保全

1643个已跟踪文件开始原字节SHA256映射（排序JSON）：
c0dab357a49c64087b9d37d229d9fe939552fc17aa3b09748fe794d4b554364f。
最终仅在内存替回修改测试的HEAD原字节，映射摘要相同，
证明其它1642个已跟踪文件原字节未变；生产修改、历史合同/CI/安全插件均未动。
前轮W05两资产SHA256分别：
6f9f68c7028729598a0f510358798f746e0e9318e6d6926a128daa298ef915aa、
baca21feaa6edbad2e8471db65b80166b0b8d21595550f8c70ef00f63c27d750。

五冻结blob与工作树一致：
- business_recalc_measure.py：782e45ba53c8de8df0d12ffa84c219855316cfda
- biz_perf_p1_04_diagnostic.py：714f78017ec252791ac6a89f9fb0e0a984333c37
- perf03_lnx_w04a_offline_contract.py：931fd4fec38551d9fac59791d2bde5ce0e6a1d48
- biz_perf_03_b_once.py：2ea473491f590893ad575b90a0ba42f932e37129
- business_sql_snapshot.py：e7532b0a0242f1e3d3b047fdc03fca7ffc3ce7c6

scripts/a42331_pytest_safety.py blob：
64fb3709d5bd74ca1a407c87c461a4c52acaff67，保持不变。

## 可复现诊断脚本

仓库根 python -X utf8 -B -，无需数据库或应用依赖。
当前源码RED脚本；只在进程内提供schema的Linux LF读取视图：

```python
import os,sys,unittest
from pathlib import Path
def guard(event,args):
    if event == "open" and isinstance(args[0],(str,bytes)):
        if Path(os.fsdecode(args[0])).name == ".env":
            raise AssertionError("OFFLINE_ENV_FORBIDDEN")
    if event in {"socket.connect","socket.bind","socket.getaddrinfo","subprocess.Popen","os.system"}:
        raise AssertionError("OFFLINE_EXTERNAL_FORBIDDEN")
sys.addaudithook(guard)
from unittest.mock import patch
original_read_bytes = Path.read_bytes
def lf_schema(path):
    raw = original_read_bytes(path)
    return raw.replace(b"\r\n",b"\n") if path.name == "r1_business_compare_schema_v1.json" else raw
sys.path.insert(0,str(Path("tests/unit").resolve()))
from scripts.r1_real_root_protocol import Refused
from tests.unit.test_r1_integration_seed_loader import SeedLoaderTests
from tests.unit.test_r1_integration_controller import ControllerTests
from tests.unit.test_r1_real_root_protocol import ProtocolTests
class Result(unittest.TestResult):
    def addError(self,test,error):
        super().addError(test,error)
        print("RED",test.id(),type(error[1]).__name__,
              str(error[1]) if isinstance(error[1],Refused) else getattr(error[1],"name","DETAIL_NOT_EMITTED"))
    def addFailure(self,test,error):
        super().addFailure(test,error)
        print("RED",test.id(),type(error[1]).__name__,"PINNED_SOURCE_ASSERTION")
suite=unittest.TestSuite([
    unittest.defaultTestLoader.loadTestsFromTestCase(SeedLoaderTests),
    ControllerTests("test_composed_real_adapters_fake_io_not_just_callback_labels"),
    ProtocolTests("test_AC31_source_sha_and_every_new_utf8_file")])
result=Result()
with patch.object(Path,"read_bytes",lf_schema):
    suite.run(result)
print("OFFLINE_RED",result.testsRun,"failures",len(result.failures),"errors",len(result.errors))
```

父源码因果对照使用相同脚本，但guard安装前只读取固定Git对象：

```python
import subprocess
parent_publication = subprocess.check_output([
    "git", "show",
    "3277c81bc85382e939f58ba5d414fef3682b4de8:backend/app/services/data_publication.py",
])
```

并仅将lf_schema开头加上：

```python
if path.as_posix().endswith("backend/app/services/data_publication.py"):
    return parent_publication
```

不应将父视图对照加入当前生产测试来假装本次CI已恢复。
