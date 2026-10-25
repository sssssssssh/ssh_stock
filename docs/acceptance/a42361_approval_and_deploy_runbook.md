# A42361 部署前审阅与停止手册（当前不得执行部署）

本轮只开发/离线测试；没有 Docker/Podman/PG/SQL/云调用，没有读取业务 .env。
普通 push 只触发原工作流，无新增 G1 job/manual dispatch/Environment/Runner。

## 先补工程，再讨论授权

当前不是“给一个 token 就能运行”。须先补齐 owner 服务端、B receiver、独立 E 审计、D 隔离 launcher/
写盘 watchdog 与部分创建 reconciliation，重新代码审阅；不得以临时 JSON、单进程扮多域或调大预算替代。
init_owner.sql/probe_roles.sql 是未完成的方法草案，不是可运行一键部署脚本。

之后独立管理员需另审：exact Git SHA/source/overlay/allowlist、PG17 digest 与签名供应链、OpenSSL exact
版本/二进制摘要、psycopg3.3.4、Python/Podman摘要、Unix peer UID/GID/只读安装、私有 runtime 目录、
无业务路由/敏感挂载、单次新 fixture、A/B/C/D/E 不同责任人、撤销/时钟源和持久审计。
本仓库不提供正式公钥、私钥、数据库凭据或正式批准记录；模板 null 保持无效，不能用占位凭据启动。

## 待单独批准的完整预算

授权1s；初始化2s/最多8个基础设施SQL/12个固定命令；探针16SQL（含4投影），每条100ms、≤8行、总窗2s；
终止/清理/写盘各2s；CPU1000m、RSS512MiB、PIDs32。全部仍是草案，不是已批准的物理保证。
冷启动达不到2s就失败，不延时重试、不扩大预算。server timeout 不能替代 OS 层 watchdog。
文件 fsync 可能不可中断；当前 IO 函数的后验 elapsed guard **不证明硬时限**，必须由外层隔离进程处置。

## 停止与恢复（尚无可宣称完成的一键停止工具）

普通 CLI 永远非资格退出，旧 run_live 继续硬拒绝。代码不能因 Git clean/CI success 自动激活。
未来独立管理员先撤销批准/阻断新任务；受信 supervisor 只终止本次未 reap 的自有子进程组（TERM→KILL→reap），
再要求 C 二次检查精确创建收据归属，E 记录 DESTROY_REQUESTED→DESTROYED→ABSENT。
没有独立 absent 只能 INCOMPLETE。禁止 prune/按前缀批删/清业务库。

提交结果未知或 ack 丢失：永久停止本次真实执行，不重置 consumption，不换 nonce 重跑。
创建中途超时：可能已产生容器/卷/secret，保留首错及 INCOMPLETE 日志，隔离资源由独立 owner 对账；
当前部分创建安全回收和 socket 目录回收代码 **未齐**，这是启动前阻断，不是可接受运行时泄漏。
没有已审核 reconciliation 之前不能申请 G1。

## 本地离线验证

使用项目 .venv，设置 synthetic 端口1 DATABASE_URL，显式 Settings.env_file=None，运行既有
scripts.a42331_pytest_safety 插件。只跑纯 unit/密码学/协议故障模型，不运行新基础设施迁移。
全量 PG17 验收只由最终一次 push 的既有 CI 执行原回归；不得把这次原业务 CI 称为 G1 实机测试。
