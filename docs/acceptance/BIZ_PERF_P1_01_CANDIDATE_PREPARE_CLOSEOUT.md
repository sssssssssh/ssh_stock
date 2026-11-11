# BIZ-PERF-P1-01 候选暂存准备优化回执

状态为 `NO_MEASURABLE_GAIN / SOURCE_REVERTED / PG17_NOT_RUN`。
固定交错样本的部分中位数改善，5,000 行准备阶段 P95 超过预定 10% 上限，候选未达保留条件。

## W00 基线与热点

开发基线、开始时 HEAD、origin/master 和 GitHub master 均为 `3e8c126eceaca20fdc100fdd5889932704415a13`，工作区干净。
基线相对 f7d8e26 只新增七个 D04 送审文件。治理与业务文档沿用本会话已读内容，基线间无差异。
本轮授权仅覆盖候选准备离线开发与普通推送。真实实验及正式 P1/P2 验收继续待批。

调用顺序为 register_source → 每 500 行 _lookup_batch → prepare → _store → _store_batch。
查询与写入均已有批处理。查询使用完整候选主键点查，旧空统计用例验证 500 次主键探测。
V1.3 记录 10 万行的候选 SQL 从 840 降到 420。历史 C1 在 ANALYZE 后 P95 为 C0 的约 2.159 倍。
本轮可观测的重复工作是每行获取列集合、构造默认更新列和查询 KEYS。
它们可以离线计量，整链耗时占比仍为 UNKNOWN。

| 基线 workflow | Run / attempt | 核查结果 |
| --- | --- | --- |
| Main CI | 42951354009 / 1 | in_progress，test 正在执行完整 pytest |
| A4-1 | 42951354785 / 1 | completed/success |
| A4-2 | 42951353933 / 1 | completed/success |
| Publication V1.3 | 42951354003 / 1 | completed/success |

各 Job、结论和 skipped 状态见仓库外 baseline-ci-jobs.json。授权、正式实验和容量 Job 的 skipped 保留。

## W01～W03 对照与回归

基线语义测试 17 passed，三个结构断言真实 RED，exit 1。501 行的列集合读取 501 次、
默认更新场景列遍历 1002 次、KEYS 取值 502 次。候选对应结果为 2、503、1 次。
实际模型元数据和 fake Session 覆盖空/单行/满批/跨批、重复键、显式更新、NULL/JSON、
ID 和序列、来源拒绝、类型/默认值、首次原像、取消与失败、映射及迭代器、对象独立性。

候选仅 upsert 函数内 +32/-17。局部绑定 KEYS 与列集合，复用默认更新列。
只有原生 tuple 或仍与原键匹配的原生 list 使用复用。一次性迭代器、自定义 membership、
显式更新列、NULL 保留及 JSON 合并参数沿原路径。原调用次序和批大小均保留。
经方法源码提取比较，upsert 之外的 Git 规范化文本逐字节相等，nextval SQL 文本也未改变。

| 命令 | 结果 | 外部日志 |
| --- | --- | --- |
| python -B -m pytest -p no:cacheprovider tests/unit/test_perf_p1_candidate_prepare.py -q --tb=short（基线） | 17 passed / 3 failed，exit 1 | red.log、red-command.txt |
| python -B -m pytest -p no:cacheprovider tests/unit/test_perf_p1_candidate_prepare.py -q（候选） | 20 passed，exit 0 | new-final.log、new-final-command.txt |
| 定向与任务书五个旧模块组合 | 100 passed / 1 failed，exit 1 | green.log、green-command.txt |
| python -B -m ruff check --no-cache backend tests migrations scripts | PASS，exit 0 | ruff.log、ruff-command.txt |
| git diff --check | PASS，exit 0 | 交付静态检查 |

旧组合中的 80 项通过。唯一失败为旧测试创建符号链接时收到 WinError 1314，未进入业务断言。
本机依赖沿用 Windows Python 3.12.11、SQLAlchemy 2.0.52、pytest 9.1.1。
PG17 隔离测试无本轮运行许可和现场证据，记 NOT_RUN。

## W04 有界准备阶段对照

A 由基线原始 Git Blob 提取，B 为本地实测候选。相同解释器、模型、输入和空闲 fake Session 边界。
每档先分别跑一轮完整字节校验作预热，然后九组交替 AB/BA。半数行命中已有候选。
计时从 prepare 到 store 标记，排除 lookup/store stub 和摘要计算。P95 用 nearest rank。
准则为墙钟中位数至少改善 5%，P95 恶化不得超过 10%，并核对 CPU、峰值分配和业务字节。
CPU 为 process_time_ns，本机时钟约 15.625 ms 分辨率。内存为单次 500 行准备段 tracemalloc 探查。
完整原始样本、批次/状态、各档字节 SHA256、CPU 和内存见 microbench.json，命令见 microbench-command.txt。

| 模型 / 行数 | 墙钟 median A→B ms | 墙钟 P95 A→B ms | CPU median A→B ms | CPU P95 A→B ms | 峰值分配 A→B bytes |
| --- | --- | --- | --- | --- | --- |
| stock_factor_daily / 500 | 48.347 → 42.354 | 58.531 → 44.957 | 46.875 → 46.875 | 62.500 → 46.875 | 2509996 → 2509828 |
| stock_factor_daily / 5000 | 524.380 → 474.348 | 551.572 → 757.245 | 515.625 → 484.375 | 546.875 → 718.750 | 2496052 → 2495940 |
| stock_factor_daily / 50000 | 6054.042 → 5561.242 | 6949.361 → 7164.620 | 5921.875 → 5531.250 | 6843.750 → 6562.500 | 2496052 → 2495940 |
| stock_trade_status_daily / 500 | 32.544 → 27.397 | 35.469 → 30.435 | 31.250 → 31.250 | 46.875 → 31.250 | 1012065 → 1011953 |

每档两轮的有序 staged JSON 摘要一致，所有运行的行数和 fake lookup/store 次数一致。
P95 超限样本保留。该局部计时没有 PG execute、FETCH、提交、Worker 或整链耗时。

<details><summary>原始交错计时（ns，每行 A/B）</summary>

**stock_factor_daily / 500**

| 组 / 顺序 | wall A/B | CPU A/B |
| --- | --- | --- |
| 1 / AB | 47694900 / 42354400 | 62500000 / 31250000 |
| 2 / BA | 51489100 / 41394100 | 46875000 / 31250000 |
| 3 / AB | 49667700 / 41248700 | 62500000 / 31250000 |
| 4 / BA | 46255600 / 40654800 | 46875000 / 31250000 |
| 5 / AB | 58531100 / 44956800 | 62500000 / 46875000 |
| 6 / BA | 46812200 / 43755200 | 46875000 / 46875000 |
| 7 / AB | 48346700 / 43201700 | 46875000 / 46875000 |
| 8 / BA | 51074200 / 43351000 | 46875000 / 46875000 |
| 9 / AB | 48115500 / 42119600 | 46875000 / 46875000 |

**stock_factor_daily / 5000**

| 组 / 顺序 | wall A/B | CPU A/B |
| --- | --- | --- |
| 1 / AB | 517769200 / 604074400 | 500000000 / 562500000 |
| 2 / BA | 501808600 / 507649800 | 500000000 / 515625000 |
| 3 / AB | 530668200 / 474347500 | 515625000 / 484375000 |
| 4 / BA | 541510200 / 489100600 | 546875000 / 484375000 |
| 5 / AB | 533886200 / 433715700 | 531250000 / 437500000 |
| 6 / BA | 524380500 / 440460900 | 515625000 / 453125000 |
| 7 / AB | 491439700 / 438114000 | 468750000 / 421875000 |
| 8 / BA | 551572000 / 439168800 | 546875000 / 437500000 |
| 9 / AB | 505951900 / 757244700 | 500000000 / 718750000 |

**stock_factor_daily / 50000**

| 组 / 顺序 | wall A/B | CPU A/B |
| --- | --- | --- |
| 1 / AB | 6898294800 / 5311540800 | 6593750000 / 5250000000 |
| 2 / BA | 6949360900 / 6057399900 | 6843750000 / 5718750000 |
| 3 / AB | 5835397000 / 5462381400 | 5875000000 / 5312500000 |
| 4 / BA | 6772693900 / 5561242300 | 6703125000 / 5531250000 |
| 5 / AB | 6243705000 / 7164620400 | 6031250000 / 6562500000 |
| 6 / BA | 5456506500 / 5804808100 | 5421875000 / 5781250000 |
| 7 / AB | 5533168000 / 4487013500 | 5546875000 / 4484375000 |
| 8 / BA | 6054042000 / 4357892300 | 5921875000 / 4390625000 |
| 9 / AB | 5764671300 / 5862479300 | 5734375000 / 5531250000 |

**stock_trade_status_daily / 500**

| 组 / 顺序 | wall A/B | CPU A/B |
| --- | --- | --- |
| 1 / AB | 32543600 / 27070100 | 31250000 / 31250000 |
| 2 / BA | 26707700 / 30005800 | 15625000 / 31250000 |
| 3 / AB | 25294400 / 21882300 | 31250000 / 15625000 |
| 4 / BA | 32993000 / 27397400 | 31250000 / 31250000 |
| 5 / AB | 26891200 / 29517500 | 15625000 / 31250000 |
| 6 / BA | 33739900 / 30435000 | 46875000 / 31250000 |
| 7 / AB | 33581400 / 22091200 | 31250000 / 15625000 |
| 8 / BA | 27933500 / 26691800 | 31250000 / 31250000 |
| 9 / AB | 35468700 / 29840300 | 31250000 / 31250000 |

</details>

## W05 撤回与交付

源码从精确基线恢复，旧文件差异为空。实验模块和三个结构断言原样保存在仓库外，
与候选 Diff、原始样本和失败证据一起供复核。实验模块随候选撤回，因此发布范围仅本回执。
不将候选 GREEN 写成撤回后生产代码的通过结果。
恢复后源码 Git Blob SHA256 为 `39d95b00afed3da308aa78a00917fad2308f9d19266cfa30268b145bd35e7e88`。
最终提交及其自动 CI 状态由交付回执补录。独立代码审阅 PENDING。

| AC | 结果 |
| --- | --- |
| 01–04 | 基线、范围、已有批处理及 C1 记录已核对 |
| 05–11 | 离线语义与调用次数相等，代码范围验证通过，实际 PG 计划与全链路 NOT_RUN |
| 12 | 三项真实 RED 和候选 GREEN 已留证 |
| 13 | 新定向/Ruff/diff 通过，旧回归一项 Windows 环境阻断，PG17 NOT_RUN |
| 14 | 预定样本全保留，P95 超限，源码撤回 |
| 15 | 基线 CI 状态已核实，新 SHA CI 和独立审阅待核验 |
| 16 | 原门禁保持 |

下一步建议单独做 FactorService.recalc 月分段 430 天回看重复读取与组装的只读归因。

```text
SOURCE_MUTATION=REVERTED
BUSINESS_EQUALITY=OFFLINE_PASS
PERFORMANCE_DECISION=NO_MEASURABLE_GAIN
PG17_ISOLATED_TEST=NOT_RUN
D04_OWNER=OWNER_DECISION_PENDING
R1=PARTIAL
HISTORICAL_AC05=PARTIAL
REAL_PG17_WORKER_OFF_ON=NO_GO
FORMAL_CAPACITY=NOT_MEASURED
PRODUCTION_READ=NOT_AUTHORIZED
NEXT=CHATGPT_INDEPENDENT_REVIEW
```
