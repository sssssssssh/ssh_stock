# FACTOR-RECOVERY-02-CI-R2：恢复真实CI绿灯，保护历史R1合同，继续因子计算主线

当前基线c690b5006bb6f50d069eba80a4f5b446b46cba53。上轮诊断报告 docs/acceptance/FACTOR_RECOVERY_02_CI_FIX.md 已定位两个确定性阻断：
1. tests/unit/test_factor_candidate_write.py:138 E501，当前工作树已有纯格式修复（保留）。
2. 历史R1 schema 固定 backend/app/services/data_publication.py 的LF SHA；c690b50生产修改导致12个R1合同RED；旧父提交3277c81源码对照GREEN。禁止修改旧schema、hash、安全插件、R1测试、CI workflow或通过skip/xfail绕过。

用户中心目标始终是“正常完成因子计算并解决真实瓶颈”，不是把历史审计变成无限任务。本阶段最小修复：**将 backend/app/services/data_publication.py 的 c690b50 那一个record_scope局部变更恢复为3277c81原实现**，保证该文件完整LF SHA回到历史合同期望；不回滚其他合法提交、不做git reset。这样明确撤销尚未被真实PG验证的单SQL优化，恢复全量CI可信基线，未来另选不破坏冻结合同的安全性能优化路径。同步调整仅新引入的 tests/unit/test_factor_candidate_write.py 中对该SQL计数的断言以准确反映回退后的原行为，保留批次增长界限、输出等价、幂等和取消回归；不要删测试或降低其他语义断言。现有纯格式修复保留。不要动W05两份未跟踪资产与前轮诊断报告。

先按AGENTS读治理与业务文档，核对工作树并独立验证以上因果；如发现恢复父源码不安全或还有其它变化则STOP。用纯离线测试验证12个RED中的代表节点变GREEN（全12能跑则全跑）、现有candidate_write测试、factor_service_cancellation测试、git diff --check、ruff（若可用）。不能安装依赖、不接业务PG/Worker、不运行真实SQL/迁移、不读取.env、不重拉Raw，不触碰其他冻结文件。只允许改动 backend/app/services/data_publication.py 和 tests/unit/test_factor_candidate_write.py；另外新建 docs/acceptance/FACTOR_RECOVERY_02_CI_R2_CLOSEOUT.md。禁止提交推送，完成交给ChatGPT独立审阅。报告必须明确本轮性能优化已撤销、业务计算尚未真实验收，下一阶段必须优先恢复Worker因子计算链路/找到更大热点，而不是另做泛用审计框架。
