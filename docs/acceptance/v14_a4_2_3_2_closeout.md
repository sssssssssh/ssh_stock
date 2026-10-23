# A4-2.3.2 P0/P1交付：INSUFFICIENT_EVIDENCE / STOP / OPEN

## 1. 结论、提交与CI身份

没有确认唯一可修复候选。唯一预注册批次采集了64/128个lookup记录；block1末轮后检查发现
合成库活跃autovacuum worker由0变1，按冻结协议立即停止，block2/3未启动，没有重跑或补样。
实际四关键表统计字段/摘要没有观测到变化，不能把本次失败编造成“又发生了自动ANALYZE”。
整个实验仍为INCOMPLETE_ENVIRONMENT_DRIFT，完整稳态和预注册四进程因果合同未通过。
P1c只交付真实部分证据和不足结论，不是生产优化完成、P95通过或正式L2成功。

| 阶段 | 提交 | 实际结果 |
|---|---|---|
| P0协议先行 | `da97cbe63b57499c4b3705ba671c179e4440fd0e` | 在新测量代码之前独立提交；未运行新SQL性能实验 |
| P1a初始工具 | `5e2ac9e0135e94a92af09f948e6600fc94e94ecf` | pytest同名模块收集失败，采样跳过，0样本 |
| P1a收集修正 | `462d46e26e8ea4e3bcc1b2631e8c20eeb213a87a` | 171测试/Ruff通过，采样仍跳过 |
| P1b唯一激活 | `3916dc4dc72f83f2470a96ff265428bd2e9549e2` | 同SHA预检172通过；唯一归因批次失败关闭 |
| P1c离线结案 | 本记录所属提交 | 固定ZIP复算/不足结论；普通提交不再次触发实验 |

实验源是3916dc4 / [run39833706083](https://github.com/sssssssssh/ssh_stock/actions/runs/39833706083) / attempt1，
[归因Job120019624908](https://github.com/sssssssssh/ssh_stock/actions/runs/39833706083/job/120019624908)实际FAILURE，
contracts Job120016349504实际SUCCESS。不能因为预检绿色把整个工作流写为PASS。
最终结案SHA的新CI须独立记录，不能继承实验源SHA的容量或发布资格；本轮没有这种资格。

截至2026-10-23 03:12（北京时间），实验源的
[主CI39833706219](https://github.com/sssssssssh/ssh_stock/actions/runs/39833706219)、
[A4-1（39833706185）](https://github.com/sssssssssh/ssh_stock/actions/runs/39833706185)、
[Publication39833706235](https://github.com/sssssssssh/ssh_stock/actions/runs/39833706235)仍运行，
[A4-2（39833706105）](https://github.com/sssssssssh/ssh_stock/actions/runs/39833706105)排队，均NOT_VERIFIED。
原release严格门禁不变，正式L2仍NOT_AUTHORIZED，不把跳过或旧SHA工件填为成功。

## 2. 修改清单与冻结范围

新增隔离脚本a4232_stability_contract、a4232_plan_probe、publication_tail_stability_a4232：
新UUID库双身份校验、正式规模分表计数、四表pg_statistic服务端摘要、fresh/cached计划签名、
默认ANALYZE/条件式四表控制、固定交叉顺序、原wall和完整自然GC/资源/错误证据。
新增独立a4232-statistics-tail-diagnostic工作流，contracts先行，唯一标记/master/attempt1采集，
原主CI/audit/A4-1/A4-2/capacity/release无改动。
新增a4232_test_receipt/a4232_pytest_receipt，预检工件只保存计数、错误类/SQLSTATE/脱敏栈，
不上传JUnit原异常或SQL。新增publication_tail_stability_review_a4232只读复算固定ZIP，不连接数据库。
unit测试及test_tail_stability_pg17_a4232微型集成测试覆盖身份、稳定性、异常、清理及旧A/B安全合同。
README、PROJECT_RULES、PRD、系统设计同步维护；没有更新导出版docx。

相对基线29ee845，backend/config/migrations/frontend、原lab、a4231采集器/指标、旧历史JSON全部无差异。
生产仍C0，源码SHA256：7708d91c831a64093f18aa4f8515789492762f464ccfe202ee0219b756f32976。
[冻结协议](v14_a4_2_3_2_protocol.md) SHA256：
047db54f9ac95b1729afa30e221f0fbd7013013db5fa4bf6f6302c4645affb39，测量后未修改。

## 3. 统计稳定性：观测事实与未完成项分列

PG17.11，Python3.12.15，4CPU/约16.77GB主机，容器CPU/memory未设限（0），不宣称独占I/O或受控冷缓存。
测量实例marker=e276cf5b-e571-459c-a6f5-f870963e51a6，system ID=7699568229653577772，
与预检实例分离，均通过marker+system identifier双核验。
正式Alembic+原seed：public十表603040行，诊断B503020行，分表计数、固定2000键hash均一致。
模型hash=f8bb5cf42d3f38757eda46ff149239789638f3aabe14434cda6ed7fe9daee20f；
索引定义hash=85923be916dcd7bfde34be15c5e8a329f76c121de97b415d612f90e94e9ffa63。

默认路径手动ANALYZE四表后，北京时间2026-10-23 **02:57:58至02:58:04**，
四次固定预检统计摘要一致且worker=0，故未进入table autovacuum fallback，表级选项保持默认。
原工件时间戳为UTC，例：2026-10-22T18:58:04.515755+00:00。
采样开始后不允许因失败回到fallback；因此后续检测到worker时没有关闭autovacuum再测一遍。

| 维度 | 实际证据 | 不能声称的事项 |
|---|---|---|
| 数据快照 | 两子进程共享parent snapshot hash af59354091a45070461606e0b670e651f8affc5f9eb4c7ecea3b63d540373c0d | 不能由此推断统计和plan cache也冻结 |
| 四表统计 | 已记录的reltuples/relpages/last_analyze/last_autoanalyze/reloptions/pg_statistic摘要无差异 | 不证明未来不会变化或全128合同完成 |
| 索引/settings | 已记录指纹无差异；SQL300s、plan_cache_mode=auto | 不等于生产默认环境性能通过 |
| 计划 | 34个已记录快照中，同方案fresh/cached结构签名不变 | block1末轮后计划未采到；4个样本后置签名缺失 |
| prepared | C0保持custom，C1保持generic，threshold5/max100不改 | 两SQL并非同一个prepared mode，不能只归因SQL形态 |
| 背景维护 | 02:58:55.241885，block1/round7后检查，worker从0变1 | 只有计数，表/操作/开始时间NOT_AVAILABLE，不证明新ANALYZE |

四关键表为data_publication_row、signal_forward_eval、stock_opportunity_daily、stock_trade_status_daily。
data_publication_row reltuples=503197是估计，不是B实际503020行丢失或增加。
故障时四表pg_statistic SHA仍分别为b753eab2…、93938e52…、932f8d29…、d9798ec8…（完整值见工件）。
此次唯一变化是数据库级active_autovacuum_workers，**不是具体表统计字段发生漂移**。
协议把后台活动列为失效条件，停止是正确失败关闭，不是超时/RESOURCE_DEFERRED。

64条lookup均有Golden与完整计时；parent仅接纳已完全验证的block0共32条。
block1也保存32条，但最后4条因post-round守卫失败没有后置计划签名；它们完整保留而未伪装合格。
block2/3共64条没有采集。没有补样、剪裁、换Runner、改seed、提高预算或修改P95标准。

## 4. GC/Telemetry/顺序/SQL机制与反证（仅描述部分样本）

保留1026个自然GC事件：Gen0=932、Gen1=86、Gen2=8；64个样本退出点GC策略均为enabled，threshold=(700,10,10)。
八个Gen2均在wall内；所有GC/JSON/next/CPU时间存在嵌套，不相加、不从wall扣除。
同轮/位置随两个进程的交叉顺序，长GC出现于相反的observer模式：

| 0基round/position | block0：方案/模式/Gen2秒 | block1：方案/模式/Gen2秒 |
|---|---|---|
| 0/1 | C1/full/0.088345 | C1/minimal/0.122026 |
| 2/3 | C0/full/0.123841 | C0/minimal/0.123979 |
| 5/1 | C0/minimal/0.107751 | C0/full/0.094583 |
| 7/1 | C0/full/0.123013 | C0/minimal/0.097543 |

block1 round0 position1的C1/minimal之前，本子进程还没有实例化full Telemetry（预热无Telemetry，
该轮顺序C→D→B→A），仍出现0.122秒Gen2。这是“Telemetry实例是长GC必要条件”的直接反例，
但不证明Telemetry完全无影响；后续minimal仍可能承接前面full产生的对象历史。
固定位置、预热/探针/共享进程分配节奏尚无单独因果干预，不能据此给某个生产代码行定因。
触发栈分别出现raw_decode/decode/loads/call或load/fetchone/_fetchiter_impl，不是回收对象归属证明。
block1末轮没有后计划探针，最后一行同样保留，不能挑掉后算出漂亮结果。

以下每格16条，共64条，包含末轮未验证记录；仅DESCRIPTIVE_PARTIAL，**不是原P95门槛或新稳态验收**。
新版本包含tracemalloc和额外计划探针，不和旧1100/128绝对时间比较收益。

| 方案/模式 | wall P50/P90/P95/P99 秒 | execute中位数秒 | buffered-next中位数秒 |
|---|---|---|---|
| C0/full | 0.298274 / 0.398653 / 0.422476 / 0.424399 | 0.098542 | 0.119512 |
| C0/minimal | 0.295399 / 0.397331 / 0.407381 / 0.423016 | 0.097343 | 0.119662 |
| C1/full | 0.257610 / 0.264576 / 0.284734 / 0.329677 | 0.061548 | 0.116771 |
| C1/minimal | 0.255919 / 0.266119 / 0.295154 / 0.360146 | 0.060959 | 0.116031 |

JSON中位数约0.0295–0.0299秒。backend CPU区间中位数C0约0.09秒、C1约0.05–0.06秒，
包含观测开销、时钟粒度有限，不能视作纯查询CPU；execute还含驱动传输/缓冲。
四组queryid窗口的calls中位数均4、shared hits中位数均18000，read/temp/WAL中位数均0；
这不证明独占I/O为零或解释了所有尾部。样本退出点RSS最大240345088字节，约229.2MiB，不是逐查询峰值。
C0/custom与C1/generic不同，观察到execute差异不能直接命名为SQL形态净收益。
旧repeat81的非大GC execute异常仍UNKNOWN。两个未启动进程及不完整末轮使八分块H3判定NOT_EVALUATED，
不能用已完成block0或两个进程的局部结果替代原四进程合同。

## 5. P1是否证明唯一修复候选

**否，INSUFFICIENT_EVIDENCE。** H1确认自然GC事件但不知道分配者；H2行物化只观察未单独干预；
H3有跨模式/首次minimal反例；H4位置/历史存在关联但未证实独立因果；H5存在execute/cache-mode差异，
旧非GC例未解释。背景维护约束又中止完整队列，因此不能提出“修复后必过”的唯一生产修改位置。
unique_repair_candidate=null，停止后续生产优化并等待用户再次审阅。
历史1100样本（44e46b0/run39785757520/attempt1）analyzed C0/C1 P95仍为0.088756/0.191595秒，
约2.159倍失败，七异常中六个大GC相关点和repeat81非GC反例不改写。
旧128样本（947966d/run39820748153/attempt1）H3仅2/8、四长GC均在C0及as_seeded漂移也仍保留。
两批均HISTORICAL_DIAGNOSTIC，详见[冻结历史身份](evidence/a4232_historical_baseline.json)，不与本64合并。

## 6. 测试、原始工件与可复算性

P0前1857单测；初始P1a 1927；收集修正1929；唯一激活前1930项均实际通过；
本P1c专项79项通过，完整1936项单元测试通过（24.86秒、两个既有弃用警告），Ruff/diff检查通过；
这不是当前SHA全CI或完整128样本验收。
预检实际171/172项分别来自462d46e/3916dc4，均包括4个微型PG17测试与既有A/B安全回归。
最初同名模块错误已在本地collect-only复现并修正，不是重跑性能实验取PASS；仅3916dc4带一次性标记。
本机Docker未启动，所有实际PG17在CI新实例/UUID库内运行；未跑本地集成测试或借用业务.env。

| 工件 | 身份与摘要 |
|---|---|
| [初始收集失败](https://github.com/sssssssssh/ssh_stock/actions/runs/39831770523/artifacts/12448308593) | 5e2ac9e / run39831770523 / attempt1；样本0 |
| [修正预检](https://github.com/sssssssssh/ssh_stock/actions/runs/39832828251/artifacts/12449991106) | 462d46e / run39832828251 / attempt1；171测试，非性能证据 |
| [激活预检](https://github.com/sssssssssh/ssh_stock/actions/runs/39833706083/artifacts/12450836240) | 3916dc4 / run39833706083 / attempt1；172测试，SHA256=0714ed280e497efc0d2814c479a0bf6895ddb4db3f6e791d7217c03e0ca5572d，已下载核对 |
| [唯一原始批次](https://github.com/sssssssssh/ssh_stock/actions/runs/39833706083/artifacts/12450573698) | 同3916dc4/run/attempt；109252字节，root+两个child JSON |

原始ZIP SHA256=3276cdbc12413ce2ab4a3a522a53b6d9c434dfbd19d85f7655126b8f3094ad10，已下载匹配GitHub摘要。
child0 SHA256=38526d8fb324c1f81edad8411153e9d010fe6a6d8e1405167061f393d23dfa3b；
child1 SHA256=2f1590ce2cf1954773ce97e778830cf3c9a5105dca4a2c57aacfc8c5f83192d6。
[源工件身份](evidence/a4232_source_manifest.json)与[离线审阅](evidence/a4232_stability_review.json)永久保留；
审阅SHA256=67b61d90f5d07978a53b06cfdef44c825c85eb823050283fa962c6dcfd235fe9。
复算重读原ZIP，不重新执行SQL；原测量脚本及冻结协议在P1c无改动。
工件模式扫描未发现数据库URL、股票代码自然键明文、Query Text或Query Parameters；只留白名单计划结构。

```bash
python scripts/publication_tail_stability_review_a4232.py --archive SOURCE.zip --manifest docs/acceptance/evidence/a4232_source_manifest.json --output NEW.json
python -m pytest tests/unit/test_tail_stability_a4232.py
python -m ruff check backend tests migrations scripts
git diff --check
```

本地完整单测实际安全包装（非服务启动，不使用业务.env）：

```bash
env -u LLM_ENABLED DATABASE_URL=postgresql+psycopg://disabled:disabled@127.0.0.1:1/a4232_disabled_test TUSHARE_TOKEN=synthetic-a4232 python -c 'import sys; sys.path.insert(0,"backend"); from app.core.config import Settings; Settings.model_config["env_file"]=None; import pytest; raise SystemExit(pytest.main(["tests/unit","-q"]))'
```

T01/T02沿用冻结1100/128的ZIP/样本/顺序复核；T03–T09由物理目标/分表计数/统计与计划/越权测试覆盖；
T10–T14覆盖自然GC、异常清理、PID/顺序/完整样本计算；T15沿用typed/null/tombstone/跨root/发布/取消/回滚；
T16–T19覆盖嵌套计时、后台活动失败关闭及无唯一候选；T20–T24仍以原严格门禁和新增隐私/独立Job测试为准。
“128完整样本”和“完整四进程环境合格”明确未完成，不能用测试覆盖替代实际缺失。

## 7. 审批状态

本轮只P0/P1。P2/P3、正式5/100、生产C1、正式603040行L2及A4-3/B/C均NOT_AUTHORIZED。
capacity_ready/performance_eligible/production_matches_candidate/production_read_authorized始终false。
没有生产补丁、候选修复ADR或L2合格报告，不改变原发布准入。

## 8. 未关闭项

完整128/四进程合同、覆盖整个采样周期的背景维护约束未达到；具体worker关联表/动作/开始时间未采集；
block1最后4条后计划签名、该进程最终分配摘要/GC final及block2/3缺失；H1–H5尚无唯一生产可修复机制。
旧正式C1 P95失败与repeat81反例仍OPEN；最新主CI/聚合门禁未核验完毕，既有依赖风险独立保留。
唯一后续方向是先审阅覆盖整个采样周期的后台维护控制/观测协议，不在本轮追加试验或修改生产。

## 9. 业务安全声明

未访问阿里云/ECS/RDS/业务数据库，未读取业务.env、修改原始数据、部署/重启服务或操作在途任务。
只清理自建PG17容器、UUID库和自身子进程。未关闭/强制GC或改阈值，未改SQL/发布300秒、
L2 270分钟、1000万行预算或batch500，AB_MERGE_READ_ENABLED保持false。

## 10. 后续 CI 配置单测修复（2026-10-23，独立于原实验）

本节仅追加后续记录，前九节的历史结论、原始 ZIP、manifest、协议和审阅 JSON 均不改写。
核验基线为 master `0dddfa5609c31bff5c4aad4d266486233c418808`，工作区原本干净，
与实际 origin/master 一致；仓库仍为 `sssssssssh/ssh_stock`，没有按任务书 URL 的拼写差异更换远端。
[该 SHA 的主 CI 39839230208](https://github.com/sssssssssh/ssh_stock/actions/runs/39839230208)
已失败：test 失败，audit/lookup 成功，capacity 因未获授权跳过，publication-release-gate 失败。
任务书提供的全量结果为 2746 passed / 1 failed、覆盖率 89.26%；这是基线，不是本补丁结果。

### 已证实根因与未证实项

原 `test_eas_dotenv_values_configure_effective_chat_identity` 没有隔离五个 LLM 进程变量。
本机 Python 3.12.11 / pydantic-settings 2.11.0 / pydantic 2.13.4：

- 五个进程变量未设置时，原文件 4 passed（退出码 0）。
- 仅设置合成 `LLM_ENABLED=false`，同一原文件稳定复现 1 failed / 3 passed（退出码 1），
  原 `llm_chat` 断言实际为 `tools_only`。本地 JUnit 分别为
  `.codex_tmp/a4232-followup/before-clean.xml` 与 `before-ci-environment.xml`。
- Settings 没有自定义 source 优先级，进程环境覆盖临时 dotenv；
  `_apply_agent_llm_overrides` 按已解析的 false 正确生成 tools_only，不是生产配置缺陷。
  [Pydantic 官方优先级](https://docs.pydantic.dev/latest/concepts/pydantic_settings/#field-value-priority)
  与此一致。未启用会输出配置值的 settings DEBUG。
- 既有诊断 `setup_runtime()` 会设置 LLM_ENABLED=false，部分集成 fixture 调用它；
  这是代码中可确认的环境污染入口。但没有采集原 CI 的逐测试环境追踪，
  不能把具体最后写入者或 Runner 来源猜测写成已确认事实。

最小修复仅在本测试模块的临时 dotenv fixture 中，使用 monkeypatch 清除
LLM_ENABLED/LLM_ENDPOINT/LLM_MODEL/LLM_AUTH_SCHEME/LLM_API_KEY，退出后恢复原环境。
保留旧 OPENAI_API_KEY 干扰项，真实 provider 仍必须选用显式 LLM_API_KEY。
独立 enabled=true/false 两例用冲突进程值验证五个字段优先级、密钥 repr、provider 选钥/禁用。
原 raw endpoint 请求、disabled 不要求 key、invalid endpoint 失败关闭测试均保留。
未修改 Settings、生产优先级、Provider 或其他测试 fixture。

### 实际验证与 Checklist

以下命令使用本地单元测试、合成不可连接的 loopback 配置，不运行集成数据库或业务服务：

```bash
python -m pytest -q tests/unit/test_m16_eas_llm_config.py
python -m pytest --collect-only -q tests/unit/test_config.py tests/unit/test_m16_1_agent_contracts.py tests/unit/test_m16_2_llm_orchestration.py tests/unit/test_m16_eas_llm_config.py
python -m pytest -q tests/unit/test_config.py tests/unit/test_m16_1_agent_contracts.py tests/unit/test_m16_2_llm_orchestration.py tests/unit/test_m16_eas_llm_config.py
python -m ruff check backend tests migrations scripts
git diff --check
```

| 编号 | 本地结果 / 后续要求 |
|---|---|
| A01 | 分支/HEAD/远端/干净工作区已核验 |
| A02 | 原失败已复现；优先级机制确认，具体 CI 最后污染源未追踪 |
| A03–A04 | 目标文件 6 passed；dotenv 正向、环境 true/false 覆盖均验证 |
| A05 | 清洁环境连续三次各 6 passed（2.03/2.07/2.42 秒），退出码均 0 |
| A06 | 五个环境变量同时合成冲突时仍 6 passed；既有安全测试保留并通过 |
| A07 | Ruff 和 diff 检查通过，退出码 0 |
| A08 | [观测提案](a4232_background_activity_observation_proposal.md) 已新增；PROPOSAL / NOT APPROVED / NO MEASUREMENT EXECUTED |
| A09 | 历史证据/协议、生产目录及所有 workflow/gate 保持基线内容；提交前再次 diff 核验 |
| A10 | collect-only 为 39 项，实际 39 passed；完整 pytest/覆盖率本地未执行，DEFERRED 至本提交 exact-SHA CI，不沿用基线或旧 SHA 结果 |
| A11 | 无业务库连接、迁移、服务操作、新性能实验或开关变更 |
| A12 | 本节记录范围/命令/结果；最终 commit SHA、推送及 exact-SHA CI 结果由 Git/Actions 与最终交付绑定，不预写通过 |

重复验证 JUnit 为 `.codex_tmp/a4232-followup/repeat-{1,2,3}.xml`，
冲突环境与相关回归分别为 `after-conflicting-environment.xml`、`related.xml`；均为本地临时产物，不提交。
只读 GitHub 状态核验不等于完整测试验收。推送后的主 CI 必须核对完整 pytest 数量、覆盖率、
退出码和 head/run/attempt；尚未取得时状态为 PARTIAL，不能因提交成功宣称 COMPLETED。

按本次任务书最小文件范围，仅修改目标单测、新增提案并追加本节；
没有功能或长期规则变化，四份权威 Markdown 的既有口径不变，未更新 DOCX。
后续 worker 关联、观测开销校准、完整新协议、128 样本、正式 5/100、L2 和生产优化均 DEFERRED/未批准。
原尾延迟因果仍不明确，capacity_ready=false 与严格发布门禁继续保留；
主测试通过不等于发布门禁通过，不能以 skipped/取消/部分证据补足验收。

已有 A4-1/A4-2 工作流会在每次 master push 自动调度性能矩阵；本轮不修改其定义。
为落实禁止新实验的范围约束，只取消本补丁 SHA 对应的这两条自动运行，不取消其他提交，
也不触发任何一次性归因标记。主 CI 和 a4232 的小型 contracts 回归保留；
被取消的工作流明确记为未执行，不能称为通过。具体 run ID 与取消结果在推送后核验。
