# A42361 源码交付与未完成项

**PARTIAL_OFFLINE_TESTED / BLOCKED**。没有达到任务书的完整可部署链目标，不标CODE_READY。
已交付真实Ed25519/独立审批核验、专用PG事务/CAS/schema、rootless固定命令与完整创建后的精准销毁路径、
锁定驱动固定16SQL执行器、TERM/KILL/reap原语、安全失败工件/非资格Reviewer及第三层精确冻结。
owner/独立auditor服务端、RPC安装包、部分创建回收、完整supervisor接线尚未形成，详见unresolved_methods。

## Git、范围与历史

初始master=origin/master=实际远端6d54841522bc013ad21a52bc45d75218de2d9ce6且干净。
阶段A已提交d172ba7（路径冻结/四真实方法RED）。后续实现/最终冻结提交的完整SHA由Git与最终交付回执给出；
文档不能嵌入自己的未知commit SHA制造循环。保持master、分阶段commit、最终一次push，不重写历史。
精确新增11source/5test/8Markdown+manifest/8infra、两旧文件精确兼容、四权威只追加，共39路径。
旧A4236测试仅一函数逐层26旧路径+新登记路径/旧新pin核验；用户明确允许；原308项/其他函数AST不变。
old A42351/A4236 manifest原字节、旧Reviewer/协议/授权/生产/工作流/依赖全冻结。

新manifest pin37个原始文件、旧两文件before SHA、guard归一化字节SHA；guard唯一manifest digest文字以0归一化
避免自引用，其余字节全部固定，原始guard及manifest仍须与独立Git HEAD blob一致；全树真实字节防隐藏index。
这只证明源字节，不是签名或批准。

## 测试证据与CI层级

先真实运行4项RED（4 failed/0.06s）；真实RFC8032 positive与篡改负例已运行，不是FakeIssuer。
本地完整unit在f8287c3e9bb8655391033312738892ff6b091fd5运行：**3324 passed / 5 warnings / 225.32s**，
JUnit核对0 failure/error/skip；其中新A42361为145项，旧A4236为308、A42341为279、A4235为238、A42351为85。
本次中文路径NUL修复前目标163项曾3 fail/160 pass；定位修复后全unit通过。Ruff全backend/tests/migrations/
scripts/.github/actions与git diff --check通过。本段文档/摘要冻结后的final SHA另跑目标回归及既有CI。
仅针对新增文件运行安全pytest、全unit、Ruff和diff；最终实测计数由末次本地记录/最终交付回执报告。
任何失败不通过skip/xfail/改阈值吞掉。新PG/控制库/fixture/worker/OSkill全部未执行，SQL实际发送0。
最终一次push后只核对既有CI的新exact SHA；分开记录API metadata、实际日志、ZIP字节摘要和内容。
历史CI40175893177/attempt1的4006/89.28%仅为基线，绝不是本轮结果；旧Observer未触发不算专项PASS。

## 停止线

本阶段结束只供代码审阅，工程缺口仍需补齐，不应直接申请G1。独立issuer/注册/撤销/双审批、持久库、
rootless/runtime与独立absent审计没有部署；不接触阿里云或业务.env/库/任务，无正式token/key。
G2有效8次待决，16/32未批准；G3真实128点/64对未授权；production/performance/capacity/attribution均false。
没有性能比较/P95/603040行/L2或唯一修复候选结论。本轮普通回归成功也不改变这些状态。
