# P0_LNX_W04_D04_BUSINESS_GOLDEN_DECISION_PREP_01

日期 2026-11-11（Asia/Shanghai）。本轮交付状态为 `D04_REVIEW_PACKAGE_READY`。
业务 owner 的方法选择、五列实际值、时间策略、C01～C16 审阅和签名均待决。

## W00 基线与来源

本地开始于干净的 `master`，HEAD 为 `e5c85c57da66f1becd3dd1ba562ee1ace71d6b3f`。
GitHub master 与任务书均指向 `f7d8e264041db4f7d5600e1ce5b2bbd6b7ff0345`。
核对两笔上游提交只涉及 W04-C V2 后执行快进。七个新增路径均空闲。五份治理文件和相关业务权威文档
沿用本会话预读，核对两笔提交未改变其内容。基线 GitHub Main CI 42837989562 为 attempt 1、completed/success。
test Job 129905230697 的日志为 6608 passed、1 skipped、821 warnings，覆盖率 90.02%。
安全回执为 COMPLETE，8609 个 JUnit 节点，0 failure/error、1 approved Skip。
基线摘要归档于 `baseline-ci-safe-extract.txt`。

| 原始证据 | 锚点 | 核验范围 |
| --- | --- | --- |
| 冻结业务 schema | `f6be0a5de1ce46e30758039a3ab345a308ff96cb36f6ee86ec3ccdc39759f297` | 原 Git Blob 37 表/520 列，独立 datetime 投影 49 列 |
| 历史 seed/根任务协议 | `b6ffb7bf8ec7d26f771d9b89923e4f7e926edbed` | 原两股/420 日、2026-02-23～24 请求窗、250/430 预热和策略摘要 |
| V2 Oracle 原始 Blob | `7351e99af94b9de89105d0a2ee9ec75b093f04a3c5ed09d1ed32627a7efda825` | 16 个草稿案例、PENDING_D04、NOT_SIGNED |
| V2 scenarios 原始 Blob | `851365e3a60eb47b054c1e6da8fb83a99e4260069e510e13cca821225d0b98b7` | 固定虚构投影及观测变异 |
| V2 contract 原始 Blob | `610faf751e344b05732eb67310b39e0ced825376bd27301e8e58624d01a1734b` | 固定结构协议 |
| W04 Readiness §7.2–7.5、§8–10 | f7d8e26 的原 Git Blob | 归属、时间复制、G05/G08/G09 缺口及 D04 独立裁决 |

V2 三个 fixture 的引入提交为 `997f0a26f259424e3c566bff96bcae407e69f674`，
与审查基线对应文件字节相同。审查基线另含 V2 合同声明修复。
仓库外 `source-blobs.json` 保存原 Git Blob 和 Windows 工作字节的独立摘要。

## W01～W03 交付和决策边界

| 文件 | 交付内容 |
| --- | --- |
| scripts/r1_d04_decision_review.py | 标准库内存 API、预算、固定字段与来源、首次错误、结构审阅结果 |
| tests/unit/test_r1_d04_decision_review.py | T01～T30、重算摘要负例、原 Blob 对照、无 I/O 审阅测试 |
| [r1_d04_timestamp_inventory_v1.json](r1_d04_timestamp_inventory_v1.json) | 49 列原始来源与候选角色，五列 SEED_INPUT、19 列 ROOT_RUNTIME、25 列 EVIDENCE |
| [r1_d04_decision_contract_v1.json](r1_d04_decision_contract_v1.json) | 固定 JSON 字段、来源、A/B 提案、签认和预算约定 |
| [r1_d04_decision_request_v1.json](r1_d04_decision_request_v1.json) | 九项待决问题、五个待填时间槽、16 个未签 Golden |
| [r1_d04_owner_decision_form_v1.md](r1_d04_owner_decision_form_v1.md) | 逐项审阅与空白签名区 |
| 本回执 | 开发验收、Git 状态和证据索引 |

检查器独立固定历史和当前来源身份、两个 D04 JSON 原字节及协议内容摘要。原始 49 列通过表列键、
来源和策略投影交叉验证。合同声明变异即使重算摘要也拒绝。输入限原始 UTF-8 JSON，整数最大 63 位，
排除重复键、浮点、非有限数、异常 Unicode、循环和超预算结构。
默认包结构合法并可交 owner 审阅，调用方来源标 `CALLER_SUPPLIED_NOT_AUTHENTICATED`。

A 的两臂提案槽要求声明同一原始摘要。B 的两臂提案槽要求分别保留原始摘要，并提供五个 seed 时间列
有序双射样例、固定来源引用与域内唯一身份。两类提案都要求保留同一原业务 source hash，
`raw_byte_identical` 恒为 false。样例预算至多每容器 256 项，真实行级证据、自然键、运行时事件与复制事实仍待
人工审核。运行时 copy policy 检查覆盖 Job/发布/metadata 关系声明，物理和真实数据证明保持待决。
序列策略登记三项输入序列的 last_value、is_called、increment 和生成器状态字段。

V2 草稿状态逐例保留。C11 为 EVENT_MAPPING_UNDECIDED，C12/C13/C15/C16 保留阻断状态，
C01/C05/C06 的类型探针留待业务 owner 审阅。D04-08 的完整 37/520 业务预期仍缺真实 typed/original 证据。

## W04 验证

| 项目 | 实际结果 |
| --- | --- |
| 初始 RED | 1 个收集错误，exit 2，接口尚不存在 |
| 语义 RED | 16 failed，52 deselected，exit 1，宽松 stub 对具体变异未拒绝 |
| 最终定向 GREEN | 74 passed，18.47s，exit 0 |
| 旧合同回归 | 原始 Blob 副本 15 个模块，228 passed、2000 subtests passed、5 条 xunit2 警告，808.45s，exit 0 |
| Ruff | 全仓 backend/tests/migrations/scripts，exit 0 |
| 静态检查 | 两个 Python 文件编译到仓库外，diff/check，严格 JSON，范围及原字节检查 |

初次定向运行有 71 passed、4 errors。大字节与大节点输入进入 pytest 默认节点名，超过 Windows
环境变量长度，使用固定短 ID 后覆盖内容和断言均保留。初次外部归档继承 Git 的 CRLF 转换，
旧回归 168 passed、68 failed、10 errors，396 subtests passed。冻结 schema 的 CRLF 版摘要为
`e023206e7209ff96ebeb0417dbd516a061c9dc58aee4bf98e9f63fc84e04ea47`。
第二份外部副本使用 `git -c core.autocrlf=false archive`，逐一核对关键文件与 `git cat-file blob` 字节相等。
仓库冻结原件和旧测试原断言均保留。复验平台为 Windows CPython 3.12.0、pytest 9.1.1，
沿用已有隔离 venv，依赖无安装或升级。

| 新 JSON | 原字节 SHA256 |
| --- | --- |
| decision_contract | `45f4d2e8d9c8c4aa8f144ff55b1794d9a0e50977e9e15789cc34d9ea57f9dcdc` |
| decision_request | `f75331fefa88879ab3b9e322b793a9bad2aa0ba524889ffda161763872629b43` |
| timestamp_inventory | `25eac0b98acd3ac67046cf5be7a690b09b8ed790d59338df3f27316cf62eb65b` |

SHA256 使用未经过滤的原字节。仓库外 `file-summary.json` 同时记录 `git hash-object --no-filters`
所得 Git Blob ID、字节数与七文件 SHA256。`review-result.json` 保存 49/5/16 结构审阅回执。
普通 Git diff 不含未跟踪文件。仓库外 `new-files-diff-stat.txt` 记录七份新增文件的完整统计，
`git-status.txt` 和 `git-diff-stat.txt` 保存工作区状态与跟踪 diff 事实。
命令、退出码和日志分别在 `red-import`、`red-semantic`、`green-delivery`、`old-lf`、`ruff-final` 同名前缀文件。

## W05 验收与交接

| AC | 状态 | 核验 |
| --- | --- | --- |
| AC01 | PASS | master 与任务书基线对齐 |
| AC02 | PASS | 白名单七个新增文件 |
| AC03 | PASS | 49 个 datetime 键与原 Blob 的独立投影全等 |
| AC04 | PASS | 五列精确归类并保留待填槽位 |
| AC05 | PASS | 原两股、420 日、预热、请求窗与策略身份固定 |
| AC06 | PASS | 单选、A/B 两臂摘要、B 的 raw 和 source hash 负例 |
| AC07 | PASS | 序列和生成器必决字段 |
| AC08 | PASS | 候选角色、UTC 微秒、事件声明、来源与排序检查 |
| AC09 | PASS | 16 个案例逐项待审，未决和拒绝状态保留 |
| AC10 | PASS | 从原 V2 Oracle 提取草稿状态，未调用比较器生成预期 |
| AC11 | PASS | 固定预算、字段、来源及协议内容 |
| AC12 | PASS | T01～T30 和 16 个语义 RED |
| AC13 | PASS | 首错固定安全码，输入哨兵无回显 |
| AC14 | PASS | 检查器纯内存、标准库，测试封堵调用期间的 I/O |
| AC15 | PASS | 原件哈希及旧拒绝逻辑 |
| AC16 | PASS | 定向、原始 Blob 副本旧回归、Ruff、编译及范围检查完成 |
| AC17 | PASS | owner、负责人和 reviewer 签名区空白 |
| AC18 | PASS | NO_GO、NOT_AUTHORIZED，G05/G08/G09 不变绿 |
| AC19 | PASS | 真实实验及 Actions 操作数为零 |
| AC20 | PENDING | 后续独立审阅与人工业务签认 |

本地最终 HEAD 为 `f7d8e264041db4f7d5600e1ce5b2bbd6b7ff0345`。交付为 master 工作区七个未跟踪新增文件，
暂存区为空，现有 1561 个跟踪文件原字节核对一致。当前任务 Main CI 为 NOT_RUN。
下一步由 ChatGPT 独立审阅后提交业务 owner 作 D04 人工决定。

```text
OWNER_METHOD=NOT_SELECTED
OWNER_SIGNATURE=NOT_SIGNED
D04=OWNER_DECISION_PENDING
INDEPENDENT_REVIEW=PENDING
R1=PARTIAL
HISTORICAL_AC05=PARTIAL
G05=MISSING
G08=PARTIAL
G09=PARTIAL
G1=NOT_AUTHORIZED
REAL_PG17_WORKER_OFF_ON=NO_GO
PERFORMANCE_ACCEPTANCE=NOT_MEASURED
REAL_PG_CONNECTIONS=0
WORKER_RUNS=0
OFF_ON_PAIRS=0
ACTIONS_MANUAL_DISPATCH_OR_RERUN=0
```
