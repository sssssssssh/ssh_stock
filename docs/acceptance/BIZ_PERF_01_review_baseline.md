# BIZ-PERF-01 review remediation baseline

基线 master/origin `06b4cd6ee1783c399bdb89264c8da6190f282273`，从60eeb0f无冲突快进，初始clean。
业务对比历史 `1e510532bd140110e29b10b6e4eed30fbd573159`。
任务书为本轮最新指令，替代上轮“暂不适配”的决定；不改变任何历史实验原始样本或准入。

原始CI 40485168159 attempt1，test job122125022473；下载artifact12725526310，
实际ZIP SHA256=1ac7b9ff1ce2f0583725ac567a9a9a081a033ba79168eb91d0d84bc0d17081fd。
从实际a42331-targeted.xml确认唯一失败：
`tests.unit.test_a4233_background_observer::test_frozen_baseline_bytes_and_old_workflows_unchanged`。
143cases=142pass/1fail；全量pytest未执行，failure.json为INCOMPLETE。
这不同于lookup-diagnosis的`test_workflow_does_not_repeat_the_disallowed_100_trial_or_weaken_capacity`；
A4-1为`test_a4_diagnostic_freezes_production_sources`。原始去敏XML及failure原字节另存本目录。

本轮RED首批9fail/0skip：上述三个现存CI缺陷、6个Job策略冻结/继承/重启漂移合同。
当前物理资源：arm64 macOS，8GiB内存，可用磁盘约14GiB；Docker daemon未运行，未启动。
正在安装独立PG17二进制，使用--skip-post-install，禁止初始化/启动默认数据库或服务。
新合成实例只允许独立目录/loopback端口/UUID marker/物理system_identifier；不读取业务.env。
如资源不足，完整容量保持RESOURCE_DEFERRED，不缩减百万行或三轮要求，不伪造30%PASS。

PG17.11 独立实例已建立；仅自己的合成目录和端口，启动前后物理system_identifier一致。
初次 initdb 因 Homebrew 跳过 post-install 的版本路径缺失而失败，原日志保留；补齐缺失运行时
软链接后第二次初始化成功；未创建或启动默认服务。真实21项业务PG回归通过，新增6项
Job漂移/子任务/SQL超时回滚回归通过。macOS内存观测缺陷修复前12项失败亦保留。

A4-2 原artifact12723658777只有source/status/matrix JSON，无JUnit。原source.json精确记录
ValueError，main:615 -> source_contract:31，发生在 Frozen sources and formal parent migration
步骤，尚未运行迁移及pytest；不得描述成某个不存在的JUnit失败。原source/status字节另存。
ZIP SHA256=36637a88f46f35a801e9c009412d9aee4ebe1296ed47eaabcc17bb2b413359b6。
A4-1原JUnit另存，artifact12724357997的ZIP SHA256=
25e3dab4a5048c18a4a675dfa66437d10226a40acbc869311cf916874ef1feeb。
