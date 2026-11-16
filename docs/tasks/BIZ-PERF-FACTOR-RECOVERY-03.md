# FACTOR-RECOVERY-03：Worker可靠性与候选写入业务链路离线复现

## 执行基线与中心目标
用户唯一中心目标：让ssh_stock使用已存Raw重新计算因子、完成候选生成与原子发布，不再卡死，且实际性能瓶颈获得证据与改善。前一轮02-CI-R2修复已推送master SHA 232baf9e13cd7b23731e59188c86e0e253c3a394；经外部独立查询2026-11-16四项同SHA CI均completed/success：主CI 43771443208、A4-2 43771443183、A4-1 43771443164、Publication 43771443115。工程CI通过不代表真实PG/Worker可用。

## 开始前
在S:\work\project\ssh_stock、master、原GP持久会话执行。先git status --short --branch、HEAD/origin/master，核验GitHub master，再按AGENTS.md顺序读五治理文件及相关业务文档；保留两份未跟踪W05审计/任务文件，不能覆盖或清理。确认没有另一个同任务Codex CLI在运行。阅读前轮 docs/acceptance/BIZ_PERF_FACTOR_RECOVERY01_CLOSEOUT.md 与02/R2验收、实际源码、测试；如文件名不同先搜索定位。不得因为旧任务文本而误重做01/02。

## 本轮唯一任务
1. 精确追踪因子计算入口、job claim、Worker心跳/取消/失败回滚、已有Raw复算、候选批次去重、发布、查询的实际代码路径，识别一个最直接的未解决P0阻断或可复现性能热点。重点看Worker卡死、领取/取消竞态、批量候选重复查询；不把已回退的data_publication单SQL优化重新应用。
2. 使用不接触外部PG/Worker/网络的纯离线mock或现有fixture构造RED反例，记录原始错误/调用次数、输入规模、重复执行是否幂等；没有证据不能假定根因。优先修复导致任务无法结束/结果不能正确发布的问题，其次修复真实可证明的候选写入N次查询热点。
3. 仅在已复现且不涉及冻结文件/旧源码摘要合约的情况下，做最小范围代码修复（最多两个业务源码文件和两个测试文件），RED→GREEN，验证取消/失权/异常、原子发布/结果一致性/身份/PIT/Decimal、查询计数。修改前特别核对历史R1固定源码hash合同；如生产源码一改就必然导致旧冻结合同失败，停止并提出兼容方案，不篡改历史hash/测试/安全插件。
4. 若缺少足够离线证据，交付精准阻断定位与下一步受控测试计划，而不是泛用工具或文档循环；允许只读分析，不允许扩大范围。

## 严格安全边界
不得连接用户生产或业务PG17、不得运行真实Worker、迁移、DDL、SQL、数据删除或原始数据重拉，不得启动云资源或正式性能实验。不得修改Raw/Derived、业务阈值、S0-S6、PIT/Decimal、冻结五件、CI工作流、a42331插件或依赖。B_GATE/TARGETED_PG17_GATE=NOT_APPROVED。不得用CI success宣称实际因子计算已成功。

## 交付
只修改明确白名单内的最小业务文件/单测；生成 docs/acceptance/BIZ_PERF_FACTOR_RECOVERY03_CLOSEOUT.md（含真实调用链、RED/GREEN证据、变更清单、测试命令与结果、性能前后计数、风险、仍缺的真实验收）。运行定向pytest、相关纯离线回归、ruff（环境允许时）、git diff --check。保留原有未跟踪文件。不提交、不推送，等待ChatGPT独立审阅。回执写明BASELINE_SHA、ROOT_CAUSE、TESTS、CHANGED_FILES、REAL_FACTOR_RUN=NOT_RUN、NEXT=CHATGPT_REVIEW。
