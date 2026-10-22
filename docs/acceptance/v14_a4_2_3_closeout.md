# V1.4-A4-2.3 阶段交付：P0完成，生产与正式L2未授权

## 结论与版本

结论 OPEN。起点 master `44e46b0cf4b52b2e7008e1f9ed842cd251971864`，初始工作树干净。
保持当前master，不改写历史、不使用业务环境；最终SHA及对应最新Actions以本轮提交与交付消息为准。
本文件中的44e证据全部HISTORICAL，不能填充本轮新SHA发布验收。

| 阶段 | 状态 | 证据/原因 |
|---|---|---|
| P0/W0 | 完成 | 摘要固定、1100样本完整、原顺序、分位数/whole/decision重新计算 |
| P0/W1 | 审阅完成，因果未证明 | 完整400点C0/C1控制序列、40点慢表样本、异常分解、wrapper功能回归 |
| P1/W2 | NOT_AUTHORIZED | 没有已证明且获准的唯一修复候选，不重跑已有100次实验 |
| P2/W3 | NOT_AUTHORIZED | P1不满足，生产保持C0，未启用源码冻结例外 |
| W4拒绝路径 | 已实现；当前CI结果另行核对 | 当前身份CAPACITY_NOT_AUTHORIZED及明确原因；Release Gate仍拒绝 |
| P3/W5 | NOT_AUTHORIZED | 不启动正式L1/L2/L3；不是资源延期 |

详见[基线与全部逐样本表](v14_a4_2_3_baseline.md)、[JSON](evidence/v14_a423_tail_baseline.json)、
[预注册协议](v14_a4_2_3_protocol.md)、[ADR](../design/adr_v14_a4_2_3_c1_tail_decision.md)。

## 性能与生产准入

原统计快表C0/C1 P50=0.084719762500/0.065962649000，P95=0.137348492750/0.074126759950秒。
analyzed快表P50=0.083800149500/0.066161928500，P95=0.088755977800/0.191595000500秒。
GC与行物化/CPU嵌套；6个analyzed样本与大GC相关，另1个execute增长；不能扣除GC或推断因果修复。
两个慢表、三表逐轮整体结果完整保留在JSON；本轮未重新测量，不对新代码宣称性能收益。

`performance_eligible=false`；`production_matches_candidate=false`；`capacity_ready=false`。
生产SHA256=7708d91c831a64093f18aa4f8515789492762f464ccfe202ee0219b756f32976；
候选SHA256=5409c99ed43ca4d306e441a12736fb866c9f920e38e4b81d9d465a242eb18964。
全部历史样本Golden为PASS，但旧Golden不授权新SHA生产。
当前lookup Job仍执行真实隔离PG17小型候选安全回归；它不等于正式L2。

## 正式L2精确结果

| 项目 | 目标 | 本轮实际 |
|---|---|---|
| 环境 | CI自建双物理身份PG17 | 未创建正式容量实例；小型安全回归另计 |
| 股票/交易日 | 5000×20 | NOT_AUTHORIZED |
| 十表/行数 | 603040 | NOT_AUTHORIZED，不填0或伪造已完成数 |
| root/ledger | SUCCESS/PUBLISHED | NOT_AUTHORIZED |
| row_budget/sql_timeout回滚 | 两项真实通过 | 正式规模NOT_AUTHORIZED |
| 队列/读者/A摘要 | max_running≤1、读者有样本无错、失败不改A | 正式规模NOT_AUTHORIZED |
| 预算 | batch500、SQL300s、merge300s、1000万行、原270min软预算 | 原代码/CI保持不变，未提高 |

历史603040 public诊断fixture不是603040行正式B候选upsert/发布收据。
capacity skipped不等于RESOURCE_DEFERRED；没有创建正式COMPLETE或资源延期收据。

## 测试映射（条件项不冒充完成）

| 用例 | 实现/验收入口 |
|---|---|
| T01/T02 | 原ZIP摘要+完整顺序复算、400点inclusive P95精确比对，历史失败保留 |
| T03/T04 | GC回调成功/异常恢复，不强制GC；嵌套标签，未扣除任何成本 |
| T05 | 固定三个2000键摘要、同源快照证明及缺键摘要拒绝 |
| T06–T10 | 原candidate PG17集成：候选优先/删除/原像/类型/重复键/跨root/table隔离 |
| T11/T12 | 少样本/重复/错顺序/错SHA/attempt/缺统计状态/计划探针均拒绝 |
| T13–T15 | 原严格median/whole/P95阈值控制回归 |
| T16 | 当前C0文件hash；历史复核不能产生capacity_ready=true |
| T17 | 新拒绝收据错身份/脏树/伪造true被拒绝；原缺工件/INCOMPLETE门禁保留 |
| T18–T20 | 原三档capacity校验+新增损坏行数/读者/回滚/旧A摘要等反例；真实L2未授权 |
| T21 | 原性能决策合格控制单元，仅测试合同，不是实测准入；无真实合格候选 |
| T22 | NOT_AUTHORIZED，三档正式容量和Release未通过不得关闭 |
| T23 | 原Node审计schema/lock/count及缺报告/假零回归保持 |
| T24 | 原PG17取消/超时/未知提交安全回归；生产SQL/事务/预算未改 |

本地测试显式在pytest导入前禁用Settings dotenv并指定禁用的合成loopback URL；
本地不运行PG17集成或业务服务。完整pytest、前端/构建/浏览器以新SHA实际CI为准，未完成不标PASS。
本地最终完整unit **1801项通过**（2个既有弃用warning），相关合同回归170项通过；Ruff与diff-check通过。

## 历史CI（仅背景，不作本轮验收）

| 工作流 | run / attempt | P0查询状态 |
|---|---|---|
| 主CI | [39785757520](https://github.com/sssssssssh/ssh_stock/actions/runs/39785757520) /1 | failure；Core/Lookup/audit成功、capacity跳过、release失败 |
| A4-1 | [39785757699](https://github.com/sssssssssh/ssh_stock/actions/runs/39785757699) /1 | success |
| A4-2 | [39785757493](https://github.com/sssssssssh/ssh_stock/actions/runs/39785757493) /1 | 未全部结束 |
| Publication | [39785757491](https://github.com/sssssssssh/ssh_stock/actions/runs/39785757491) /1 | success |

本轮新CI保持Core与独立npm audit；lookup只重算历史、另产当前拒绝收据，不启动新100次试验。
Release工件记录CAPACITY_NOT_AUTHORIZED及HISTORICAL_EVIDENCE_ONLY/P95_REGRESSION/
CORRELATED_NOT_CAUSAL/NO_APPROVED_REPAIR_CANDIDATE/PRODUCTION_NOT_VERIFIED_CANDIDATE。

## 变动与遗留

新增离线复核脚本/测试/证据/协议/ADR，最小增加CI拒绝原因；不更改审计有效性定义。
README/PROJECT_RULES/PRD/系统设计同步本次条件阶段未授权状态；不覆盖历史A4-2.2失败证据。
没有backend/config/migrations/frontend改动，无生产反向diff可应用；未来任何部署/停止Writer须另行批准。
现有A4-2 Q1/Q2历史读取性能仍OPEN；B写前lookup优化不代表它已关闭。
旧审计all11/prod4漏洞未修复；新数量以本轮同SHA合法报告为准，不用历史填补。
阿里云资源未实测，不要求升级服务器；暂无独立Runner不改为购买或借用业务ECS。

本任务没有读取业务.env，没有连接或修改阿里云业务数据库/生产数据/业务任务；
未改变GC设置、P95标准、SQL/发布预算或AB_MERGE_READ_ENABLED=false。
前一任务已披露的早期本地dotenv偏差是历史事实，本任务不重写它；本次开始即避免该路径。
