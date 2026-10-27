# A42365 集中交付记录

开始 HEAD/origin：`2c8870f67d65e20465ad8a88affac3e1b32e9da3`；master；开工 clean=true。

总体状态：**PARTIAL_ENGINEERING_BLOCKED / PHYSICAL_NOT_RUN**。本轮新增了实际持久账本、原子跨进程预算预留、四资源去重恢复和 broker 适配、固定安装工厂/Unix peer 消息接线、独立审计连接工厂、只读 FD 委托收发、两阶段发布组件，并在同一装配入口运行 SQLite/SCM_RIGHTS/固定子进程的 L1 模型链。

**没有完成任务书的全部运行源码闭环**，不能写为“仅待审批”：mandatory 全写者 provider；B/O/C/D/E v4 server 安装；native exec/FS/SQL 全局中介；跨 UID E 的 RO mount namespace 创建与 UID 映射；完整 root cgroup/worker/Guardian 工厂；actual target generation 持久注册；independent Reviewer 仍有缺口。具体源码和 node id 见 a42365_capability_matrix.md。后续 G1 工程实现负责这些缺口；OWNER/SAFETY_PLATFORM 的签字不能替代实现。

本轮不改 backend、frontend、config、migrations、依赖、工作流、历史八层 manifest、BIZ manifest、旧测试、旧一次性授权。四份权威文档仅追加本阶段实际状态。最终精确变更文件和 hash 在 a42365_overlay_manifest.json。

RED：8 个实际 ModuleNotFoundError，完整原始 XML 与 hash 在 a42365_baseline.md。存在性 GREEN 不是 source closure 证明。L1 journal/预算是实际 SQLite；文件资源和 PG/E preparation 是明确模型；没有 actual PG target-session evidence。

提交前针对本轮新增实现的测试46 passed / 0 failed / 0 skipped，Ruff（backend/tests/migrations/scripts）及 git diff --check 通过。targeted JUnit SHA256：`9fb44377eb9c337a5b305c20298b8b3a50b2ac96c1d4a710622e7bac97106076`。完整回归及同 SHA CI 在本提交中记录为 PENDING；最终以完全相同40位 SHA 的 ordinary Actions、JUnit、coverage、ZIP 和内部报告 SHA256 为准，交付消息给出可核验链接。未触发 expensive/manual workflows。CI 失败不许标绿，也不反复跑性能到 PASS。

D1/D2/D3：UNSELECTED / NOT_SIGNED；G1_L2_EXECUTION 独立 NOT_SIGNED。

实际 G1 SQL=0；Podman=0；G1 initdb=0；cgroup/mount/namespace 创建=0；服务安装=0。物理 L2=NOT_RUN_NOT_AUTHORIZED；G2 effective total warmup=8 pending；G3=NOT_AUTHORIZED；BIZ-PERF-01=PERFORMANCE_OPEN。

首次本地完整 unit 回归：4048 passed / 14 failed / 0 skipped（JUnit SHA256 `72cf8a85243dd62a52a0d50f2ce5199349d9c9dad1ed007fbdda99410b4e4220`）。其中9项为新 guard 错误码前置导致旧拒绝合同失败，已修复检查顺序且未改旧测试；另5项为 macOS 的 Linux 回收/系统 OpenSSL 运行环境失败，仍须同 SHA Linux CI 验证，不能记为本地全绿。原始失败工件保留，不通过 skip/xfail 规避。
