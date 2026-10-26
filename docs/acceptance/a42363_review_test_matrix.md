# A42363 审查矩阵：60项逐项映射

“合同”指新增/原有L0或文件SQL模型；“Linux限界”指普通CI Linux进程行为，
不是cgroup/Podman实机。旧4590case不改字节，全部保留，新数只以最终CI为准。
新增文件：unit/test_a42363_review.py、unit/test_a42363_review_guard.py、
integration_offline/test_a42363_review_process.py；旧完整进程/guard/签名/身份测试继续执行。

| AT | 证据/限界 |
|---|---|
|01|baseline记录master/origin/a8、clean|
|02|review_guard六份历史manifest及各收口commit的pin|
|03|原full FD/index/中文NUL/symlink/race负例保留；全HEAD扫描|
|04|新exact STAGE_PATHS+新增未登记/缺项负例|
|05|原Reviewer fake joined/cleanup负例保留|
|06|基线已import re；新增两正向模型确认非NameError|
|07|Secret/Container合法ID模型删除、执行非零/异常稳定错误|
|08|ID/epoch/标签/名称漂移不删除|
|09|Volume有ID SAFE_DELETE_UNPROVEN；无ID REMOVE_ID_REQUIRED细化|
|10|Volume实际rm0；物理机制NOT_IMPLEMENTED|
|11|原FixtureIdentity派生合同+新全链一致动态身份|
|12|原身份漂移前置拒绝保留|
|13|原9>8无副作用拒绝|
|14|新增独立17>12成本拒绝|
|15|BootstrapProposal明确计入image/initdb/HBA/认证；非executor|
|16|独立bootstrap ADR A/B，P95 NOT_MEASURED|
|17|新增伪Owner无raw/健康拒绝，原健康/缺安装合同|
|18|持久phase/stop成功回放无需inspect|
|19|原start ACK未知不重放|
|20|原stop ACK未知不重放，新增stop已提交复用|
|21|原role raw负向合同+新owner_acl全链；不是实际ACL验收|
|22|新真实OwnerRuntime类进入Host O，动态SQL/连接身份模型|
|23|原lease v2不含backend_start|
|24|原postconnect漂移测试保留|
|25|新ApprovedMethodStub反向入口拒绝、原lease/Worker首SQL阻断|
|26|候选406bytes/OIDs/null/type/continuity+旧templates不改|
|27|GUC ADR新版本/旧token拒绝；方法仍无条件阻断|
|28|原真实Ed25519向量、撤销/TTL测试原样执行|
|29|原B并发合同+新跨进程独占消费/ACK不退款重放|
|30|同文件payload+receipt事务；新read独立open、B账本新连接|
|31|新runtime.create验证原B已提交CREATE_ATTEMPTED|
|32|原create非零前拒绝inspect测试保留|
|33|新4资源×4创建中断点+跨进程4createACK|
|34|新4资源ABA/原始C identity不覆盖|
|35|新4资源×4删除中断点+跨进程4removeACK；不重发|
|36|原Socket FD/marker/inode/权限模型，Linux分支CI执行|
|37|新增首错持久与错误优先；旧预算不改|
|38|原PGstop失败仍安全反向恢复合同|
|39|原E不同UID/namespace/store；新全链错store|
|40|新未visibility不能直接read；FD安装合同|
|41|原E双轮8观察；新完整正例8观察|
|42|新增末轮后C变化拒绝；原中途B/C变化合同|
|43|原E 125/空输出/权限拒绝；新permission全链|
|44|E独立journal/read新进程，file DB_MODEL_ONLY|
|45|原cgroup fstatfs普通文件拒绝；物理NOT_RUN|
|46|原attach-before-exec合同，物理NOT_RUN|
|47|原Linux setsid/pidfd限界不认证cgroup终止|
|48|原外部PID拒绝/owned child；不引入调用者PID|
|49|新增Guardian abandon/父死亡/分配失败FD关闭|
|50|原stdout/IPC/fsync超时保留incomplete；原Linux分支不skip|
|51|新增publication持久不重放/完整链artifactfsync顺序|
|52|原所有FixedCommandRunner均要求CgroupScope|
|53|原26方法ACL/schema；新6Host+精确安装FD正负合同|
|54|新六域各自进程独立源读取；原forged reference负例|
|55|新signature/peer/E/Owner/Root/forged_source等全链失败|
|56|新Orchestrator→六Host→Source ResourceLedger→六源Reviewer完整正例|
|57|所有基线test blob相同；最终CI JUnit旧case集合逐项包含|
|58|最终SHA CI与ZIP下载审计在交付报告，不能用历史run|
|59|不运行G1/L2，G2=8/G3未授权，资格false|
|60|三独立ADR+机读差异+ENGINEERING_BLOCKED|

测试报告区分源缺陷RED、测试模型编码错误、平台能力缺失和最终GREEN，不丢异常样本。
不得把表内合同覆盖写为全部物理PASS；NOT_IMPLEMENTED/审批/安装/未运行分别保留。
