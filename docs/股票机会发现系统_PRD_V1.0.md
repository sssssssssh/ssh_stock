# A股机会发现与趋势研究系统 PRD

**版本**：V1.0  
**日期**：2026-08-25  
**产品定位**：面向个人投研的 A 股日线级“市场理解 + 热点识别 + 趋势发现 + 机会池压缩”系统  
**主数据源**：Tushare Pro  
**核心运行方式**：交易日收盘后运行一次；支持本地电脑手动运行、定时运行和后续迁云  

---

## 1. 产品背景

A 股股票数量超过 5000 只，个人投资者无法在每日收盘后逐一阅读全部 K 线、板块变化和相对强弱。传统行情软件通常提供涨幅榜、板块榜、资金榜和单股技术指标，但用户仍需自行完成：

1. 判断当前市场环境是否适合做趋势；
2. 判断近期真正的热点/主线板块，而非只看单日涨幅；
3. 从全市场发现“左侧下跌/筑底 -> 右侧确认”的股票；
4. 识别已经形成持续趋势的强势股；
5. 把“热点板块”和“强势个股”交叉，形成更小的重点观察池；
6. 记录系统历史判断，用数据验证策略是否有效。

因此，本产品不定位为实时交易终端，也不直接给出“买入/卖出”结论，而定位为：

> **A 股机会发现与趋势研究系统：由机器完成 5000+ -> 10~30 只候选的压缩，由用户完成最终研究和交易决策。**

---

## 2. 产品目标

### 2.1 V1 核心目标

V1 每个交易日收盘后自动回答以下问题：

1. **市场怎么样？** 当前是强势、震荡还是弱势环境？
2. **市场在炒什么？** 当前最热的行业/板块是什么，哪些正在升温、主升、分歧、退潮？
3. **哪些股票刚从左侧转右侧？** 今日哪些股票从筑底状态进入右侧确认状态？
4. **哪些股票已经形成趋势？** 全市场当前最强的趋势股有哪些？
5. **哪些股票同时满足热点 + 趋势共振？**
6. **今天相较昨天发生了什么变化？** 包括市场状态、板块热度排名、股票状态跃迁和新增/退出候选。

### 2.2 V1 成功标准

- 每个交易日可完成全 A 股数据更新和计算；
- 5000+ 股票经过筛选后，最终重点观察池原则上控制在 5~30 只；
- 每只入选股票必须给出结构化“入选原因”，禁止黑盒结果；
- 每个交易日保存因子、状态、信号，能够回看任意历史日期当时系统的判断；
- 能对“右侧确认”信号做 5/10/20/60 个交易日的后验统计；
- 系统规则可配置，不把阈值硬编码到业务代码中；
- 本地部署与未来阿里云部署使用同一套 Docker 化架构。

### 2.3 非目标（V1 不做）

- 不做盘中高频或 Level-2 实时交易；
- 不做自动下单；
- 不做收益承诺或确定性涨跌预测；
- 不以大模型直接预测个股涨跌；
- 不把新闻/研报 NLP 作为 V1 主筛选依据；
- 不在 V1 实现完整短线打板系统，仅预留模块和数据结构。

---

## 3. 用户与核心使用场景

### 3.1 目标用户

首期为单用户本地使用：具备一定技术分析/股票研究能力，希望每天收盘后快速完成市场复盘和趋势机会发现。

### 3.2 核心场景

#### 场景 A：收盘后快速判断市场

用户打开首页，希望在 1 分钟内知道：

- 市场状态：RISK_ON / NEUTRAL / RISK_OFF；
- 市场综合分；
- 上涨家数比例；
- MA20/MA60 以上股票比例；
- 新高/新低数量；
- 成交活跃度；
- 与上一交易日相比是改善还是恶化。

#### 场景 B：发现热点板块

用户希望知道：

- 热度 TOP20 板块；
- 每个板块当前生命周期；
- 1/3/5/20 日收益与相对基准超额；
- 板块内部上涨广度、趋势广度、新高比例；
- 热度变化率 Heat Momentum；
- 哪些板块是“刚启动/快速升温”，而不是已经高潮。

#### 场景 C：发现刚右侧确认的股票

用户希望系统自动找到：

- 昨日处于 S1/S2、今日首次进入 S3 的股票；
- RightSide Score；
- 触发原因，如“20 日平台突破、MA20 拐头、RPS 加速、量能确认”；
- 所属板块及板块热度；
- 排除 ST、长期停牌、新股、低流动性标的。

#### 场景 D：查看当前趋势强股

用户希望看到：

- Trend Score TOP N；
- RPS20 / RPS60 / RPS120；
- 趋势状态 S4/S5；
- 所属板块和热点共振程度；
- 最大回撤、趋势效率、均线结构等解释性指标。

#### 场景 E：每日变化复盘

系统自动展示：

- 新进入 S3 的股票；
- S3 -> S4、S4 -> S5 的股票；
- S4/S5 -> S6 的趋势衰退股票；
- 新进入板块热度 TOP10 的行业；
- 板块状态由“观察 -> 启动”“升温 -> 主升”“主升 -> 分歧”等变化。

---

## 4. 产品总体信息架构

```mermaid
flowchart TD
    A[市场总览] --> B[热点板块]
    A --> C[右侧启动]
    A --> D[趋势强股]
    A --> E[每日复盘]
    C --> F[个股详情]
    D --> F
    B --> G[板块详情]
    H[短线体系-预留] --> H1[情绪周期]
    H --> H2[涨停/连板]
    H --> H3[题材梯队]
```

V1 页面：

1. 市场总览 Dashboard
2. 热点板块
3. 右侧启动
4. 趋势强股
5. 个股详情
6. 每日复盘
7. 系统运行/数据状态

P2 预留：短线情绪、涨停梯队、题材龙头、AI 复盘。

---

## 5. 全局股票池规则

系统所有趋势计算先建立 Eligible Universe，可配置：

### 5.1 默认排除

- 已退市股票；
- 当日停牌且无行情数据；
- 名称包含 `ST` 或 `*ST`；
- 上市交易日不足 120 个交易日；
- 最近 20 日平均成交额低于 5000 万元（配置项）；
- 可选：收盘价低于 2 元；
- 数据缺失超过允许阈值的股票。

### 5.2 配置要求

所有过滤阈值写入 `config/strategy.yaml`，前端后续可配置，V1 不要求做配置页面。

---

## 6. 市场环境模块（Market Regime）

### 6.1 页面输出

首页展示：

- Market Score：0~100；
- Market Regime：RISK_ON / NEUTRAL / RISK_OFF；
- 市场状态相较昨日变化；
- 主要指数 1/5/20 日表现；
- Breadth20：收盘价高于 MA20 的股票比例；
- Breadth60：收盘价高于 MA60 的股票比例；
- NewHigh20 / NewLow20 数量；
- 上涨家数、下跌家数、涨跌比；
- 全市场成交额及 Amount20 Ratio；
- 可选短线指标：涨停/跌停数量。

### 6.2 Market Score V1

各子分数先统一映射到 0~100，再加权：

| 因子 | 权重 | 说明 |
|---|---:|---|
| Index Trend Score | 25% | 沪深300、中证1000、上证指数趋势综合 |
| Breadth Score | 30% | MA20/MA60 以上股票比例 |
| Advance/Decline Score | 15% | 上涨股票比例、涨跌比 |
| New High/Low Score | 15% | 20/60 日新高新低结构 |
| Liquidity Score | 15% | 全市场成交额相对 20 日均值 |

`MarketScore = 0.25*IndexTrend + 0.30*Breadth + 0.15*AD + 0.15*NewHighLow + 0.15*Liquidity`

默认状态：

- `RISK_ON`: MarketScore >= 70
- `NEUTRAL`: 45 <= MarketScore < 70
- `RISK_OFF`: MarketScore < 45

阈值全部可配置，后续以回测优化。

---

## 7. 热点板块模块（Sector Heat）

### 7.1 V1 板块口径

**主口径：申万行业一级/二级。**

原因：分类稳定、成分可追溯、易于历史回测。概念板块作为增强层，不作为 V1 成功运行的硬依赖。

### 7.2 板块核心因子

对每个交易日、每个行业计算：

- Return1 / Return3 / Return5 / Return20；
- ExcessReturn5 = SectorReturn5 - BenchmarkReturn5；
- ExcessReturn20；
- Breadth20 = 成分股 close_adj > MA20 的比例；
- Breadth60；
- UpRate = 当日上涨成分股比例；
- NewHigh20Rate = 20 日新高股票比例；
- RPS60Median = 成分股 RPS60 中位数；
- RPS60Top20Rate = RPS60 >= 80 的成分股比例；
- AmountRatio20 = 板块当日成交额 / 板块 20 日平均成交额；
- LimitUpDensity（可选）= 涨停股数 / 有效成分股数；
- MoneyFlowScore（可选）= 板块资金流截面分位数。

### 7.3 Sector Heat Score V1

核心指标在**当日板块截面内做 percentile rank**，统一为 0~100，避免固定涨幅阈值在不同市场环境下失真。

默认权重：

| 因子 | 权重 |
|---|---:|
| 5日超额收益分位 | 20% |
| 20日超额收益分位 | 15% |
| Breadth20 分位 | 15% |
| Breadth60 分位 | 10% |
| NewHigh20Rate 分位 | 10% |
| RPS60Median 分位 | 10% |
| AmountRatio20 分位 | 10% |
| 当日上涨率分位 | 5% |
| 资金/涨停增强因子 | 5% |

如果可选数据不可用，剩余权重按比例归一化。

### 7.4 Heat Momentum

- `HeatMomentum1 = Heat_t - Heat_t-1`
- `HeatMomentum3 = Heat_t - Heat_t-3`
- `RankChange = Rank_t-1 - Rank_t`，正值表示排名提升。

产品重点展示 `Heat` 和 `HeatMomentum3`，因为“正在升温”往往比“绝对热度最高”更值得观察。

### 7.5 板块生命周期 V1

生命周期判断按优先级执行：

1. **高潮 CLIMAX**：Heat >= 90 且 Breadth20 >= 80% 且 5 日收益分位 >= 90；
2. **分歧 DIVERGENCE**：Heat >= 70 且 HeatMomentum3 <= -8；
3. **主升 MAIN_UP**：Heat >= 75 且 HeatMomentum3 >= 0；
4. **升温 HEATING**：Heat >= 60 且 HeatMomentum3 > 5；
5. **启动 STARTING**：上一交易日 Heat < 55，今日 Heat >= 55 且 HeatMomentum3 >= 10；
6. **观察 WATCH**：40 <= Heat < 60；
7. **退潮 COOLING**：Heat < 60 且 HeatMomentum3 < 0；
8. **冷却 COLD**：Heat < 40。

阈值必须配置化。

---

## 8. 个股因子体系

### 8.1 价格统一口径

原始 OHLCV 永久保存。趋势计算使用复权价格：

- `adj_close = close * adj_factor`
- `adj_open = open * adj_factor`
- `adj_high = high * adj_factor`
- `adj_low = low * adj_factor`

采用乘复权因子的稳定序列用于趋势计算；因子以比例/排名为主，不依赖价格绝对值。

### 8.2 基础技术因子

每个股票每日计算：

- MA5 / MA10 / MA20 / MA60 / MA120 / MA250；
- Return5 / Return20 / Return60 / Return120 / Return250；
- MA20Slope5 = `(MA20_t / MA20_t-5 - 1) / 5`；
- MA60Slope10；
- ATR14、ATR20、ATR20Pct = ATR20 / adj_close；
- AmountMA20；
- AmountRatio20 = amount / AmountMA20；
- High20 / High60 / High120；
- Low20 / Low60；
- DrawdownFromHigh60 / 120；
- MaxDrawdown60；
- TrendEfficiency20 = `abs(close_t/close_t-20 - 1) / sum(abs(daily_return), 20)`；
- HigherLowScore；
- Breakout20 / Breakout60；
- DistanceToMA20 / 60 / 120；
- DistanceToHigh60 / 120。

### 8.3 RPS 相对强度

对 Eligible Universe 计算：

- `RPS20 = percentile_rank(Return20) * 100`
- `RPS60 = percentile_rank(Return60) * 100`
- `RPS120 = percentile_rank(Return120) * 100`
- `RPS250 = percentile_rank(Return250) * 100`

同时计算：

- RPS20Delta5 = RPS20_t - RPS20_t-5；
- RPS60Delta5；
- RelativeReturn20 = StockReturn20 - BenchmarkReturn20；
- RelativeReturn60。

### 8.4 突破定义

为避免把当天最高价本身包含进滚动高点：

- `PrevHigh20 = max(adj_high[t-20:t-1])`
- `Breakout20 = adj_close_t > PrevHigh20`
- `PrevHigh60 = max(adj_high[t-60:t-1])`
- `Breakout60 = adj_close_t > PrevHigh60`

可增加近突破：`adj_close / PrevHigh20 >= 0.98`。

### 8.5 Higher Low

V1：

`HigherLow = min(adj_low[t-19:t]) > min(adj_low[t-59:t-20])`

并保存两段低点的涨幅百分比。

---

## 9. RightSide Score（右侧启动评分）

目标：寻找“过去弱/筑底，当前开始被市场确认”的股票，而不是单纯寻找已经涨很多的股票。

默认权重：

| 子因子 | 权重 | 规则示例 |
|---|---:|---|
| Breakout Score | 20% | 20/60 日平台突破或接近突破 |
| MA20 Turn Score | 15% | MA20 由下行 -> 走平 -> 上行 |
| MA Recovery Score | 15% | 重新站上 MA20/MA60 |
| RPS Acceleration | 20% | RPS20、RPS60 快速提升 |
| Volume Confirmation | 10% | AmountRatio20 >= 1.2 等 |
| Higher Low | 10% | 中短期低点抬升 |
| Volatility Structure | 10% | 筑底期波动收敛、突破时波动扩张 |

输出 0~100。

默认 S3 候选要求：

- RightSideScore >= 70；
- adj_close > MA20；
- MA20Slope5 > 0；
- `Breakout20 = true` **或** 当日由下向上穿越 MA60；
- RPS20 >= 70；
- 不触发全局股票池排除条件。

---

## 10. Trend Score（趋势强度评分）

Trend Score 只衡量个股自身趋势质量，**不掺入板块热度**，避免后续综合评分重复计权。

默认权重：

| 子因子 | 权重 |
|---|---:|
| RPS20 | 15% |
| RPS60 | 25% |
| RPS120 | 15% |
| 均线结构 MA Structure | 15% |
| MA20/MA60 斜率 | 10% |
| Trend Efficiency | 10% |
| Drawdown Quality | 10% |

其中 MA Structure 可按以下方式打分：

- close > MA20：25 分；
- MA20 > MA60：25 分；
- MA60 > MA120：25 分；
- MA20/MA60 均向上：25 分。

最终映射 0~100。

---

## 11. 股票趋势状态机

### 11.1 状态定义

| 状态 | 名称 | 产品含义 |
|---|---|---|
| S0 | DOWN | 明确下跌趋势 |
| S1 | DECELERATING | 下跌减速/弱势修复 |
| S2 | BASE | 筑底/震荡，趋势未确认 |
| S3 | RIGHT_CONFIRMED | 右侧首次确认 |
| S4 | TREND | 趋势形成 |
| S5 | MAIN_UP | 强趋势/主升 |
| S6 | DECAY | 趋势衰退 |

### 11.2 V1 判定建议

#### S0 DOWN
满足多数条件：

- close < MA60；
- MA20 < MA60；
- MA20Slope5 < 0；
- RPS60 < 50。

#### S1 DECELERATING

- 仍未形成上升趋势；
- MA20Slope5 相较 5 日前明显改善；或 close 重回 MA20；
- 最近 20 日不再持续创新低；
- RPS20Delta5 > 0。

#### S2 BASE

- 不满足 S0；
- MA20 走平或轻微向上；
- close 与 MA60 距离在可配置区间（默认 ±10%）；
- 20 日价格区间收敛，或 HigherLow 为真；
- 未达到 S3 条件。

#### S3 RIGHT_CONFIRMED

- RightSideScore >= 70；
- close > MA20；
- MA20Slope5 > 0；
- Breakout20 或 CrossAboveMA60；
- RPS20 >= 70；
- S3 作为“刚确认状态”，默认最长保留 5 个交易日，随后进入 S4/S2/S6。

#### S4 TREND

- close > MA20 > MA60；
- MA20Slope5 > 0；
- MA60Slope10 >= 0；
- RPS60 >= 70；
- TrendScore >= 70。

#### S5 MAIN_UP

- TrendScore >= 85；
- RPS60 >= 90；
- RPS120 >= 80；
- close > MA20 > MA60 > MA120；
- 60 日最大回撤不超过可配置阈值。

#### S6 DECAY

从 S3/S4/S5 进入，满足任一强衰退或多个弱衰退：

- 连续 2 日 close < MA20；
- MA20Slope5 < 0；
- RPS20 < 50；
- TrendScore 较 5 日前下降 >= 20；
- 跌破关键 20/60 日结构位。

### 11.3 状态优先级

每日分类优先级：`S5 -> S4 -> S3 -> S6 -> S0 -> S1 -> S2`，同时结合 `previous_state` 约束非法跳转。

禁止无解释地从 S0 直接跳到 S5；即使因极端涨停导致条件满足，也先记为 S3，并记录 `fast_transition=true`。

---

## 12. 综合机会评分 Opportunity Score

最终候选池需要把个股与板块、市场结合：

`OpportunityScore = 0.45*StockScore + 0.35*SectorHeat + 0.10*SectorHeatMomentumScore + 0.10*MarketScore`

其中：

- 对 S3 股票，`StockScore = RightSideScore`；
- 对 S4/S5 股票，`StockScore = TrendScore`。

页面必须同时显示原始分项，禁止只显示综合分。

---

## 13. 页面需求

### 13.1 市场总览

模块：

1. 日期、最后更新时间、数据完整状态；
2. Market Regime 卡片；
3. 市场宽度；
4. 主要指数；
5. 热点板块 TOP10；
6. 今日新 S3 股票 TOP10；
7. 趋势强股 TOP10；
8. 今日关键变化。

验收：用户不进入二级页，也能在首页理解当天市场主线和系统发现的核心机会。

### 13.2 热点板块

列表列：

- 行业名称；
- Heat；
- HeatMomentum1/3；
- Rank / RankChange；
- Lifecycle；
- Return1/5/20；
- Breadth20/60；
- NewHigh20Rate；
- RPS60Median；
- AmountRatio20。

支持按 Heat、HeatMomentum3、RankChange 排序。

### 13.3 右侧启动

默认只显示今日 `state=S3` 且 `is_new_state=true`。

字段：

- 股票代码/名称；
- RightSideScore；
- OpportunityScore；
- 昨日状态 -> 今日状态；
- RPS20/60；
- Breakout20/60；
- AmountRatio20；
- 所属行业；
- SectorHeat；
- 入选原因标签。

### 13.4 趋势强股

默认显示 S4/S5，按 TrendScore 降序：

- TrendScore；
- RPS20/60/120；
- 状态；
- 状态持续天数；
- 20/60 日收益；
- 60 日最大回撤；
- TrendEfficiency；
- SectorHeat；
- OpportunityScore。

### 13.5 个股详情

顶部：状态、RightSideScore、TrendScore、OpportunityScore、RPS、所属板块、SectorHeat。

图表：

- 日 K + MA20/60/120；
- S0~S6 状态带；
- S3 信号标记；
- RPS20/60/120 曲线；
- RightSideScore / TrendScore 曲线；
- 成交额及 AmountRatio20。

历史表：最近 60 个交易日状态变化。

### 13.6 每日复盘

自动生成结构化内容：

- 市场状态变化；
- 板块 Top10 和新进入 Top10；
- 今日新 S3；
- S3 -> S4；
- S4 -> S5；
- 进入 S6；
- 退出重点观察池；
- 昨日候选今日表现。

V1 可先模板化文本，P2 再接 LLM 生成自然语言总结。

### 13.7 系统运行状态

展示：

- 最近交易日；
- 数据库最新 trade_date；
- 每张事实表最新日期；
- 当日股票行情条数；
- 因子计算条数；
- 状态计算条数；
- 任务执行状态、耗时、错误信息；
- 手动执行“补数据/重算因子/重算状态”。

---

## 14. 每日运行流程

```mermaid
flowchart TD
    A[启动 daily job] --> B{是否交易日/是否需要补历史}
    B -->|否| Z[结束]
    B -->|是| C[拉 trade_cal/stock_basic必要更新]
    C --> D[拉当日 daily]
    D --> E[拉 adj_factor]
    E --> F[拉 daily_basic]
    F --> G[拉指数/行业相关数据]
    G --> H[数据完整性校验]
    H --> I[计算复权价格与基础因子]
    I --> J[计算全市场RPS]
    J --> K[计算 Market Score]
    K --> L[计算 Sector Heat]
    L --> M[计算 RightSide/Trend Score]
    M --> N[计算 S0-S6]
    N --> O[生成 strategy_signal]
    O --> P[生成每日复盘快照]
    P --> Q[任务成功]
```

要求：

- 所有任务幂等；
- 同日期重复运行不得产生重复主键；
- 支持指定 `trade_date` 重跑；
- 支持从数据库最后日期自动补缺；
- 某可选数据源失败不能阻断核心链路；
- 核心行情缺失则禁止生成当天最终信号。

---

## 15. 历史回填与回测

### 15.1 初始化

默认首次回填最近 5 年交易日；支持配置 10 年。

顺序：

1. 股票基础信息；
2. 交易日历；
3. 日线；
4. 复权因子；
5. daily_basic；
6. 指数；
7. 行业分类及成分；
8. 因子批量计算；
9. 状态机从最早日期顺序重放。

### 15.2 信号后验统计

对每个 S3 信号保存未来收益评估（注意不能反写到当日可见特征中）：

- ForwardReturn5；
- ForwardReturn10；
- ForwardReturn20；
- ForwardReturn60；
- MFE20（20 日最大有利涨幅）；
- MAE20（20 日最大不利跌幅）。

V1 验证指标：

- S3 信号数量；
- 5/10/20/60 日平均、中位收益；
- 正收益比例；
- 分板块热度区间统计；
- 分 Market Regime 统计；
- 按 RightSideScore 分组统计。

---

## 16. 数据源需求

### 16.1 P0 必需接口

| 数据 | Tushare API | 用途 |
|---|---|---|
| 交易日历 | `trade_cal` | 判断交易日、补数 |
| 股票基础 | `stock_basic` | 股票池、上市日期、状态 |
| A股日线 | `daily` | OHLCV 核心行情 |
| 复权因子 | `adj_factor` | 复权趋势计算 |
| 每日指标 | `daily_basic` | 换手、市值、估值、量比等 |
| 指数日线 | `index_daily` | 市场环境/基准 |
| 申万行业分类 | `index_classify` | 板块维度 |
| 申万行业成分 | `index_member_all` | 股票-行业映射 |

### 16.2 P1 增强接口

| 数据 | API | 用途 |
|---|---|---|
| 同花顺板块行情 | `ths_daily` | 概念/行业板块增强 |
| THS行业资金 | `moneyflow_ind_ths` | Sector Heat 增强 |
| DC板块资金 | `moneyflow_ind_dc` | Sector Heat 增强 |
| THS个股资金 | `moneyflow_ths` | 个股增强因子 |

### 16.3 P2 短线预留

| 数据 | API | 用途 |
|---|---|---|
| 涨跌停池 | `limit_list_ths` | 涨停、连板、炸板、跌停 |
| 最强概念 | `limit_cpt_list` | 短线题材/板块热度参考 |

**要求**：P1/P2 无权限时，系统仍应正常完成 V1 核心计算。

---

## 17. 数据质量要求

每个交易日核心链路至少校验：

- `daily` 行数与正常交易股票数量合理；
- `daily` 主键无重复；
- OHLC 合法：high >= max(open, close)，low <= min(open, close)；
- vol/amount 非负；
- adj_factor 缺失率低于配置阈值；
- 基准指数当天有数据；
- 行业覆盖率达到配置阈值；
- 当日数据未通过完整性校验时，任务标记 `PARTIAL/FAILED`，不生成最终信号。

---

## 18. 非功能需求

### 18.1 性能

本地 4 核 8G 参考目标：

- 日常单日增量：原则上 5 分钟内完成；
- 5000+ 股票日因子扫描：原则上 2 分钟内；
- 首页 API P95 < 500ms（结果已预计算）；
- 个股 3 年日线详情 P95 < 1s。

这些是工程目标，不作为首轮阻塞条件。

### 18.2 可维护性

- 数据源 Provider 抽象，不能把 Tushare SDK 调用散落在策略代码；
- 因子、状态、评分参数配置化；
- 数据迁移用 Alembic；
- 每个核心因子有单元测试；
- 每日任务有运行日志和 `job_run` 记录；
- 所有日期统一使用交易日 `YYYY-MM-DD`，调 Tushare 时转换为 `YYYYMMDD`。

### 18.3 安全

- TUSHARE_TOKEN 只能放环境变量，不进入 Git；
- 数据库密码使用 `.env`；
- 本地默认仅监听 `127.0.0.1`；
- 未来上云再增加认证、HTTPS 和访问控制。

---

## 19. V1 验收标准

### 19.1 数据链路

- 可执行一次历史初始化并入库至少 5 年日线；
- 任意停机数日后重新运行，能自动补齐缺失交易日；
- 重跑同一天不重复写数据；
- 核心表可查询最新日期和行数。

### 19.2 计算链路

- 每个有效股票每日存在基础因子记录；
- RPS20/60/120 在截面上可解释；
- 每只股票每日有 S0~S6 之一；
- S3 信号有解释原因；
- 每个行业每日有 Heat 和 Lifecycle；
- 每日有 Market Score / Regime。

### 19.3 产品链路

- 首页可看到市场、热点、右侧、趋势四块核心内容；
- 支持查看历史日期；
- 点击股票可查看 K 线、状态、评分和信号；
- 每日复盘能够展示“今日新增/状态变化”。

---

## 20. 版本规划

### V1.0 - 趋势发现主链路

- 数据仓库；
- Market Regime；
- Sector Heat；
- RPS；
- RightSide Score；
- Trend Score；
- S0~S6；
- Dashboard；
- 历史后验统计。

### V1.1 - 策略研究增强

- 参数回测；
- 分行业/市值/市场环境统计；
- 策略版本管理；
- watchlist；
- 候选股备注。

### V2.0 - 短线体系

- 情绪周期；
- 涨停/连板/炸板；
- 热点题材；
- 龙头/中军/趋势核心分类；
- 短线候选池。

### V2.1 - AI 复盘

- 结构化数据 -> LLM；
- 自动每日市场复盘；
- 个股入选原因自然语言解释；
- 不允许 LLM 直接修改因子结果。

---

## 21. 默认假设与待用户后续确认项

这些不阻塞 Codex 开发，全部已有默认值：

1. 数据库默认 PostgreSQL 16；
2. 后端/量化统一 Python 3.12 + FastAPI；
3. 前端 Vue 3 + TypeScript + Vite + ECharts；
4. 本地优先，Docker Compose 部署；
5. 调度时区 `Asia/Shanghai`；
6. 日常自动任务默认 18:10 执行，同时支持手动运行；
7. 首次历史回填默认 5 年；
8. 基准指数默认沪深300，市场环境同时参考上证指数和中证1000；
9. 行业主口径默认申万一级，页面支持切换二级；
10. P1/P2 高积分 Tushare 接口全部按“有权限则启用”设计。

---

## 22. 参考资料

- Tushare A股日线 `daily`：https://tushare.pro/document/1?doc_id=27
- Tushare 股票基础 `stock_basic`：https://tushare.pro/document/1?doc_id=25
- Tushare 交易日历 `trade_cal`：https://tushare.pro/document/2?doc_id=26
- Tushare 复权因子 `adj_factor`：https://tushare.pro/document/2?doc_id=28
- Tushare 每日指标 `daily_basic`：https://tushare.pro/document/2?doc_id=32
- Tushare 申万行业成分 `index_member_all`：https://tushare.pro/document/2?doc_id=335
- Tushare THS板块行情 `ths_daily`：https://tushare.pro/document/2?doc_id=260
- Tushare THS行业资金 `moneyflow_ind_ths`：https://tushare.pro/document/2?doc_id=343
- Tushare DC板块资金 `moneyflow_ind_dc`：https://tushare.pro/document/2?doc_id=344
- Tushare THS个股资金 `moneyflow_ths`：https://tushare.pro/document/2?doc_id=348
- Tushare 涨跌停榜 `limit_list_ths`：https://tushare.pro/document/2?doc_id=355
- Tushare 最强板块 `limit_cpt_list`：https://tushare.pro/document/2?doc_id=357
- Sequoia-X：https://github.com/sngyai/Sequoia-X

---

## 23. 实现进度（2026-08-26）

### 23.1 当前已落地范围

当前已完成 Milestone 0、Milestone 1、Milestone 2、Milestone 3 和 Milestone 4，不提前实现页面、完整 REST API 和后验统计。

- 已创建后端工程骨架：Python 3.12、FastAPI、SQLAlchemy 2.x、Alembic、pytest。
- 已创建 Docker Compose：PostgreSQL 16、backend、worker。
- 已补充 `requirements.txt` 和 `requirements-dev.txt`，支持传统 pip 方式安装依赖。
- 已实现配置系统：`.env` + `config/app.yaml` + `config/strategy.yaml`。
- 已实现 `MarketDataProvider` 抽象与 `TushareProvider`。
- 已实现 `stock_basic`、`trade_calendar`、`stock_daily`、`stock_adj_factor`、`stock_daily_basic`、`index_daily` 原始数据表。
- 已实现 `job_run` 和 `provider_api_log` 运行日志表。
- 已实现 daily / backfill / scheduler CLI。
- 已补充 `check-config` 和 `check-tushare`，用于脱敏检查配置与 Tushare token 可用性。
- 已按代理版 Tushare 要求调整 SDK 初始化方式：`ts.set_token(...)`、无参数 `ts.pro_api()`、设置 `_DataApi__http_url` 为 `TUSHARE_HTTP_URL`。
- 已实现 `stock_factor_daily` 因子表和 Alembic 迁移 `0002_stock_factor_daily`。
- 已实现 Factor Engine：复权 OHLC、MA、收益率、斜率、ATR、突破、higher-low、回撤、趋势效率、Eligible Universe、RPS，并补充 `return1` / `return3` 支撑行业短周期收益。
- 已实现 `recalc-factors` CLI，并接入 daily / backfill 任务链路。
- 已实现 `market_daily` 市场温度表和 Alembic 迁移 `0003_market_sector`。
- 已实现 Market Score V1：指数趋势、市场宽度、涨跌家数、新高新低、成交额活跃度，并输出 Regime。
- 已实现 `sector`、`sector_member`、`sector_factor_daily` 行业表和申万行业元数据/成分同步。
- 已实现 Sector Heat V1：行业收益、超额收益、宽度、RPS、成交活跃度、Heat Momentum、Heat Rank、Lifecycle。
- 已实现 `recalc-market` / `recalc-sectors` CLI，并接入 daily / backfill 任务链路。
- 已修复 PostgreSQL 单条 SQL 参数上限问题，`upsert_rows` 会按参数数量自动分批写入，避免 `number of parameters must be between 0 and 65535`。
- 已兼容代理接口的申万行业口径：行业分类使用 `SW2021`，行业成员使用 `SW` 返回的 `l1_code` 映射到一级行业。
- 已实现 `stock_state_daily` 状态表和 `strategy_signal` 信号表，新增 Alembic 迁移 `0005_trend_state_signal`。
- 已实现 RightSideScore V1、TrendScore V1、S0-S6 状态机、OpportunityScore。
- 已实现 RIGHT_SIDE_NEW、TREND_ENTER、MAIN_UP_ENTER、TREND_DECAY、LEADER_BREAKOUT 信号生成。
- 已实现 `recalc-states` CLI，并接入 daily / backfill 任务链路。
- 已实现原始日线数据的基础质量检查。
- 已实现 pytest 单元测试与 API health 导入测试。

### 23.2 验证结果

- `python -m pytest`：25 passed，1 个 FastAPI/Starlette TestClient 第三方弃用警告。
- `python -m ruff check .`：All checks passed。
- `python -m alembic heads`：当前单头为 `0005_trend_state_signal`，迁移链可被 Alembic 正常加载。
- `python -m app.cli --help`：CLI 入口可正常显示 daily、backfill、recalc-factors、recalc-market、recalc-sectors、recalc-states、evaluate-signals、scheduler。
- `python -m app.cli check-tushare`：代理连接验证成功，返回 `tushare_ok=true rows=10`。
- `python -m app.cli daily --trade-date 2026-08-26`：执行成功，写入 `stock_daily` 5547 行、`stock_daily_basic` 5547 行、`index_daily` 3 行、`stock_factor_daily` 5547 行、`market_daily` 1 行；当前仅单日数据，Eligible Universe 为 0，所以 `sector_factor_daily` 暂为 0 行。
- `python -m app.cli recalc-states --start 2026-08-26 --end 2026-08-26`：执行成功，写入 `stock_state_daily` 5547 行，`strategy_signal` 0 行；当前仅单日数据，全部股票为基础 S0 状态。

### 23.3 已在后续补齐

- Milestone 5：完整 REST API。
- Milestone 6：Vue 前端。
- Milestone 7：后验统计和研究接口。

### 23.4 换电脑继续开发要求

新电脑继续开发前，先阅读 `README.md` 和 `PROJECT_RULES.md`。后续 Codex 开发必须保持以下约束：

- 先完成当前 Milestone 的验收标准，再进入下一 Milestone。
- 不把策略阈值硬编码进业务代码。
- 服务层不得直接 import `tushare`。
- token 和密码只来自 `.env` 或环境变量，不写入代码和日志。
- 每次功能推进后同步更新 README、PROJECT_RULES、本 PRD Markdown 和对应 DOCX。

---

## 24. 实现进度（2026-08-27，Milestone 5-7）

### 24.1 当前已落地范围

当前已完成 Milestone 5、Milestone 6 和 Milestone 7，项目从后端计算链路推进到可查询、可展示、可做后验研究的完整 V1 闭环。

- 已新增 Dashboard API：`GET /api/v1/dashboard/summary`，返回市场温度、状态分布、信号分布、行业热度 Top、右侧新增和趋势领先股票。
- 已新增数据覆盖率 API：`GET /api/v1/system/data-coverage`，返回每个已拉取交易日在核心数据表里的行数。
- 已新增行业 API：`GET /api/v1/sectors/heat`、`GET /api/v1/sectors/{sector_id}`、`GET /api/v1/sectors/{sector_id}/history`。
- 已新增股票 API：`GET /api/v1/stocks/right-side`、`GET /api/v1/stocks/trends`、`GET /api/v1/stocks/decay`、`GET /api/v1/stocks/{ts_code}/overview`、`GET /api/v1/stocks/{ts_code}/history`、`GET /api/v1/stocks/{ts_code}/factors`。
- 已增强任务 API：`GET /api/v1/jobs` 支持 `status`、`job_type`、`limit`、`offset`。
- 已新增任务触发 API：`POST /api/v1/jobs/daily` 和 `POST /api/v1/jobs/backfill`，用于从页面发起单日同步或历史回填。
- 已新增后验评估表 `signal_forward_eval` 和 Alembic 迁移 `0006_signal_forward_eval`。
- 已实现 `evaluate-signals` CLI，计算信号后 5/10/20/60 个交易日收益、MFE20、MAE20。
- 已新增研究接口：`GET /api/v1/research/signals/stats` 和 `GET /api/v1/research/signals/buckets`。
- 已新增 Vue 3 + TypeScript + Vite + ECharts 前端，目录为 `frontend/`。
- 前端已接入系统状态、Dashboard 摘要、右侧池、趋势池、衰退池、行业热度和后验统计。
- 前端浏览器标题和首页显示名称已统一为“空间”。
- 前端已改为左侧目录的页面切换结构，一级目录为“总览 / 数据 / 长线 / 短线”。
- 数据页面主要面板支持点击标题收起/展开，收起后只保留标题行和右侧操作区。
- 长线股票池和短线风险池支持点击股票代码查看实时 K 线，默认展示最近 180 个自然日，并支持 90 / 180 / 365 日切换；K 线数据实时来自 Tushare，不写入本地数据库。
- 已修复 Vite 开发服务返回旧样式导致目录按钮裸露的问题，并将前端视觉调整为固定侧边目录的工作台布局。
- “数据”页面已新增“补算因子与股票池”入口，调用 `POST /api/v1/jobs/recalculate` 后台补算因子、市场、行业、状态和信号后验。
- 已新增数据覆盖日历接口 `GET /api/v1/system/data-calendar` 和前端月份日历视图，直观看到休市、未拉取、已拉未算、基础已算、行业完成等状态。
- 前端“数据”页面已新增“数据覆盖”面板，用于查看已经拉取了哪些交易日。
- 前端“数据覆盖”明细表已改为分页展示，默认每页 20 条，可切换 10 / 20 / 50 / 100 条，避免页面无限下拉。
- 数据覆盖明细默认加载数据库中全部已拉取交易日，不再固定限制为最近 120 条。
- “数据覆盖”面板已新增日期范围输入和“拉取数据”按钮，点击后创建后台 `backfill` 任务，无需手动进入终端执行 CLI。
- “数据覆盖”面板已新增任务状态展示，轮询 `GET /api/v1/jobs` 显示当前任务、最近任务、进度条、当前步骤、当前交易日、已处理交易日数量和已写入行数。
- 补算因子任务已按自然月分块执行，任务状态会显示当前分块范围、累计写入行数和进度百分比，避免大区间补算时页面长时间停留在同一个步骤。
- 因子补算的已写入/处理行数在当前分块完成写库后更新；分块计算期间页面会提示“当前因子分块完成后更新行数”。
- 前端任务列表已展示 `error_message`，失败时可直接看到 Tushare 代理、数据库或计算阶段的真实错误。
- `TushareProvider` 已对 `requests` 网络异常做 3 次自动重试，降低代理 HTTPS 瞬断导致的任务失败概率。
- `TushareProvider` 已新增请求节流，默认每次 Tushare 请求之间等待 `TUSHARE_MIN_INTERVAL_SECONDS=1.5` 秒；代理不稳定时可在 `.env` 调大到 `2` 或 `3`。
- 前端开发代理默认指向 `http://127.0.0.1:9034`，可通过 `frontend/.env` 改为 8000 或其他后端端口。

### 24.2 验证结果

- `python -m alembic upgrade head`：已在当前 PostgreSQL 执行成功，迁移到 `0006_signal_forward_eval`。
- `python -m pytest`：28 passed，1 个 FastAPI/Starlette TestClient 第三方弃用警告。
- `python -m ruff check backend tests migrations`：All checks passed。
- `python -m app.cli evaluate-signals --signal-type RIGHT_SIDE_NEW --algo-version v1.0`：执行成功；当前 `strategy_signal` 为 0 行，所以 `signal_forward_eval` 写入 0 行。
- API smoke test：`/api/v1/system/status`、`/api/v1/dashboard/summary`、`/api/v1/sectors/heat`、`/api/v1/stocks/right-side`、`/api/v1/stocks/trends`、`/api/v1/research/signals/stats` 均返回 HTTP 200。
- `npm run build`：前端生产构建成功。

### 24.3 当前数据状态说明

当前数据库仅同步了 `2026-08-26` 单日行情，因此 Eligible Universe 为 0，行业热度和策略信号暂时为空。完成足够历史回填后，重新运行 `recalc-factors`、`recalc-market`、`recalc-sectors`、`recalc-states` 和 `evaluate-signals`，前端股票池、行业热度和后验统计会随数据自动填充。

### 24.4 后续增强入口

- 补充历史回填后的真实样本验证，检查阈值是否需要调参。
- 增加信号后验导出、按市场环境/行业生命周期分层统计。
- 增加前端个股详情页和行业详情页的交互入口。
- 增加生产部署、权限控制和可观测性面板。
