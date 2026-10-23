# A4233 W00–W05 交付记录

状态：**PARTIAL（实现完成，等待本提交真实微型PG17/CI验证）**。
基线73a3273301502822dc7a881a64dfdca45db4d063，master；未授权性能测量。
本文件只记录新观测能力，不更新旧A4231/A4232协议、工件、报告或一次性授权记录。

## 工作项与实现

| 项 | 交付 |
|---|---|
| W00 | a4233_baseline_and_contract.md、evidence/a4233_frozen_manifest.json；历史身份/冻结hash/权限与禁区 |
| W01 | a4233_background_observer.py；独立只读连接、固定SELECT/PG17精确字段、受限权限/双身份、四表及目录索引/TOAST映射 |
| W02 | a4233_observation_contract.py；typed/extra-forbid、单调/UTC/DB时钟、PID复用/跨视图矛盾、事件分类、部分记录、清理失败关闭 |
| W03 | 新unit与微型PG17测试；不调用lookup或seed，四空关系，每个成功用例3ticks，故障可0ticks |
| W04 | v14_a4_2_3_3_observation_protocol_draft.md；DRAFT/未批准，校准与归因分开，候选预算/样本/门槛仅提案 |
| W05 | 新a4233-observer-contracts.yml，唯一contracts job；原五workflow/policy/Gate未改；补登记清单/静态测试 |

复用verified_test_url/isolation与atomic、自有容器清理；不调用旧owned/statistics_snapshot的
DDL/统计刷新行为。管理员测试fixture在新UUID库显式创建并清理受限合成角色，observer无授权能力。
代码不读取环境DATABASE_URL/.env、不导入业务服务；只读URL显式且只允许本机合成目标。

## 实际验证（开发中记录，不预写通过）

- 首轮本机目标测试收集因psutil未安装失败，已移除未声明依赖，复用原RSS helper；未改依赖文件。
- 初次unit 82 passed/1 failed：SQL静态测试把has_table_privilege的权限名字符串误识别为命令；
  改为检查SQL可执行token，仍禁止全部写/维护/控制语句；没有降低只读约束。
- 首轮相关259项/全unit2118项各有1项失败：原治理清单拒绝第六条workflow；
  仅登记新contracts-only例外并保持未知workflow仍拒绝，原昂贵workflow断言全保留。
- 修正后相关命令：`python -m pytest -q tests/unit/test_a4233_background_observer.py tests/unit/test_tail_stability_a4232.py tests/unit/test_a4_ci_governance.py`，259 passed，exit0（3.07秒，无DB）。
- `python -m ruff check backend tests migrations scripts .github/actions`：exit0。
- 本机`docker info --format '{{.ServerVersion}}'`：exit1，daemon未启动。
  本地微型PG17为NOT_RUN，未借用业务库；真实PG17结果只以本提交新contracts CI为准。
- 全unit安全包装：2118 passed、两个既有Starlette弃用警告、27.22秒、exit0，无DB。
- 全范围Ruff exit0；冻结文件逐字节/哈希检查在259项相关测试内通过；未运行本地默认全pytest/业务.env。
- 最终diff/新PG17/CI结果待推送后追加，不把本机unit当数据库或性能通过。

完整unit包装（合成不可连接loopback，只运行unit，不启动服务）：

```bash
env -u LLM_ENABLED DATABASE_URL=postgresql+psycopg://disabled:disabled@127.0.0.1:1/a4233_disabled_test TUSHARE_TOKEN=synthetic-a4233 python -c 'import sys; sys.path.insert(0,"backend"); from app.core.config import Settings; Settings.model_config["env_file"]=None; import pytest; raise SystemExit(pytest.main(["tests/unit","-q"]))'
```

## 工件与复核

新CI保存`.codex_tmp/a4233/micro/{manifest,observer-contract,ticks,review,failure}.json`，
每份绑定exact head/run/attempt/source/protocol/instance摘要，标SYNTHETIC_MICRO_SELFTEST/DIAGNOSTIC_ONLY。
manifest记录每个文件SHA256/大小、序列化wall、含重序列化的原子write wall；不可相加或冒充开销校准。
schema额外字段/哈希破坏/身份不匹配/缺tick/虚假COMPLETE/越权准入均拒绝。
合同状态仅COMPLETE_CONTRACT或INCOMPLETE_OBSERVABILITY，NOT_OBSERVED不证明无维护。
线程SQL异常、部分tick、SIGTERM、join/close/write异常保留，不上传原始driver异常或JUnit。
离线review CLI的六项身份由独立可信执行上下文提供，不能只信待审manifest自己的声明。
内容hash证明一致性，不提供对能同时重写工件与manifest的攻击者的密码学真实性担保。

## 变更范围与剩余项

新observer/contract/reviewer、unit/PG17测试、独立contracts workflow、W00/草案/本报告/hash清单；
更新四权威Markdown、workflow inventory及其单测。backend/config/migrations/frontend、所有旧脚本/
协议/原始证据、原workflow、governance policy/consumed记录和Release Gate保持基线。

本轮不捕获新真实autovacuum性能事件，不证明监控开销已合格、不校准、不修复C1、不做P95/L2；
未访问阿里云/ECS/RDS、业务数据库/任务/服务。旧64/128结论不变、未补样。
管理员需在未来独立受信任合成环境预置所列受限权限；无权限时INCOMPLETE而非自动GRANT。
新预算只是待审草案，后续profile、开销校准/归因/生产均NOT_AUTHORIZED。
performance_eligible/capacity_ready/production_read_authorized恒false，unique_repair_candidate=null。
完成本阶段后停止等待用户代码审阅。
