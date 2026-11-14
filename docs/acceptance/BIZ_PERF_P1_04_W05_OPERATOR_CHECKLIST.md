# W05 单次隔离试验操作员待批清单

2026-11-14；沿用 [PRETEST申请草案](BIZ_PERF_P1_04_ISOLATED_RUN_REQUEST_DRAFT.md)。
结论固定 `OWNER_SIGNOFF_PENDING`。这是一份待填写清单，无启动/删库命令、执行脚本或许可。
`ROOT_ATTEMPTS=0 / AUTHORIZATION_PENDING / BUDGET=DRAFT_NOT_APPROVED`；
`B_GATE=NOT_APPROVED / TARGETED_PG17_GATE=NOT_APPROVED / HOTSPOT=NONE_PROVEN`。

每个具名字段由负责人/独立核验主体另行填写，不能把本会话执行者、机器、任务书、
离线自检或普通 CI 当成真实操作授权。审批自述、签名字符串与 permit 均不构成可信凭证。

## PREPARE：资源、输入、费用与主体

| 待填项 | 当前值 / 必须独立核对的证据 |
| --- | --- |
| 负责人姓名 / 批准引用 / 签认时间 | OWNER_DECISION_REQUIRED；须新的明确用户请求，不由本清单生成 |
| 唯一操作人姓名 / 机器 / 具时区窗口 | NOT_VERIFIED；不得自动填当前用户或主机 |
| 独立审阅人 / 验收人姓名与职责 | NOT_VERIFIED；核对真实来源及独立性 |
| 最终实施SHA / worktree / CI / 审阅 | NOT_VERIFIED；精确SHA主CI/A4-1/A4-2/Publication的run/attempt/Job/Step，skipped不表示性能通过 |
| config / strategy / business / dataset / 逐表 fingerprint | NOT_VERIFIED；提供内容来源、生成方式、逐表行数和摘要，不能用自述hex证明内容 |
| 唯一run UUID / 租约 / 单次消耗主体 | NOT_VERIFIED；只允许一次根，失败/超时同样消耗，不补样或重试 |
| 全新Linux x86_64实例 / PG17版本 / 镜像digest | NOT_VERIFIED；禁止既有PG17、旧测试库或生产资源 |
| UUID marker / offline与online system_identifier | NOT_VERIFIED；实际物理身份观察及时间，不能只复制marker或自述JSON |
| 专用独占PGDATA / 卷 / 网络 / cgroup / owner / lease | NOT_VERIFIED；核对新建、专用、独占、唯一租约和清理范围；环回地址不足以证明隔离 |
| 输入与开关固定 | 草案：8股、2025-01-01～01-31、一个根、900日历日合成seed；五开关false。交易日/PIT、250/430、500行候选批、300秒发布及原子语义不变 |
| Seed与预热核验 | NOT_VERIFIED；931日历条目/665合成weekday/5320股日仅静态规则，逐表真实生成与因子/派生/后验quality摘要待核验；不冒充真实交易日 |
| CPU / 磁盘 / IO / 内存 / 导出 / 停止阈值 | OWNER_DECISION_REQUIRED；草案Worker3GiB/PG4GiB/卷10GiB/证据10MiB；CPU配额不能用累计CPU时间替代 |
| 成本承担人姓名 / 币种 / 金额上限 / 付费范围 | OWNER_DECISION_REQUIRED；不自动填资金来源或金额 |
| 外部停止控制人姓名 / 失联和失败处置 | OWNER_DECISION_REQUIRED；未知ACK或所有权漂移停止，人工介入 |
| 原始脱敏证据保管人 / 位置引用 / 留存期限 | NOT_VERIFIED；不得提交凭据、生产数据或私有连接信息 |

**拟议计时**：新资源创建、seed、迁移及预热是否包含在20min内均为 **UNDECIDED**。
每项必须勾明“计入”或“单列”、预计时长、独立上限、责任人及成本；不能省略seed/预热，
也不能因为它们在root之外就默认免费。若全部计入，准备耗时会压缩<15min的root及post窗口。
若单列，单列期限必须覆盖在操作窗口和费用批准中，不得增加root尝试次数。

## MEASURE：一次根、原始证据与停止

| 待填项 | 当前值 / 核对要求 |
| --- | --- |
| 单次启动核对人 / 时间 / run UUID与SHA | NOT_VERIFIED；所有前置缺项则拒绝；此表无执行入口 |
| create/claim前根起点、Worker调用与finally返回终点 | NOT_VERIFIED；root包含Worker，分别记录，不相加 |
| 原始事件前缀 / seq / UTC与单调时间 / root/run身份 | NOT_VERIFIED；先保留脱敏原始证据，再读回验证和派生摘要 |
| SQL次数/execute、driver FETCH行数与时间、CPU/RSS及阶段覆盖 | NOT_VERIFIED；root SQL总时长当前缺测保持UNKNOWN；inclusive和SQL/FETCH可能重叠，禁止求和冒充独占份额 |
| 停止确认人 / 原始失败证据 | OWNER_DECISION_REQUIRED；超时/失败/取消/身份漂移/预算越界/UNKNOWN_ACK均停止；不补样、重放、恢复或释放占用 |

**拟议计时**：root计入20min且严格<15min；准备（若计入）+root+post合计须<15min，
末5min保留清理。实际时间来源、外部中止控制、预算强制和可信证据均尚未实机验证。
本轮不运行真实SQL/EXPLAIN、因子、Worker、Scheduler、容器或性能采集。

## VERIFY：root冻结后独立核验

| 待填项 | 当前值 / 核对要求 |
| --- | --- |
| 验收人 / post开始结束 / 证据来源 | NOT_VERIFIED；独立于已冻结root，不修改Wall/CPU/SQL/FETCH根快照 |
| Job SUCCESS / PUBLISHED / ledger / source / 当前身份 | NOT_VERIFIED；失败或未知不能伪装为空结果、成功或旧身份 |
| 逐表行数/摘要、公开结果、质量及无B泄漏 | NOT_VERIFIED；固定同根同SHA同run，不跨根拼证据，不猜测派生行数 |
| 原始前缀完整性 / 留存回执 / 缺测与失败 | NOT_VERIFIED；缺失字段UNKNOWN/NOT_INSTRUMENTED，不填0；真实输出需独立核验 |
| 允许报告的结论 | 只调查8股五OFF一根的方向；没有多样本，不报P95/P99、提速、容量或生产资格；不归因未启用的FactorInputWindow._verify |

**拟议计时**：post计入20min及cleanup前窗口，单列计时但排除root。
不能挪入最后5min或用root/Worker/阶段重复加总。具体post预算仍OWNER_DECISION_REQUIRED。

## CLEANUP：本次归属与人工结束

| 待填项 | 当前值 / 核对要求 |
| --- | --- |
| 清理负责人姓名 / 窗口 / 权限引用 / 目标清单 | NOT_VERIFIED；仅限独立证明归属的本次新资源，不能扩大到已有库/卷/主机 |
| 清理前物理身份/owner/lease再核验 | NOT_VERIFIED；必须与准备阶段相符；声明匹配不等于实际安全 |
| 失败、失联、身份漂移、UNKNOWN_ACK人工处理人 | OWNER_DECISION_REQUIRED；记录CLEANUP_BLOCKED并停止，不自动删除、释放或再次启动根 |
| 结束观察 / 费用终止 / 原始证据保留 | NOT_VERIFIED；分别记录实际结果和观察时间，清理失败不能记COMPLETE；不删除失败证据或占用历史 |

**拟议计时**：cleanup计入20min，末5min专用，目标总期限≤20min；提前结束也不续期。
如身份或ACK不确定，停止自动动作并由具名人员裁决，不能为满足时间目标越过归属证明。
清理主体、能力和失败后的人工期限仍OWNER_DECISION_REQUIRED；本轮没有真实清理动作。

最终结论：**OWNER_SIGNOFF_PENDING**。下一步仅ChatGPT独立审阅与负责人决定；
必须新的明确用户授权，才可另行评估真实执行条件。填写清单本身不能产生permit或改变门禁。
