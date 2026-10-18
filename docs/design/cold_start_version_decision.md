# 冷启动 V1.2 版本决定

## W01 冻结与范围

基线 `f3158dd5317f1da2ba950522b300f66b70d9f901`，master 与远端一致；该提交
CI 39139452440 SUCCESS。依赖锁定 Pandas 3.0.5 / NumPy 2.3.3；迁移单头
0058_data_publication。此次不修改旧迁移、配置阈值、公式、金融账本或历史 Hash。

复现实验 `scripts/cold_start_comparison.py` 直接加载上述 Git 源码与当前源码，使用相同合成输入，
不连接数据库/Provider。完整三股 270 日因子及左侧/右侧/趋势三类机会冻结比较全部输出字段，
浮点 rtol=atol=1e-12。JSON 包含实际行和失败类型，不用截图或手填数字证明相同。

已确认部分左连接后的 object bool 对 `~` 得到负整数，存在状态的股票也被误排除；
`is_active` 空值会误判或异常；None/NA 机会比较、可空布尔和 object NA rolling 也可异常。
具体红灯以专项 JUnit 为准；bool/nullable boolean 并不都复现负整数，不夸大触发范围。

## W05 发布前决定

虽然修复恢复原有布尔/空值定义，部分历史结果的 eligibility、RPS 横截面、市场/行业/题材、
状态/信号和机会可能变化。因此采用显式新计算身份，不让旧结果冒充修复版：
Factor、Market、Sector、Theme、Trend、Signal、Opportunity 的 CALC_VERSION 统一从 v1 到 v2。
TradeStatus 自身计算未变，仍为 trade_status_v1。公式 algo_version、strategy/opportunity
config_hash 的算法和配置值不变，不能给旧行补造新版本。金融/Research 版本不因此重编号。

所有 Service/当前查询/质量/发布/队列和调度必须继续引用集中版本常量。
新旧队列身份不同，旧排队请求按既有身份漂移规则拒绝，不能偷偷续跑；新 Scheduler 计划键不同。
现有冻结 Backtest/PAPER/研究 Artifact 内容保留，执行时来源不匹配继续失败关闭。
旧公开行在未显式补算前保留原版本；当前接口可能显示“未就绪/无当前数据”，不自动 fallback。
旧历史可通过冻结报告/原有显式历史读取查阅，不新增绕过当前来源门禁。

没有 Schema 变化，不新增空迁移；0058 字节保持。历史需要回补时须用户另批日期范围、
Provider 配额、候选/WAL/磁盘和旧快照保留。此次不授权任何业务库回补或部署。

## 差异与兼容证据

实际实验：完整因子/机会各 3 行全字段相同（rtol=atol=1e-12），完全缺状态 3 行也相同。
仅缺 C 股票的状态时，原版 3 股全不合格，新版 A/B 合格、C 保留 TRADE_STATUS_MISSING；
变化列仅 eligible/exclusion_reason、RPS20/60/120/250 及 RPS delta5，价格/MA/ATR/收益不变。
将上述结果继续交给未修改的真实 Trend/Signal 引擎：完整样本旧/新均 2 条信号且所有字段相同；
部分缺状态由 0 恢复为 2 条，完全缺状态旧/新均 0。该传播是显式升版的直接证据，不能称历史选股不变。
对比脚本同时记录集中版本和两个配置 Hash，配置 Hash 修复前后一致，只有七类计算版本显式改变。
机会缺 None / pd.NA 从 TypeError / DataError 变为 3 行正常输出，无无依据布尔/RPS 原因。
完整样本左/右/趋势各一行，阶段、分数、原因码和排序不变；既有趋势/信号服务回归保留原数值断言。

当前版本 fixture 改为引用集中常量，并保留 trend_v1/opportunity_v1 与当前版本并存负例；
不是降低断言。PG 证明旧行值/来源仍可读、当前过滤拒绝，旧队列身份明确失败而不建立候选。
现有 Research/Portfolio/PAPER/冻结报告全量回归继续验证，不重新签署旧 Artifact。

完整输入必须全字段一致；仅缺状态时，缺失股票仍明确 TRADE_STATUS_MISSING，
有状态股票不误排除，排名改变是纠错的传播而非阈值变化。
缺 RPS/ATR/布尔的机会输入只移除无依据原因，不增加假强信号；沿用原有可用值归一化和
已有零分组件政策，不将任意未知分数统一补零。无穷/非法对象视为不可用，输出无 JSON 非有限数。
实际差异报告、下游兼容与容量/发布门禁见本专项 closeout 与同 SHA CI 产物。
