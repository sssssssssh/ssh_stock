# A4236 信任模型、原子消费协议与真实RED记录

## 威胁与默认拒绝

不信任：工件自报身份、Git干净/自签hash、Mock issuer/consumer、CLI flags、环境token、push/dispatch、
重复fixture JSON、未经审核公钥、probe进程自身签发、任意DSN或执行callback。
本轮无独立签发者、公钥部署、持久消费服务、真实fixture owner或独立销毁审计服务。
live入口第一分支固定拒绝；未配置接口分别报ISSUER_NOT_CONFIGURED、PERSISTENT_CONSUMER_UNAVAILABLE、
HARNESS_NOT_CONFIGURED。不从真实路径fallback到Fake，不安装插件或创建基础设施。

未来外部签发payload须绑定完整HEAD/source/overlay/run/attempt、唯一G1 profile、fixture UUID/nonce/marker、
allowlist哈希、固定资源预算/TTL、审批记录、issuer/key/algorithm版本、唯一token ID和审计对象。
真实信任根由独立管理员审核部署并支持轮换/撤销，不来自待审artifact或仓库提交。
本轮只验证Mock签发匹配和拒绝语义，不能把该匹配称为验签成功。

## 受信持久化消费协议（未部署）

1. 受信签名服务独立核验scope、payload全字段、issuer/key、撤销及时间；不可用即拒绝。
2. 外部持久服务用唯一token ID与payload SHA在同一事务/CAS中PENDING→CONSUMED。
3. 提交并取得独立消费回执之后才允许fixture创建及任何SQL。并发请求最多一个获准。
4. 提交前崩溃：未消费、没有资源。提交后/响应丢失/fixture前崩溃：不可重试或重消费；
   不确定状态一律停止，不能用新nonce绕过同一批准范围；由独立服务审计处置。
5. 消费后probe失败仍保持CONSUMED；清理不回退消费，销毁仅作用于已交叉证明的自有fixture。

FakeCAS的原子转移/恢复/交错测试只是掉电与并发**模型**；内存快照或普通文件不是可信持久服务。
本轮没有SQLite/锁文件充当one-shot，也不把Mock state的“consumed”宣称为真实持久消费。
未来实现还需故障注入、存储唯一约束、事务提交可见性、独立签名回执和部署审核。

## 已实际运行的RED（修复前）

新模块的惰性Mock scaffold故意缺少纯校验，refusal_case返回None；不包含真实执行能力。
八个固定断言要求矛盾输入必须抛A4236 Fault，而不是返回低资格状态。
场景：伪grant、replay、PID漂移、cache-key改变、false join、false cleanup、超SQL预算、历史写越权。
这不是发现八个历史生产漏洞，也不是把任意stub的通过当实机证明。

命令：禁用Settings env_file后，用不可连接synthetic loopback测试URL和既有安全插件运行：
`pytest -p scripts.a42331_pytest_safety -q tests/unit/test_a4236_harness_grant.py
--tb=short --show-capture=no -rN`。

实际退出码 **1**，stdout：`FFFFFFFF [100%]`、八个固定用例各A42331_TEST_FAILURE，
**8 failed in 0.04s**。安全插件按原规则去敏，不改变失败事实。
本文件/基线/RED断言和惰性Mock在补齐实现前提交，最终一次push不单独推送RED提交。
后续GREEN须保留原八断言，并另测有效Mock正例与真实入口无条件拒绝，防止“总抛错”假修复。
实际GREEN和完整验收见本阶段closeout；未执行结果不得提前填绿。
