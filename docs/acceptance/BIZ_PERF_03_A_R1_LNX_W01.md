# BIZ-PERF-03-A-R1-LNX-W01 离线工具交付

## REV1 当前整改回执（2026-11-07）

负责人明确批准：**批准 REV1 实施及限定离线测试**。
当前状态 **REV1_IMPLEMENTED_LOCAL_REVIEW_PENDING / NO_COMMIT_NO_PUSH**。
基线仍为 `eb8cfe7d2ddb04a12f969b8a65e2e952e7165510`；已有七份W01文件与审阅ZIP
逐字节一致后开始整改。另有负责人此前要求生成的 `p0-lnx-w01-review.zip`，本轮不修改、
重打包、删除或提交；其SHA256为
`61796447f031bb9d3a8e312ad4ef14281c048f86ac27428719d98ee8ae43ab67`。
下方原W01的177项记录是历史结果，不替代本轮整改验证。

### 缺陷与 RED → GREEN

先只添加REV1负例，未改工具实现，执行原三份新unit文件、`-k rev1 --tb=short`：
**21 failed、5 passed、177 deselected，0.30秒，退出1**。
其中20个失败确认五类伪失败终态被validate/seal/unseal/parity接受；5个statistics用例
原本已拒绝，不把它们写成新修复。另1个失败复现post-link读取错误后磁盘残留可自校验的
COMPLETE_MOCK候选。没有执行PG或真实根任务。

初步修复后全范围203通过；补充发布/确认/状态和期限注入后227通过。该轮Ruff的1处行长
和1处import排序已修正。扩展后的本轮三文件验证为 **233 passed、0 failed/errors/skipped，
3.61秒，退出0**，定向Ruff通过。最后仅整理本轮新增测试位置，交付前同范围再确认，
以会话最终输出为准；不累计重复测试次数。

| 测试组 | 本轮节点 | 相对原ZIP |
| --- | ---: | ---: |
| contract | 118 | +40 |
| supervisor | 72 | +16 |
| parity | 43 | 不变 |
| 合计 | 233 | +56 |

### P1：准备 → 发布 → 独立消费确认

1. 信任发起者在监督前持有 `MockConsumptionAuthority`。`begin(run_id, arm)` 产生随机scope，
   不能传入已知scope；进程内登记scope与run/arm，scope本身不是秘密、签名或授权。
2. 先保存不可覆盖prefix；进程退出、阶段、清理及内容验证后，写入独占候选final。
3. 所有封存JSON升级为 `perf03-lnx.sealed-mock.v2`，最外层publication恒为
   `UNCONFIRMED_REQUIRES_OWNER_CONFIRMATION`。磁盘上不写“已可信确认”的标记。
4. staged/link、目录fsync、inode检查、读取、原始expected hash及内容核对，直到目录FD
   close全部返回后，才允许owner确认。`confirm`要求同一实例已有的随机scope登记、完整
   supervised回执及run/arm绑定，消费登记并签发仅存在内存中的不透明object票据。
5. **规范消费者是 `consume_final`**：必须同时提供原owner实例及其交付票据，逐字节绑定
   整个封存对象；改内容后重新计算hash也拒绝。票据验证通过后才返回可消费COMPLETE_MOCK。
   `unseal`仍可作结构/hash解码以保留旧断言，它不是发布成功判定或授权接口。
6. 发布或确认失败，撤销该scope下所有pending与ticket，即使confirm已签发但回复丢失也撤销。
   不交付票据，不覆盖/删除候选原件；原prefix及首错保留。FD close失败向调用者报错，
   外层仍撤销scope，不能消费残留候选。其他运行的scope不受影响。

因此，失败后final可能仍存在，payload也可能记载此前候选COMPLETE_MOCK、archive_verified=true；
但**单文件始终UNCONFIRMED，不能被规范消费者认定为最终成功**。archive_verified在候选中
描述准备时点的检查声明，不等于外部消费确认。不得绕过consume_final把解码结果当最终验收。
本地调用者若需后续消费，须在执行前持有owner并提供confirmations字典，成功后取得该
run/arm的独立票据。不能读取final后新建owner、begin/confirm来追认其scope；新随机scope不匹配。

内容hash仅证明字节一致，不是可信签名。该进程内信任边界假设owner及调用代码可信；
不抵御同一进程恶意修改私有状态，不实现持久签名、跨进程票据或独立服务授权。owner/票据
丢失后文件仍不可独立认证，不提供“从工件恢复认可”或自动重签路径。未来跨进程/真实适配
必须另批；四项真实资格仍固定false。

发布负例包含link前、重复final、link后fsync/check/read、外层二次读取、confirm前、confirm
发出票据后报错、消费确认故障、FD关闭故障。各路径验证prefix保留、作用域撤销及规范消费
拒绝；正常mock完成能用独立票据消费。附带首个child错误后再发生归档错误的sticky回归。

### P2：逐终态一致性

共同规则：phase与final_receipt_status一致；first_failure必须等于非空原因列表首项；
reaped必须有整数退出码与REAPED进程状态；UNCONFIRMED不能同时child_reaped；
archive_verified必须有parent_verified；父监督时间线与完成阶段列表精确对应。

| 终态 | 必须具备的对应证据 |
| --- | --- |
| COMPLETE_MOCK | 无首错、ACK、exit0、cleanup COMPLETE；父验证版本须三阶段时间线完整、子已reap及archive检查；最终消费还须独立票据 |
| INCOMPLETE | 无首错仅允许未启动prefix，或合法UNKNOWN_ACK；有首错须为父中断并有监督证据 |
| TIMED_OUT | 非空超时原因、父监督及时间线；至少一次截止超限或已完成阶段后的退出超过截止 |
| CRASHED | CHILD_EXIT原因、异常模拟/信号退出码、父确认reap、非完整业务cleanup；exit0拒绝 |
| FAILED | 非空已知首个工具故障、父监督；单独CHILD_EXIT还须非零退出；不与业务FAILED/ABORTED混淆 |
| CLEANUP_UNCERTAIN | cleanup INCOMPLETE；有明确cleanup失败，或process UNCONFIRMED且未reap |
| EVIDENCE_UNAVAILABLE | 明确证据失败原因、archive_verified=false、父监督；此前首错仍保留 |

失败状态本身不构成失败证据；仅改phase/final标签不再通过。合法未启动prefix、成功、失败、
取消、UNKNOWN_ACK正例仍通过；unknown ACK不能进三对统计。seal/unseal、parity/statistics
均调用新约束；不同工具phase或cleanup状态不能被parity当作同一结果。

### 监督期限边界

**AC-05 = PARTIAL / HARD_BLOCKING_IO_NOT_COVERED**。
已覆盖子进程已启动后的阶段轮询、无进度、超时回收及启动前截止检查；没有实现对同步
Popen、read/check/fsync、close或归档调用自身的内核级抢占。新增短时mock注入分别在
Popen、prefix写入、fsync停留25ms，而setup期限为10ms，证明检查只能在调用返回后继续；
这不是硬超时通过，也不触发任何真实数据库。目录I/O故障注入与硬I/O期限是不同证据。
真实Linux运行前必须独立解决启动及阻塞I/O的硬监督缺口，不能用233项mock通过代替。

### 范围、差异及下一步

本轮实际修改contract、supervisor、其对应两份unit测试及本文；mock_child和parity测试原字节
保留。旧测试函数/断言未删改或跳过，新增负例追加；通过与审阅ZIP对照核验。
所有原tracked源码、Workflow、配置、锁、治理文档及四份历史JSON保持原样。
原ZIP是REV1前的审阅快照，不能冒充本轮整改包；本轮没有重新生成ZIP。

按原三份unit测试执行定向pytest（默认安全插件保留），按原六份Python文件执行Ruff；
对七文件做no-index空白检查和与ZIP的逐文件Diff核对。不git add/commit/push，不运行
完整/集成pytest、安装、PG、Worker、root_arm、真实OFF/ON、Docker或Actions。
G0 DONE、R1 PARTIAL、Windows UNKNOWN、Linux REAL_NOT_RUN、04-F NOT_STARTED不变。
仅等待负责人审阅REV1 Diff；硬阻塞监督及持久可信确认尚未实现，不自动申请真实试跑。

日期：2026-11-07，Asia/Shanghai。任务书 V1.0。
负责人明确批准：**批准按 LNX-W01 V1.0 开始离线开发**。
原W01历史状态：**IMPLEMENTED_LOCAL_REVIEW_PENDING / LNX_W01_OFFLINE_TOOL_READY_FOR_REVIEW**。
仅供负责人本地 Diff 审阅；没有提交、推送或 CI 授权。

## 1. 基线及白名单

开始时 master、HEAD、origin/master、实时远端均为
`eb8cfe7d2ddb04a12f969b8a65e2e952e7165510`，工作区 CLEAN。
仅新增以下七个文件；原业务、诊断、集成测试、配置、锁、工作流、治理文件均不修改：

- `scripts/perf03_lnx_offline_contract.py`
- `scripts/perf03_lnx_offline_supervisor.py`
- `scripts/perf03_lnx_mock_child.py`
- `tests/unit/test_perf03_lnx_offline_contract.py`
- `tests/unit/test_perf03_lnx_offline_supervisor.py`
- `tests/unit/test_perf03_lnx_offline_parity.py`
- 本文件。

这不是生产补丁；没有复用 03-B 的授权、Environment、Run ID、数据集或执行入口。
原有读取与监督工具只作静态参考，新代码不导入它们。

## 2. 函数与证据合同

### W01-01 / W01-04：协议、证据及统计

`protocol/validate_protocol` 固定两股、420 自然日、2025-01-01～2026-02-24 日历、
2026-02-23～24 请求、250 交易日预热、430 日查询、manual、evaluate_signals=false。
420 日是种子布局，430 日是每计算块查询范围，不宣称所有块有完整430日行情。
不执行 seed 或业务开关。原180/180/30、六臂2700秒和3%门槛写入不可变协议合同。

新 schema 均以 `perf03-lnx` 开头；`evidence_kind` 恒为
`MOCK_ONLY_DO_NOT_USE_FOR_PERFORMANCE_ACCEPTANCE`，平台为 MOCK_HOST。
SHA/tree 字段仅验证格式；示例为人工摘要，不伪称绑定当前真实运行源码。
真实执行、容量、生产授权四字段固定 false，未知字段拒绝。

`seal/unseal` 复制对象并使用规范JSON SHA256绑定所有字段；读取拒绝重复键、非标准
NaN/Infinity、错误编码和超大输入。摘要只证明内容一致性，不是签名或执行授权。
对归档后重新计算hash的替换，消费者必须持有独立expected_sha256；父监督器用原内存
摘要及完整内容复核自己刚发布的工件，不能信任文件自报摘要。

`statistics` 只接受同协议、源码、配置、数据、运行身份的完整OFF1/ON1/OFF2/ON2/OFF3/ON3，
同时校验各对比较及跨对输出一致。记录六份原件，保留慢样本；用Decimal计算中位比值、
均值、min/max、样本标准差。P95=null，数值为synthetic，不测真实wall/CPU/RSS。
`arithmetic_threshold_met` 仅是算术断言；REAL_MEASUREMENT=false、
PERFORMANCE_ELIGIBILITY=NOT_CLAIMED、R1_STATUS=PARTIAL，不签发性能PASS。

### W01-02：固定mock监督通道

`supervise/batch` 只能构造 `sys.executable -m scripts.perf03_lnx_mock_child`，shell=False。
不接受外部命令、模块、解释器路径或数据库入口。CLI只接受显式--mock；未知参数在创建
临时目录前拒绝。仅使用已有解释器，不安装依赖。

子环境只有PYTHONDONTWRITEBYTECODE/PYTHONUNBUFFERED；不传HOME、PATH、数据库配置或Token。
工作目录固定为源码根以加载唯一模块，写入只通过继承的专用目录FD；临时叶目录0700、
文件0600。三个工具仅标准库互相调用，没有应用、ORM、驱动、网络或进程扫描入口。

父进程在同步调用返回后使用自身monotonic检查期限，保存每阶段开始、deadline、结束及完整性时间线；
这些是mock监督审计，不是业务性能指标。原180/180/30合同保持不变，测试单臂模拟期限
最多1秒，mock六臂轮询控制窗口最多10秒；子进程wait有界，挂起mock自身最多等待4秒，
但同步启动和文件I/O不具备硬截止保证，见REV1的PARTIAL结论。
不会真的等待180秒或45分钟，也不切换PERF_DIAGNOSTICS_ENABLED。

每臂独立Popen、独占目录和prefix/final文件。子进程自报成功不能替代三阶段、零退出、
父进程wait/reap及归档验证。失败停止批次，不重试、不补样。首错粘性，清理问题另加码。
仅kill自己持有的Popen句柄；固定mock子模块不创建后代，不将此能力冒充任意进程树/cgroup
终止证明。Windows没有同等FD/信号语义时明确拒绝；本轮仅macOS实测，Linux运行未验证。

`OwnedDirectory` 限系统temp根内、已存在的显式父目录；拒绝路径穿越、别名、链接、重复
run/arm。父目录及叶目录使用FD/inode交叉验证；文件NOFOLLOW、EXCL、staged硬链接发布，
先写prefix再写final，不覆盖原件。读取有限字节并核验文件身份和摘要。
只允许导出已校验的prefix/final sealed JSON；单件64KiB，六臂最多12件，导出上限768KiB。
子阶段文件为内部控制证据，不作为公开任意附件出口。无法发布final时返回
EVIDENCE_UNAVAILABLE，保留先前prefix，不声称完整证据已归档。
测试目录由pytest管理；CLI自有TemporaryDirectory在结束时清理，不扫描或清理其他目录。

### W01-03：人工业务比较器

`validate_snapshot/normalize_snapshot/parity` 使用固定v1人工表与owner/root/job/calc_run/
generation实体图。不反射或导入真实ORM；拒绝缺/多表、列、行及重复/乱序自然键。
dtype严格区分int/float/decimal/date/datetime/uuid/string，bool不冒充int。
Decimal字符串保留scale，日期和时区显式比较；null、tagged NaN、空串、零不混淆。
JSON数值NaN/Infinity拒绝，合法NaN只能使用受控标签。

身份映射由固定列声明逐项定义，UUID列仍在比较中；节点必须唯一、引用存在且kind匹配。
owner不允许跨臂改名。时间列默认精确比较，本版没有时间忽略/任意映射能力。
SUCCESS/PUBLISHED、FAILED/ABORTED、CANCELLED/ABORTED、UNKNOWN_ACK/INCOMPLETE分开；
未知ACK可作为合法不完整模拟状态比较，不能进入完整六臂统计。
业务calls/writes、heartbeat、observer控制SQL分别比较，没有混合total字段。

输出仅MOCK_PARITY_VALIDATED/REJECTED，REAL_PG_PARITY始终NOT_VERIFIED。
文本只接受空串或SYNTHETIC命名空间，任意SQL、用户路径、URL、token等原文拒绝导出。

## 3. 实际离线验证

已有本地venv：macOS/Darwin、CPython3.12.14、pytest9.1.1。
默认 `-p scripts.source_contract_pytest` 保留；没有禁用插件、改配置、导入业务或使用PG fixture。

执行范围始终限定本轮三份新unit测试和六份新Python文件：

```bash
.venv/bin/python -m pytest tests/unit/test_perf03_lnx_offline_contract.py tests/unit/test_perf03_lnx_offline_supervisor.py tests/unit/test_perf03_lnx_offline_parity.py -q
.venv/bin/python -m ruff check scripts/perf03_lnx_offline_contract.py scripts/perf03_lnx_offline_supervisor.py scripts/perf03_lnx_mock_child.py tests/unit/test_perf03_lnx_offline_contract.py tests/unit/test_perf03_lnx_offline_supervisor.py tests/unit/test_perf03_lnx_offline_parity.py
git diff --check
git status --short --branch
```

逐节点核验另用同三文件的-v输出，未扩大测试范围。177 passed、0 failed/errors/skipped，
2.90秒、退出0；定向Ruff退出0。超大JSON负例使用固定短node id，避免日志打印64KiB人工
空白输入；不改用例数据或断言。另补同一AST检查节点的sys.modules断言，确认父测试进程
没有加载业务/PG入口；交付前再执行同范围确认，以会话最终回执为准。

| 测试文件 | 实际节点数 | 覆盖 |
| --- | ---: | --- |
| contract | 78 | 固定协议、统计、身份拼接、缺臂、非有限指标、终态矛盾、脱敏、篡改、历史字节 |
| supervisor | 56 | 14种失败场景、7种非法CLI、9种非法API输入、6种非法路径及正常/中断/清理/替换、显式mock CLI等 |
| parity | 43 | 4种合法终态、37种值/结构/计数/闭包差异、owner漂移、NaN/null |

RED/开发失败保留：首批新测试在模块尚不存在时收集错误，退出2；这是开发顺序证据，
不是旧业务缺陷复现。基础实现6通过；扩大后157通过/5失败，均为标准差零的规范字符串
`0.0`与`0`不一致；修复输出规范化，未降低断言。后续162、173、176、177项逐步通过。
初次Ruff有3处超长行和1处未使用导入，已修正，不改规则。

节点完整定义和所有参数见三份测试源码；各命名test函数及参数即完整本轮测试清单。
不把重复运行数量相加；所有耗时都是离线工具验证，不是R1业务测量。

## 4. 验收映射与剩余项

| AC | 离线范围结论/证据 |
| --- | --- |
| 01 | PASS：master三方同SHA、初始clean；末态仅七个新增文件 |
| 02 | PASS：旧tracked文件零修改；四份历史JSON原始SHA256测试通过 |
| 03 | PASS：固定mock模块、AST导入白名单、非法入口先拒绝 |
| 04 | PASS：独立schema、MOCK_ONLY、四项资格固定false |
| 05 | PARTIAL / HARD_BLOCKING_IO_NOT_COVERED：阶段轮询通过，同步启动及文件I/O无硬期限 |
| 06 | PASS（mock）：三阶段时间线、冻结180/180/30与2700字段 |
| 07 | PASS：异常退出/首错/提前假报/清理失败/不重试测试 |
| 08 | PASS（mock）：仅回收自有固定子句柄；不宣称通用进程域终止 |
| 09 | PASS：路径/目录inode/链接/独占/hash/大小/出口负例 |
| 10 | PASS：固定原两股420日等全部输入，只校验不执行 |
| 11 | PASS（人工模型）：表/列/自然键/值/dtype/null/NaN比较 |
| 12 | PASS（人工模型）：五类实体、显式映射、外键及owner保护 |
| 13 | PASS（mock）：成功/失败/取消/未知ACK合法与矛盾组合 |
| 14 | PASS（合同）：计数分离，真实root计时实现未修改 |
| 15 | PASS（算术）：三对/边界/保留慢值/P95=null；真实性能NOT_VERIFIED |
| 16 | PASS：定向测试及Ruff，diff检查见最终会话回执 |
| 17 | PASS：本节明确全部未运行项和后续审批 |
| 18 | 本地交付待审：全部新增内容见七份文件，未commit/push |

真实ORM→规范JSON导出、全业务表身份闭包、真实未知ACK注入、Linux运行与PG17隔离适配、
OFF/ON/正式六臂、独立资源及CI均NOT_RUN。本轮不增加真实执行adapter，未读业务.env/凭据，
未安装依赖、操作DB/Worker/容器或调用外网业务服务。

文件FD、hash及mock测试不提供独立签名、恶意同UID防护或内核进程树隔离保证。
父监督可以有界等待/回收固定mock子进程，但不提供内核级抢占阻塞文件系统I/O的保证；
真实资源适配必须另审硬监督及工件I/O边界，不能凭本轮测试声称该能力已验证。
同UID可重算hash，因此不能把自报摘要当可信签名；本工具没有任何正式Gate消费接口。
SHA与源码身份、数学通过、mock运行和真实性能资格严格分离。

R1 PARTIAL、Windows 0xC0000005根因UNKNOWN、03-B DIAGNOSTIC_ONLY、04-E CLOSED、
04-F NOT_STARTED、正式容量PENDING、生产读取NOT_AUTHORIZED，全部保持。

## 5. Diff审阅、回滚与下一步

七份均为全新未跟踪文件，`git diff`不会自动展示其内容；不能把空diff误称没有改动。
完整新增内容就是本节列明的七份文件。可逐文件只读查看完整新增Diff：

```text
git diff --no-index -- /dev/null <上述某个新增文件>
```

此命令正常有差异时退出1，不代表验证失败。交付时同时检查tracked diff为空、
untracked列表精确等于白名单，并对新增文件执行no-index空白检查；不为展示而git add。
无需数据回滚或迁移；拒收后仅在负责人确认下撤回本轮新文件，不reset/clean或覆盖其他修改。

当前下一步只请求负责人Diff审阅；通过后另外批准一次master提交推送与普通CI。
后续真实Linux适配、资源准备、单对、独立结果审阅及三对验收仍分别获批，不自动接续。
