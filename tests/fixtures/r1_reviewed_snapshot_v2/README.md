# W04-C V2 独立预期候选

这些文件是 Codex 逐条手写的虚构语义样本及预期候选，不是业务 owner 已签认的 Golden。
`authorship=CODEX_MANUAL_DRAFT_NOT_OWNER_APPROVAL`、`approval=PENDING_D04`、
`reviewer=NOT_SIGNED` 是刻意保留的事实。没有调用旧 `golden()`、ORM 默认值提取器、
seed 生成器、新旧比较器或 encoder 来产生预期；没有真实股票行、数据库导出或性能样本。

## 独立文件和信任输入

- `scenarios_v2.json`：手写观察包模板、两臂虚构身份、C01～C16 的观察变化。
  只有测试加载器展开 `$job` 等固定替身、替换指定观察字段；不调用审核层构造输入。
- `expected_oracle_v2.json`：另行写入的预期值、身份角色对应、业务依据和预期拒绝码。
  `@job` 等角色来自独立预期的双射，不从观察包推导。场景文件与预期文件不互相生成。
  共享的 `base_rows` 是本文件自己写下的预期；case changes 是完整的手写行替换/删除。
- `evidence_contract_v2.json`：字段集合、类型标签、限制、固定状态/拒绝码和摘要分域。
  是本离线协议的字段合同，不是数据库 DDL，也不是执行令牌。

单测为三个 JSON 各钉住明确 LF/完整 CRLF 的两个字节摘要；不会运行时转换文件后再验摘要。
更改场景和预期后重新计算两臂自己的 hash，不能改变测试中独立固定的草稿字节身份。
后续合法修订需审阅真实差异、更新明确版次和预期锚点；没有“更新快照并接受”接口。

`review_pair(left, right, oracle_bytes, contract_bytes, expected_provenance)` 只接收内存对象。
`expected_provenance` 必须由调用方从独立审阅记录显式提供；审核层不访问 Git/磁盘/环境。
它分别绑定 reviewed revision、历史 b6ffb7bf 基线、冻结 schema、工具、三个 fixture 摘要、
namespace 和 Golden revision。模板 reviewed revision 是本轮审阅基线 e5c85c57，
不是把旧基线改为交付 commit；新交付 SHA 在任务外部回执记录。

源码/工具声明摘要和调用者的相符输入不是签名或外部真实性证明。恶意调用方若同时控制
所有信任输入，不能靠这个纯数据层获得独立认证；结果仍拒绝真实执行/等价/性能权限。
该 API 不是对不可信 Python 代码的沙箱。`RAW_INPUT.declared_sha256` 中的重复十六进制
字符是虚构的非认证描述值，不冒充实际数据库或 seed 的摘要。真正计算的域摘要另列。

## 范围和业务依据

本合同只审阅人工挑选的字段投影，**不复制或替代原 37 表/520 列结构合同**。
投影允许字段在 contract 中逐表列出；`synthetic_type_probe` 仅为类型语义练习，不是数据库表。
`row_key`、候选/公开行和元数据示例也是投影，不声称构成可加载的完整 ORM 行。

业务状态、事务和引用依据来自以下冻结源码；精确修订为
`e5c85c57da66f1becd3dd1ba562ee1ace71d6b3f`：

- `backend/app/repositories/job_run.py::_update_owned_data_job`：归属、terminal CAS 与发布提交。
- `backend/app/services/data_publication.py::finish_publication`、`PublicationWorkspace`：
  候选、首次原像、删除和公开发布关系。
- `backend/app/models/data_publication.py`：候选 SQL NULL 条件、Scope 的实际字段与重复语义。
- `backend/app/services/job_worker.py::_hold_unconfirmed_execution`：未知 ACK 不释放 Writer。
- `docs/acceptance/BIZ_PERF_03_A_R1_LNX_W04_READINESS.md` 第 5、7 节：
  事件/身份/引用、多重集和范围外守卫的设计约束；设计不等于物理已验。

数值 ma20=1.25、原像=1.0、类型探针 Decimal 1.00 等均由本草稿直接选择，
用于检验复制/独立预期，未依据输入行情推算，不能评价因子公式正确性或金融效果。
sector=101/theme=TH001 是 C08 的人工引用练习，不是原 R1 seed 出现题材成员的声明。

| Case | 固定语义和独立期望 | 本版预期 |
|---|---|---|
| C01 | SUCCESS/PUBLISHED；相同 root/token 复制；公开值 1.25 | OFFLINE_ORACLE_MATCH |
| C02 | FAILED/ABORTED；公开原像仍为 1.0 | OFFLINE_ORACLE_MATCH |
| C03 | CANCELLED/ABORTED；明确 cancel_requested 和已知候选前缀 | OFFLINE_ORACLE_MATCH |
| C04 | UNKNOWN ACK 不因状态标签变成功样本 | INCOMPLETE / V2_ACK_UNKNOWN |
| C05 | candidate.base=首次 preimage；未覆盖为新值 | OFFLINE_ORACLE_MATCH |
| C06 | tombstone SQL NULL，原像保留，公开行不存在 | OFFLINE_ORACLE_MATCH |
| C07 | 同自然 Scope tuple 两条，固定 UUID 顺序/ordinal/范围和次数 | OFFLINE_ORACLE_MATCH |
| C08 | FK、非 FK JSON、job/token/sector/theme 引用闭合 | OFFLINE_ORACLE_MATCH |
| C09 | Decimal scale、有限 float hex/负零、bool/int 不混同 | OFFLINE_ORACLE_MATCH |
| C10 | SQL_NULL/JSON null/MISSING/空串/空数组/0/false 七种区别 | OFFLINE_ORACLE_MATCH |
| C11 | 候选 UTC 微秒事件双射；尚无 D04 时间方案签认 | PENDING_OWNER_DECISION |
| C12 | 迁移/schema/序列观察缺证；不能推出整库等价 | INCOMPLETE / V2_SENTINEL_UNKNOWN |
| C13 | 范围外表前后描述不同；不能推出无越界写入 | INCOMPLETE / V2_OUTSIDE_CHANGED |
| C14 | 左右同时错误改为 1.5；独立预期仍为 1.25 | UNEQUAL / V2_ORACLE_MISMATCH |
| C15 | 两臂自述来源漂移，不能自签或信任重算 hash | INCOMPLETE / V2_SOURCE |
| C16 | 清理未知，close/join/exit=0 不等于外部资源 absent | INCOMPLETE / V2_CLEANUP_UNKNOWN |

上述 match 只描述草稿级离线合同；所有结果另有
`business_golden_status=PENDING_OWNER_DECISION`、`physical_proof=NOT_PROVEN`。
C11 的预期不得从 pending 改 approved 来追求全绿。C12/C13 的正向守卫描述也只有
OFFLINE_ASSERTED，实际迁移/序列/整库范围外表并未核查，绝不输出全库等价。

## 类型、身份和摘要

每个语义值有显式 type 标签。SQL NULL/JSON null/MISSING 分别为仅含 type 的对象；
MISSING 只允许出现在语义探针中，不能替代必需的真实表投影字段。
Decimal 采用非指数十进制字符串，保留 scale；float 只接收有限 binary64 的规范 hex，
保留负零；date 与 UTC 微秒 datetime 分开，不自动转换时区或容忍非有限数。
递归 object/array 保留值类型、数组次序及空值，拒绝缺键/额外键。

job/token/scope/worker/event 各有独立的角色及左右对应；拒绝跨域 UUID 碰撞、
多对一/一对多/重复角色和事件反序。非 FK 元数据也必须命中对应 job，候选、原像、
公开行及 Scope 按独立预期检查，不能以左右互等替代。

四域摘要采用 SHA256：`prefix || u64be(header_len) || header || u64be(payload_len) || payload`。
header 为 ASCII 规范 JSON，绑定协议、来源（含 schema/Golden/工具/fixture）、case、arm、
input_ref 和完整 subject。prefix 分别是 `R1-V2-RAW\0`、`R1-V2-TYPED\0`、
`R1-V2-BUSINESS\0`、`R1-V2-TELEMETRY\0`。

- RAW_INPUT：原始输入的**非认证描述**，不是重新取得的数据库原像。
- TYPED_OUTPUT：本臂原始 typed 投影与哨兵；保留原身份及表示顺序。
- BUSINESS_EXPECTATION：映射后的业务 canonical 投影和独立预期，分别保留。
- TELEMETRY：独立遥测描述，不混入业务字段或当作资源/退出证明。

所有传出值只有固定状态、固定拒绝码、摘要和检查阶段。首次错误保留，之后检查 NOT_RUN；
失败步骤 FAIL。未安全完成的域摘要为 NOT_COMPUTED，不制造空摘要。
始终 decision=NO_GO、authorization=NOT_AUTHORIZED，四项真实等价/性能/生产布尔全 false。

## 预算和 D04 待决

每个输入 JSON 至多 1 MiB；内存树逻辑文字/标量预算同为 1 MiB、20,000 节点，
深度 24、单字符串 2,048 字符、每容器 256 项、每臂最多 128 投影行，
每身份域最多 16 组、最多 16 个投影表/32 个字段。先封顶，再规范编码/排序/比较；
无无界流、spill 或 Counter 索引。这是小型离线处理上限，不是 OS RSS 或真实运行配额，
也不提高旧导出器 10,000 行/64 MiB 上限。

D04 仍待业务 owner 和独立审阅人裁决：

1. 一次原 seed 快照双加载还是每臂执行并逐列映射；时间与业务 source hash 如何保真。
2. `stock_basic.updated_at`、`stock_daily.source_updated_at`、
   `stock_limit_daily.created_at/updated_at`、`data_quality_daily.checked_at` 五列的冻结值和影响。
3. 原 49 个时间源分类、事件精度/复制/次序/歧义、多对一停止策略及序列政策。
4. 本版虚构业务投影的语义及后续完整业务 Golden 的人工签认。

审批主体与日期均未填写；代码没有签署/消费/自动审批接口。不自动进入 W04-B/D、G1、
04-F、真实 PG17/Worker 或 OFF/ON。重复核验只给相同数据结果，不消费许可或修改 fixture。
