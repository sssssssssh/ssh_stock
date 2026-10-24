# A42341 交付记录（模拟工具，不是真实校准）

当前总体：**BLOCKED_NEEDS_USER_PROTOCOL_DECISION**。工具合同结果以最终同SHA实际CI为准；
本记录在最终推送前提交，推送后run/attempt/job/工件及最终40位SHA由最终回执提供，不能提前标通过。
基线f5c0fe4d08f37c01714a3085d49f30da4bc4f1d4；master，开工与origin/远端一致且干净。
用户明确批准分阶段提交、最终一次push，**未批准16次预算或任何真实校准**。

## 提交、冻结和范围

- 协议先行本地提交：e4dd9bdd04a1a5f5cf1eb66684eb248f8600b9ed。随后才编码。
- v3提案SHA256：065b529f759308c49630c5ce390864a7589b51fcb1be645ca420ed3575692220。
- 新manifest SHA256：4cca8088909821371f99d8cd9dba450d2fa6ada4c6dbc462ccd8ec64498a163e。
- 原v2/manifest/input/旧两模块哈希、旧readiness与W00记录在新清单逐字节冻结。
- 8次仍是有效确认；16只是同真实连接/driver字节/OID键、四SQL/lookup假定下的必要下界，不是稳态充分性。
- 原backend/config/migrations/frontend、全部旧scripts、历史evidence/协议/policy/one-shot/五旧workflow/Gate不改。
- 仅新六a42341模块、新三文件unit、新文档与四权威文档/索引追加；专项三步骤/三paths精确白名单，
  旧CI治理测试的原断言保留并严格投影，新测试逐字段重建完整预期工作流。

## W00–W08

| 工作包 | 当前完成边界 |
|---|---|
| W00 | DONE：基线、同SHA旧CI、七ZIP与内部JUnit/迁移/Observer证据实际离线重验，见baseline_and_blocker |
| W01 | A提案DONE/USER_APPROVAL_PENDING；B仅研究PARTIAL，估计目标/分层/局限已列，但正式B接受门槛须另定，不回退至B |
| W02 | 静态/模拟DONE；真实同连接、driver字节/OID与server prepared/plan能力BLOCKED/NOT_PROVEN |
| W03 | MOCK DONE：128唯一点/64对/16候选记录、四逻辑串行block；无真实进程/DB/lookup |
| W04 | 模拟资源/统计/计划/后台事件失败合同DONE；真实CPU/权限/无扰动cached plan及长期bridge仍PARTIAL/未验证 |
| W05 | MOCK DONE：独立expected、全样本/分组/Decimal inclusive、原子新写与离线复核；无真实资格 |
| W06 | DONE：旧execute保持，新入口始终拒绝，两道人审独立，环境变量/token/普通事件不激活 |
| W07 | 本地结果及最终同SHA CI见最终回执；不能用基线绿灯继承本次验收 |
| W08 | 此报告与索引交付；最终回执追加推送后事实后停止等待人审 |

## AT01–AT20 覆盖索引（真实通过数以实际测试/CI回执为准）

| AT | 合同/反例 |
|---|---|
| AT01 | prepared_capability：旧字节hash、8次、旧execute拒绝 |
| AT02 | 固定128/64/variant/方向/顺序hash，完整模拟bundle往返 |
| AT03 | 候选16=8条件×2；4次不足/8次仅理论越阈值，prepared_stable恒false；锁定PrepareManager纯缓存函数 |
| AT04 | SQL文本/参数类型/连接/缓存键分别替换及四批缓存键分裂拒绝 |
| AT05 | threshold/缓存键/驱逐/pool checkout/计数/driver观察未知拒绝 |
| AT06 | 原8次guard与新execute即便伪造批准也不能执行 |
| AT07 | 源码/协议/model/依赖/HEAD/脏树/短SHA/两道批准/假env、token反例 |
| AT08 | OFF空tick，ON缺边界/微型v2误用/128ticks/假真实适配器拒绝 |
| AT09 | 四批/driver/JSON/自然GC全wall，嵌套段不求和、不扣除；错误wall拒绝 |
| AT10 | backend PID/起点/proc start/单位/时间区间/不可得/零分母拒绝 |
| AT11 | CPU/RSS作用域、缺值、整worker比例门槛等值与越界 |
| AT12 | 四表统计/索引/fresh/cached/模板/模式/累计计数异常、探针次序拒绝 |
| AT13 | 所有维护/未知/冲突/PID事件、partial tick、STOP_TIMEOUT和生命周期、时钟漂移反例 |
| AT14 | 缺1/重1/乱序/错pair/block并发/预算、预热与样本混计拒绝 |
| AT15 | Decimal inclusive P50/P95精确等值、越界、负signed/abs/positive原值保留；慢点不删 |
| AT16 | 坏JSON/重复键/NaN/Inf/符号链接/过大/路径穿越/坏摘要/未知字段/错schema/SHA/attempt拒绝 |
| AT17 | sticky首错、失败末点、未join快照、cleanup错、原子写盘错/超时/不覆盖、失败脱敏 |
| AT18 | 全部模拟门槛合格仍MOCK_CONTRACT_ONLY、所有准入false、因果NOT_EVALUATED、absence_proven=false |
| AT19 | 原A4233/A4234/治理/迁移兼容由本地unit及未改动最终SHA CI验证，70%不变 |
| AT20 | 最终一次push触发原普通CI/专项，新unit与独立a42341工件；昂贵jobs仍应skipped；待真实回执 |

所有新增测试只用纯函数/内存mock/本机临时文件及只读Git元数据，不运行新的PG/容器集成测试。
本机完整unit显式禁用业务.env，使用假loopback不可达DB地址；完整PG pytest/前端/容器/浏览器留给原普通CI。
原CI会连接自己的隔离合成PG17跑既有回归；这不等于新校准器有真实DB/预热/2000键benchmark执行。

推送前实际结果：任务书五文件定向测试266 passed（新增157，原109）；全部unit 2426 passed、5条原有弃用警告，
48.35秒；Ruff（backend/tests/migrations/scripts/.github/actions）与git diff --check通过。
冻结清单20文件逐字节校验通过，backend/config/migrations/frontend/历史evidence相对基线零差异。
这些是本地单元结果，不替代最终SHA的完整pytest、PG17迁移和前端/构建/浏览器CI。

## 异常修复及审阅约束

负向回归先复现未join末点被标COMPLETE/cleanup完成，随后改为INCOMPLETE、cleanup未完成，
whole-worker未知CPU/elapsed为None并保留已取得ticks、lookup与首错；新增断言保留，不能以无准入掩盖状态误报。
开发中另纠正测试构造：模拟嵌套段意外恰好求和、Decimal数值相等但字符串尺度不同、run/attempt为外部
独立可信上下文而非Git可推导字段。最终使用精确Decimal等值及独立expected的错误attempt断言，不增加容差。
所有这些都是纯mock/单元调试，不是真实性能重复试跑；原P95门槛、样本与GC设置完全没变。
另复现了model_copy伪造配置触发Pydantic警告回显原值：改为序列化告警抛错并转换固定错误码，
负向测试同时断言无原值异常输出、无warning；未全局屏蔽警告。最终仅余五条原有弃用警告。

## 工件与真实能力缺口

专项新a42341-contract-SHA-run-attempt包含去敏unit计数/独立身份，以及mock-complete、mock-incomplete
的samples/review/failure/manifest；每份原子新写、哈希绑定、已存在拒绝覆盖；失败没有完整manifest就拒绝。
离线Reviewer不能从工件自己提取expected当独立来源；run/attempt须来自可信外部CI索引，其他摘要重建自Git/冻结文件。
完整与失败fixture均只能SIMULATED_ACCEPT/REJECT，外层NOT_RUN_NOT_AUTHORIZED，不能导入正式Gate当性能凭据。

真实fixture的marker/system双身份、受限角色和真实driver/cache键尚未核验；pg_prepared_statements仅是同会话只读视图，
计数不能证明cached plan结构。当前没有获批且已实证的无扰动cached plan采集器、backend CPU生命周期采集或长期bridge。
旧EXPLAIN EXECUTE/pg_stat_clear_snapshot不能直接挪用；不提权、不更改planner/GC/autoanalyze。
方案B的正式接受条件未注册；若用户坚持8次，需另一个B设计任务，不沿用A的稳态解释。

## 下一道人审与停止

请先裁决是否批准修订协议/预热预算（A至少16，仍需确定充分准备和固定上限；或另设计B；否则C继续阻塞）。
这不自动批准运行。工具及真实能力预检完成后，还须第二次明确批准真实exact SHA/profile/未消费one-shot/
预算/隔离runner与角色/Environment真实保护。此任务不注册这些执行权限，也不启动任何测量。
本地新增工具/测试无真实数据库、预热、lookup或容器启动；未访问业务.env/阿里云/业务数据库或改动在途任务。
所有真实资格恒false；Historical A4231/A4232=UNCHANGED/INSUFFICIENT_EVIDENCE。到本阶段交付为止，等待再次审阅。
