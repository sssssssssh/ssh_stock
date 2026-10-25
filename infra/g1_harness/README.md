# Rootless PG17 harness 源码与部署阻断

模板全部 NOT_CONFIGURED，digest/null 不得以 latest 或猜测摘要替代。没有执行 Podman/SQL。
FixtureController 只构造固定 PG17 命令；network=none，无 public ports/host PID/proc/敏感 mount，
资源草案CPU1、RSS512MiB、PIDs32仍待独立批准。rootless runtime、socket共享GID及私有 runtime目录
必须由独立管理员审核；不能给 probe Docker socket 或 controller 的通用命令权限。

本轮不声称可部署链完整：PG owner 初始化/短期凭据服务、独立 namespace/absent 审计和真实 worker
隔离 launcher/有界写盘 supervisor 的服务端尚未交付。SQL 文件是方法草案，不是完整 bootstrap。
不能手动执行这两份 SQL 以绕过完整资源审批或 8 条独立初始化预算。

完整创建回执后销毁：再次验证 labels/image/mount/UID → DESTROY_REQUESTED独立审计 →
精确 stop/rm 本容器 → 再验本卷/secret身份后移除 → DESTROYED → 独立 ABSENT。
任一缺口均 CLEANUP_NOT_VERIFIED，不通过 prune、按前缀删除或扩大权限解决。
创建中途超时可能已有资源；当前只能记 INCOMPLETE 并阻断，尚缺可信部分资源 reconciliation。
这项代码缺口必须先补齐、审阅，再讨论独立部署和一次性 G1；不得通过追加批准掩盖工程缺口。
