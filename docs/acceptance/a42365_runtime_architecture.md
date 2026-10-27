# A42365 运行入口、权限与安装缺口

结论：PARTIAL_ENGINEERING_BLOCKED；没有可部署或物理合格声明。

`a42364_manager.serve_installed → a42365_runtime_factory.build_installed_runtime` 已接线。旧安装包缺 FD6 时返回 BlockedRuntime；不再把构造一个无 backend 的 host 当作完整安装。FD6 必须为 root-owned、只读、单链接伴随文件。四项签名仍由既有 DecisionVerifier + 独立 RegistryChannel 验证，短期到期、撤销及独立签名人检查继续生效；没有测试签名或批准布尔值。

固定 FD：3 旧 installation；4 source archive；5 listener；6 v4 companion；7 Registry；8 root journal；16/17/18 graph/run/user namespace；19 B、20 O、21 E、22 C、23 D 的已连接 Unix channels；24 broker journal。FD 数值不是 RPC 参数。Linux peercred 在解码前及读写后核验，消息绑定 Scope、epoch、source archive、budget plan 与 domain。新消息不兼容旧 server，未部署新 server 时不能 READY。

工厂可组装 RuntimeCoordinator 和真实 Unix DomainClient，但**不能组装全部域的真实服务后端**：root cgroup/launcher、native B budget server、O/C/E v4 server 与 RO mount launcher 的安装组合仍不完整。当前代码不能据四张签名自动运行，broker 在消费前强制拒绝。因此目前不是 SOURCE_ENGINEERING_CLOSED_PENDING_DECISIONS。

## 状态与恢复

运行：权限复核 → broker 能力复核 → RUN_ATTEMPTED → B_CONSUME → C_PREPARE → O_PREPARE → D_RUN → D_TERMINATE → C_RECONCILE → E_AUDIT → PENDING_INDEPENDENT_REVIEW。

每步 ATTEMPTED 和 COMMITTED 分开持久化，外部 ACK 不明不重放。主错误先记录，清理异常追加，不覆盖主错误。stop 先写 CONSUMPTION_FROZEN 再通知 B；无法证明回收则 quarantine，既有 CONSUMED 不退款。原始创建身份只允许一次 ORIGINAL 事件。

ResourceLifecycle 与 BrokerResourceDriver 实现 CREATE/INSPECT/START/STOP/REMOVE 的源代码调用关系；Socket/Volume/Secret/Container 全部通过 broker。Volume 只生成准确名称 rm，原始标签/创建身份、MountCount、双 inspect 和排他租约均为必需。**全写者租约尚无内核 provider，实际 rm 始终 0**。不能凭 StorageID、flock 或 PID 列表解禁。

## E 的权限边界

ReadOnlyProvisioner.provision/accept 已实现权限前置检查、固定五 FD 的 SCM_RIGHTS 传递、同-store inode 与 ST_RDONLY 核验；E 沿用 ReadOnlyDelegation。它仅传递已经存在的可信只读挂载；**并未创建 mount namespace 或解决 rootless user namespace 中 E 的跨 UID 映射**。未完成安装不产生 ABSENT。不能把 O_RDONLY 目录 FD 当作只读挂载。

## L1 与物理证据

同一个 build_installed_runtime 的内部 ControlledInstallation 分支使用同一个 RuntimeCoordinator、ResourceLifecycle、DurableJournal，创建私有临时文件，运行固定 FD-only 子进程；B/O/C/E 事实明确标记模型。它不从网络、CLI 或环境变量启用。真实入口仅接受既有 InstalledPackage。L1 没有独立 UID/RO mount/cgroup 资格，不产生 ROOT_V3_TERMINATED 或物理 ABSENT。

StagedPublisher 先写 .incomplete，再分别 fsync evidence/manifest；只有独立 root 终止、E 八项观察、Reviewer 关联的持久回执齐全才允许 finalize。独立 Reviewer 的完整生产 server 尚缺，当前实际链停在待审状态，不删除标记。
