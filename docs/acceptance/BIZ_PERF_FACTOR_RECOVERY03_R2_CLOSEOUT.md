# BIZ-PERF-FACTOR-RECOVERY-03-R2 closeout

日期：2026-11-16。
BASELINE_SHA=232baf9e13cd7b23731e59188c86e0e253c3a394。
STATUS=PHASE1_CLASSIFICATION_BLOCKED / REVIEW_PENDING。
PHASE1_MIGRATION_GREEN=NOT_ACHIEVED；WORKER_FIXED=false。
REAL_FACTOR_RUN=NOT_RUN；NEXT=CHATGPT_REVIEW。
未暂存、未提交、未推送。

## 执行结果与停止条件

已完成第一阶段最关键的独立归属核对，并新增原生回归证明：
旧12个节点**不能整体认定为纯历史证据**。
controller节点执行当前适配器的组合行为；
seed节点也包含当前FrozenSeed的篡改拒绝、资源独立性、重放与真实执行禁用行为。
不能仅将它们列入历史路由便声称当前等价测试得到保留。

本轮没有改三个路由脚本，没有改Worker，没有改原R1测试或任何旧hash。
只新增允许的tests/unit/test_source_contract_r1_history.py和本报告。
原因是保持这些当前行为覆盖的独立版本化校验需要白名单外文件；
任务书明确“若合同路线需要改范围外文件，停在明确文件与理由，不可越界”。
所以停止第一阶段，不进入以第一阶段完全验证为前提的第二阶段。
29项测试通过是分类与既有保护测试通过，**不是历史迁移GREEN，也不是Worker修复GREEN**。

## 基线与已有资产

master，开始HEAD=origin/master=已认证GitHub master，均为完整基线SHA。
全部已有未跟踪文件属于03/03-R1任务及报告、W05两资产和本次R2任务书，
未覆盖、移动或删除。AGENTS、前轮任务/报告、固定合同机制均已核对；
治理及业务权威边界沿用本持久会话已读同版本，没有取得真实DB/Worker许可。

可见多个Codex桌面/CLI/host进程；Get-Process不能区分任务命令行，
此前CIM查询权限拒绝，未尝试越权或终止进程。
同任务CLI并发=UNKNOWN；没有证据确认另一个同任务正在运行。
为此也未修改共享业务/路由源码，只新增本轮隔离测试与报告。

## 原生反例：当前行为不能被历史checkout掩盖

新增测试文件含5项参数展开用例：

| 用例 | 操作与实际结果 |
|---|---|
| test_legacy_history_rejects_r1_before_git | R1 controller节点传入现有history.run，原机制在Git前拒绝UNREGISTERED_HISTORICAL_NODE |
| test_composed_controller_still_exercises_current_adapters | 直接调用原ControllerTests组合方法，使用当前真实适配器类及原fake I/O，原断言通过 |
| test_current_controller_assertions_detect_behavior_damage[preflight] | 只在进程内使当前preflight返回fake_only=False；原方法抛AssertionError，检测当前行为损坏 |
| 同上[execute_fake_root] | 只在进程内使当前fake-root返回错误status；原方法抛AssertionError |
| test_same_current_controller_refuses_proposed_worker_change | 只在read_bytes内存视图给Worker加入拟议ident保护；原组合方法在业务检查前因INTEGRATION_BUSINESS_DRIFT拒绝 |

基线正例是当前行为GREEN，两个故障注入是原断言检测到RED；
它们不是路由或生产修复的RED→GREEN。
拟议Worker修改只存在于读取替身，没有写入job_worker.py。
测试调用完整原方法，不抽取其断言AST，不以只校验callback标签替代组合行为。

在Windows仅给旧schema读取提供精确Linux LF视图，避免已知CRLF环境差异；
当前Worker原字节及所有原行为断言均保留。
fake DB/owner/facade仍为原测试组件，不启动真实线程、Worker或PG。
所有monkeypatch随各用例恢复。

这证明：若原controller节点迁往固定232baf9子进程，而不另保留
当前同等行为检测，当前preflight/fake-root损坏可能被旧checkout的通过结果遮住。
本轮没有接受这种迁移，也没有对其提前制作绿色路由receipt。

## 具体源码阻断

固定schema仍为docs/acceptance/r1_business_compare_schema_v1.json；
Worker LF SHA256仍为
91069dd58733e442831977f58ee1c37616d1ef37a271d7845856421251d6e7da。
schema自身SHA256仍为
f6be0a5de1ce46e30758039a3ab345a308ff96cb36f6ee86ec3ccdc39759f297。

双重绑定位置：
- scripts/r1_integration_controller.py:75，
  OfflineIntegrationComponents.preflight直接调用verify_business_sources()；
- scripts/r1_integration_seed_loader.py:93，
  original_fixture_oracle同样先调用verify_business_sources()；
  FrozenSeed._capture调用该oracle，实际验证18表4024行原fixture、默认值、
  catalog及entity digest，不能只换成一个FakeSeed而仍称覆盖等价；
- 实际校验实现scripts/r1_integration_evidence.py:82–96，
  只支持原schema来源，遍历当前工作树所有sources，包含完整Worker文件摘要。

因此存在两个同时不能丢失的语义：
1. 旧固定schema及其真正历史断言必须原样保留。
2. 当前controller/seed的业务拒绝与组合行为必须仍测试当前模块。
在新Worker合法变化后，当前校验入口没有独立当前版本可选；
其在行为检查前即拒绝。路由脚本本身不能给该入口增加正确的业务版本语义。

本轮明确不采用：
- 在新“等价”测试里把verify_business_sources改成lambda True；
- 将Worker读取替换回旧字节后称其已经验证当前Worker；
- 给旧schema直接换hash、接受任选hash、忽略Worker或失败后fallback；
- 将所有12项或整个目录送入旧checkout；
- 把真实FrozenSeed替换为只回固定标签的假对象。
这些做法无法同时满足原断言和当前等价覆盖要求。

## 超出白名单的精确最小需求

推荐先审阅“当前版本校验与历史证据分离”，而不是先迁12个节点：

1. **scripts/r1_integration_evidence.py**（当前未授权）：
   为当前离线集成校验定义独立显式版本/来源入口，
   与旧schema验证严格区分，未知版本/缺来源/内容变化继续拒绝；
   不通过文件存在、固定hash不匹配或异常来自动fallback。
   旧历史入口及旧schema的来源含义不能改写。
2. **一份新增独立当前来源定义**，例如
   docs/acceptance/r1_current_business_sources_v2.json（当前未授权）：
   绑定当前Worker及所需fixture/model来源的完整摘要、定义版本和非执行用途。
   这是候选路径/方案，不是本轮已经建立的合同。
   原r1_business_compare_schema_v1.json、其hash和原测试不改。
   新定义不能授予B_GATE/PG/Worker执行、真实输入相等或性能资格。

两个文件以明确授权为前提；若审阅认为当前调用者必须显式传版本，还需额外批准
scripts/r1_integration_controller.py和scripts/r1_integration_seed_loader.py的窄调用点，
不能在当前白名单内暗自修改。seed_loader还被其它旧源冻结表引用，
更不能先改后让CI碰出下一层hash失败。

下一步应先验证当前版本路径能够保持原controller/seed原生正反例，
再逐节点判断哪些断言仍应历史执行。AC31的逐物理文件固定hash检查是明确的
历史候选；其它11项不应仅因依赖旧schema就自动归历史。
所有新增当前版本正反例在当前源码运行；保留当前Worker/取消/发布测试。

若上述分离经独立审阅获准，仍复用已授权的三路由脚本实现真正历史节点，
而不再扩一个通用框架：
- R1执行语境commit232baf9e13cd7b23731e59188c86e0e253c3a394，
  tree=d21c4a1d870c68177175ebee276b7c1f350345f7，旧A42366常量原样保留；
- 精确注册、双SHA/tree、原测试committed/物理字节、离线clone、
  .env/网络拒绝、严格JUnit唯一节点和零failure/error/skip；
- unittest必须在收集阶段准确替换，不允许当前setUpClass先运行再委托；
- 用真实子进程标记证明历史setup/body/teardown均运行，
  当前setup不运行且非注册当前节点不被转移。
本轮这些路由实现与验收均NOT_IMPLEMENTED，未执行历史clone或创建Git目录。

## 测试命令与实际结果

原生安全启动新增文件：
python -X utf8 -B -，执行下方脚本：**5 passed，5.82秒，退出0**。

扩展同次执行新增文件与旧A42366路由保护6组：
- exact node/path拒绝2项；
- 子进程failure/error/skip/计数拒绝6项；
- CLI未知参数拒绝4项；
- 两版本非执行用途拒绝8项；
- 未知版本拒绝4项。
合计 **29 passed，5.62秒，退出0**。
旧73项独立checkout回归未运行，不能把这24项边界回归写成73项通过。

两次pytest在atexit清理既有pytest-current临时路径时出现WinError5警告；
未手工删除/清理或越权，实际测试数与进程退出码如上。
安全启动保留默认pytest安全插件，audit hook拒绝.env读取、网络及子进程。
实际测试均为进程内假I/O，不连接数据库。

当前Worker原生pytest收集尝试：
test_job_worker.py因缺fastapi退出1，0个测试执行，ENV_BLOCKED。
使用既有安全启动，Engine.connect禁止连接；未安装依赖。
本轮未进入Worker实现阶段，候选/取消完整原生回归及新Worker原生故障矩阵NOT_RUN，
不以此前AST结果冒充本次原生GREEN。

Ruff针对三路由脚本及新测试尝试：
No module named ruff，退出1，ENV_BLOCKED。
新文件AST解析、≤100字符行长、git diff --check通过。
没有新SHA CI、性能前后收益或真实因子验收。

安全测试启动脚本（仓库根）：

```python
import os,sys
from pathlib import Path
import pytest
def guard(event,args):
    if event=="open" and isinstance(args[0],(str,bytes)):
        if Path(os.fsdecode(args[0])).name==".env": raise AssertionError("NO_ENV")
    if event in {"socket.connect","socket.bind","socket.getaddrinfo","subprocess.Popen","os.system"}:
        raise AssertionError("NO_EXTERNAL")
sys.addaudithook(guard)
raise SystemExit(pytest.main(["tests/unit/test_source_contract_r1_history.py",
                            "-q","-p","no:cacheprovider"]))
```

29项扩展使用03-R1 closeout的保护测试脚本，
仅在pytest参数列表追加tests/unit/test_source_contract_r1_history.py，
原24个节点/断言未改。

## Diff、保全及剩余风险

精确diff为新增tests/unit/test_source_contract_r1_history.py，
包含分类fixture及5项用例；不修改任何现有文件。
另新增本closeout。任务书、前轮03/03-R1/W05未跟踪原件均保留。

1646个已跟踪文件原字节映射（排序JSON SHA256）仍为：
702a421ae1366d401ccccd0df2c665ac0edb45f8978907cc66241b4650898a8e。
所以全部旧源码、schema、hash、原断言、安全插件、CI、依赖、冻结五件保持原字节。

保留原件SHA256：
- R2任务书：25668afa7fc32073369aeffe662c8d1fd726dbd839e57da62f8548daa85c7dcc
- R1任务书：df9fb876927dc82467729bc1290a71fa5dccfb72616cd99844b51ced3a6776d8
- R1报告：74b90e237eb5f613694ee5d3dbe993ef22f7bce0226f6dbd6b01811201764ac2
- 03任务书：aae3179df7d44bd28ff6912d3f1f0132514c45b690b0c23123f7a3dd7d86343f
- 03报告：d9c034fa2aff97e965bd225b9c5f9457b9b8f66ca0c893ca0ebd5fbf2ee245e3
- W05任务书：6f9f68c7028729598a0f510358798f746e0e9318e6d6926a128daa298ef915aa
- W05审计：baca21feaa6edbad2e8471db65b80166b0b8d21595550f8c70ef00f63c27d750

本次分类回归是当前旧校验入口的明确阻断证据；
将来批准新版本后应同步改为新版本正反例，不能保留一个“永远拒绝合法Worker变更”
的断言来再次阻断已批准实现，也不能先删掉该证据假装问题不存在。
所有原R1测试和旧合同仍不改。

B_GATE=NOT_APPROVED；TARGETED_PG17_GATE=NOT_APPROVED；ROOT_ATTEMPTS=0。
未连接真实DB、未运行真实Worker/SQL/迁移、未改Raw/Derived、未重拉数据、
未建云资源或做正式性能实验，未提交推送。
心跳join缺陷仍未修复；合同迁移未完成；不能宣称恢复了真实因子计算或CI迁移已绿。
下一步是对上述额外版本化入口作窄范围裁决，然后回到原生Worker可靠性修复，
而不是继续迁移更多历史节点或扩W05审计。
