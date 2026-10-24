# A42341 W00：基线与8次预热阻塞

2026-10-24；HEAD/origin/master/远端均为f5c0fe4d08f37c01714a3085d49f30da4bc4f1d4，开工工作区干净。
本轮只设计、纯内存模拟和离线验证，不连接数据库、读取业务.env、启动服务或执行预热/lookup。

## 已实际复核

- [主CI40052175974](https://github.com/sssssssssh/ssh_stock/actions/runs/40052175974)：同SHA、attempt1，SUCCESS；
  全量3096 passed，覆盖率89.28%；test job120747025651，正式authorize/归因/capacity/release跳过。
- [专项40052175973](https://github.com/sssssssssh/ssh_stock/actions/runs/40052175973)：同SHA、attempt1，SUCCESS；
  原319、新109 passed；job120747025356。
- 重新请求上述job状态，并对上一轮已下载7份ZIP重新计算摘要/内部JUnit/迁移清理/Observer严格review，
  OFFLINE_REVERIFIED；6份完整JUnit、19个主CI迁移库及专项3ticks证据一致。
  原始ZIP链接/摘要见a4234最终交付对应CI工件；重点为新unit工件12543643162、
  完整JUnit12544628653、迁移12544837911、Observer12544116262，不重新跑旧CI。

## 原状态保留

用户确认的有效约束是**全批总共8次，能力不足就阻塞**；v2继续BLOCKED_NEEDS_SPEC_OR_CAPABILITY。
本任务仅允许提出方案，不表示用户已批准8→16、方案B或真实实验。新终态BLOCKED_NEEDS_USER_PROTOCOL_DECISION。
4进程×2模板=8条件；假定每条件只用同一真实连接、SQL字节和参数OID向量，每完整lookup四条同缓存键SQL，
threshold5时第6次prepare，故ceil(6/4)×8=16是必要下界。SQL/类型/连接分裂会破坏这个假定，
16不能推出server prepared存在、未驱逐、generic/custom稳定或可比较。

## 冻结指纹

新a42341_preparation_manifest.json的frozen_files逐项锁定旧文件，SHA256：
4cca8088909821371f99d8cd9dba450d2fa6ada4c6dbc462ccd8ec64498a163e。

| 旧文件 | SHA256 |
|---|---|
| v2协议 | b22df81e1e439a5109dc6a92c929adbfa7ac0384f1d3a1c4bd33ec4f65677b96 |
| 原manifest | 4ceb7149357ac7a91a48eda1407d0d621b7ca24f256f417e8e4e8ba35052947d |
| 原input | 918104253d18ad21629323befc4d2d2c198ca71a56629ca577b4ca1a9cb58e9a |
| 原contract | 747fdeb6de4b3a271945db615aac1203981efd0f97f28e18664de12489162e59 |
| 原guard | 6e4eea1857bedfbe6fa47959ce47afe89438a40f01041eb0d97fcd355576f0ac |

上述原文件、旧readiness/收尾/证据/one-shot/policy保持字节不变。新工具使用a42341命名空间。
旧guard不会接受新诊断源码为旧实验授权来源，原execute硬拒绝与prepared_readiness的8次阻塞保持；
不为让旧check_repository接受额外源码而扩充其白名单。

## 尚未实证能力

真实driver连接及SQL/OID身份、同会话server prepared、无扰动cached plan结构探针、generic/custom比较、
独立backend CPU生命周期、自然GC/资源采集、真实完整Observer bracket及角色/物理隔离均未实证。
本轮可完成模拟合同，但这些真实能力仍NOT_PROVEN/METRIC_UNAVAILABLE；不允许由mock推导运行许可。
