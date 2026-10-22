# A4-2.3 预注册协议 v1：P0 离线复核，条件阶段未授权

## 冻结范围与当前决策

起点 master `44e46b0cf4b52b2e7008e1f9ed842cd251971864`，工作树初始干净。
只从主 CI 39785757520 / attempt1 的工件 12429939366 做确定性离线复算。
ZIP SHA256：`e2ceaf9137e0ce52c0d91201329bf0de15a4cd14ab6321aaebf74e069ba4eceb`。
历史工件的全部 1100 样本、60 个 EXPLAIN、36 个实际连接探针不可覆写；旧 SHA 不能授权新 SHA 发布。

本协议没有新测量候选：`repair_candidate=NONE`；P1/P2/P3=`NOT_AUTHORIZED`。
这不表示减少原试验次数或门槛，而是 W1 未证明可修复根因，按用户要求停止进入条件阶段。
不运行“再试一次”100 次矩阵，不从 C2/C3 事后挑赢家，不启动完整 L2。
本次没有使用 W1.2 可选的那一次专项性能实验额度。

## P0 必须运行的确定性复核

1. 原 ZIP 摘要固定，不允许 CLI override；只内存读取指定 JSON，不展开归档，不加载 Settings/.env。
2. 身份核对 source SHA/run/attempt、PG17 marker/system ID、生产/候选文件 hash、模型/键摘要、规模。
3. 原顺序严格核对：regime→table→repeat→variant；variant 起点 repeat%5，五方案轮换。
   两统计状态、两慢表各 5×5、快表各 5×100，总数 1100；少一次/重复/改顺序均拒绝。
4. summary/whole_workloads/decision 逐数复算；分位数用 `statistics.quantiles(n=100, method='inclusive')`。
   不扣除 GC、不剪裁、不做 winsorization、不选最快样本；控制表 400 点 C0/C1 完整列出。
5. 保存 P50/P90/P95/P99、全部排名、越过 C0 P95×1.10 的 C1 样本、CPU/RSS/等待/计数。
   GC 是嵌套指标；backend CPU 含计时外观察区间；VmHWM 为生命周期峰值。
6. 仅增加功能性测试：GC 回调成功/异常清理、JSON/Session 恢复、一次 mappings 迭代。
   使用模拟回调，不调用 gc.collect、不关闭 GC、不设置阈值；不把功能测试计时当性能证据。
7. 新 CI 只重算历史失败，另输出绑定当前 SHA/run/attempt 的拒绝收据。
   该收据只能是 CAPACITY_NOT_AUTHORIZED，不能转换成性能或容量 PASS。

## 若要进入 P1，需要先审阅的新协议（本轮不执行）

必须先有可复现的因果证据并明确唯一允许修改；没有候选不得重复旧试验。
任何 observer/计时边界修正均需独立版本化、用户审阅，历史结果不能直接当收益对照。
保留原 C0、C1 与至多一个经批准修复候选，不增加方案、次数或事后筛选。
同一隔离 PG17、同 public603040/B503020、同 2000 键/模型索引/settings/资源；
as_seeded/analyzed 分开，慢表每方案每状态 5 次，快表 100 次，轮换顺序运行前固定。
wall 完整保留 SQL、JSON、Python 映射与真实 GC；所有方案计时边界相同。
GC 只能观测，不关闭、不强制收集、不改阈值。没有受控冷缓存时明确不主张冷缓存结论。

全部门槛不变：两慢表 median≤C0×0.70；逐轮三表 wall 求和的 median≤C0×0.80；
控制表 median≤C0×1.10；全部表 P95≤C0×1.10；两种统计状态分别成立；Golden/资源均不回归。
单 SQL300s、全诊断软预算100min、Job120min 不提高。预算不足保留 INCOMPLETE，不删关键样本。
失败立即停止生产修改；不追加重复至 PASS。

## P2/P3 条件与不变保护

只有新协议测量与安全等价全部通过，才能申请 candidate_source() 的精确 C1 文件差异；
本轮不批准 Python 行物化重构或额外生产源码变化。冻结校验只可给精确已验证差异例外，不能全局关闭。
正式 L2 必须实际生产源码匹配、最新 SHA/attempt 的完整样本/计划/Golden/资源门禁齐备。
仍是 5000×20、十表603040行、batch500、SQL/发布300s、1000万行预算，真实发布/两个回滚/读者/FIFO 不减。
缺少前置时明确 NOT_AUTHORIZED；skipped 不是 RESOURCE_DEFERRED。
不连接阿里云业务数据库、不改业务数据或在途任务、不启用 AB_MERGE_READ、不进入 A4-3/B/C。
