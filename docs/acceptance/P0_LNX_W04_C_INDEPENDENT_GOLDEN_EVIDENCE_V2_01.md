# P0-LNX-W04-C 独立预期与离线证据 V2 交付

2026-11-10，Asia/Shanghai。任务编号
`P0_LNX_W04_C_INDEPENDENT_GOLDEN_EVIDENCE_V2_01`。

本报告记录提交前实现与验证事实，不预填尚未产生的新 SHA/CI 结果。
业务状态始终 **BUSINESS_GOLDEN_PENDING_D04 / INDEPENDENT_REVIEW_PENDING**。
本轮只交付离线证据审核层，不关闭 R1、历史监督 AC-05 或物理准入。

## 基线、来源与授权

修改前 master、HEAD、origin/master、只读实时远端均为
`e5c85c57da66f1becd3dd1ba562ee1ace71d6b3f`；工作区干净。
前序审阅的七份工件及 receipt 中的逐件 SHA256 均已重新读取并核验；
1554 个既有跟踪文件原始工作字节与前序基线一致。
先读 AGENTS，再依次读五份治理文件和相关 PRD/设计/PROJECT_RULES/README；
核对真实比较器、schema、PG 导出器、seed 配方、旧测试后才修改。

用户本次明确要求“根据任务书开发，推送代码”，授权七文件离线实现、定向验证、
master 普通提交推送及其自动普通 CI。此要求覆盖任务书的默认 Git 等待文字，
不覆盖 D04 业务签认、真实实验/数据库/Worker/环境或手动 CI 的独立限制。
不建分支、不重置、不强推，不修改 Git 全局配置。

治理指针仍保留历史 G0/CI-OPT 语境。本任务禁止修改五治理及四业务文档，
因此仅在本新增回执登记本轮事实，不顺带修订旧指针或历史验收。

## 七文件变更范围

1. `scripts/r1_reviewed_snapshot_v2.py`：标准库、内存输入、固定 NO_GO 的 V2 审核层。
2. `tests/unit/test_r1_reviewed_snapshot_v2.py`：T01～T26 及补充严格解析/身份负例。
3. `tests/fixtures/r1_reviewed_snapshot_v2/README.md`：独立草稿编写方法、语义/时间待决和信任边界。
4. 同目录 `evidence_contract_v2.json`：精确字段、类型、限制、拒绝码和分域。
5. 同目录 `scenarios_v2.json`：独立手写的观察模板、固定虚构两臂身份和 C01～C16 观察变化。
6. 同目录 `expected_oracle_v2.json`：另行手写的预期、来源、关系、拒绝码及未签字段。
7. 本新增回执。

所有既有源码/测试/schema/manifest/Workflow/锁/治理/业务配置原样。
没有 scope expansion、没有修改旧 BASELINE 或 Fake-only 入口，没有生成真实执行桥。
报告自身及最终 commit 的摘要在外部交付清单提供，避免自引用哈希循环。

## 实现与独立预期

唯一审核入口是 `review_pair(left, right, oracle_bytes, contract_bytes, expected_provenance)`。
不接文件路径、连接器、ExportResult、SQL/DSN/URL、时钟、Git 或进程句柄；
不增加 CLI/API/授权消费者，不读取磁盘、环境或业务服务。
import 白名单只有 hashlib/json/math/re/datetime/decimal/uuid。

先限制 JSON 字节/树预算、拒绝重复 key/非法数/循环，再核版本/来源/独立固定预期，
逐值检查类型和分域身份、业务引用/生命周期/哨兵，最后与独立预期逐项比较。
job/token/scope/worker/event 分域双射，候选/公开/原像/Scope 及元数据非 FK 引用均受约束。
错误只有固定 code；首错保留，失败阶段 FAIL，未执行阶段 NOT_RUN；
未安全计算的域摘要为 NOT_COMPUTED。未知 ACK、心跳、清理和哨兵不产生可用样本。

四域使用不同 NUL 结尾前缀及 u64be 长度封帧；header 绑定协议、完整来源、
schema/工具/Golden/fixture、case、arm、input_ref 和 subject：

- RAW_INPUT 只是非认证描述，不冒充数据库原始行。
- TYPED_OUTPUT 保留本臂原 typed 投影和哨兵，包括原身份与呈现顺序。
- BUSINESS_EXPECTATION 绑定 canonical 实际投影与独立预期，不只核两臂互等。
- TELEMETRY 单独记录，不混入业务值，不构成 OS/资源证明。

每输入至多 1MiB、20,000 树节点、深度24、单文本2048字符、每容器256项、
每臂128投影行、每身份域16组。编码和排序处理有这些前置上限；
不声称 OS RSS 硬限制，不扩大旧导出器10,000行/64MiB边界。

本版仅是人工语义投影，不重写37表520列比较器。8～11条小型投影不代表完整ORM行、
全部输出、实库类型、完整schema、生产金融计算或整库无越界写入。
老比较器/导出器仍分别只接受历史 SYNTHETIC_ONLY/FAKE 证据。

### Golden 的独立性与 D04

预期文件由 Codex 逐项手写虚构值和自然语言依据，未调用新旧 encoder/comparator、
旧 golden()/seed/ORM/default/schema 生成器来生成预期，也没有从观察文件复制生成预期。
同一文件的手写 base_rows 和显式 case 行替换仅减少重复文字，不引用观察包或运行结果。
三个 JSON 的 LF/完整 CRLF 原字节摘要在新测试独立固定，不能修改两臂与草稿再自行重签。

`authorship=CODEX_MANUAL_DRAFT_NOT_OWNER_APPROVAL`、`approval=PENDING_D04`、
`reviewer=NOT_SIGNED` 全部保留。冻结合同关系可以得到草稿级 OFFLINE_ORACLE_MATCH；
每个结果另有 `business_golden_status=PENDING_OWNER_DECISION`，不表示 owner 验收。
C11 的候选事件映射返回 PENDING_OWNER_DECISION，而不是借匹配结果填 APPROVED。

真实 D04 仍缺：一次快照/逐臂映射选择；五个 seed 时间列冻结值及影响；
49时间源及事件复制/精度/次序/歧义策略；序列与完整业务Golden的独立签认。
两股 SZSE 的历史局部澄清不是这些规则的全部批准。
源码、schema、工具和输入摘要相符是完整性事实；调用方自己控制所有 provenance
不能凭纯数据函数得到独立真实性，任何输出仍不签发权限。

### C01～C16 与 T01～T26

C01成功、C02失败、C03取消、C05首次原像、C06删除、C07多重Scope、
C08 FK/非FK/sector/theme、C09精确类型、C10七种空/缺/零语义：9项草稿级离线匹配。
C04未知ACK、C12哨兵未知、C13范围外变化、C15来源漂移、C16清理未知：5项INCOMPLETE。
C14两臂同时把1.25改成1.5但独立预期不变：UNEQUAL。
C11候选UTC事件双射：PENDING_OWNER_DECISION。每项来源/含义/列/预期码见独立JSON和README。

新 unittest 中 `test_T01_...` 至 `test_T26_...` 对应任务书矩阵；补充方法覆盖
大小写/旧版本、坏JSON/大整数、反序/多对一/跨域碰撞。
包括真实旧包/v2双向拒绝、PG_TYPED_UNVERIFIED→旧Fake拒绝、双重来源漂移、
同错相等、七空值全排列、Decimal scale/float负零、未知状态、超限/隐私和隔离import。

## RED、GREEN 和本地环境事实

解释器为本机现成 Windows CPython3.12.7。未安装/升级任何依赖。
本机 pytest7.4.4不是锁定目标版本，本轮选择任务书允许的标准库 unittest，
未禁用/改写原 pytest 插件或用旧 pytest 冒充目标验收。

| 检查 | 实际结果 |
|---|---|
| 初始 RED | T02/T06/T12 共3项，3 errors、exit1；均在fixture读取前因V2模块缺失失败 |
| 初始 GREEN | 相同3项全部通过，exit0 |
| 扩展首轮 | 29顶层：28通过、1失败；节点预算测试误构造约一万节点，未达到两万上限 |
| 扩展修正 | 只增加该新负例的数据规模至超过20,000节点，未提高上限或降低断言；29项通过 |
| 新模块最终定向 | 29顶层通过，0失败/错误/跳过；完整日志与实际subtest统计见外部最终回执 |
| 工作副本旧指定回归 | 27顶层执行，1 failure、29 error事件（含subTest），exit1；均受冻结schema CRLF拒绝影响 |
| 原始Git blob指定回归 | 27顶层通过，0失败/错误/跳过；66.411秒，exit0 |
| 相关R1纯离线最终组合 | 12模块、129顶层通过、1796个成功subTest，0失败/错误/跳过，143.609秒、exit0；包含上述单跑，不重复累计 |
| py_compile/JSON/范围 | 两个新Python编译至仓库外；三个JSON解析；1554原件SHA256检查；diff空白检查通过 |
| 本机Ruff | 模块未安装，命令exit1：No module named ruff；不安装，须由新SHA普通Linux CI核验 |
| 全量本机pytest/PG17/前端/Compose | NOT_RUN；本任务不授权本机这些真实运行，仅允许既有自动工程CI |

首次测试母本不修改旧断言。工作副本schema的原始字节SHA256为
`e023206e7209ff96ebeb0417dbd516a061c9dc58aee4bf98e9f63fc84e04ea47`，
是Git原始LF blob（`f6be0a5d…f297`）完整CRLF表示。
旧load_schema按原始字节核查并拒绝，不能改旧代码刷绿。

先尝试的外部git archive副本也受本机checkout转换而带CRLF，旧回归同样失败，原日志保留。
随后改用 `git cat-file --batch` 直接读取固定HEAD的1554个不可变blob，逐个校验并写入新的
仓库外验证目录；没有运行时换行归一化、修改旧hash或覆盖工作树。
只将本轮新增文件原样复制进去。该副本的旧指定回归通过，平台仍为Windows，
不能称Linux/PG17通过；原失败也不删除或改为skip。

外部组合运行器首轮未采用unittest discovery的同目录搜索路径：113顶层、
1781成功subTest、0断言失败/4导入错误，exit1。三个旧模块使用bare sibling import，
另一个组合用例受其连带影响。只对仓库外运行器补上discovery等价的tests/unit搜索路径，
没有修改旧测试或业务导入。该失败日志保留，修正运行器后的最终129/1796完整组合全通过。
最终组合日志为offline-combination-discovery-path.log，统计JSON同名；初轮另存不覆盖。

完整命令/退出码/时间、原始RED/各次日志、raw-blob来源索引及新增/原件摘要保存在仓库外
本任务独立证据目录。这里只保留相对工件名，不提交本机绝对路径、缓存/pyc/归档或秘密。

```text
python -B -m unittest tests.unit.test_r1_reviewed_snapshot_v2 -v
python -B -m unittest tests.unit.test_r1_business_snapshot_contract tests.unit.test_r1_integration_pg_export -v
python -B <external>/run_offline.py
python -B -m ruff check backend tests migrations scripts
git diff --check
```

## AC01～AC18 对照

| AC | 状态/证据 |
|---|---|
| AC01 | 基线与实时远端同e5c85c57，CLEAN；不继承旧SHA工程成绩 |
| AC02 | 仅七新增路径，1554原跟踪文件SHA256不变 |
| AC03 | 标准库import白名单；隔离解释器中阻断文件/env/socket/进程API后import成功，无app模块污染 |
| AC04 | contract精确字段、版本、枚举、递归类型/预算/重复key拒绝 |
| AC05 | 8项关键旧边界固定LF/CRLF字节；全部原件另有1554项范围校验；旧拒绝入口实测 |
| AC06 | 观察/预期独立手写；固定JSON字节；同错/自批准反例；owner NOT_SIGNED |
| AC07 | 16场景完整，三终态与UNKNOWN明确；不是实际Root样本 |
| AC08 | 基线3项RED→同3GREEN；29项最终负例/正例；不是声称26方法均先在旧实现独立失败 |
| AC09 | 七空值、Decimal scale、float负零/有限性、UTC和事件双射、摘要分域 |
| AC10 | projected job/token/source/candidate/public/preimage/scope/FK及JSON/sector/theme闭包 |
| AC11 | 哨兵与范围外证据槽是OFFLINE_ASSERTED，物理始终NOT_PROVEN；未知/漂移拒绝 |
| AC12 | 固定单错误码、有界树/结果、无原行/异常repr回显 |
| AC13 | R1/历史监督AC-05 PARTIAL，G01～G12无任何授权升级 |
| AC14 | BUSINESS_GOLDEN_PENDING_D04；C11及每结果总体业务门禁仍PENDING_OWNER_DECISION |
| AC15 | 新定向/旧纯离线回归及静态如实分环境；本机Ruff明确ENV_BLOCKED |
| AC16 | 新SHA普通CI提交后独立核验；本报告提交前CI_PENDING，不预填成功 |
| AC17 | 本机真实PG/Worker/OFF-ON/云端/部署/手动Workflow计数均0 |
| AC18 | 交付后独立代码审阅；不自动进入B/D/G1/04-F，不代owner签认 |

## 门禁、Git交付与下一步

G01 NOT_AUTHORIZED；G02/G04/G05物理证据仍BLOCKED；G03/G06/G08/G09/G11/G12 PARTIAL；
G07/G10外部监督与持久权威仍NOT_PROVEN。普通工程CI即使通过也不提升这些门禁。
Windows原生OFF异常根因UNKNOWN、三对NOT_RUN、≤3% NOT_VERIFIED保持。

本次允许普通master提交推送；仅暂存七文件。提交前检查完整diff/numstat/空白、原件摘要、
fixture锚点、路径与敏感输出。实际完整提交、远端对齐及精确Run/attempt/jobs/artifacts
写仓库外最终回执并在交付对话提供，不为追填本文自身SHA反复提交。
不手动dispatch/rerun，不调整Workflow/Environment/Secrets/权限或改冻结文件凑通过。

```text
TASK=P0_LNX_W04_C_INDEPENDENT_GOLDEN_EVIDENCE_V2_01
BASELINE_SHA=e5c85c57da66f1becd3dd1ba562ee1ace71d6b3f
BRANCH=master
FROZEN_FILES_CHANGED=0
OLD_BASELINE_CHANGED=false
REAL_EXECUTION_BRIDGE_CHANGED=false
SCHEMA_VERSION=r1.reviewed-evidence.v2
GOLDEN_OWNER_APPROVAL=PENDING_D04
BUSINESS_GOLDEN=BUSINESS_GOLDEN_PENDING_D04
SOURCE_REVIEW=PENDING_INDEPENDENT_REVIEW
MAIN_CI=CI_PENDING_AT_PRECOMMIT_REPORT
R1=PARTIAL
HISTORICAL_AC05=PARTIAL
G1=NOT_AUTHORIZED
W04_B=NO_NEW_INCREMENT_AUTHORIZED
W04_D=NOT_AUTHORIZED
BIZ_PERF_04_F=NOT_STARTED
REAL_PG17_WORKER_OFF_ON=NO_GO
PERFORMANCE_ACCEPTANCE=NOT_MEASURED
REAL_PG_CONNECTIONS=0
WORKER_RUNS=0
OFF_ON_PAIRS=0
WORKFLOW_DISPATCHES_OR_RERUNS=0
NEXT=CHATGPT_INDEPENDENT_CODE_REVIEW
```

W04-B已有历史部分实现，不能用模板NOT_STARTED抹去；本轮没有启动其新增切片。
功能/离线工程交付、业务Golden签认、独立代码审阅和物理验证分别验收。
回退仅能在另行批准后撤回本次明确新增文件，不重写历史、不清理用户数据或旧证据。
