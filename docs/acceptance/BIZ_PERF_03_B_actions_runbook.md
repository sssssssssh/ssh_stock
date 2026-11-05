# BIZ-PERF-03-B Actions 环境适配：等待审阅，不执行实验

## 2026-11-05 最小修正：Action 固定与归档期限

本次修改前已核实 master/HEAD/origin/master/实时远端一致为
`de7081a77567081a8c31a41a8960455cbd2d874e`，clean。
仅固定第七 Workflow 的外部 Action，并修复 controller 的清理→归档切换及导出期限。
不恢复 B0，不修改原六份 Workflow、业务/SQL/模型/迁移、冻结实验协议、数据或五个开关。
Environment/reviewer/Variables/Secrets 未操作；真实性能 dispatch、容器/数据库及根任务均未执行。

下列 SHA 于 2026-11-05 使用官方仓库的 `git ls-remote refs/tags/...` 取得，并逐一核实官方 commit 页面。
标签仅记录核查来源；Workflow 实际使用完整 40 位 commit，不再跟随标签漂移。

| Action | 核查标签 | 固定 commit / 官方来源 |
| --- | --- | --- |
| actions/checkout | v4 | [11d5960a326750d5838078e36cf38b85af677262](https://github.com/actions/checkout/commit/11d5960a326750d5838078e36cf38b85af677262) |
| actions/setup-python | v5 | [a26af69be951a213d495a4c3e4e4022e16d87065](https://github.com/actions/setup-python/commit/a26af69be951a213d495a4c3e4e4022e16d87065) |
| actions/upload-artifact（两处） | v4 | [ea165f8d65b6e75b540449e92b4886f43607fa02](https://github.com/actions/upload-artifact/commit/ea165f8d65b6e75b540449e92b4886f43607fa02) |

预算数字及协议文件不变：初始化≤T0+180，根截止=min(root_started+180,T0+330)，
清理≤60秒且≤T0+390；归档截止=min(cleanup_finished+30,T0+420)，达到归档截止即停止。
清理记录实际完成时间后，在最终证据I/O前立即替换 watchdog；旧阶段已排队的alarm按当前
有效deadline复核，不得提前中断归档。清理和归档不扣旧的3秒提前量。
初始化/根阶段原有3秒终止余量保留，重复归档检查不能续期。`--check-export` 复用收据中的
相同截止点，不能获得第二个30秒窗口；超时不继续写新工件、不公布可用的完整导出结果。
最终上传额外要求 export 步骤 outcome=success，阻断“输出已写出但步骤随后超时”的路径。
平台7分钟兜底、原始提前上传的INCOMPLETE前缀仍保留；Runner丢失/平台硬取消和实际网络上传
未实机验证，不能用离线通过宣称最终工件一定可用或真实性能验收完成。

新增 `tests/unit/test_biz_perf_03_b_archive.py`：27项通过，包括官方pin/负例、389/390清理、
419归档、420拒绝、提前清理仅30秒、重复进入不续期、清理失败、归档中途/输出后超时及
controller收尾和延迟送达的旧alarm。此前先RED复现9项缺口；原测试未改断言、未跳过，70%门槛不变。
另一次原治理合同和当时20项新用例合计117通过；新文件最终27项单独通过，不能把重叠用例相加。
本机Windows一次合跑（当时19项新例+95项旧BIZ）105通过/9项POSIX接口缺失（getuid/getpgid/killpg/getitimer）；
不放宽这些旧测试，使用普通Linux CI验收。Ruff全范围与diff检查通过，最终SHA普通CI在推送后核验。
基线de7081a7的主CI41888520120及A4-1/A4-2/Publication均success，仅为修改前工程证据。
此处是提交前快照，不为追填自身最终SHA或CI状态循环提交；新版本结果以实际同SHA Actions为准。
本次交付后停止等待负责人审阅，不dispatch、不自动重试实验。

## 第一阶段历史记录（以下保留原证据语境）

2026-11-05。实施前 master 为 `b27fa109530002f2cddbb1a4c28b356bad11b398`，clean。
负责人批准第一阶段环境适配、离线合同、master 提交推送与普通 CI；没有批准
创建/修改 GitHub Environment、reviewer、Secrets、Variables，也没有批准 dispatch。
W00/W01 已获审阅通过；上次本机预检 RESOURCE_DEFERRED，根任务尝试0次。

## 本阶段范围

新增 `biz-perf-03-b-once.yml`，仅 workflow_dispatch，标准 ubuntu-24.04 x64，一个 Job，
7分钟平台兜底，与历史昂贵实验共享 `ssh-stock-a4-expensive`、不取消在途执行。
原六份 Workflow、旧授权 policy/协议/manifest、CI-OPT-01分流、串行完整 pytest、
70%覆盖率、业务源码/SQL/模型/迁移/配置不变。仅精确扩展旧 Workflow 清单，未知第八个仍拒绝。

本入口是 DIAGNOSTIC_ONLY，不授予 W02、容量、G1、生产、恢复或部署资格。
既有 observer 测试失败继续 UNKNOWN；本阶段不修复它，不以普通 CI 成功代替本实验。

旧CI-OPT-01的T11冻结登记只同步增加已批准的inventory函数名；对应新反向AST合同把这次精确
增量剥离后逐字核对原函数结构，原六份清单检查不变，未登记改动继续拒绝。

## 冻结协议

机器协议：`biz_perf_03_b_actions_once_protocol.json`。
固定4股、2025-01-01至2025-01-31、原900自然日种子、预期实际 Raw daily=2660、硬上限5000。
保留250个交易日预热、430自然日回看、原金融计算/身份、500行候选批次和原子发布。
FACTOR_INPUT_REUSE_ENABLED、RAW_PREFLIGHT_BATCH_ENABLED、FACTOR_CPU_OPTIMIZATION_ENABLED、
AB_MERGE_READ_ENABLED、PERF_DIAGNOSTICS_ENABLED 均必须为 false；不允许提供优化/重试/放宽输入。

PG17镜像固定为协议中的 linux/amd64 manifest digest。摘要由官方 Docker Hub 的 postgres:17
只读 tag API取得；本轮未拉取镜像、运行容器或验证其实际小版本，后续仍需实际major17核验。
Python固定3.12.14，requirements.lock不修改。记录完整解析版本；22个直接包锁定不等于所有
传递依赖/wheel hash均锁定，依赖安装失败不重试、不自行升级。

绝对T0在Job第一个受控步骤记录，checkout、setup-python、prefix上传、依赖安装、PG准备、
迁移/种子均计入初始化180秒。根任务≤180秒且绝对不晚于T0+330，清理≤60秒且不晚于T0+390；
最后保留最多30秒证据归档，总计≤420秒。初始化/根阶段父进程提前3秒进入终止，
清理与归档按上方最小修正的独立deadline切换，避免旧定时器提前终止归档。
若准备花满180秒，剩余根预算更短；不因此缩小数据或追加试验。平台硬取消/Runner丢失时
最终工件无法保证存在，只能保留先前prefix并判INCOMPLETE，不能用always宣称证据完整。

## 隔离与复用

controller不导入业务应用；先校验仓库/master/精确SHA、clean、受保护allowed_run_id和协议，
从公共GitHub元数据核验Environment配置。保护不足或接口不可得即拒绝，不能降级。
使用现有PG action的命名/标签规范，但创建分支受父进程监督、固定digest、显式自有卷、
`--network none`且不发布host端口，原action文件不改。

新PGDATA/容器属于当前run/attempt/job；容器内pg_controldata的system_identifier与服务器值、
UUID marker、major17交叉核验。复用 verified_test_url / isolated_v14_database，随后原Alembic
升级自有UUID子库。既有业务库、宿主默认库、生产dump/卷/凭据都不输入。

测量子进程经sudo/nsenter只进入该自有容器的network namespace，setpriv降为Runner原UID/GID，
清除附加组/能力并禁止新增权限；没有继承网络FD，环境白名单不带GitHub token/业务Secrets。
该namespace只有loopback；业务连接只到127.0.0.1:5432。controller/上传留在宿主网络。
新Runtime隔离未实机验证，权限/能力不满足必须 RESOURCE_DEFERRED，不能退回普通bridge网络。

复用原 business_recalc_measure.py 的种子与真实create→claim→execute_claimed_job，
独立单次模式增加阶段通知/真实行数/开关校验、安全失败前缀；原默认命令行为保留。
CandidateObserver原样使用；只采实际定时查询计划，本模式不执行旧发布后EXPLAIN回放。
SQL/FETCH不是纯服务器/网络时间，inclusive阶段不能相加，未知值不填0。

## 后续由负责人配置的Environment（本轮没有执行）

1. 在仓库 Settings创建 `biz-perf-03-b-once`，不要添加任何业务Secrets。
2. Required reviewers至少1名独立审阅者，Prevent self-review开启，禁止管理员绕过。
3. Deployment branches选custom，唯一branch规则为master，不允许tag或通配符。
4. Environment Variables设置 `BIZ03_ALLOWED_SHA` 为最终获审完整infra提交SHA，
   `BIZ03_PROTOCOL_SHA256` 为该提交协议文件的SHA256。不能填写旧b27fa109作为新增Workflow的SHA。
5. 最终运行另外批准后，只dispatch一次；Job等待审批时核对Run ID并把
   `BIZ03_ALLOWED_RUN_ID` 设置为该唯一数字ID，然后批准该Run。切勿先批准再补配置。
   空值/别的ID/重复run_attempt均拒绝。防自审意味着触发者不能担任该Run审批者。

变量在进入Environment后的guard步骤读取，不在Job级提前展开；这是为避免环境变量在Runner
启动后才可用导致空值/旧值。不要在仓库或组织层同名配置变量。实际可用性仍待单独获批的Run验证。

三项变量不是生产秘密，不放入旧A4协议、不复用已消费协议ID。它们不由脚本自动写入。
当前代码没有GitHub写接口或自动dispatch逻辑；只读contents权限。
run_attempt=1只防rerun，真正限制全新dispatch的是受保护的唯一allowed_run_id。
重新授权其他Run ID必须由负责人另行裁决，不能为了通过而循环改值。

## 手动运行说明（仅最终另行批准后）

先核验普通CI实际结果和已知observer风险，再审阅精确SHA及协议hash。
在Actions选择 **BIZ-PERF-03-B one-shot evidence**、master，填写：

- target_sha：最终获审完整40位infra提交SHA；
- protocol_id：`biz-perf-03-b.actions-once.v1`；
- protocol_sha256：该提交的协议文件SHA256；
- confirm_once：true；
- run_reason：获审理由，不包含凭据。

不要选择旧CI的capacity/a4231，不能用rerun或矩阵替代本Run；不用本命令开启其他开关。
严格校验当前远端master仍为目标SHA，任何源码漂移须停止重新审阅。
只允许一个完整根任务，无自动重试。失败或超限保留结果后停止。

## 证据、失败与清理

公开输出目录只含：receipt、source、resources、dependencies、physical、measurement、manifest JSON。
父/子内部状态、进程stdout/stderr、原始Job.error_message、SQL/参数、环境全文、PGDATA和dump不上传。
指标为计时/计数/哈希/计划结构/根状态；prefix预先上传，最终工件按SHA/run/attempt独立命名、保留7天，
总量≤10MiB。未知终态不猜测为FAILED、CANCELLED、ABORTED或SUCCESS。

失败时首错sticky；先停止仅由本controller创建的进程组，再复核run/attempt/job/purpose标签，
删除自有容器与事前登记的卷，不执行prune或全局清理。所有清理也受绝对期限保护。
标签漂移/超时/权限/磁盘故障可导致CLEANUP_INCOMPLETE，不算通过；临时VM销毁不冒充已验证清理。

只有恰好一次完整SUCCESS/PUBLISHED、来源/输入/输出/隔离证据齐全、清理完整，才记
COMPLETE_DIAGNOSTIC_ONLY，仍没有提速/正式容量/生产资格。本阶段真实运行是NOT_RUN。

## 回滚

本阶段不部署、不启用业务开关、不修改数据库结构。审阅不通过时，用新revert撤销本次
基础设施与对应精确清单扩展，保留历史提交/协议/失败证据，不reset/强推。
若负责人以后已配置新Environment，是否删除/停用它及其变量由负责人另行决定，本脚本不操作设置。
将来若实验正在执行，先等待其有界收尾并核验清理，不热换源码或自动重跑。

## 第一阶段验证回执

离线主回归255 passed，Ruff全范围及diff检查通过；进程组后代残留和失败前缀丢计数先RED后修复。
扩展旧合同213 passed/3个A4235_DIRTY_TREE，后者要求提交后clean源身份，不能在工作区伪造通过。
提交后仅复核这三项，最终结果见交付回执；普通CI状态以实际同SHA Actions为准，不追填文档自身SHA。
原始JUnit摘要及测试源码指纹见 [离线验证记录](biz_perf_03_b_actions_offline_verification.json)。
本阶段只运行离线测试；没有新Environment写操作、性能dispatch、PG容器或合成根任务。
GitHub实机、PG image内库能力、namespace降权、冷启动预算和真实根结果均保持NOT_RUN。
