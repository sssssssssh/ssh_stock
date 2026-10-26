# ADR_SAFE_VOLUME_DISPOSAL — 排他删除独立决策

冻结基线 a8a675ea8b93dadbba9e905a7a4af67eba163d99；最终字节见第七层 manifest。
决策 NOT_APPROVED；safe_volume_disposal=NOT_IMPLEMENTED；物理 NOT_RUN。
项目 owner 决定资源协议，平台管理员证明隔离，独立安全审批者复核攻击面。
当前源码对 Volume 恒拒绝删除；仅 Name/Mountpoint/StorageID 而没有ID仍是
REMOVE_ID_REQUIRED，有ID也必须 SAFE_DELETE_UNPROVEN，实际 rm调用0。
任务 AT09 的泛称由 W01.3“无ID保留REMOVE_ID_REQUIRED”细化，不改历史错误断言。

固定审查版本 **Podman v5.6.2**，不是本机已安装版本声明。
官方 [volume inspect](https://docs.podman.io/en/v5.6.2/markdown/podman-volume-inspect.1.html)
列出 Name、StorageID、LockNumber、CreatedAt、Mountpoint。它只描述观察字段。
固定源码 [CLI rm.go](https://raw.githubusercontent.com/containers/podman/v5.6.2/cmd/podman/volumes/rm.go)
将参数传给 VolumeRm；
[ABI volumes.go](https://raw.githubusercontent.com/containers/podman/v5.6.2/pkg/domain/infra/abi/volumes.go)
执行 LookupVolume(arg)→RemoveVolume(vol)；
[runtime_volume.go](https://raw.githubusercontent.com/containers/podman/v5.6.2/libpod/runtime_volume.go)
中 LookupVolume 查名称/部分名称。由此不能证明 StorageID 是原子删除目标。
不采用 inspect有ID→rm ID安全 的推断；也不把 JSON LockNumber 当跨进程锁FD。

## 推荐的待实现方案 A：保留四资源语义的专属 store

每个fixture独立 rootless UID/usernamespace、graphRoot/runRoot 和 store DB，
root-manager持有根目录/namespace FD；C/E没有写命名空间或其他runtime socket权限。
所有写者（CLI、API service、health helper、管理员维护通道）必须经同一manager，
禁止旁路进程执行Podman或打开store写FD，可信包/syscall broker固定命令；
安装者应证明 UID/namespace/cgroup/file权限与可执行文件访问策略共同阻断外部 writer。
不能仅靠一个应用flock、C锁或“大家约定”保证排他；root仍属于安装信任根。

账本原始ID/StorageID/CreatedAt/labels/epoch/namespace/lock和挂载引用在排他区间
内独立inspect，逐字节匹配；任何外部挂载、进程存活、同名ABA、不认识的资源隔离。
只有被证明全局排他的manager可在同一临界区内 name lookup→rm→独立E双轮观察；
要审查 Podman 所有helper进程和API入口是否受同一排他约束。崩溃后不得重发rm，
B保存REMOVE_ATTEMPTED，E只读重查原始目标；不见/无权限/错store均UNKNOWN。
这个安装能力当前没有实作，不提供虚假的“安全 rm wrapper”。

验证计划（另行批准后）：独立writer同名create、ABA、外部挂载、CLI/API旁路、
namespace替换、manager死亡、rm提交丢ACK、E错store/权限拒绝；每项记录实际version、
内核权限、store inode、原始ledger和并发痕迹。本轮只模型验证，不运行Podman。

## 备选 B：改变 Volume 合同为独占数据目录

root持有目录FD，目录绑定nonce/epoch/marker/dev/inode，精确unlinkat非递归清理。
这改变原四资源中 Volume 的语义和receipt/allowlist/镜像mount，必须新版本双审批；
不是本轮可实施的替换。未经批准不引入bind-directory作为Volume降级。

决策栏：owner 待签；平台管理员排他证明 未提供；安全审批者 待签。
两方案均未批准、未部署、未物理验证。拒绝默认继续SAFE_DELETE_UNPROVEN，不能宣称
四资源完整销毁或进入真实G1。下一步是选择协议并提供可审安装实现，再独立复核。
