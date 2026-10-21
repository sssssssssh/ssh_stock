# ADR：V1.4 A4-2.1 CI 无损分片与证据门禁

## P1 决策与边界

基线为 master `02c69c6127860f72adaf79071a9a11930b69e411`。仅修改实验脚本、CI、测试与文档；
backend、config、migrations、frontend、生产 SQL、公式和 A4-1 冻结文件不变。不连接云端业务库。
这是 CI 基础设施整改，不是 A4-3 或历史复用 B/C，也不是生产性能批准。

旧运行 [A4-2 39561947935](https://github.com/sssssssssh/ssh_stock/actions/runs/39561947935)
与 [主 CI 39561948002](https://github.com/sssssssssh/ssh_stock/actions/runs/39561948002)
均 CANCELLED，不能作为新 HEAD 验收。元数据冻结于
[历史索引](../acceptance/evidence/v14_a4_2_1_history.json)。
主实验在百万级 actual cursor plans 阶段中断：177 次百万读取完成，但只有 6/59 组计划；
旧日志 531 次读取是三种规模各 177 次，不能误报 531 次百万读取。
补充实验任务成功不等于主实验或主 CI 成功。

## 无损分片

`scripts/a42_ci_contract.py` 定义版本化自然键与 21 个实验工作负载；独立 contract job 校验集合，
聚合 job 不承担实验。测试从基线 Git AST 与 workflow 独立重建原矩阵，要求严格集合相等，
既不能漏组也不能靠重复组补数量。

| 工作负载 | 必需组数 | 预算（分钟） |
|---|---:|---:|
| 10k、100k 各完整原矩阵 | 各 236 | 各 120 |
| 百万 full，两个 fraction 分开 | 各 30 | 各 240 |
| 百万 window，两个 fraction 分开 | 各 18 | 各 240 |
| 百万 full plans，两个 fraction 分开 | 各 10 | 各 240 |
| 百万 window plans，两个 fraction 分开 | 各 6 | 各 240 |
| 百万三个月根链 | 81 | 300 |
| 百万 monthly plans，三组 variant 分开 | 各 9 | 各 240 |
| 百万 RR2 | 24 | 240 |
| 五种 shape，各三个 tombstone | 各 45 | 各 120 |
| 100k E3 全读与月链 | 45 | 120 |

总必需组 1002，其中 read 825、plan 177。另加 6 个同 job 的窗口等保护 Q0 对照，
明确 auxiliary，不能替代任何必需组。每种规模的原矩阵为 full 60 + window 36 + monthly 81 + plans 59。
所有三轮原始样本保留，不删除慢样本。计划分片先捕获真实语句，再分别获取 SELECT ANALYZE、
DECLARE 估计与原生游标 actual；独立采集时间不混入读取计时，也不跨 runner 计算提速比例。
读取比较使用同 job、同 fixture 的等保护对照。窗口额外 Q0 控制用于避免跨 runner 对比。

百万 fixture 保持 A=2,570,000 / 当前 B=1,350,000 / 其他根 B=2,800,000，
partial+tombstone=1 黄金输出 3,104,443。PG17 读取实验固定 2 CPU / 3 GiB；SQL 300 秒，
不能为赶 CI 提高。capacity 沿用原 workload、原预算，单独记录资源等级，不能冒充读取实验同资源比较。
若任一分片仍无法完成，报告 RESOURCE_DEFERRED，再按实际证据无损细分或申请专用 runner；不缩规模。

## 检查点与失败关闭

每个组在开始前写 NOT_STARTED/运行状态；成功后以临时文件 + 原子 rename 写独立压缩 JSON。
小 manifest 保存键、状态、文件名、SHA256、身份、起止时间，不反复重写数百 MB 的累计 JSON。
所有收据携带 HEAD、基线、workflow attempt、job、model hash、fixture recipe/digest、PG17 随机 marker、
独立物理 system identifier、资源与设置。任何 DDL 前验证物理身份，子库创建与删除均再验证。
金标准包括自然键、排序哈希、dtype、NULL、行数、游标 EOF/close、B 遮蔽/墓碑以及原 E0/T8。
三个月必须保留真实 430 天边界、同根读集累积、每次 E0 与仅链尾 T8。E3 仍 UNPROVEN。

每个新组前检查剩余预算，预留清理与上传；不足时停止并标记 INCOMPLETE，不提高 SQL 超时。
SIGTERM/异常只保留实际完成组，当前组失败信息脱敏；SIGKILL/宿主丢失无法保证上传，缺工件本身阻断。
`always()` 上传不是完成证据，不能把取消、空文件、旧 HEAD 或部分收据当成功。

## 主 CI 与容量

主 CI 的 full pytest/coverage、Ruff、迁移、十表、单/双 Worker、Docker、前端与浏览器门禁保持。
只将长期容量移出核心串行链。L1=(10,2)、L2=(5000,20)、L3-scaled-10pct=(500,120)
各自独立物理 PG17。新增 `--level` 与旧 `--levels smoke|all` 互斥，旧默认 all 兼容。
不改 `run_level` 的真实工作负载，仍保留 1000 万行/300 秒预算、双读者、两个失败回滚探针、
A 摘要不变、占槽、最终 SUCCESS/PUBLISHED。

严格 merger 只接受同 HEAD/attempt/model、每级唯一且 COMPLETE 的三份收据，稳定按 L1/L2/L3 输出旧结构。
release job `needs` 核心与全部容量，`always()` 执行、失败也产生报告；任何 upstream 非 success、
缺工件、错身份或安全断言失败均非零退出。不同 workflow 的 attempt 不混为同一个编号。

## 分阶段交付

P1：本 ADR、矩阵、纯契约与负向单测。P2：接入脚本/原子工件/CI，不宣称 CI 已成功。
P3：最终 SHA 真实完整验收、原始工件及性能对照。代码通过与证据通过分别报告；
READ_PERFORMANCE_PASS=false/NOT_CLAIMED、production_read_authorized=false、authorize_a4_3=false。
