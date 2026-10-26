# A42363 集中整改：实现边界与接口

状态 ENGINEERING_BLOCKED。接收器可在受信对象/FD 合同下运行，并不表示已安装、实机通过。
保持既有26方法、LocalService、固定16条 probe SQL 和默认 session_method 拒绝。

| 域 | 入口与受信来源 | 独立读取与失败行为 |
|---|---|---|
| A registry/approval | ServiceHost，安装策略+外部签名/双审批 | 原审批/撤销表；TTL、签名错误拒绝；不自签 |
| B consumer | ConsumerService+PostgresConsumer，签名绑定全 payload | 原子消费后新连接读；ResourceLedger 新连接确认每个事件；未知提交不退款 |
| O pg_owner | OwnerRuntime+RawOwnerBackend，动态 FixtureIdentity+专用 Owner 连接 | libpq 原始 host/db/user/version、runtime inspect 和 pg_control_system；新 store reader |
| C controller | ControllerService+RecoveryEngine，B 账本及独立 C journal | CREATE_SCOPE_ATTEMPTED 在首个事件前；CREATION_KIND 保存原ID/SHA/epoch；首错独立持久 |
| D supervisor | SupervisorService+RootManager+Guardian，受信 cgroup FD | 终止→TERMINATION_PROVEN→PUBLICATION_ATTEMPTED→fsync→TERMINATED；不确定禁止二次发布 |
| E absence_auditor | IndependentObserver+DelegatedReadOnlyCollector，root 委托 namespace/store/code FD | 单次 visibility 后才可读；8观察前中后复核 C/B；UNKNOWN不等于ABSENT |
| Reviewer | ReceiptSet 的六个独立源 | 回取原始 receipt、原始创建身份与错误；最多 OFFLINE_CROSS_DOMAIN_VERIFIED |

新增 InstalledFDDocument 只读入口核对 root-owned/single-link/只读 FD、内容摘要、
Scope/epoch/source/TTL 与精确 capabilities/code 摘要；compose_installed 核对当前 UID、
对象的 FixtureIdentity 后调用原 compose，不提供 CLI/env 开关、不创建 socket/服务。
它是管理员提供合法 FD 后的校验接口，不是安全安装程序，也不能证明 Python 对象由该
代码生成。受信 root manager、包供应链和对象装配仍是独立安装前提。

固定命令（包括短 inspect）仍必须通过 CgroupScope；分配 FD/fork 失败闭合释放；
未知 fork/终止不能取消 Guardian，改用 abandon 触发原 held kill FD。bounded_child
只管理自己仍未回收的子进程，不作为全部后代退出证明。父退出 Guardian EOF 也触发。
L1 普通文件写入不是 cgroup.kill 实测。真实 cgroup 创建/安装不执行。

生命周期固定：RESERVED→CREATE_ATTEMPTED→OBSERVED_CREATED；反向 REMOVE_ATTEMPTED→
OBSERVED_ABSENT，异常为 UNKNOWN。C 保存原始创建事实，ACK不确定后不能用新对象替换。
恢复重读首错/清理错；已发送删除只向独立 E 问原目标状态，不重发 remove。
PgFixtureRuntime 对持久 START/STOP_ATTEMPTED 恢复拒绝重放，成功 stop 回用原收据。
Owner审计要求真实 raw 字段、顺序 PG 状态和当前 running+healthy，不接受自填身份 hash。

当前可机读差异由 scripts/a42363_installation.py::capability_matrix 返回。
bootstrap_image 和 safe_volume_disposal 为 NOT_IMPLEMENTED，不能以“仅缺审批”遮蔽。
