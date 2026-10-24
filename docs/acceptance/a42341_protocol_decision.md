# A42341 协议决策记录（不是用户批准记录）

状态：**PROPOSED / USER_APPROVAL_PENDING**。
Effective protocol：旧v2，总8次、BLOCKED；开发授权只覆盖新提案、纯模拟和低成本合同。

| 路线 | 待决定的内容 | 当前状态 |
|---|---|---|
| A | 至少16次，四进程/128点/原查询路径不变；16仅条件式下界，不足时另议预先冻结的上限 | 推荐提案，未批准 |
| B | 保留8次，接受cold→prepared混合态，重新确定估计目标和分层可比性，放弃同prepared稳态结论 | 研究备选，未批准、不可用于当前模拟资格判据 |
| C | 原v2及真实执行继续阻塞 | 默认安全状态，不等于用户已否决A或选择B |

两道人工门互不替代：①明确批准协议/预热预算；②工具验收后，单独批准真实实验exact SHA、
未消费profile/token、物理fixture/角色/CPU/计划能力、资源预算与Environment真实审核。
本轮不实现这两道门的授权消费，不接受环境变量、普通push、旧token或单元测试绿色代替任一道门。
开发/提交/推送许可也不表示用户已批准预热提案或真实测量。

新提案：v14_a4_2_3_4_calibration_protocol_v3_proposal.md。
清单：a42341_preparation_manifest.json，SHA256 4cca8088909821371f99d8cd9dba450d2fa6ada4c6dbc462ccd8ec64498a163e。
协议本地冻结提交的完整SHA、协议字节SHA将在编码前取得，并追加到新closeout记录；旧记录不回填。
若尚无Git提交授权则停止在协议草案，不把代码开发顺序要求当作自行提交/推送许可。
