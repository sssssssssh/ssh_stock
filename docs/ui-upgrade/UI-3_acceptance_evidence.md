# UI V1.2 验收证据索引与覆盖边界

## 证据身份与下载

本轮不修改生产代码；视觉版本仍是 `16912a5515ec8ed75ae63598ab8d1d6a22b15ae4` 的 CSS，
业务冻结基线为 `0136ee9e03727314102cc041d52dd488cca50def`。
实际 CI 链接、提交身份和结论见 [交付记录](UI-2_delivery.md)。

在对应 Actions run 页面下载 `ui-visual-acceptance-<完整 SHA>` Artifact。
解压后进入 `<SHA>/`，打开自动生成的 `index.md`；每一行来自实际完成的截图采集，
包括视口、before/after、fixture 状态、checkpoint 和相对 PNG 链接。
`screenshots.json` 是机器可读索引，`result.json` 记录真实完成数量、脚本/CSS 哈希、环境、
Git 身份、CI URL、失败原因和清理结果。索引没有收录失败截图时，还可检查对应状态的 `failure.png`。
Actions 产物保留 14 天，过期后须在同一提交重新运行工作流获取，不能以其他 SHA 产物替代。

所有截图来自实际 Vue 应用，不是原型 HTML。页面上方的“合成验收数据”标记由测试注入，
不修改产品组件。全部 API 在浏览器进程中拦截；生产配置、模型和数据库没有连接或变更。
`before` 仅将根样式替换为冻结 Git 树中的 CSS，用户、时钟、权限、fixture 和操作完全相同。

## 八导航必需前后截图

以下每项均在 `1440`、`390` 两个目录、`before`、`after` 两个版本下采集，
即每页四张、八页共 32 张必需截图。路径相对 Artifact 的 `<SHA>/`：

| 原导航 | checkpoint | 路径模板 |
| --- | --- | --- |
| 总览 | overview | `<width>/<variant>/rich/overview.png` |
| 数据 | data | `<width>/<variant>/rich/data.png` |
| 长线 | long | `<width>/<variant>/rich/long.png` |
| 短线 | short | `<width>/<variant>/rich/short.png` |
| 回测分析 | analytics | `<width>/<variant>/rich/analytics.png` |
| 智能研究 | agent | `<width>/<variant>/rich/agent.png` |
| 研究报告 | reports | `<width>/<variant>/rich/reports.png` |
| 决策与模拟 | paper | `<width>/<variant>/rich/paper.png` |

同时为 1280/1024/768 保留这些截图，不把本地移动端结果冒充 CI 移动端验收。

## 次级视图与异常截图

下表是可定位的 checkpoint，不手填截图数量；实际存在文件以本次生成索引为准。
`rich` 等九状态在五宽度运行；`evidence`、`recovery` 在 1440/390 前后运行。

| 组别 | 状态目录 | checkpoint / PNG 文件名（省略 `.png`） |
| --- | --- | --- |
| 账户 | rich / login / password | user-menu、password-optional；login、password |
| 总览研究/抽屉 | rich | theme、research-题材/左侧/右侧/趋势/位置 |
| 数据折叠/日历 | rich | collapsed-补算因子与股票池、collapsed-拉取数据与任务、collapsed-数据覆盖日历、calendar-detail |
| 趋势与 K 线 | rich | trend、kline-90（180/365 保留请求及控件 JSON） |
| 首次 K 线 / tooltip | evidence | kline-initial、kline-tooltip（首次真实打开后悬停，不以空图冒充轴线检查） |
| 回测/比较 | rich / evidence | analytics、compare-two；missing-period、generated-period |
| 证据与窗口来源 | evidence | agent-evidence-answer、earlier-messages、agent-evidence-panel、walk-forward、chat-archive、chat-archived |
| 长文本/末列 | evidence | long-text-last-column、stock-research-context |
| 冻结报告 | rich / evidence | report-detail；frozen-verification、frozen-fact-detail、contract-verification、contract-detail |
| 四种报告比较 | evidence | report-comparison-AUTO/STRICT_SAME_SAMPLE/DIFFERENT_ASSUMPTIONS/WINDOW_DEGRADATION |
| PAPER 四页签/五弹窗 | rich | paper、paper-模拟组合/执行与账本/后验复盘；modal-新建账户/记录决策/人工审批/驳回/关闭账户 |
| PAPER 异常账户 | disabled / schema / PAUSED / CLOSED | paper-state-disabled/schema/PAUSED/CLOSED |
| 结算/取消 | evidence | paper-running-job、paper-cancelled-job、paper-advance-queued |
| 未知结果/失败恢复 | recovery | unknown-result、unknown-retry、failed-result、failed-new-draft |
| 空态/错误 | empty / error | overview、data、long、short、analytics、agent、reports、paper |
| 短屏 | 1280/after/short | overview（其余八导航操作及 footer 边界在 checkpoints.json） |

## 已实测与未实测必须区分

| 项目 | 依据及边界 |
| --- | --- |
| 五宽度 × 九状态等价 | 浏览器实际采集：可见文本、控件值、disabled/required/aria、表头/单元格和每步请求多重集；前后严格相等，不匹配即失败 |
| 研究五 Tab/周期 | 实际点击五 Tab、60日；原控件/所有周期定义由 74 文件字节门禁保护，并非穷举每个周期组合 |
| 数据提交/分页 | 实际点击三类提交、三折叠、上/下月、日期、10/20/50/100、上/下页；失败长错误与空态有截图；不启动真实计算 |
| 股票入口/回测 | 代码按钮打开 K 线 90/180/365；长线趋势、末列研究入口、月/年、缺失周期生成、两个 Run 比较、三个排序实际操作；全部 Episodes/Period/Compare 列逐项对照，无前端 PnL 重算 |
| 智能研究 | 会话归档、消息分页、证据、Walk-forward 跳转/返回、UNKNOWN_RESULT 原请求重试和 FAILED 新草稿实测；五上下文输入定义字节不变，新增全站脚本只主动填写证券代码；其他组合由原组件测试保护 |
| 报告 | 四类型筛选、四比较模式、报告/比较 Markdown/HTML 下载、冻结证据及合同复核实测；不可比较时四列表，不展示标记审计差值；报告归档及全部权限分支仍依赖原组件/M16.6 浏览器，不声称新增脚本穷举 |
| PAPER | 四页签、九集合、五弹窗、人工二次确认、ACTIVE/PAUSED/CLOSED、禁用/schema、取消及结算入队实测；M17 原脚本补充响应丢失、防双击、恢复；未执行真实批准/交易/账本计算 |
| 图表 | ECharts 原代码/数据/颜色选项逐字节保护；轴线/图例及首次K线tooltip人工核对：同日OHLC10.50/10.70/9.50/11.50与MA5一致，缺失MA20/60仍为`--`，不转0；没有穷举所有tooltip/缩放/长序列/缺口组合 |
| 真实服务 E2E | **未执行**。合成响应不证明 PostgreSQL、Worker、外部行情或模型运行正确；本次不得连接生产数据补测 |

## 人工视觉核对办法与遗留

核对同数据 before/after：桌面总览卡片/轴线/图例、390 长线内部滚动、账户菜单层级、
人工审批弹窗与未勾选禁用、短屏导航/footer；另已查看移动端证据抽屉、Walk-forward身份、
不可比较四列表及UNKNOWN_RESULT的原请求重试截图，文字/控件可读，无新增视觉阻断。
最新完整运行也已核对390px长原因末列与PAPER取消任务截图，研究入口可见可点击，取消状态可读。
只把浏览器已经完成的点击作为“可操作性实测”，
不使用强制点击，也不把 DOM 存在等同于鼠标可点。

金融涨跌颜色沿用原组件（例如市场分布图原有“上涨绿/下跌红”图例），本次不重定义金融语义。
密集表采用内部横向滚动而非删列。冻结旧 CSS 在 390px 的比较排序表头已有鼠标覆盖，
前后都用原生 focus+Enter 对照；新版额外执行真实鼠标 click，不修改事件、不使用 force。
### 继承问题 UI-V1.2-KLINE-01（非本轮样式回归，未修复）

人工检查发现K线区间重载后截图可能空白，before/after均存在；首次打开时图形也有窄画布现象。
证据：两版本 `rich/kline-90.png`；首次 `evidence/kline-initial.png` 与 `kline-tooltip.png`。
疑似原图表实例仍绑定被替换DOM/未完成尺寸更新，属于待独立确认的生命周期问题；
源码未修改，不能在UI-only任务中修Vue事件或图表实例管理。
复现：代码按钮首次开图→点击90/180/365重新加载→检查画布；另立功能修复任务后验证首次/重载尺寸及tooltip。
本轮保留原三个区间请求与控件断言，额外采集首次canvas/tooltip，不将空图作为完整图表渲染已通过。

OpportunityTable 原空态 colspan、11 项依赖审计告警与大 JS chunk 均为历史问题，留待独立任务。

真实环境人工复核须另获授权：使用隔离测试账户/数据，在原入口逐项验证真实请求、权限/失败态、
工具证据返回、审批幂等与账本；图表逐项悬停核对 tooltip/轴线/缺口。不能把这项未执行
的真实服务验收写成合成浏览器已完成，也不能为修业务问题修改本次冻结的 Vue/API。
