# D2 SAFE_VOLUME_DISPOSAL｜UNSELECTED

Disposition：**UNSELECTED**。可选 `Approve / Reject / Need changes`。不授权 Volume 删除。

InstalledWriterBroker 提供固定资源命令计划、Scope/epoch/held store/namespace 身份复核、ATTEMPTED/DONE 持久事件和同一 broker 路由；BrokerResourceDriver 不使用 _remove_attempted 集合作为新路径去重依据。Volume rm 只使用 `volume rm <本fixture准确名称>`，没有 StorageID rm、force、all 或 prune。

**ENGINEERING_BLOCKED_BY_RUNTIME_CAPABILITY**：verify_all_writers 没有可证明的内核 provider，故任何 live create/inspect/start/stop/rm 在 runner 前拒绝。该拒绝是显式缺口，不是 SOURCE_READY。

所需安装权限模型：root 管理受信 binary/source/namespace FD；独立 runtime UID 拥有 graphRoot/runRoot；C、O、worker 不持有可旁路的写权限或 Podman API socket；只允许 broker 内核域写 store。仅 root-owned broker、0700、单进程 flock、进程 census 或名字前后 inspect，不能阻止同 UID writer/API/helper。Landlock 仅限制被约束进程及其后代，不能直接证明外部同 UID writer 被排除。

尚待安全证明：不可旁路的 MAC/其他内核写者约束；管理员/daemon 重启与 namespace 重建的 lease 撤销；同 UID API/socket/helper 对抗；Volume 名称 ABA；Mounted 与 ACK-loss；不同 UID E 对同一 store 的只读观察能力。没有这些证明，不能通过签署 JSON 放行删除。

## 隔离备选 ADR：OWNER_DIRECTORY_V4（未激活）

改用 owner directory 会改变四资源合同、MountCount/删除/absence 语义和历史验收。当前协议不接受该 choice。若选择，需要独立版本、四资源新合同、原子 identity 删除模型和独立审批，不能由当前 factory 自动切换；本轮未创建、不运行该目录替代路径。

- OWNER disposition / kid / signature：UNSELECTED / 空 / 空
- 独立 SAFETY_PLATFORM disposition / kid / signature：UNSELECTED / 空 / 空
- 外部 proof/policy digest / installation identity / namespace/store identity：待可信安装与对抗验证
- G1_L2_EXECUTION：NOT_SIGNED
