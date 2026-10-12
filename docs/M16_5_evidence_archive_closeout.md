# M16.5 Evidence Archive 分阶段验收

开发基线：`5c7c52474b0dffc5b42c513f0b657d51705a5d33`，分支 master。
状态：开发中；仅已完成阶段可声明通过，未完成部分不表示已交付。

| 阶段 | 当前状态 | 验证 |
|---|---|---|
| A 存储 / Capture Contract | 实现完成 | 11 项单测、1 项 PG 迁移/约束/Trigger/有档拒绝降级测试、全量后端 1138 项通过；Ruff 通过。 |
| B Chat 原子完成 | 实现完成 | 2 次实际调用/3 Evidence、缓存审计、同 request 竞争、写入异常/超限/截止回滚；全量后端 1143 项通过，最新预算路径专项 36 项复核。 |
| C Offline Verifier / API | 实现完成 | 20 项离线/API 单测、最新业务数据变更隔离 PG 回归、全量 1164 项通过；Ruff 通过。 |
| D Report v3 绑定 | 待实现 | 历史报告保持 v1/v2 |
| E UI / 遗留整改 | 待实现 | 不开放未经验证状态 |
| F 回归 / CI / 交付 | 待完成 | 最终补记真实 SHA、CI URL、覆盖率与浏览器结果 |

## A 阶段契约

- 迁移：`0051_m16_5_evidence_archive`，不修改 0046–0050。三表仅追加；owner/chat/turn/audit 复合引用，call/Evidence/turn 唯一，hash/JSONB 大小检查，UPDATE Trigger 与父 FK RESTRICT。
- 空库测试演练 0049→0050→0051、回退再升级；有任意 Archive/Binding/Manifest 时 downgrade fail closed。不自动删除档案。
- `EvidenceRef._archive_projection` 仅为服务端内部字段；取自实际 `evidence_ref(content=...)`，不在公开 tool payload、模型消息或 API 中序列化。v2 canonical/content_hash/evidence_id 算法未改变。
- Projector `m16.5-content-projector-v1` 适配原九工具 1.0：Derived/Backtest 为 record；Coverage 为 summary+daily；Performance 为 artifact_type+bundle_identity+summary；Study 为 identity+summary；Window 为 study_id+validation_id+window。不能用 records 的近似内容取代投影。
- Archive canonical 版本使用既有 Evidence v2 算法，payload/projection 使用其精度字符串规则。存储大小按带空格 UTF-8 JSONB text 估计；原工具 64 KiB 上限之外还检查 JSONB 表达大小。
- 默认预算：payload 64 KiB、turn 总计 640 KiB、8 calls、64 bindings；可在 agent.archive 配置调整但不越过数据库硬界限。当前 Chat 默认总调用 8，单工具 Evidence 64；保持原 45s 总 Deadline。
- 同一 Evidence 不允许内容/来源/冻结 payload 冲突，错误为 EVIDENCE_DUPLICATE_CONFLICT。缓存使用两条 call 身份与单一 Evidence binding；所有实际选中调用保留来源。
- 新开关默认 false，A 尚无聊天/报告写入口。历史数据不回填，也不查询最新业务指标补证据。

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
部署/生命周期与最终回滚验收将在后续阶段补齐；当前不得对外宣称完整研究可重验。
