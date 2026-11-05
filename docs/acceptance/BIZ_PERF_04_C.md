# BIZ-PERF-04-C：容量与授权状态合同

2026-11-06。基线 master/HEAD/origin/master/实时远端均为
`decaaba86535575e307edd676221ec066517caf6`，clean。
负责人已审阅04-B，要求其CI成功后再实施04-C。本轮在主CI42073561595 completed/success后
才创建新源码；A4-1 42073561496、A4-2 42073561744、Publication 42073562006均success。
04-B主test Job127407664698：5651 passed /816 warnings，2919.29秒，coverage90.02%。
因此按负责人条件关闭04-B；不重跑、不改其源码或原交付证据。

## 独立合同

`scripts/business_capacity_contract.py`，标准库纯函数，无探针、文件读取、DB、网络、
Worker、授权设置或原controller接入。版本 `biz-perf-04-c.status.v1`。
不增加运行入口、不建立另一套权限执行器。旧capacity_ready=false不迁移、不导入新状态。

| 字段 | 语义 | 证据来源/推导 | 本版本取值与边界 |
| --- | --- | --- | --- |
| runner_resources_ready | 当前输入资源观测是否达到预检门槛 | CPU数/可用内存/可用磁盘整数观测；固定4核、8GiB、8GiB | NOT_ASSESSED或true/false；不能影响其他字段 |
| dataset_contract_ready | 指定合成数据输入是否通过合同校验 | 04-B validator版本、实际校验outcome及manifest字节摘要；绑定数据集摘要 | NOT_ASSESSED或true/false；不推出容量/性能结论 |
| diagnostic_capacity_assessed | 指定输入是否实际完成容量评估 | 需未来单独批准的规模实验与判据 | 固定NOT_ASSESSED；本轮无实验，不接受true/false记录 |
| performance_eligible | 是否获正式性能验收资格 | 未来独立协议/完整验收；本版只允许明确的阶段政策拒绝证据 | NOT_ASSESSED或false；任何true均拒绝 |
| production_read_authorized | 是否获生产数据读取授权 | 未来独立负责人授权流程；本版只允许明确的阶段政策拒绝证据 | NOT_ASSESSED或false；任何true均拒绝 |

初始五项均为NOT_ASSESSED、evidence=null。缺字段不等于NOT_ASSESSED，直接拒绝。
检查未执行不能填写false；false必须是实际资源/数据校验失败，或明确的政策DENIED。
最后两项的DENIED不是“检查失败”，而是当前阶段明确不授予资格/权限。
资源阈值沿用BIZ03预检数值，但没有修改其协议、Environment或授权。没有执行资源探针。

## 证据与转换

每份文档绑定commit SHA与dataset SHA256，严格字段集合；已评估状态携带schema_version、
对应field、相同源码/数据集身份、类型化payload及规范JSON SHA256。
资源成功/失败由观测值自动推导，不能另外声称true；数据结果必须为严格bool且带版本和
manifest摘要；政策只接受本版DENIED及审批边界引用摘要。布尔数值1/0、未知字段、
错误版本/身份/摘要、无证据、矛盾结果全部拒绝。

transition复制输入，只允许一个NOT_ASSESSED字段变为带证据bool，其他字段逐项保留；
revision恰好+1，previous_sha256绑定原文档。validate_transition再次核对前后状态。
已评估字段不能覆盖、清空或改回NOT_ASSESSED；重新评估须另立快照/将来的版本协议，
本轮不实现刷新、重试、生产准入或权限恢复。新初始文档不证明此前没有其他历史，
本纯函数也不是持久审计账本。

证据hash是内容完整性/引用身份，不是签名、检查执行证明或授权凭证。调用方必须保留
实际资源观测、04-B校验回执/manifest或负责人政策原件并核对出处；不能把自行构造的
JSON当作已执行检查。此模块不生成这些事实、不读取其外部来源，也不消费合同来执行高风险
操作。未来实际采集和证据归档的集成需要另行任务；没有把该缺口伪装为可信授权链。
旧BIZ03 capacity_ready固定false是历史安全/验收边界，不代表机器不足，禁止用它推导新字段。

## 验证与交付

新增离线测试覆盖：全未评估、资源/数据成功和失败、政策拒绝、独立性、缺字段/证据、
身份/hash错误、数值冒充bool、未知版本/字段、错误转换、复写、取消评估及越权true。
相关04-A/04-B/BIZ03、安全工作流及CI-OPT-01合同原断言保留。
执行命令：

```text
python -m pytest tests/unit/test_biz_perf_04_c.py tests/unit/test_biz_perf_04_b.py tests/unit/test_biz_perf_04_a.py tests/unit/test_biz_perf_03_b_once.py tests/unit/test_biz_perf_03_b_archive.py tests/unit/test_business_recalc_measure.py tests/unit/test_business_candidate_observer.py tests/unit/test_a4_ci_governance.py tests/unit/test_ci_opt_01.py -q
python -m ruff check backend tests migrations scripts
git diff --check
```

最终统计与JUnit摘要见biz_perf_04_c_validation.json。普通CI推送后自动执行，最终结论按
精确提交/Run核查，不为追填文档自身SHA再提交。本轮没有资源/容量测量、PG/Worker、
大规模生成、业务库/凭据访问、Environment/Secrets/Variables/Reviewer变更或实验dispatch。
旧协议、04-A/04-B实现和历史工件不变；04-C交付后REVIEW_PENDING，04-D～F未授权。
