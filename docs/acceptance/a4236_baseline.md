# A4236 W00：基线、权限与精确路径登记

开工分支 master，git status 为干净 `## master...origin/master`。
HEAD、origin/master 与实际 git ls-remote 均为
`af08f8724e988121402988b4e8fb70c8ef5b53f2`。用户授权本轮分阶段提交、最终一次推送；
**仅开发/离线验收，不批准 G1/G2/G3**。

## 新执行的基线核对

GitHub API 再次读取主 CI40155861800/test121057011508 与专项40155861812/contracts121057011490，
均 success。普通 push/attempt1；正式 authorize/capacity/release 等仍 skipped。
本地已下载原工件再次核验（纯读取，exit0）：

- 主安全 JUnit3698/0/0/0，六份安全XML，279 A42341/238 A4235/85 A42351；19份PG17清理收据，head0058。
- 专项四ZIP字节摘要、完整128点/64对与未完成3点原始Mock bundle独立重审通过；旧319/109/279计数不改。
- 主安全ZIP12584553812 SHA256：4369a5cffc0ceab52c4f6dd4ae15d5f73074961a1514ca0950c169b6aa7e04e0。
- 专项Mock ZIP12584214155 SHA256：a08a4c0baf2a9d1985a60a83dc7c45cfb606581fa2ecd42b3524e7f9efba8571。

当前 A4235 source_sha256：43765d891dc0f30270d4ad5ffc035df72b031758797fee7153fb56366b777404。
当前 overlay_sha256：22f813ea34ff21893dd4e4c95b77fe4358f8b5edba4aa271c837a69dbaa1df79。
历史 frozen_sha256：b7aecb955fb32bf285ae71ff3bdf6cfdc6aa15828e70bb46c507d31bfc1418e9。
A42351 manifest SHA256：ea795278e3fb84e4eebabeba737d23a92a4a0c42e6402cc828bf3801d3c9f648；
六个 patch path 字节与已提交 blob 已由原 guard 全部重新核对。
新提交必须重新取得同SHA CI；上述不是新提交绿灯。

## 开发前登记的唯一变更集合

只修改旧 `scripts/a4235_capability_guard.py` 的精确下一层叠层支持；旧常量、manifest、六patch及历史身份事实不回写。
新增以下固定文件（不是允许命名空间通配）：

- scripts/a4236_g1_harness_contract.py
- scripts/a4236_grant_verifier.py
- scripts/a4236_g1_probe.py
- scripts/a4236_session_prepared.py
- scripts/a4236_resource_probe.py
- scripts/a4236_observer_feasibility.py
- scripts/a4236_evidence.py
- scripts/a4236_cli.py
- scripts/a4236_mock.py（封闭纯数据Fake工厂/集成驱动，不是真实adapter）
- tests/unit/test_a4236_harness_grant.py
- tests/unit/test_a4236_probe_prepared.py
- tests/unit/test_a4236_resources_observer.py
- tests/unit/test_a4236_evidence_cli.py
- tests/unit/test_a4236_source_guard.py
- docs/acceptance/a4236_baseline.md
- docs/acceptance/a4236_trust_and_red.md
- docs/acceptance/a4236_closeout.md
- docs/acceptance/a4236_capability_matrix.md
- docs/acceptance/a4236_g1_authorization_request_TEMPLATE.md
- docs/acceptance/a4236_unresolved_methods.md
- docs/acceptance/a4236_overlay_manifest.json

四权威文档 README/PROJECT_RULES/PRD/系统设计仅追加新节。合计26个路径。
新增叠层固定上述路径全集、代码/测试字节SHA256、独立Git HEAD、已提交blob和工作区。
旧历史树/overlay原字节与语义保留；不以新Git hash自证签名或执行权限。

## 运行平台和现实信任边界

本地仅Python虚拟环境/静态Git/纯Fake/新工件文件IO；不读业务.env，不启动Docker/PG，不读取/proc。
普通既有CI的隔离PG17回归可运行，但不增加新G1 fixture/profile/dispatch/Environment。
独立issuer/密钥信任根/审批记录服务：UNRESOLVED，NOT_CONFIGURED。
受信持久化CAS消费服务、fixture所有者与启动权限、网络隔离实证、独立销毁审计者：UNRESOLVED。
本阶段实现接口与封闭Mock执行器；若外部基础设施未配置，代码阶段如实PARTIAL/BLOCKED，
不能把仅接口/Mock称为可运行的实机实现。REAL永不回退到Fake。

新建/删除/SQL/角色授权/云操作/proc采集均NOT_RUN，SQL=0。真实清理NOT_APPLICABLE_NO_FIXTURE。
G2仍总8次；16/32未批；G3未授权；C0/C1/P95/L2/生产与因果证据不足。

## 官方技术依据（仅设计，非实机证明）

PG17的prepared视图只反映当前session，其parameter_types可转换OID，from_sql区分SQL和协议准备，
generic/custom计数不是cached结构证据。见[PG17视图](https://www.postgresql.org/docs/17/view-pg-prepared-statements.html)、
[PREPARE](https://www.postgresql.org/docs/17/sql-prepare.html)。
driver键与阈值按[psycopg3.3.4源码](https://github.com/psycopg/psycopg/blob/3.3.4/psycopg/psycopg/_preparing.py)
及本地锁定版本复核；不把滚动开发文档版本当3.3.4的物理证据。
