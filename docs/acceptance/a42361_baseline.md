# A42361 W00：先冻结边界与路径（不是G1授权）

开工master干净，HEAD=origin/master=实际ls-remote=
6d54841522bc013ad21a52bc45d75218de2d9ce6。基线CI40175893177/attempt1重新查API为success；
旧四ZIP再次只读核验exit0：4006/0/0/0、六份安全JUnit、19份PG17/public/0058与owned cleanup；
279 A42341、238 A4235、85 A42351、308 A4236。原工件摘要不重签，Observer专项无新run。
本次新SHA必须重新获取既有CI；不把以上基线绿灯冒充本轮结果。

## 用户范围与执行边界

本次用户授权开发、提交并推送；按阶段commit、最终一次push，保持master，不重写历史。
只允许静态/离线/密码学测试及协议故障注入，不启动PG、Podman/Docker、控制面或G1 worker，
不读业务.env、不生成正式token、不部署信任根、不申请云资源。
普通既有push CI仍可运行原隔离回归，但不新增G1 job/dispatch/Runner/Environment。
G2总8次、G3未授权；生产/容量/因果资格恒false。

## 提交前固定的路径登记

新增源码：

- scripts/a42361_contract.py
- scripts/a42361_deployment.py
- scripts/a42361_trust_verifier.py
- scripts/a42361_one_shot_store.py
- scripts/a42361_fixture_controller.py
- scripts/a42361_live_probe_worker.py
- scripts/a42361_watchdog.py
- scripts/a42361_trusted_evidence.py
- scripts/a42361_control_service.py
- scripts/a42361_source_guard.py
- scripts/a42361_offline_cases.py（明确TEST_ONLY的协议替身，不作部署入口）

新增测试：test_a42361_trust.py、test_a42361_store.py、test_a42361_controller_watchdog.py、
test_a42361_worker_evidence.py、test_a42361_source_entrypoints.py，均在tests/unit/。

新增docs/acceptance/文档：a42361_baseline.md、a42361_trust_model.md、
a42361_approval_and_deploy_runbook.md、a42361_capability_matrix.md、a42361_unresolved_methods.md、
a42361_test_traceability.md、a42361_closeout.md、a42361_dependency_review.md、a42361_overlay_manifest.json。

新增基础设施源文件（只写源，不执行）：

- infra/g1_control_plane/001_control.sql
- infra/g1_control_plane/README.md
- infra/g1_harness/pg17-spec.json
- infra/g1_harness/init_owner.sql
- infra/g1_harness/probe_roles.sql
- infra/g1_harness/runtime-lock.json
- infra/g1_harness/deployment.example.json
- infra/g1_harness/README.md

旧文件唯一拟改：scripts/a4235_capability_guard.py的第三层精确冻结兼容；
tests/unit/test_a4236_source_guard.py中旧26路径及自身pin的逐层兼容（须用户确认精确例外）。
四权威Markdown只追加新阶段。除此之外全部旧源码、308旧用例、协议、manifest和工作流冻结。

旧guard Git blob：5e2b02d78ce0b5bdf6559d3b14cd5160cb6f8389。
旧source_guard测试Git blob：643b1257d505cdc878e0ae811e88696c01fc7aa3。
旧A4236 manifest SHA256 d93bf795a59cb0a168f0e96f4382d58efcbdc2833bc43e22ebde3254a09c1156；
旧A42351 manifest SHA256 ea795278e3fb84e4eebabeba737d23a92a4a0c42e6402cc828bf3801d3c9f648。
新增层将分别固定原/新patch SHA、全路径集、已提交blob与工作字节，不把目录加入通配豁免。
最终新字节摘要待代码完成后独立冻结；本文件不自签批准。

## 当前缺口：真实接口不是Fake

现有四类未配置接口实为固定拒绝；本轮先保留四个原始RED断言，再交付新命名空间真实实现。
这不是四个生产越权漏洞；原拒绝行为继续保留。真实实现的启用仍须独立运维部署与人工G1审批。
owner A/B/C/D/E、信任根/撤销、专用控制库、rootless运行平台、镜像digest、独立absent审计均UNRESOLVED。
在可部署实现未全部形成前状态PARTIAL/BLOCKED；不为结束任务填CODE_READY。

## 原始RED：实际执行，非物理试验

四个旧默认接口实际调用均固定拒绝：ISSUER_NOT_CONFIGURED、PERSISTENT_CONSUMER_UNAVAILABLE、
HARNESS_NOT_CONFIGURED、G1_NOT_RUN_NOT_AUTHORIZED，未创建/连接任何资源。
新增四个静态断言盘点真实verify_signature/consume_transaction/create_owned_fixture/terminate_owned实现：
初始inventory指向上述旧接口，实际 **4 failed in 0.06s / exit1**。
命令使用既有安全pytest插件、禁用Settings.env_file和synthetic端口1 URL；没有改日志插件。
断言只证明可部署代码曾缺失，不是四次物理运行失败，也不把方法存在当完成标准；
后续须保留四断言并以RFC密码学、事务/执行器故障合同和全量回归验证实现。

## 用户追加授权：只补全树隐藏索引防护

初次推送6b29f5d619f41b9e5e88a90f9fb89c3b6def99b7后，只读复核发现旧保护树/infra/登记路径以外的9个根文件
仍依赖diff/status。用户明确允许追加一次精确修复和推送，并重新核验新SHA CI；不是G1授权。
范围仅新a42361 guard、新测试/文档和对应manifest/旧guard唯一digest literal；不增加路径，不改旧test其余内容。
在临时目录使用真实文件及独立Git协议fixture复现：9根文件内容+symlink/缺失/mode共12 failed，正常正例1 passed。
未操作用户真实index flags；没有读取忽略的业务.env。新walk覆盖全部HEAD tracked blobs，以NUL读取路径、
独立blob ID、实际文件模式和no-follow FD前后metadata验证，不改变旧PROTECTED/历史frozen digest。
新增21项包括12拒绝、正常中文/换行路径、3项读期间write/replace/symlink竞态、5项路径转义负例；
修复后21 passed/0.36s。旧服务端/部署/物理证明缺口不因此关闭，仍PARTIAL/BLOCKED。
