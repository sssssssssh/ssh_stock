# A4234 准备交付：用户确认8次总预热后的能力阻塞

状态：**BLOCKED_NEEDS_SPEC_OR_CAPABILITY**，不是READY或PERFORMANCE_PASS。
基线5215145152ae732fdba2cc5104c022eb0bed2618；master，开工HEAD/origin/master/远端一致且干净。
本轮未读取业务.env、连接业务/阿里云数据库、修改运行任务、启动本地API/Worker/Scheduler。
未新建实验库或装载5000×20数据、未执行真实预热/2000键lookup/128次校准，也未dispatch昂贵任务。

## 1. 冲突与静态证据

用户最新裁决：“**全批共8次，能力不足则标阻塞**”。当前协议v2据此冻结，不增加到32或16。

| 项目 | 可复核事实 |
|---|---|
| 新进程/模板条件 | 4个独立进程 × C0/C1 = 8；prepared缓存不跨连接共享 |
| 用户预热总量 | 8，均无Observer；每block仅C0/C1各一次 |
| 一次完整lookup | 2000键 / 500批 = 4次批调用，非空批只有1条lookup SQL |
| 锁定driver | psycopg 3.3.4；prepare_threshold=5、prepared_max=100 |
| 实际纯缓存合同 | 前5次Prepare.NO，第6次Prepare.SHOULD；未连接数据库 |
| 每条件预热SQL数 | 1 × 4 = 4，尚未创建prepared；第一个正式pair仍会过渡 |
| 算术必要下界 | 每条件ceil(6/4)=2次完整预热，合计16；**不保证**generic/custom计划稳态 |

证明来自冻结workload的mock分批、生产_lookup_batch AST单execute、已锁定driver的纯Python
PrepareManager.get/maybe_add_to_cache。mock不调用真实lookup/SQL，缓存合同没有cursor/connect。
八次重新分配也不能让八个条件均获得至少两次；共享连接违背独立进程，提前同模板探针/强制prepare/
改threshold/用正式样本充预热均是未经许可的条件变化。因此在数据库/预热/采样之前停止。
错误码A4234_PREPARED_WARMUP_BUDGET_INSUFFICIENT；guard即使模拟身份/权限全部正确也返回阻塞。
它不是“8次测过性能不好”的结论，本轮没有性能数值、对比或唯一修复候选。

## 2. W00–W07 分项

| 工作包 | 状态与边界 |
|---|---|
| W00 | DONE：同SHA旧CI/ZIP摘要/内部JUnit/Observer严格离线复核；新增a4233_1_final_review.md，不覆盖旧PARTIAL |
| W01 | DONE（阻塞协议）：v1先于代码本地提交；用户确认总8次后另提交v2，保持历史，不执行任何版本 |
| W02 | PARTIAL：本地文件/Git/依赖/模型核验、typed模拟物理/权限、无条件拒绝入口；可信真实fixture/权限未重证，不能宣称完整guard ready |
| W03 | BLOCKED：仅样本身份/顺序定义；无runner、适配器、资源/GC记录器、128点模拟成功包 |
| W04 | BLOCKED：探针/漂移检查只冻结未来要求；不调用旧statistics_snapshot/plan_snapshot或维护助手 |
| W05 | BLOCKED：无校准Reviewer、无PASS_CANDIDATE，统计门槛只在协议中定义，未实测应用 |
| W06 | PARTIAL：仅本阶段已实现能力的unit/静态治理与原合同回归；不声称全部18类校准用例完成 |
| W07 | 阻塞交付：四权威文档/工作流索引/本报告更新；最终SHA与推送后CI在本轮回执提供 |

未实现W03–W05不是用额外功能替代任务，而是用户确认的能力不足停止线。后续需新任务审阅后继续。

## 3. 冻结身份与提交顺序

- 协议：docs/acceptance/v14_a4_2_3_4_calibration_protocol.md；SHA256
  b22df81e1e439a5109dc6a92c929adbfa7ac0384f1d3a1c4bd33ec4f65677b96。
- 清单：docs/acceptance/a4234_preparation_manifest.json；SHA256
  4ceb7149357ac7a91a48eda1407d0d621b7ca24f256f417e8e4e8ba35052947d。
- 输入仅定义2000键，未装载；字节SHA918104253d18ad21629323befc4d2d2c198ca71a56629ca577b4ca1a9cb58e9a。
- 模型/迁移/配置树、SQL模板、依赖及旧脚本摘要在manifest；source摘要从两份新脚本字节重算。
- A：fb10b2e（W00/v1），6b92c8f（明确CPU分母），b4b07c4（用户总8次v2）；均未测量、未推送刷CI。
- B：843d996（离线contract/guard，非可执行校准工具）；C测试/索引本地提交后最终**一次push**。
  最终40位SHA/同SHA实际CI链接以推送后回执为准，不为回填本文再推一次触发主CI。

## 4. 数据/权限/CPU 可行性（不冒充现场证明）

上一轮已有双物理身份PG17、受限observer微型合同和三ticks的真实CI证据，见
[A4233.1最终记录](a4233_1_final_review.md)。它不能替代下一轮新fixture/精确SHA/run/attempt的证明。
当前typed物理证明只校验模拟loopback、UUID归属、PG17、marker/system ID和角色权限约束，
不获取真实DB状态，不信任输入自述为现场批准；始终physical_verified=false。
无DML/DDL/MAINTAIN/信号/业务行权限、不提权，不修改SQL/字段白名单或v1/v2解析。

backend CPU为**METRIC_UNAVAILABLE**：旧backend_snapshot可读容器进程资源，但当前没有核验本轮
PID/backend_start/proc starttime/clockticks及完整生命周期对应；不能填0、用SQL wall替代或宣称校准合格。
新observer窗口是否能保持2..8ticks包围、整worker CPU、自然GC/RSS/异常工件等均NOT_RUN/未实现。
现有statistics_snapshot含pg_stat_clear_snapshot、plan_snapshot含EXPLAIN EXECUTE计数副作用，
不直接借用它们作为无扰动入口。正式物理/角色/CPU可行性仍需解决阻塞后的独立设计审阅。

## 5. 低成本合同覆盖与未执行矩阵

| 验收项 | 本轮状态 |
|---|---|
| AT01 | 旧同SHA真实证据已独立复核与归档，未重跑旧实验 |
| AT02 | 纯定义128点/64对顺序、分组与8次总预热SHA测试；不执行lookup |
| AT03 | PARTIAL：顺序生成冻结；未实现Reviewer拒绝路径 |
| AT04 | PARTIAL：替换协议/输入/源/model/依赖/HEAD/attempt/双身份拒绝及本地树核验；真实fixture待证 |
| AT05 | 硬拒绝execute/approve/force/repeat/预算/旧profile；伪造环境与token也不能执行 |
| AT06、AT07、AT08 | BLOCKED：无耗时统计/inclusive Reviewer/backend CPU校准判定，不伪造通过 |
| AT09、AT10、AT11、AT12、AT13、AT15 | BLOCKED：新适配/记录/漂移及资源失败合同未实现；旧Observer合同保持，不当作新校准覆盖 |
| AT14 | PARTIAL：JSON重复键/NaN/Inf/缺失/符号链接/过大文件拒绝；无校准bundle schema/reviewer |
| AT16 | 保留原v1/v2及A4232/治理测试并运行回归；新代码不改旧字节 |
| AT17 | 生产/旧脚本/旧证据/policy/consumed/五工作流/Gate全部冻结，合同静态核对 |
| AT18 | 推送后等待最终同一SHA主CI、原A4233和新unit；不能提前标SUCCESS |

本机只运行unit/static及Ruff/diff，未新建数据库，未本机运行完整含PG集成的pytest。
实际本机结果：新增109项全部通过（4.75秒）；全部unit为2269 passed、5 warnings（33.32秒）；
Ruff覆盖backend/tests/migrations/scripts/.github/actions，exit0；diff --check，exit0。
开发中首次新合同106 passed/1 failed：新增CI检查按子串误选pytest步骤，触发KeyError；已改为精确
模块命令定位，保留always/计数断言，随后加入两个拒绝用例并验证109通过；没有真实测量或刷性能PASS。
完整pytest、迁移current=heads、前端/浏览器/Worker/容器原检查交由未改动的最终SHA主CI；
专项原有微型PG17合同仍沿用，不调budget、不删用例、不降低70%门槛。实际计数见本轮最终回执。
专项新增收据a4234命名空间为.codex_tmp/a4234/tests.json，仅计数/固定错误与字节摘要；
COMPLETE_CONTRACT仅表示这些unit成功，内部preparation仍BLOCKED，physical_verified=false。
收据绑定HEAD/run/attempt且拒绝覆盖，失败仍exit1，缺JUnit/写盘失败不伪装成功；原始异常文本不上传。

## 6. 下一阶段申请与停止

保持用户总8次约束，先审阅“同prepared状态/四独立进程”在此预算下的可证明方案；
若无兼容方案，继续BLOCKED。若要改变其中任何条件，须由用户另行明确修订协议和预算，
不能由开发者把16次算术下界当作充分性/预热授权，也不能直接启用测量。
解除设计冲突后仍需完成W02余项、W03–W05、完整AT矩阵和新同SHA验收；本轮不申请直接执行128次。
未来真实实验还要新profile、未消费一次性token、精确SHA、独立批准与真实Environment审核；现阶段均NOT_AUTHORIZED。

Calibration run: NOT_RUN_NOT_AUTHORIZED。Historical A4231/A4232: UNCHANGED / INSUFFICIENT_EVIDENCE。
execution_enabled / performance_eligible / capacity_ready / production_read_authorized / attribution_authorized:
**false**。unique_repair_candidate: **null**。到此停止，等待人工代码/协议审阅。
