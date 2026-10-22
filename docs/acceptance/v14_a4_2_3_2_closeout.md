# A4-2.3.2 阶段记录（P1a预检待CI，尚未采样）

本轮只执行P0/P1，当前尚无新性能/因果数据。旧1100与128样本均为HISTORICAL_DIAGNOSTIC，
旧C1 P95失败、repeat81非大GC反例、H3仅2/8及as_seeded统计漂移保持原样。

## P0冻结

基线29ee84548a4254c646b30305ed620ae0fdd2f49c，开工master/clean，fetch后origin相同。
P0独立提交`da97cbe63b57499c4b3705ba671c179e4440fd0e`，在任何新测量代码之前。
[协议](v14_a4_2_3_2_protocol.md) SHA256：
`047db54f9ac95b1729afa30e221f0fbd7013013db5fa4bf6f6302c4645affb39`。
[冻结历史身份/反例](evidence/a4232_historical_baseline.json)已由两个原ZIP重新校验；不改旧JSON。

## P1a实现范围

- `a4232_stability_contract.py`：新UUID库物理校验、分表计数、服务端pg_statistic摘要、
  默认ANALYZE/条件式四表控制、漂移失败关闭、固定四进程顺序和非准入H3检查。
- `a4232_plan_probe.py`：只驻内存的原SQL/参数捕获、fresh/cached EXPLAIN结构签名、
  SQL/参数类型hash、generic/custom计数和mode；不导出SQL/表达式/bind。
- `publication_tail_stability_a4232.py`：专用CI唯一批次、逐轮统计/计划前后检查、原wall计时、
  自然GC与所有128样本/部分失败证据；原a4231/lab字节冻结，生产未改。
- 独立`a4232-statistics-tail-diagnostic`工作流：contracts先行，无release准入边，
  仅P1b唯一标记、master push、attempt1且contracts成功才可进入attribution。
- `a4232_test_receipt.py`：JUnit仅导出计数，原失败文本与driver SQL不进入上传工件。

P1a提交不带一次性采样标记；只跑70个新unit契约、既有历史/GC/失败关闭单测、
4个微型PG17稳定性集成测试与既有A/B安全用例，不执行128样本或百万级性能采样。
P1a的PG17通过之后才允许P1b激活；不能拿单测结果冒充真实统计稳定或机制已证实。

本地Docker daemon未运行，本轮未启动它/用户服务，未读取业务.env或连接云库。
本地单测使用Settings.env_file=None及显式不可用合成loopback配置：完整1927项通过（26.35秒，
两个既有弃用警告），新增70项通过，Ruff与git diff --check通过；PG17结果待CI，不冒充已完成。
所有生产/模型/配置/迁移/前端、旧诊断和历史证据仍相对29ee845冻结。

## 当前审批/剩余项

P1a提交5e2ac9e的[预检run39831770523](https://github.com/sssssssssh/ssh_stock/actions/runs/39831770523)
在测试收集阶段失败：unit/integration同名模块触发pytest import mismatch；attribution跳过，样本0。
已在本地collect-only复现并将PG17模块改为test_tail_stability_pg17_a4232.py，新增命名回归。
另为预检失败增加仅含类名/SQLSTATE/脱敏栈的工件，不上传原异常/SQL；协议不变，未运行实验。
修正后全库2740项可收集，完整1929项单测通过（24.43秒，两个既有警告），新增72项与Ruff通过。

新实验NOT_RUN；unique_repair_candidate=null。P2/P3、生产SQL、正式5/100、正式L2均NOT_AUTHORIZED。
capacity_ready/performance_eligible/production_matches_candidate=false，原release gate和P95门槛不变。
统计稳态、原始新工件、因果分析和最终exact-SHA CI尚待P1a/P1b/P1c实际执行；没有通过前保持OPEN。
