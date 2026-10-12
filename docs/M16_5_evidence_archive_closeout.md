# M16.5 Evidence Archive 分阶段验收

开发基线：`5c7c52474b0dffc5b42c513f0b657d51705a5d33`，分支 master。
状态：A–F 本地实现与验收完成；远端 CI 结果以末尾 Git / CI 实际记录为准。

| 阶段 | 当前状态 | 验证 |
|---|---|---|
| A 存储 / Capture Contract | 实现完成 | 11 项单测、1 项 PG 迁移/约束/Trigger/有档拒绝降级测试、全量后端 1138 项通过；Ruff 通过。 |
| B Chat 原子完成 | 实现完成 | 2 次实际调用/3 Evidence、缓存审计、同 request 竞争、写入异常/超限/截止回滚；全量后端 1143 项通过，最新预算路径专项 36 项复核。 |
| C Offline Verifier / API | 实现完成 | 20 项离线/API 单测、最新业务数据变更隔离 PG 回归、全量 1164 项通过；Ruff 通过。 |
| D Report v3 绑定 | 实现完成 | 8 项版本/Hash 单测、真实 PG 报告创建/证据/复核/导出/归档/owner/损坏门禁；历史 v1/v2 原 JSON/Hash 不变。 |
| E UI / 遗留整改 | 实现完成 | 后端 1179 项、前端 90 项；全局覆盖率 81.35%、归档面板 98.23%；Chrome 1440/390 合成实测通过，未调用真实模型或用户库。 |
| F 回归 / CI / 交付 | 本地验收完成，远端 CI 待核查 | 后端 1192 passed / 86.77%；前端 90 passed / 81.35%；PG 17 / Ruff / Compose / Browser 通过。 |

## A 阶段契约

- 迁移：`0051_m16_5_evidence_archive`，不修改 0046–0050。三表仅追加；owner/chat/turn/audit 复合引用，call/Evidence/turn 唯一，hash/JSONB 大小检查，UPDATE Trigger 与父 FK RESTRICT。
- 空库测试演练 0049→0050→0051、回退再升级；有任意 Archive/Binding/Manifest 时 downgrade fail closed。不自动删除档案。
- `EvidenceRef._archive_projection` 仅为服务端内部字段；取自实际 `evidence_ref(content=...)`，不在公开 tool payload、模型消息或 API 中序列化。v2 canonical/content_hash/evidence_id 算法未改变。
- Projector `m16.5-content-projector-v1` 适配原九工具 1.0：Derived/Backtest 为 record；Coverage 为 summary+daily；Performance 为 artifact_type+bundle_identity+summary；Study 为 identity+summary；Window 为 study_id+validation_id+window。不能用 records 的近似内容取代投影。
- Archive canonical 版本使用既有 Evidence v2 算法，payload/projection 使用其精度字符串规则。存储大小按带空格 UTF-8 JSONB text 估计；原工具 64 KiB 上限之外还检查 JSONB 表达大小。
- 默认预算：payload 64 KiB、turn 总计 640 KiB、8 calls、64 bindings；可在 agent.archive 配置调整但不越过数据库硬界限。当前 Chat 默认总调用 8，单工具 Evidence 64；保持原 45s 总 Deadline。
- 同一 Evidence 不允许内容/来源/冻结 payload 冲突，错误为 EVIDENCE_DUPLICATE_CONFLICT。缓存使用两条 call 身份与单一 Evidence binding；所有实际选中调用保留来源。
- 新开关默认 false；最终 B–E 已完成聊天/报告入口。历史不回填，不查询最新业务指标补证据。

## 阶段验证命令

所有 DB 命令只对一次性 PostgreSQL 17 测试库运行，Python 3.12；不读取用户生产连接。

```bash
python -m alembic upgrade head
python -m pytest tests/unit/test_m16_5_archive_capture.py -q
python -m pytest tests/integration/test_m16_5_archive_migration.py -q
python -m pytest -q
python -m ruff check backend tests migrations scripts
```

## 边界

E 使用独立 Archive Panel 展示 Capture、Integrity、Claim Recheck；详情仅白名单安全字段，
20 条证据分页、取消旧请求、失败不保留复核成功、会话归档读档。桌面与手机截图在 assets/m16-5。
比较新政策 m16.5-report-comparison-v3；旧 v2 的冻结签名仍核验，展示视为旧策略而关闭差值。
DATE/IDENTIFIER 进入 context_facts，不强制 Decimal。真正 A-only/B-only 进入 side_by_side_facts，
PAIR_MAPPING_NOT_PROVIDED 与 CONTEXT_REQUIRED、无 delta/排序；错误指标/配置仍 INCOMPATIBLE。
前端只消费 display_result，无安全投影时不降级渲染审计 result。复核从未授予算法重跑等级。

D 新报告版本 m16.5-v1 / m16.5-report-snapshot-v3，级别 FROZEN_TOOL_EVIDENCE；快照冻结
Manifest ID/版本/hash/COMPLETE 与 FROZEN_FACT_RECHECK。Source Contract 冻结 Manifest Hash、
复核政策、校验范围、字段绑定及 M14/M15 缺口；先计算 Contract Hash 再计算 Snapshot Hash，无循环。
仅完整性及字段重验真实通过才创建 v3，详情/导出/归档/幂等/比较读取再次验证归档绑定。
无档来源继续创建 v2，旧 DTO 序列化与契约签名保持原形，不填 null 或新字段改变旧摘要。

C 抽出实时与离线共用的纯字段验证核心；精确路径、日期/实体/单位、Decimal 值与真实 Evidence 绑定一并验证。
离线只读加载 Archive/Chat/Report，重核全部 Hash、Audit、缓存来源、Message/Turn 及 Citation 身份。
未知版本 UNVERIFIABLE；一致 Hash 但错误 Claim 返回 MISMATCH，不发布失败数值。旧无归档返回 UNAVAILABLE。
四个 owner 隔离 API 使用只读事务、严格 DTO/OpenAPI、分页/数量与 5s 复核预算；重放也核验现存 Manifest。
独立回测与 TRAIN/OOS 缺完整 M14/M15 冻结契约时保持缺口，不授予差值或算法重跑等级。

## B 阶段原子完成

执行服务通过内部捕获回调取得 PrivateAttr 投影，CapturedToolPayload 的投影不是 dict 键，不进入模型 JSON。
ToolResultContext 冻结工具版本、严格输入 Schema、当次参数及原调用 ID；round cache 两次调用保留两条审计，但只执行一次。
Assembler 在完成事务前核对证据，Repository 核对 audit args/tool/status/Evidence 与 cache origin。
同一事务写入 ToolArchive、Binding、Manifest、Assistant 与 COMPLETED Turn；完整性/存储/资源失败 rollback 后写 FAILED。
归档消耗原 45s 总预算，写 SQL statement_timeout 也受剩余预算约束。提交前检查 Deadline；已原子提交但 HTTP 响应丢失/过期时不得倒写失败或删除 Archive，客户端通过原 request_id 查询/重放确认结果。
Manifest 冻结原 Claims Digest、助手 content+metadata Digest、owner/chat/turn/message 与全部工具/Binding 摘要。
开关关闭时无归档写入；无有效 Claim 的澄清轮记录 UNAVAILABLE，不授予 COMPLETE。旧 Turn 不补档。

SHA 是持久化一致性校验，不是防 DB 超级用户同时改内容及 Hash 的签名。M16.5 不实现 CALCULATION_REPRODUCED。
当前 M14/M15 原工具响应不含完整执行/会计/费用/基准/日期集与窗口血缘证明，不能凭 Archive 存在自动开放收益差值。
最终上线与回滚边界见下文；不得宣称原算法已重跑。

## 分阶段提交与文件范围

A `f6f6e4e`，B `f2c4ef2`，C `5481ace`，D `fd03cf9`，E `bc3e5f0`；F 为本次收尾提交。
后端变更集中在 core/agent_archive_config、domain/agent、models/repositories/agent_archive、
services/agent/archive、原 chat 捕获/事实核心、report 绑定/完整性/比较以及 API 路由。
前端复用原工作台与报告组件，新增 EvidenceArchivePanel / agentArchive service；迁移仅新增 0051。
测试在 test_m16_5_* 及原实际 Window 投影测试；维护四份 Markdown 权威文档，不更新 docx。

## API、版本与资源

均以 `/api/v1/agent` 为前缀：

| 方法 | 路由 |
|---|---|
| GET | /chats/{chat_id}/turn-archives/{request_id} |
| GET | /reports/{report_id}/evidence?limit=20&offset=0 |
| GET | /reports/{report_id}/evidence/{evidence_id} |
| POST | /reports/{report_id}/verify，严格 body `{}` 或 max_evidence |

Turn 路由采用 request_id:path，避免任务书建议的 `/turns/{request_id}/archive` 截获既有带斜杠
或 archive 后缀的 Turn 状态请求。旧状态 API 不变，新增兼容测试；跨 owner 404。
DTO/OpenAPI extra=forbid，安全输出身份、参数摘要与验证字段，不外发 raw payload/projection。

归档 m16.5-archive-v1，投影 m16.5-content-projector-v1，完整性 m16.5-integrity-v1，
复核 m16.5-frozen-recheck-v1。Capture、Integrity、Claim、Comparison 独立；不将 SHA 等同事实。
未知 Evidence/tool/projector/manifest 版本均不可解释，不隐式套用当前规则。

默认 payload 64 KiB、Turn 640 KiB（含工具/投影/Manifest）、8 calls、64 bindings。
配置硬上限 payload 64 KiB、Turn 1 MiB、16 calls、100 bindings；JSONB text 大小有数据库二次门禁。
分页默认 20、上限 100；verify 默认 max_evidence=64、上限 100；共享 5s 预算包含读取与核验。
SQL 超时及归档写入受配置/剩余时间限制。同步 DB/commit 不可线程级抢占；提交前检查 Deadline，
提交后响应丢失必须以 Turn 状态恢复，不能倒写失败。读验证不在逐 Claim 中查询 DB。
读取大 JSON 前先在归档表聚合检查数量与字节，超量不加载 payload；共享预算在每个读取阶段检查。

## 实测性能与验证

环境：Python 3.12 Docker、PostgreSQL 17 临时库；两工具、三 Evidence/Claim，2 次预热 + 20 样本。
序列化 P95 1.359ms、Assistant/Turn/Archive 原子写入含 commit P95 6.256ms、合计 P95 7.615ms。
由 `python -m pytest tests/integration/test_m16_5_closeout.py -q -s` 实测，不是最大负载或生产保证。
生产须监测容量、延迟、超时与 ARCHIVE_LIMIT_EXCEEDED / ARCHIVE_PERSIST_FAILED / 完整性、
字段、未知版本、不可复核错误码；日志不输出问题正文、Token 或证据 payload。

- 后端全量 1192 passed，覆盖率 86.77%；原 70% gate 未降低，Ruff 通过。
- npm ci；前端 90 passed，覆盖率 81.35%、branches 77.20%；归档面板 98.23%、归档 service 100%；build 通过。
- PostgreSQL current 与 heads 均为 0051；0049→0050→0051、重复升级、空档降级、有档拒绝降级、FK/唯一/大小/UPDATE 门禁通过。
- 旧真实报告与比较升级前后 ID/JSON/Hash 不变；无伪回填。九工具实际 Adapter 投影通过，Window 在真实 PG 上验证。
- Compose config --quiet / build、前端镜像 nginx -t 通过。未启动用户生产服务，不等同于真实连接已验证。
- Chrome 1440/390 合成实测：无 pageerror/页面横向溢出；22 证据分页、精确 Decimal、复核/反例/断网、旧限制、键盘、会话归档读档与面板清理通过。

截图：[桌面](assets/m16-5/desktop.png)、[手机状态](assets/m16-5/mobile.png)、
[手机详情](assets/m16-5/mobile-detail.png)、[旧报告手机限制](assets/m16-5/legacy-mobile.png)。
可重复冻结样例由 archive_capture / offline_recheck / archived_reports 中实际 canonical、Compiler、
Assembler 和 Repository 生成。未提交用户业务数据或生产证据。

```bash
python -m alembic upgrade head
python -m alembic current
python -m alembic heads
python -m pytest --cov=backend/app --cov-report=term-missing --cov-fail-under=70
python -m ruff check backend tests migrations scripts
cd frontend
npm ci
npm run test:coverage
npm run build
```

## 22 项验收矩阵

| # | 场景 | 回归证据 |
|---|---|---|
| 01 | 两工具/三证据原子完成及复核 | chat_archive / archived_reports |
| 02 | 旧无档 UNAVAILABLE | archive_api / report_binding / UI legacy |
| 03 | 参数及输出 Hash 不符 | offline_recheck 完整性参数化反例 |
| 04 | content 非 records 形状 | archive_capture + projector_adapters 八实际工具 + PG Window |
| 05 | Evidence 冲突 | archive_capture / 原 Compiler duplicate conflict |
| 06 | 缓存双审计一次执行 | chat_archive cached replay |
| 07 | 同 request 竞争与重放 | chat_archive concurrent、原 M16.2 竞争测试 |
| 08 | 写入异常/超限回滚 | chat_archive failure 参数化 |
| 09 | JSONB/ref/Manifest 篡改 | offline_recheck 10 类反例、migration Trigger |
| 10 | 旧/新报告读取导出归档比较 | archived_reports、closeout 旧 JSON/Hash 不变、M16.4 全量 |
| 11 | 跨 owner 报告/证据/Turn | archived_reports / chat_archive readonly owner / M16.2 Cookie |
| 12 | 数值/单位/日期/实体/路径错 | offline_recheck 完整重新封 SHA 后仍 MISMATCH |
| 13 | 聚合 OOS 不冒充 Window | offline_recheck TRAIN_VS_OOS 缺口、原 M16.2.2 lineage |
| 14 | M14 缺口不授差值 | offline_recheck / M16.4.1 独立 Run 反例 |
| 15 | 日期/ID/数值分层 | context_comparison / 共用验证核心 |
| 16 | 真正 A-only / B-only | context_comparison 两意图、配置/单位拒绝 |
| 17 | 旧 result.delta 仅审计 | integrity、Reports Vitest 旧 API 无 display_result、Browser |
| 18 | 未知版本不可解释 | offline_recheck projector/evidence/tool/manifest |
| 19 | 非预期/敏感字段、大小 | archive_capture、0051 JSONB 检查 |
| 20 | 最新业务变更不漂移 | chat_archive 新 MarketDaily、READ ONLY/SQL spy，无业务 SELECT |
| 21 | 异常与提交后网络丢失 | chat_archive rollback、LostResponseChat 原 request 恢复 |
| 22 | 桌面/手机/反例/断网/分页/键盘 | verify_m16_5_archive.mjs、真实 Chrome 合成夹具 |

## 部署、回滚、生命周期与剩余边界

1. 独立备份 PostgreSQL 并核对目标/head；先升级 0051，再后端，最后前端，默认关闭归档。
   新 Chat 唯一约束需要短暂 DDL 锁，应在部署窗口升级；不扫描/重算上游业务全表。
2. 明确开启 config/agent.yaml 的 agent.archive.enabled、重启后，才捕获后续新 Turn；检查新完成
   Turn 的 COMPLETE、Manifest、证据列表与 FACT_REVERIFIED。未修改用户 .env，未自动启用真实模型。
3. 回滚优先关闭新写入并回退应用，保留 0051 表。有归档数据拒绝 downgrade，不清档绕过检查。
   旧代码不认识 v3 时隐藏入口或保留兼容后端，不改快照/Hash 伪装旧版。
4. 保留/删除方案另行审批；无隐式 TTL、普通删档或“修复历史”API，监控存储及诊断码。
5. 未冻结完整独立 M14/M15 契约，保留 EXACT_M14_BUNDLE_NOT_ARCHIVED / FROZEN_M15_WINDOW_LINEAGE_REQUIRED。
   不授予 FROZEN_CONTRACT_RECHECK / COMPARISON_REVALIDATED，不实现或宣称 CALCULATION_REPRODUCED。
6. npm ci 现有锁定依赖审计提示 11 项（4 moderate、3 high、4 critical），未擅自跨阶段升级依赖。
   Vite 保留既有大 chunk 警告。依赖安全升级另行安排，未降低任何测试门槛。

## Git / CI

本地全量验收通过；F 提交后推送 master，核查对应 GitHub Actions 后回填真实成功记录。
