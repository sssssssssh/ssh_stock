# A42361 源码交付与未完成项

**PARTIAL_OFFLINE_TESTED / BLOCKED**。没有达到任务书的完整可部署链目标，不标CODE_READY。
已交付真实Ed25519/独立审批核验、专用PG事务/CAS/schema、rootless固定命令与完整创建后的精准销毁路径、
锁定驱动固定16SQL执行器、TERM/KILL/reap原语、安全失败工件/非资格Reviewer及第三层精确冻结。
owner/独立auditor服务端、RPC安装包、部分创建回收、完整supervisor接线尚未形成，详见unresolved_methods。

## Git、范围与历史

初始master=origin/master=实际远端6d54841522bc013ad21a52bc45d75218de2d9ce6且干净。
阶段A已提交d172ba7（路径冻结/四真实方法RED）。后续实现/最终冻结提交的完整SHA由Git与最终交付回执给出；
文档不能嵌入自己的未知commit SHA制造循环。保持master、不重写历史；原计划分阶段commit最终一次push，
首次推送后用户另行明确允许一次精确guard修复追加推送并重新核验CI。
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

## 首次推送后的精确补充

6b29f5d619f41b9e5e88a90f9fb89c3b6def99b7既有主CI40207987554/attempt1/job121212957066已success，
实际日志4151 passed/674 warnings/1836.70s、coverage89.28%；四ZIP实际下载比对API digest，解析六JUnit、
旧308/279/238/85与新145、19份PG17/public/0058迁移及OWNED_CLEANUP证据完整。其余三个既有流水线API success。
这是首推SHA证据，不能冒充后续修复的新SHA。高成本/Observer/正式容量没有运行，资格保持false。

只读复核另外发现9个根文件的隐藏index未被原字节walk覆盖。用户已授权仅追加全HEAD树字节校验及对应测试/
文档/摘要，一次追加push。补丁不改旧保护树digest、不改历史manifest、不增加39路径之外文件。
12项真实文件篡改负例先RED，再以全tracked tree的独立blob、模式、no-follow目录/文件FD、前后metadata
和最终路径摘要拒绝；正常中文/换行NUL路径、3竞态和5路径边界共21项GREEN。
新增层不会遍历忽略的.env；普通diff/status/index flags都不能免除对HEAD文件实际字节的核验。
新完整unit/同SHA CI的实际结果由补充交付回执记录，未出结果不预填；其他服务端工程缺口仍BLOCKED。
追加完整unit初次在8cf2677实测1 failed/3344 passed/5 warnings/244.92s：新全树检查提前发现旧补丁篡改，
错误分类先变成HEAD_BYTES_MISMATCH，旧冻结断言要求OVERLAY_BYTES_MISMATCH。没有改/放宽旧测试；
新层先重复核验原六个manifest pin，再完整全树检查，保持首错分类和所有后续防护。

## 2026-10-26继续未完成工程

续作起点master/origin为a1bd4cec7e8c4fd9d44c91b018614243a9ad119a，干净。该SHA本地3345项、
既有主CI40213654303/attempt1/job121230040204实测4172 passed/674 warnings/1951.40s、coverage89.28%；
四验收ZIP（12607288715、12607408491、12607358478、12607533220）API摘要与实际字节/内容已核验。
三个辅助既有CI成功，旧Observer/高成本/正式容量未运行；这不替代续作新SHA CI。

用户另行授权本轮master分阶段提交、最终一次推送，不含部署/G1。首次RED提交1a0d815及四失败保留；
实现B监听FD receiver/peer ACL、消费和journal的新连接身份校验/已提交读取、未知提交不重试。
worker以lease v2/session v2替代预连接backend_start预测；实际run_owned离线测试证明失败前不进入固定SQL。
相关125项通过，后续全unit/冻结/最终CI计数必须从实际日志与工件读取。

**仍PARTIAL_OFFLINE_TESTED/BLOCKED，不是整任务完成。** B死锁/新连接身份和worker预测session的源码缺口已补；
独立审批写入、owner初始化与会话GUC原始证明、E审计、partial-create安全回收、runtime/socket映射与完整独立
launcher/fsync监督仍需审定实现。未扩大任何预算/权限，不以Mock计数替代工程闭环，不连接PG/云/业务.env。
