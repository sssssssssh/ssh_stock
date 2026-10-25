# A4236 W00–W09 开发交付与验收边界

Baseline：af08f8724e988121402988b4e8fb70c8ef5b53f2；保持master。
用户明确授权分阶段提交，最终一次push；没有实机授权。
**当前代码状态 PARTIAL / BLOCKED，不是实机 implementation ready**：独立issuer、
真实验签、持久消费者、受信fixture harness/销毁审计均未配置，仅有接口与封闭Mock。
全任务精确26路径见 baseline；14源/测试字节在新overlay manifest固定，旧manifest不变。

## 工作包映射

| 包 | 修改/输入输出/异常及覆盖 |
|---|---|
| W00 | baseline + next overlay；Git/CI/artifact输入→精确冻结；FROZEN_FILE_CHANGED、HEAD_BYTES_MISMATCH |
| W01 | harness_contract + harness_grant测试；Fixture/Consumption→Mock双域创建及三收据销毁；身份/权限/网络/absent拒绝 |
| W02 | grant_verifier + trust_and_red；Grant→假验证及模型CAS；重放/过期/撤销/未知key/身份预算拒绝；真实接口NOT_CONFIGURED |
| W03 | g1_probe + probe_prepared测试；固定Request/FakeReply→≤16事件；预算/超时/行数/不终止停止，无retry |
| W04 | session_prepared；同Session/OID/cache-key快照→DRIVER_MODEL_ONLY；连续性/计数/模式漂移拒绝 |
| W05 | resource_probe + resources_observer测试；CPU/资源/四关系描述→不可用/方法未证，PID/namespace/interval漂移拒绝 |
| W06 | observer_feasibility；纯Tick/Window→MODEL_ONLY或INCOMPLETE；假join/短bracket/超预算拒绝，无线程/睡眠 |
| W07 | evidence + evidence_cli测试；六文件+manifest→owner-only离线完整性；首错sticky、cleanup单列、非法JSON/文件/IO拒绝 |
| W08 | capability_matrix + unresolved_methods + 授权申请模板；输出缺口和人工决策，绝不批准 |
| W09 | 五测试文件 + source_guard + 四权威文档；AT映射、旧Reviewer真异常及正常失败回归、同SHA CI回执 |

全部现实创建/角色/网络/SQL/CPU采集/清理 **NOT_RUN**：本次只开发，没有用户G1批准，
也没有真实安全执行器。可执行正例仅Fake，不是同 session 物理证据。
错误仅固定A4236码；旧guard保留A4235码、旧Reviewer保留A42341码，不泄露输入异常。

## AT01–AT36 可复验目录

- AT01–04：source_guard测试 + baseline/manifest；精确26路径、14patch、HEAD/blob/隐藏index/dirty/race。
- AT05–15：harness_grant测试 + evidence独立expected；八原始RED→GREEN、grant绑定、CAS交错恢复、权限及双域/销毁反例。
- AT16–24：probe_prepared测试；16含投影/第17拒绝、100ms/2s/8行、driver第六次仅模型、会话与cached结论分离。
- AT25–30：resources_observer测试；CPU不可得不填零、整线程/RSS/GC、四关系/维护、短窗/假join/partial预算。
- AT31–34：evidence_cli测试；首错+cleanup+末快照、模板行数、去敏owner-only/JSON/哈希/manifest最后发布/失败marker/权限提权拒绝。
- AT35：原测试不改；新增跨阶段复现假joined必须抛A42341_FAILED_POINT_INVALID；合法joined-payload-invalid与128点cleanup-only仍INCOMPLETE。
- AT36：仅离线回执；REAL=NOT_RUN，G2/PENDING/8，G3未授权；所有生产/容量/归因资格false。

## 运行证据与提交策略

初始惰性Mock的固定八断言实际 RED：8 failed/0.04s/exit1；同八断言实现后 GREEN：8 passed/0.07s。
这是开发脚手架的缺失校验，不是八个历史生产漏洞。RED commit在实现前冻结，最终一起推送。
后续实际结果由下方本地验收记录及最终交付回执给出，不能沿用基线3698计数。

首次提交后实际新测试305 passed/1 failed（9.04s），unit3176 passed/1 failed（151.76s、5条既有warning）。
同一失败是新白名单测试把Git的中文quotePath转义当文件名；修复为NUL分隔读取，未减少26路径集合。
复核同时增加预算对象篡改和generic→custom反向模式漂移回归，并禁止已销毁Fake fixture复用。
不涉及性能采样，不通过重复试验筛选结果。修复后须重新执行完整验证，前述失败记录保留。

本地只使用虚拟环境Python、禁用Settings.env_file、synthetic disabled loopback URL/端口1及既有
`scripts.a42331_pytest_safety`插件。模板命令：

```text
pytest -p scripts.a42331_pytest_safety -q tests/unit/test_a4236_*.py --tb=short --show-capture=no -rN
pytest -p scripts.a42331_pytest_safety -q tests/unit --tb=short --show-capture=no -rN
python -m ruff check backend tests migrations scripts .github/actions
git diff --check
```

第二条仅纯unit；完整pytest/既有PG17迁移和浏览器验收交由原push CI，不在本机读取业务.env。
此源码提交不能内嵌自身SHA或预知CI ID；最终回执必须另列实际40位HEAD、run/attempt/job/artifact
以及metadata/下载字节/内部字段的核验级别。既有工作流与依赖完全未改，没有dispatch/retry/G1 job。
普通CI使用其原隔离测试服务，不代表本轮G1已运行。

## 最终停止线

G1_NOT_RUN_NOT_AUTHORIZED，实际PG17 fixture=NO、SQL=0；清理NOT_APPLICABLE_NO_FIXTURE。
prepared同session NOT_RUN；cached结构NOT_VERIFIED；backend CPU METRIC_UNAVAILABLE；长窗NOT_RUN。
G2 PENDING/有效总8；G3 NOT_AUTHORIZED/真实128点NOT_RUN；16/32预热提案未批。
生产C1/P95/L2/唯一因果修复候选 INSUFFICIENT_EVIDENCE。等待代码再次审阅；不得自动进入实机或下一阶段。
