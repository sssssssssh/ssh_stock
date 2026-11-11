# R1 D04 业务 owner 决策表 V1

当前状态为 `OWNER_DECISION_PENDING`。每项填写选择、理由、原始证据引用和失效处理。
提交给业务 owner 的数据为静态合同及 V2 独立草稿。业务签认及独立复核须由对应人员完成。

基线 `f7d8e264041db4f7d5600e1ce5b2bbd6b7ff0345`，历史 seed 合同
`b6ffb7bf8ec7d26f771d9b89923e4f7e926edbed`，V2 草稿来源提交
`997f0a26f259424e3c566bff96bcae407e69f674`。

证据入口包括[九项请求](r1_d04_decision_request_v1.json)、[49 列库存](r1_d04_timestamp_inventory_v1.json)、
[冻结 schema](r1_business_compare_schema_v1.json)、[W04 就绪报告 §7.2–7.5、§10](BIZ_PERF_03_A_R1_LNX_W04_READINESS.md)、
[原 seed 配方](../../scripts/r1_seed_snapshot_recipe.py)和
[V2 草稿与场景说明](../../tests/fixtures/r1_reviewed_snapshot_v2/README.md)。

| 方案 | 待确认解释 | 需审阅原始证据 |
| --- | --- | --- |
| A，一次原 seed 快照后双加载，建议待签 | 允许改变输入准备顺序，保留两股、420 日、请求窗、预热和原策略 | 同一原快照及两臂实际加载摘要、原值/NULL、ID、自然键、序列、生成器及原业务 source hash |
| B，逐臂 seed 与显式映射，备选待签 | 两臂独立原始字节分别登记，按明确规则审阅语义对应 | 每臂原字节摘要、原业务 source hash、逐列 UTC 微秒时间、事件域、自然键、双射、顺序与复制闭包 |

| ID | 业务决策与未决处理 | 选择 | 理由 | 原始证据 | 失效处理 |
| --- | --- | --- | --- | --- | --- |
| D04-01 | A 或 B 单选。未选时保持输入等价待证 | | | | |
| D04-02 | 逐项确认五列实际原值、NULL、精度及默认值生成语义。缺证登记 UNKNOWN | | | | |
| D04-03 | 逐行签认 49 列角色与 UTC 微秒事件策略。业务日期另列，C11 待决 | | | | |
| D04-04 | 所有输入序列及生成器状态，缺项则 G05 MISSING | | | | |
| D04-05 | 原始字节与 canonical 语义证据、业务 source hash 原样保全 | | | | |
| D04-06 | 域、自然键、多重集、双射与排序，复制或身份歧义保持 NO_GO | | | | |
| D04-07 | 逐例审定 C01～C16 的演示语义，记录金融真值证据缺口 | | | | |
| D04-08 | 逐项列出 37 表/520 列中只有静态结构合同的范围及真实原件缺口，G09 PARTIAL | | | | |
| D04-09 | 决策主体、版本、独立复审及失效触发。改选方法、schema 或来源版本需重新审阅 | | | | |

| 五个 seed 时间列 | 原值或 NULL 证据 | 原精度、时区和生成语义 | 审阅意见 |
| --- | --- | --- | --- |
| data_quality_daily.checked_at | | | |
| stock_basic.updated_at | | | |
| stock_daily.source_updated_at | | | |
| stock_limit_daily.created_at | | | |
| stock_limit_daily.updated_at | | | |

逐列回复须附上对应库存表列键、原始证据引用和确认的策略。运行时事件单独记录 UTC 微秒值、
NULL 性、域内顺序和重复次数，并核对 Job UUID 到发布与 metadata 的引用、执行 token 复制、
ledger `published_at` 到 Job metadata publication 时间的复制关系。交易日与快照日保留原业务语义。
输入序列至少覆盖 `data_quality_daily.id`、`sector.sector_id`、`sector_member.id`，
各自记录 `last_value`、`is_called`、`increment`。生成器提供算法和状态摘要或原 seed 无随机调用的证据。

本版 JSON 可供审阅两类提案结构。A 两臂声明同一原始摘要，B 两臂分别声明原始摘要，
并提交五个带静态来源引用的有序事件域样例。两类都须登记相同的原业务 source hash。
这些是有限长度的提案槽位。完整行级映射、自然键和复制闭包须另附原始证据供人工复核。

| Case | 草稿语义与待审边界 | 业务意见 | 证据引用 |
| --- | --- | --- | --- |
| C01 | 正常发布投影，ma20=1.25 为虚构类型探针 | | |
| C02 | 失败终态与保留原像 | | |
| C03 | 取消终态及原有发布边界 | | |
| C04 | 未知 ACK 保持 INCOMPLETE | | |
| C05 | 候选 base 保留首次 preimage，虚构投影 | | |
| C06 | tombstone 的 SQL NULL、原像保留及公开行缺失，虚构投影 | | |
| C07 | 同一自然 scope 的多重集、UUID 顺序、ordinal 和范围 | | |
| C08 | FK 与非 FK JSON 中的 job/token/sector/theme 引用闭包 | | |
| C09 | Decimal scale、有限 float、带符号零、bool/int 区分 | | |
| C10 | SQL NULL、JSON null、缺失、空串、空数组、0 和 false | | |
| C11 | 事件策略 EVENT_MAPPING_UNDECIDED | | |
| C12 | 迁移、schema 与序列缺证，INCOMPLETE | | |
| C13 | 范围外摘要变化，INCOMPLETE | | |
| C14 | 两臂同值仍可能与独立草稿不符，UNEQUAL | | |
| C15 | 来源漂移，INCOMPLETE | | |
| C16 | 清理不确定，INCOMPLETE | | |

完整业务 Golden 需独立审阅真实 typed/original 导出、全表列及嵌套路径、金融计算预期、
跨臂源身份和物理清理。上述草稿案例的精确意义和失败码以 V2 原始 Oracle 为准。
V2 基础草稿涉及 Job、publication/source/row/preimage/scope、factor 公开行和虚构类型探针。
实际投影以各 case 的 `columns` 和 V2 合同为准。冻结 schema 中其余表列及嵌套路径仍需
逐项登记真实 typed/original 证据，包括未在案例投影出现的输入数据、派生表和范围外表。

| 角色 | 签认主体 | 证据版本及摘要 | 签名 | 签认时间 |
| --- | --- | --- | --- | --- |
| 业务 owner | | | | |
| 项目负责人 | | | | |
| 独立 reviewer | | | | |

结构检查结果固定保留 `NO_GO` 与 `NOT_AUTHORIZED`。当前 R1、历史 AC-05 均为 PARTIAL，
G05 MISSING，G08/G09 PARTIAL，G1 NOT_AUTHORIZED。业务决定之后，仍需分别审阅后续开发与真实执行授权。
