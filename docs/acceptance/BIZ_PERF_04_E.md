# BIZ-PERF-04-E 统一证据合同

2026-11-06。实施前master、HEAD、origin/master与GitHub master均为
`946db5679a9cb2b7c12d9bd8ca035fe0f26f4bd8`，工作区CLEAN。
负责人最新请求“根据任务书进行修改，推代码”明确授权本轮实现和master提交推送；
优先于附件末尾的默认禁止自动提交。04-F、实验与生产操作仍未授权。

## 前置门禁

仅在以下同SHA的四条工作流全部completed/success后创建04-E源码：

| Workflow | Run |
| --- | --- |
| CI | [42156606243](https://github.com/sssssssssh/ssh_stock/actions/runs/42156606243) |
| A4-2 | [42156606260](https://github.com/sssssssssh/ssh_stock/actions/runs/42156606260) |
| Publication V1.3 | [42156606217](https://github.com/sssssssssh/ssh_stock/actions/runs/42156606217) |
| A4-1 | [42156606225](https://github.com/sssssssssh/ssh_stock/actions/runs/42156606225) |

这仅满足修改前置条件，不是本轮新提交的工程验收或任何性能验收。
skipped的实验Job没有被算作passed；本轮没有dispatch或rerun。

## 真实安装原件

04-D [Run 42156106471](https://github.com/sssssssssh/ssh_stock/actions/runs/42156106471)
为workflow_dispatch/master/attempt 1，completed/success；安装代码SHA
`ab5e29df5aa230076069dd587557720c2db382dc`，installation Job 127690531459。
Artifact 13474492280、5605 bytes，归档ZIP的SHA256为
`735addf5df05b36eba923ac4d8cbb257c8fafceb05a069c687ffba1fa67b0a13`。
已实际下载原件，逐字节校对任务书四份摘要；没有手工重建安装JSON。

原件及固定索引在[biz_perf_04_d_runs/42156106471](biz_perf_04_d_runs/42156106471/artifact-index.json)。
不归档ZIP、私有pip report、命令日志、wheelhouse、venv或凭据。
receipt中COMPLETE/VERIFIED/true、七阶段PASS；CPython3.12.14/Linux x86_64/64bit/glibc2.39；
67个发行包、pip check及148项合同测试均成功。pip25.0.1只作为工具链，不计入67包。

原始runtime/dependency/tests没有独立Run字段，不能为满足表面字段一致而篡改原件。
四份原件通过同一GitHub工件来源、逐文件固定摘要及artifact-index绑定receipt的
Run/Attempt/target SHA；索引不凭空补造四份原件不存在的字段。
历史离线validation.json的false/NOT_VERIFIED保持原样；当前真实安装结论以本Run为准。
负责人最终验收仍REVIEW_PENDING，不自动标记04-D DONE。

## 固定合同及摘要

新模块`scripts/business_evidence_bundle.py`仅使用标准库，不导入业务应用，
不读环境变量或私有文件，不联网、不执行子进程、数据库、Worker或数据生成。
这是固定历史证据索引的v1，不是可任意注册新证据的控制器或授权账本。

- manifest版本：`biz-perf-04-e.evidence-bundle.v1`。
- 报告版本：`biz-perf-04-e.validation.v1`。
- manifest顶层严格为schema/evidence/bundle_sha256；恰好12项且顺序、路径、类型、
  源提交、阶段和claim_scope固定。evidence条目严格为stage/evidence_kind/schema/
  source_commit_sha/path/sha256/claim_scope，未知字段包括嵌套声明一律拒绝。
- claim_scope包含supports字符串与excludes枚举列表；每项只表达所属阶段有限事实。
- JSON无schema字段的原件使用`installation-*.fields.v1`作为外部结构标识，
  不声称给原件新增了schema。Markdown使用markdown.v1并钉住原字节。
- JSON规范摘要为`json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")`；
  bundle_sha256只排除其自身字段。逐文件SHA256始终基于原始字节。
- 原A/B/C文档和JSON、D锁及四份原件还钉住历史字节摘要；即使修改证据后重算清单摘要，
  也不能改写历史。新增Run、声明或阶段须独立审阅新版本，不原地替换v1历史集合。
- schema、字段/严格类型、A UNKNOWN、B四档行数/合成边界、C零执行、
  D运行身份/七阶段/平台/67包版本与wheel摘要/148项测试均复核。
- A/B/C源码SHA、D锁实现SHA及D实际安装SHA分别保留，不合并成一个“最新SHA”。
  B数据集摘要不是C状态合同输入身份；不要求未归档的大JSONL存在。
- 不生成虚假的04-C全量状态文档；资源/容量/性能资格/生产授权仍未评估，
  通过excludes明确保留NOT_ASSESSED语义。

## 输入输出边界

```text
python -m scripts.business_evidence_bundle --root . --manifest docs/acceptance/biz_perf_04_e_bundle.json --report docs/acceptance/biz_perf_04_e_validation.json
```

仅接受上述固定manifest及report相对路径，避免把私有输入当manifest读取或覆盖锁文件。
POSIX路径必须在root内，拒绝绝对路径、反斜线、穿越、空路径段、symlink/junction和非普通文件。
manifest上限64KiB、单证据1MiB、JSON深度32、条目固定12；拒绝重复键、NaN/Infinity、
浮点溢出和损坏编码；打开前及FD读取后检查类型、身份、大小和修改时间。
不静默规范化历史字节、不使用Git/网络补救缺失文件；失败关闭。
报告同目录独占临时文件、flush/fsync、os.replace原子替换；校验或替换失败不覆盖旧有效报告。
成功报告无时间戳，重复执行字节相同；调用者修改返回值不影响后续校验政策。

Windows core.autocrlf可能把历史LF改为CRLF，原始字节校验应拒绝该副本。
请使用干净Linux/LF checkout；本轮本地测试使用Git原始blob逐字节核对的LF副本，
并明确标记实际执行平台仍为Windows，不把换行副本冒充Linux。
没有修改.gitattributes、旧文件字节或全局Git配置。

## 报告与非声明项

[固定证据包](biz_perf_04_e_bundle.json)及[可复算报告](biz_perf_04_e_validation.json)
仅报告integrity=VALID、bundle摘要、证据路径/字节摘要和各阶段有限范围。
明确包含PERFORMANCE_ACCEPTANCE_NOT_CLAIMED、CAPACITY_ACCEPTANCE_NOT_CLAIMED、
PRODUCTION_READ_AUTHORIZATION_NOT_CLAIMED、BUSINESS_DATABASE_EXECUTION_NOT_PERFORMED、
WORKER_EXECUTION_NOT_PERFORMED。没有all_stages_passed、ready_for_capacity、release_ready
或任何performance/capacity/production准入字段。
完整性不是来源签名、性能通过或执行授权；可信来源来自已独立核实的GitHub原始工件，
离线校验器自身不重新访问GitHub，也不证明机器或数据库当前状态。

## 本轮验证、剩余项与回滚

最终定向统计和精确提交普通CI见[执行回执](../tasks/BIZ-PERF-04-E.md)。
本机全A～E收集因旧04-B的Linux resource模块不可用而失败，原断言未修改或跳过。
新增测试及可执行A/C/D回归分别记录；不得把子集绿灯当作完整回归通过。
推送后的精确SHA普通Linux CI必须另行核查，未完成时明确PENDING。

本轮不改旧8份Workflow、白名单、旧A～D实现/测试、依赖锁、validation/manifest，
不改PRD/设计/README、业务代码、策略、SQL、Schema、迁移和部署入口。
只追加D归档说明及获准治理接续；不改变03-A/R1 PARTIAL、B0 WITHDRAWN或旧实验门槛。
回滚采用负责人批准的正常revert本轮独立提交，保留历史提交和真实原件，不强推/重写历史。
完整性能力交付后停止等待审阅，04-F与所有实验、生产或部署继续独立授权。
