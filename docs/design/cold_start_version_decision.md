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

## 差异与兼容证据（实施后填入实际结果）

完整输入必须全字段一致；仅缺状态时，缺失股票仍明确 TRADE_STATUS_MISSING，
有状态股票不误排除，排名改变是纠错的传播而非阈值变化。
缺 RPS/ATR/布尔的机会输入只移除无依据原因，不增加假强信号；沿用原有可用值归一化和
已有零分组件政策，不将任意未知分数统一补零。无穷/非法对象视为不可用，输出无 JSON 非有限数。
实际差异报告、下游兼容与容量/发布门禁见本专项 closeout 与同 SHA CI 产物。
