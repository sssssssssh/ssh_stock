# BIZ-WORKER-02 合同迁移提案（待独立审阅）

状态：CONTRACT_MIGRATION_BLOCKED / NOT_APPROVED。基线
`75076eac443d935d622bf59e12aad20ce5aba85e`，整改分支 `codex/biz-worker-02`。
本文件不是签名、授权记录或可执行合同，不能据此部署长补算。

## 历史义务

A42366 guard 绑定 f00be6a 的完整路径集合、旧业务字节、全部旧测试和十份历史 manifest。
其 `changed == stage_paths` 在本基线多出的 BIZ-POLICY 路径上正确拒绝。
历史清单不重签、历史负例不删改、旧实验不能接收当前业务字节。

## 提请审阅的双版本方案

1. 历史合同仍在原不可变提交与独立 clean checkout 原样执行；保存历史篡改拒绝证据。
2. 普通常规合同新增独立 `biz-worker-02.source.v1` 叠层，以 75076ea 为基线，
   再逐层验证 f00be6a 的 A42366 清单和全部旧 manifest 原字节及原提交上的摘要。
3. 新清单逐路径逐字节登记：上轮三业务文件 calculation_policy.py、job_worker.py、
   repositories/job_run.py，以及两测试 test_business_policy_identity.py、
   test_business_policy_worker_pg17.py；本轮新增心跳/只读对账/观测模块与测试也必须分别登记，
   不允许 backend/tests/scripts 全目录白名单。所有旧测试保持原字节。
4. 普通 CI 的版本选择只发生在当前源码合同入口；真实实验入口继续使用历史冻结源码，
   不能把合同成功升级为性能、G1、容量或生产许可。三个优化开关默认不变。
5. 新 guard 必须检查完整 HEAD、未跟踪/隐藏索引修改、非法第三方路径、所有登记摘要、
   旧独立 reader 的篡改注入与错误分类。审批后才实施，需新增负例证明不能伪造版本。
6. 允许的入口调整仅 `scripts/business_source_contract.py` 及必要的当前普通合同适配；
   在证明旧 negative tests 不变且有效前，不改工作流。若必须改现有测试或工作流，先提交
   精确差异另审，不把本提案视作无限授权。

## 尚未签署

独立审阅者：未指定。审阅结论：未签署。具体新路径/摘要最终清单：须随审阅代码固定。
本轮不实施该迁移；保持旧合同真实失败。W02/W03/W06 的隔离开发与诊断可独立推进，
不受理生产事故修改，不绕过发布门禁。撤回本提案无需修改任何历史合同。
