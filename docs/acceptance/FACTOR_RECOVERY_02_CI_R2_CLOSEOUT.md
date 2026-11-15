# FACTOR-RECOVERY-02-CI-R2 closeout

日期：2026-11-16。TASK=FACTOR-RECOVERY-02-CI-R2。
STATUS=PATCH_IMPLEMENTED / REVIEW_PENDING / NEW_SHA_CI_PENDING。
NEXT=CHATGPT_INDEPENDENT_REVIEW；未暂存、未提交、未推送。

## 基线与范围

开始及本轮只读GitHub核对：
master，HEAD=origin/master=GitHub master=
c690b5006bb6f50d069eba80a4f5b446b46cba53。
恢复参照为3277c81bc85382e939f58ba5d414fef3682b4de8。
开始工作树为上一轮E501纯格式修复，以及W05两资产、前轮诊断报告、本任务书，
没有未知改动。AGENTS、治理与相关业务权威边界已核对；
任务书是本次精确撤销单SQL优化的授权，不解除PG/Worker与真实业务验收禁令。

只修改两个允许文件：
- backend/app/services/data_publication.py；
- tests/unit/test_factor_candidate_write.py。
唯一新增交付为本closeout。任务书、前轮报告、W05资产均保持原字节。
不改旧R1测试、schema/hash、路由、安全插件、workflow、依赖、其他冻结文件。

## 最小修复与因果确认

独立比较c690b50与3277c81，production publication文件只有record_scope这一处差异，
没有其它需要保留的父后变更。恢复为：

```python
self.register_source(source)
self.db.execute(
    update(DataPublicationSource)
    .where(
        DataPublicationSource.publication_id == self.job_id,
        DataPublicationSource.source_job_id == source,
    )
    .values(validated_at=None, validation=None)
)
```

当前完整文件规范化LF字节与git show 3277c81完全相等，SHA256为：
39d95b00afed3da308aa78a00917fad2308f9d19266cfa30268b145bd35e7e88。
该摘要与旧schema原期望完全一致，不更新schema/hash来接受新源码。
没有git reset、切换分支或回滚其它文件；RECOVERY-01因子取消回调修复仍保留。

受控因果检查：在诊断进程读取固定HEAD c690b50 publication字节时，
原verify_business_sources拒绝INTEGRATION_BUSINESS_DRIFT（RED）；
读取实际恢复后工作树时，全部原sources校验通过（GREEN）。
旧合同和原断言原字节未变。

**RECOVERY-02的单SQL性能优化已撤销**。每scope恢复原来的注册+UPDATE两步；
不是性能提速，也不证明用户Worker/复算故障已经解决。
本轮目的是恢复可信CI代码基线，实际新SHA绿灯仍待独立审阅后提交及Linux CI。

## 新测试的同步调整

新candidate_write文件不删测试，参数展开仍9项。
- 原一语句测试改名为original_statement_sequence，
  严格期望source_insert→source_update，检查DO NOTHING及UPDATE验证字段。
- 每次replace的source_insert仍2，source_update恢复为1；
  execute总数从3+2×batch恢复为4+2×batch。
- 保留前轮E501的scope_filters换行，全部新测试行≤100字符。
- 批次上限、lookup/store增长、相同输入重复输出、字段/身份/scope、
  source失败、归属失败和取消异常传播断言均保留。

缓存断言随原实现的SQL方式作对应调整：
旧优化通过register_source(invalidate=True)主动expire，
原实现则由ORM UPDATE同步已知NULL值。
RecordingSession增加该UPDATE分支的内存同步模拟；
断言cached.validated_at和cached.validation都精确为None，
不再要求优化专有的expired_attributes形态。
这保留“验证缓存不可仍有效”的语义；未放松为任选结果，也未声称模拟证明真实DB同步。
生产实现完全恢复父字节，没有为测试另补expire或新行为。

## 验证结果

### 历史12项：当前工作树GREEN

原12个unittest方法全部执行：
SeedLoaderTests全10项、ControllerTests的fake组合1项、
ProtocolTests.test_AC31_source_sha_and_every_new_utf8_file 1项。
输出：

```text
PUBLICATION_EXACT_PARENT_LF 39d95b00afed3da308aa78a00917fad2308f9d19266cfa30268b145bd35e7e88
HISTORICAL_SOURCE_MATCH=True
CURRENT_WORKTREE_GREEN 12 failures 0 errors 0
```

这些是实际原unittest方法，不是AST替身。
Windows checkout的schema为CRLF，合同本来钉住Linux LF；
因此只在诊断进程给r1_business_compare_schema_v1.json.read_bytes提供LF视图，
没有写schema，没有替换publication读数，也没有改任何测试断言。
网络、shell/子进程和.env读取由audit hook拒绝。
controller使用原fake连接/owner/facade；没有真实SQL/PG/Worker。

复现命令（仓库根，复用前轮已审阅脚本，仅改变输出标签并核查结果）：

```python
from pathlib import Path
report = Path("docs/acceptance/FACTOR_RECOVERY_02_CI_FIX.md").read_text(encoding="utf-8")
runner = report.split("```python\n")[1].split("\n```")[0]
runner = runner.replace('print("OFFLINE_RED"', 'print("CURRENT_WORKTREE_GREEN"')
exec(compile(runner, "<offline-r2-12-tests>", "exec"))
assert result.testsRun == 12 and not result.failures and not result.errors
```

以python -X utf8 -B -运行。上述LF视图是平台模拟限制，不是Linux新SHA CI凭证。

### 受影响源码隔离回归

复用既有两份closeout内的诊断脚本，不生成新工具或修改旧报告。
- candidate_write：9项PASS；1/500/501/1001/S2行两次写入逐字段/摘要一致；
  原replace_slice的6项源码断言PASS。
- factor_service_cancellation：10项PASS；取消/归属停止9例写0、commit0；
  正常3因子行、5个checkpoint，字段/身份/scope精确相等；
  附加15项既有算法断言PASS。
- 均明确为源码隔离：真实函数/引擎/模型或SQL编译，
  progress/observed与Session/存储等边界按旧脚本替换；
  不能计作原生pytest或真实PG事务、锁、发布验收。
- 保留原pandas pct_change FutureWarning，不改公式、dtype、阈值或容差。

候选实际计数恢复：

| 行数 | 批数 | lookup/store各 | source INSERT/UPDATE | reconcile | execute总数 |
|---|---:|---:|---|---:|---:|
| 1 | 1 | 1 | 2/1 | 1 | 6 |
| 500 | 1 | 1 | 2/1 | 1 | 6 |
| 501 | 2 | 2 | 2/1 | 1 | 8 |
| 1001 | 3 | 3 | 2/1 | 1 | 10 |
| S2 / 3450 | 7 | 7 | 2/1 | 1 | 18 |

计数仍仅为相应execute边界，不含潜在owner SELECT、scope flush及独立观察。
S2候选摘要仍为112c1736266f6515403a1c81bbb81be2ff18a6b390290c2e2fee5ba054b8051f。
没有据此报告性能收益。

复现candidate脚本时只在进程内将旧测试名
test_factor_scope_invalidates_source_in_one_statement
映射为test_factor_scope_invalidates_source_with_original_statement_sequence；
执行体读取当前新测试，其余脚本不变。

### 原生检查与环境限制

安全启动原生pytest针对candidate_write、replace_slice、factor_service_cancellation：
退出1，3个收集错误，均缺loguru；未执行单测，不记作PASS。
子进程Settings禁.env、Engine.connect拒绝所有连接、禁网络，原安全pytest插件未改。
未安装任何依赖。

Ruff尝试：python -B -m ruff check backend/app/services/data_publication.py
tests/unit/test_factor_candidate_write.py；No module named ruff，ENV_BLOCKED。
两文件AST解析、测试行长≤100、git diff --check通过。
全量pytest/完整Ruff、新SHA Linux主CI/A4-1/A4-2/Publication尚待验收；
不能用此前c690b50失败run或父版本通过结果冒充本次CI绿色。

## 保全

任务开始1643个已跟踪文件原字节SHA256逐项保存并最终比对：
仅上述两个白名单文件发生变化，其余1641个原字节一致。
旧R1合同/schema/测试、安全插件、workflow、依赖、治理、策略、因子取消源码未变。
暂存区为空，无提交/推送。

保留文件SHA256：
- 本任务书：f24106f252f2cb18920a6468a8785f0c5a4f2ce6503d127629e4f71c46f3398b
- 前轮诊断：6480aad7eeecd3124d48bfbd16eee0e419d3f81599f2884d28d4269991c20e3b
- W05任务书：6f9f68c7028729598a0f510358798f746e0e9318e6d6926a128daa298ef915aa
- W05审计：baca21feaa6edbad2e8471db65b80166b0b8d21595550f8c70ef00f63c27d750

五冻结blob与工作树一致：
- scripts/business_recalc_measure.py：782e45ba53c8de8df0d12ffa84c219855316cfda
- scripts/biz_perf_p1_04_diagnostic.py：714f78017ec252791ac6a89f9fb0e0a984333c37
- scripts/perf03_lnx_w04a_offline_contract.py：931fd4fec38551d9fac59791d2bde5ce0e6a1d48
- scripts/biz_perf_03_b_once.py：2ea473491f590893ad575b90a0ba42f932e37129
- scripts/business_sql_snapshot.py：e7532b0a0242f1e3d3b047fdc03fca7ffc3ce7c6

a42331_pytest_safety.py blob仍为64fb3709d5bd74ca1a407c87c461a4c52acaff67。

## 交接与下一步

本轮性能优化已撤销，DB_HOTSPOT=UNPROVEN，业务计算尚未真实验收。
DB_STATUS=NOT_CONNECTED_UNTOUCHED；B_GATE=NOT_APPROVED；
TARGETED_PG17_GATE=NOT_APPROVED；ROOT_ATTEMPTS=0。
没有真实PG、Worker、SQL/迁移、Raw重拉、性能试验或生产访问。

等待ChatGPT独立审阅两文件diff及上述证据；只有获后续授权后才提交/非force推送，
再核查新SHA完整CI，不能现在宣布“真实CI已绿”。
后续主线优先恢复实际Worker因子计算链路：取得既有失败Job脱敏阶段证据，
定位更大的读取/计算/候选/发布热点，再在获准隔离环境验收；
不继续泛用审计框架，不凭本次撤销宣布正常复算或性能问题已经解决。
