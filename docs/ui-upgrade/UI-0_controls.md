# UI-0 逐控件、事件与表格冻结清单

基线与适用边界见 [审查总表](UI-0_audit.md)。此表由当前 Vue 模板 AST 提取；每行是源码声明，不是运行时按钮总数。`v-for` 会展开，互斥分支不会同时显示。事件为空不代表无行为：form 提交、v-model、原生 details/summary、组件 emits 和脚本链见同组表与源码。

显示上下文按祖先到本元素列出；`else/else-if` 的前序分支同时记录以避免误当成无条件显示。动态文案保留表达式，枚举实值由审查总表补充。

## frontend/src/App.vue

脚本 SHA-256：`058168a52647073ef4a424e4fb224d0a01649acc0cdbb4ce8f1251ae4c35a6da`。

| ID / 行 | 元素与文案 / 标签 | 显示、分支与循环上下文 | 原属性、事件、禁用与数据绑定 |
| --- | --- | --- | --- |
| App-001 / 1123 | LoginView · (无子文本；见属性) | preceding branches: v-if="authLoading" → v-else-if="!authUser" | v-else-if="!authUser" ; @authenticated="handleAuthenticated" |
| App-002 / 1124 | ChangePasswordView · (无子文本；见属性) | preceding branches: v-if="authLoading" ; v-else-if="!authUser" → v-else-if="showChangePassword" | v-else-if="showChangePassword" ; :username="authUser.username" ; :required="authUser.must_change_password" ; @changed="handlePasswordChanged" ; @cancel="showChangePassword = false" |
| App-003 / 1145 | button · {{ item.label }} {{ item.description }} | preceding branches: v-if="authLoading" ; v-else-if="!authUser" ; v-else-if="showChangePassword" → v-else → v-for="item in navItems" | v-for="item in navItems" ; :key="item.key" ; :class="{ active: activeView === item.key }" ; type="button" ; @click="setActiveView(item.key)" |
| App-004 / 1171 | button · {{ loading ? "刷新中" : "刷新" }} | preceding branches: v-if="authLoading" ; v-else-if="!authUser" ; v-else-if="showChangePassword" → v-else | :disabled="loading" ; @click="loadData" |
| App-005 / 1174 | UserMenu · (无子文本；见属性) | preceding branches: v-if="authLoading" ; v-else-if="!authUser" ; v-else-if="showChangePassword" → v-else | :username="authUser.username" ; @change-password="showChangePassword = true" ; @logout="handleLogout" |
| App-006 / 1188 | button · 市场 | preceding branches: v-if="authLoading" ; v-else-if="!authUser" ; v-else-if="showChangePassword" → v-else → v-show="activeView === 'overview'" | type="button" ; role="tab" ; :aria-selected="overviewMode === 'market'" ; :class="{ selected: overviewMode === 'market' }" ; @click="overviewMode = 'market'" |
| App-007 / 1190 | button · 研究 | preceding branches: v-if="authLoading" ; v-else-if="!authUser" ; v-else-if="showChangePassword" → v-else → v-show="activeView === 'overview'" | type="button" ; role="tab" ; :aria-selected="overviewMode === 'research'" ; :class="{ selected: overviewMode === 'research' }" ; @click="overviewMode = 'research'" |
| App-008 / 1211 | SectorHeatPanel · (无子文本；见属性) | preceding branches: v-if="authLoading" ; v-else-if="!authUser" ; v-else-if="showChangePassword" → v-else → v-show="activeView === 'overview'" → v-if="overviewMode === 'market'" | title="热门行业" ; subtitle="申万一级行业" ; :rows="sectorHeat.slice(0, 15)" ; :format-number="formatNumber" ; @research="openAgentResearch" |
| App-009 / 1218 | ThemeHeatTable · (无子文本；见属性) | preceding branches: v-if="authLoading" ; v-else-if="!authUser" ; v-else-if="showChangePassword" → v-else → v-show="activeView === 'overview'" → v-if="overviewMode === 'market'" | :rows="themeHeat" ; :format-number="formatNumber" ; @select="openThemeDetail" |
| App-010 / 1260 | button · 补算因子与股票池 | preceding branches: v-if="authLoading" ; v-else-if="!authUser" ; v-else-if="showChangePassword" → v-else → v-show="activeView === 'data'" | type="button" ; :aria-expanded="!collapsedDataPanels.recalc" ; @click="toggleDataPanel('recalc')" |
| App-011 / 1272 | form · 开始 结束 评估信号 {{ submittingRecalculation ? "提交中" : "开始补算" }} | preceding branches: v-if="authLoading" ; v-else-if="!authUser" ; v-else-if="showChangePassword" → v-else → v-show="activeView === 'data'" | @submit.prevent="submitRecalculation" |
| App-012 / 1275 | input · 开始 | preceding branches: v-if="authLoading" ; v-else-if="!authUser" ; v-else-if="showChangePassword" → v-else → v-show="activeView === 'data'" | v-model="recalcStart" ; type="date" |
| App-013 / 1279 | input · 结束 | preceding branches: v-if="authLoading" ; v-else-if="!authUser" ; v-else-if="showChangePassword" → v-else → v-show="activeView === 'data'" | v-model="recalcEnd" ; type="date" |
| App-014 / 1282 | input · 评估信号 | preceding branches: v-if="authLoading" ; v-else-if="!authUser" ; v-else-if="showChangePassword" → v-else → v-show="activeView === 'data'" | v-model="recalcEvaluateSignals" ; type="checkbox" |
| App-015 / 1285 | button · {{ submittingRecalculation ? "提交中" : "开始补算" }} | preceding branches: v-if="authLoading" ; v-else-if="!authUser" ; v-else-if="showChangePassword" → v-else → v-show="activeView === 'data'" | type="submit" ; :disabled="submittingRecalculation" |
| App-016 / 1301 | JobCenter · (无子文本；见属性) | preceding branches: v-if="authLoading" ; v-else-if="!authUser" ; v-else-if="showChangePassword" → v-else → v-show="activeView === 'data'" | v-model:backfill-start="backfillStart" ; v-model:backfill-end="backfillEnd" ; :collapsed="collapsedDataPanels.tasks" ; :submitting-basic-info="submittingBasicInfo" ; :submitting-ingestion="submittingIngestion" ; :active-job="activeJob" ; :jobs="latestJobs" ; :status-label="statusLabel" ; :progress-pct="progressPct" ; :job-step-text="jobStepText" ; :metadata-text="metadataText" ; :format-job-elapsed="formatJobElapsed" ; :row-count-hint="rowCountHint" ; :job-tooltip="jobTooltip" ; :job-type-text="jobTypeText" ; @toggle="toggleDataPanel('tasks')" ; @sync-basic="submitBasicInfo" ; @submit-backfill="submitBackfill" |
| App-017 / 1322 | DataQuality · (无子文本；见属性) | preceding branches: v-if="authLoading" ; v-else-if="!authUser" ; v-else-if="showChangePassword" → v-else → v-show="activeView === 'data'" | v-model:page-size="coveragePageSize" ; :collapsed="collapsedDataPanels.coverage" ; :summary="calendarSummary" ; :month-title="calendarMonthTitle" ; :cells="calendarCells" ; :selected-date="selectedCalendarDate" ; :selected-row="selectedCalendarRow" ; :page-rows="pagedDataCoverage" ; :total-rows="dataCoverage.length" ; :page="coveragePage" ; :page-sizes="coveragePageSizeOptions" ; :total-pages="coverageTotalPages" ; :page-start="coveragePageStart" ; :page-end="coveragePageEnd" ; :status-label="calendarStatusLabel" ; @toggle="toggleDataPanel('coverage')" ; @previous-month="shiftCalendarMonth(-1)" ; @next-month="shiftCalendarMonth(1)" ; @select-date="selectCalendarDay" ; @set-page="setCoveragePage" |
| App-018 / 1347 | StockPool · 右侧 趋势 | preceding branches: v-if="authLoading" ; v-else-if="!authUser" ; v-else-if="showChangePassword" → v-else → v-show="activeView === 'long'" | title="长线股票池" ; :rows="currentPool" ; empty-text="暂无符合条件的股票" ; :format-number="formatNumber" ; :reason-text="reasonText" ; :highlight-ts-code="researchNavigation?.view === 'long' ? researchNavigation.ts_code : undefined" ; :highlight-trade-date="researchNavigation?.view === 'long' ? researchNavigation.trade_date : undefined" ; @select="openRealtimeKline" ; @research="openAgentResearch" |
| App-019 / 1360 | button · 右侧 | preceding branches: v-if="authLoading" ; v-else-if="!authUser" ; v-else-if="showChangePassword" → v-else → v-show="activeView === 'long'" → #actions | :class="{ active: activePool === 'right' }" ; @click="activePool = 'right'" |
| App-020 / 1363 | button · 趋势 | preceding branches: v-if="authLoading" ; v-else-if="!authUser" ; v-else-if="showChangePassword" → v-else → v-show="activeView === 'long'" → #actions | :class="{ active: activePool === 'trend' }" ; @click="activePool = 'trend'" |
| App-021 / 1369 | SectorHeatPanel · (无子文本；见属性) | preceding branches: v-if="authLoading" ; v-else-if="!authUser" ; v-else-if="showChangePassword" → v-else → v-show="activeView === 'long'" | title="长线行业" ; subtitle="按热度排序" ; :rows="researchNavigation?.sector_id ? sectorHeat : sectorHeat.slice(0, 20)" ; :format-number="formatNumber" ; :highlight-sector-id="researchNavigation?.view === 'long' ? researchNavigation.sector_id : undefined" ; :highlight-trade-date="researchNavigation?.view === 'long' ? researchNavigation.trade_date : undefined" ; @research="openAgentResearch" |
| App-022 / 1382 | StockPool · (无子文本；见属性) | preceding branches: v-if="authLoading" ; v-else-if="!authUser" ; v-else-if="showChangePassword" → v-else → v-show="activeView === 'short'" | title="短线风险池" ; subtitle="衰退 / 破位观察" ; :rows="decayPool" ; warning ; empty-text="暂无短线风险股票" ; :format-number="formatNumber" ; :reason-text="reasonText" ; :highlight-ts-code="researchNavigation?.view === 'long' ? researchNavigation.ts_code : undefined" ; :highlight-trade-date="researchNavigation?.view === 'long' ? researchNavigation.trade_date : undefined" ; @select="openRealtimeKline" ; @research="openAgentResearch" |
| App-023 / 1412 | SectorHeatPanel · (无子文本；见属性) | preceding branches: v-if="authLoading" ; v-else-if="!authUser" ; v-else-if="showChangePassword" → v-else → v-show="activeView === 'short'" | title="短线行业动量" ; subtitle="按 Heat Momentum 3 排序" ; :rows="shortSectorRows" ; momentum ; :format-number="formatNumber" ; :highlight-sector-id="researchNavigation?.view === 'long' ? researchNavigation.sector_id : undefined" ; :highlight-trade-date="researchNavigation?.view === 'long' ? researchNavigation.trade_date : undefined" ; @research="openAgentResearch" |
| App-024 / 1426 | BacktestAnalyticsView · (无子文本；见属性) | preceding branches: v-if="authLoading" ; v-else-if="!authUser" ; v-else-if="showChangePassword" → v-else → v-show="activeView === 'analytics'" | :initial-run-id="researchNavigation?.view === 'analytics' ? researchNavigation.run_id : agentContext?.run_id" ; :navigation="researchNavigation?.view === 'analytics' ? researchNavigation : null" ; @research="openAgentResearch" |
| App-025 / 1430 | AgentResearchWorkbench · (无子文本；见属性) | preceding branches: v-if="authLoading" ; v-else-if="!authUser" ; v-else-if="showChangePassword" → v-else → v-show="activeView === 'agent'" | :key="authUser.username" ; :owner-id="authUser.username" ; :visible="activeView === 'agent'" ; :initial-context="agentContext" ; @navigate="navigateFromAgent" ; @create-report="openResearchReport" |
| App-026 / 1434 | AgentResearchReports · (无子文本；见属性) | preceding branches: v-if="authLoading" ; v-else-if="!authUser" ; v-else-if="showChangePassword" → v-else → v-show="activeView === 'reports'" | :initial-source="reportSource" ; @navigate="navigateFromAgent" |
| App-027 / 1442 | WalkForwardEvidenceView · (无子文本；见属性) | preceding branches: v-if="authLoading" ; v-else-if="!authUser" ; v-else-if="showChangePassword" → v-else → v-show="activeView === 'walk_forward'" | :navigation="researchNavigation" ; @back="setActiveView('agent')" |
| App-028 / 1446 | div · 实时 K 线 {{ klineTitle }} {{ days }} 日 {{ klineLoading ? "加载中" : "刷新" }} × {{ klineData?.start &#124;&#124; "--" }} 到 {{ klineData?.end &#124;&#124; "--" }} {{ klineData?.rows.length &#124;&#124; 0 }} 个交易日 {{ klineData?.source &#124;&#124; "tushare" }} / 不入库 {{ klineError }} 加载中 暂无 K 线数据 | preceding branches: v-if="authLoading" ; v-else-if="!authUser" ; v-else-if="showChangePassword" → v-else → v-if="selectedKlineStock" | v-if="selectedKlineStock" ; @click.self="closeRealtimeKline" |
| App-029 / 1455 | button · {{ days }} 日 | preceding branches: v-if="authLoading" ; v-else-if="!authUser" ; v-else-if="showChangePassword" → v-else → v-if="selectedKlineStock" → v-for="days in klineDayOptions" | v-for="days in klineDayOptions" ; :key="days" ; type="button" ; :class="{ active: selectedKlineDays === days }" ; @click="setKlineDays(days)" |
| App-030 / 1465 | button · {{ klineLoading ? "加载中" : "刷新" }} | preceding branches: v-if="authLoading" ; v-else-if="!authUser" ; v-else-if="showChangePassword" → v-else → v-if="selectedKlineStock" | type="button" ; :disabled="klineLoading" ; @click="loadRealtimeKline" |
| App-031 / 1468 | button · × | preceding branches: v-if="authLoading" ; v-else-if="!authUser" ; v-else-if="showChangePassword" → v-else → v-if="selectedKlineStock" | type="button" ; aria-label="关闭" ; @click="closeRealtimeKline" |
| App-032 / 1484 | ThemeDetail · (无子文本；见属性) | preceding branches: v-if="authLoading" ; v-else-if="!authUser" ; v-else-if="showChangePassword" → v-else → v-if="selectedTheme" | v-if="selectedTheme" ; :data="themeOverview" ; :loading="themeDetailLoading" ; @close="closeThemeDetail" |

## frontend/src/components/AgentResearchReports.vue

脚本 SHA-256：`cef2022c4b19946997d34ff8ab01af0a7b05f74c56ad4b1f7ee0efb1d07a5840`。

| ID / 行 | 元素与文案 / 标签 | 显示、分支与循环上下文 | 原属性、事件、禁用与数据绑定 |
| --- | --- | --- | --- |
| AgentResearchReports-001 / 246 | select · 全部类型 市场复盘 机会复盘 策略复盘 样本外验证复盘 | 组件内无额外条件 | v-model="reportFilter" ; aria-label="报告类型筛选" ; @change="loadReports()" |
| AgentResearchReports-002 / 246 | input · 显示已归档 | 组件内无额外条件 | v-model="includeArchived" ; type="checkbox" ; @change="loadReports()" |
| AgentResearchReports-003 / 252 | input · 会话 ID | 组件内无额外条件 | v-model.trim="sourceChatId" ; placeholder="从智能研究消息带入" |
| AgentResearchReports-004 / 253 | input · 消息 ID | 组件内无额外条件 | v-model.trim="sourceMessageId" ; placeholder="助手消息 UUID" |
| AgentResearchReports-005 / 254 | select · 市场复盘 机会复盘 策略复盘 样本外验证复盘 | 组件内无额外条件 | v-model="reportType" |
| AgentResearchReports-006 / 255 | input · 标题 | 组件内无额外条件 | v-model.trim="title" ; placeholder="可选，默认按类型与日期生成" |
| AgentResearchReports-007 / 256 | button · 生成报告 | 组件内无额外条件 | type="button" ; :disabled="working &#124;&#124; !sourceChatId &#124;&#124; !sourceMessageId" ; @click="createReport" |
| AgentResearchReports-008 / 263 | button · {{ report.title }} {{ report.as_of_date &#124;&#124; "日期未提供" }} · {{ report.report_type }} {{ report.archived_at ? "已归档" : report.source_answer_status }} · 来源 {{ report.source_chat_id }} | v-for="report in reports" | v-for="report in reports" ; :key="report.report_id" ; type="button" ; :class="{ active: selected?.report_id === report.report_id }" ; @click="openReport(report.report_id)" |
| AgentResearchReports-009 / 267 | button · 加载更多 | v-if="reports.length < reportTotal" | v-if="reports.length < reportTotal" ; type="button" ; @click="loadReports(false)" |
| AgentResearchReports-010 / 273 | button · Markdown | preceding branches: v-if="!selected" → v-else | type="button" ; @click="download('markdown')" |
| AgentResearchReports-011 / 273 | button · HTML | preceding branches: v-if="!selected" → v-else | type="button" ; @click="download('html')" |
| AgentResearchReports-012 / 273 | button · 归档 | preceding branches: v-if="!selected" → v-else → v-if="!selected.archived_at" | v-if="!selected.archived_at" ; type="button" ; :disabled="working" ; @click="archiveSelected" |
| AgentResearchReports-013 / 278 | button · 打开业务详情 | preceding branches: v-if="!selected" → v-else → v-for="citation in selected.snapshot.citations" → v-if="citation.navigation" | v-if="citation.navigation" ; type="button" ; @click="emit('navigate', citation.navigation)" |
| AgentResearchReports-014 / 279 | summary · 限制、警告与未纳入主张 | preceding branches: v-if="!selected" → v-else | 原生默认行为 |
| AgentResearchReports-015 / 286 | select · 选择左侧报告 {{ report.title }} | 组件内无额外条件 | v-model="leftReportId" |
| AgentResearchReports-016 / 287 | select · 选择右侧报告 {{ report.title }} | 组件内无额外条件 | v-model="rightReportId" |
| AgentResearchReports-017 / 288 | select · 原事实口径 同样本回测 假设敏感性 窗口 TRAIN/OOS | 组件内无额外条件 | v-model="comparisonMode" ; aria-label="比较模式" |
| AgentResearchReports-018 / 289 | button · {{ comparing ? '比较中' : '比较' }} | 组件内无额外条件 | type="button" ; :disabled="working &#124;&#124; comparing &#124;&#124; !leftReportId &#124;&#124; !rightReportId &#124;&#124; leftReportId === rightReportId" ; @click="compareReports" |
| AgentResearchReports-019 / 292 | button · 导出比较 Markdown | v-if="comparison" | type="button" ; @click="downloadComparison('markdown')" |
| AgentResearchReports-020 / 292 | button · 导出比较 HTML | v-if="comparison" | type="button" ; @click="downloadComparison('html')" |
| AgentResearchReports-021 / 298 | summary · 口径差异 | v-if="comparison" → v-if="comparisonDisplay?.explain_reasons?.length" | 原生默认行为 |
| AgentResearchReports-022 / 299 | summary · 比较合同身份 | v-if="comparison" → v-if="comparisonDisplay?.contract_refs" | 原生默认行为 |

表 frontend/src/components/AgentResearchReports.vue#table-1（源码 297 行）列顺序；条件列/循环列按表达式展开：

| 序号 | 表头原文/表达式 | 条件/循环上下文 |
| --- | --- | --- |
| 1 | 指标 | v-if="comparison" |
| 2 | {{ windowComparison ? 'TRAIN' : '左值' }} | v-if="comparison" |
| 3 | {{ windowComparison ? 'OOS' : '右值' }} | v-if="comparison" |
| 4 | 逐项许可 | v-if="comparison" |
| 5 | {{ windowComparison ? '窗口退化' : '授权差值' }} | v-if="comparison" → v-if="deltaAllowed" |

## frontend/src/components/AgentResearchWorkbench.vue

脚本 SHA-256：`ca11f9758fba89528c144aaae1538b6f41f4fe98a115f4614a96ed705361df26`。

| ID / 行 | 元素与文案 / 标签 | 显示、分支与循环上下文 | 原属性、事件、禁用与数据绑定 |
| --- | --- | --- | --- |
| AgentResearchWorkbench-001 / 722 | button · 新建会话 | 组件内无额外条件 | type="button" ; @click="newChat" |
| AgentResearchWorkbench-002 / 732 | button · 重试 | v-if="visibleError" → v-if="!activePending" | v-if="!activePending" ; type="button" ; @click="initialize" |
| AgentResearchWorkbench-003 / 738 | button · {{ chat.title }} {{ new Date(chat.updated_at).toLocaleString("zh-CN") }} | v-for="chat in chats" | v-for="chat in chats" ; :key="chat.chat_id" ; type="button" ; :class="{ active: chat.chat_id === activeChatId }" ; @click="selectChat(chat.chat_id)" |
| AgentResearchWorkbench-004 / 750 | button · 加载更多 | v-if="hasMoreChats" | v-if="hasMoreChats" ; type="button" ; @click="loadMoreChats" |
| AgentResearchWorkbench-005 / 756 | button · × | v-if="activeChatId" | v-if="activeChatId" ; type="button" ; title="归档当前会话" ; aria-label="归档当前会话" ; :disabled="Boolean(activePending)" ; @click="archiveCurrentChat" |
| AgentResearchWorkbench-006 / 762 | input · 股票代码 | 组件内无额外条件 | v-model.trim="context.ts_code" ; placeholder="000001.SZ" |
| AgentResearchWorkbench-007 / 763 | input · 交易日 | 组件内无额外条件 | v-model="context.trade_date" ; type="date" |
| AgentResearchWorkbench-008 / 764 | input · 回测 Run | 组件内无额外条件 | v-model.trim="context.run_id" ; placeholder="UUID" |
| AgentResearchWorkbench-009 / 765 | input · Study | 组件内无额外条件 | v-model.trim="context.study_id" ; placeholder="UUID" |
| AgentResearchWorkbench-010 / 766 | input · Validation | 组件内无额外条件 | v-model.trim="context.validation_id" ; placeholder="UUID" |
| AgentResearchWorkbench-011 / 769 | button · {{ key }} : {{ value }} × | v-if="contextEntries.length" → v-for="[key, value] in contextEntries" | v-for="[key, value] in contextEntries" ; :key="key" ; type="button" ; :title="`移除 ${key}`" ; @click="clearContext(key)" |
| AgentResearchWorkbench-012 / 776 | button · {{ loadingEarlier ? "正在加载" : "加载更早消息" }} | v-if="!loadingMessages && messageHasMore" | v-if="!loadingMessages && messageHasMore" ; type="button" ; :disabled="loadingEarlier" ; @click="loadEarlierMessages" |
| AgentResearchWorkbench-013 / 807 | button · {{ citation.marker }} · {{ citation.tool_name }} | v-for="message in messages" → v-if="message.role === 'ASSISTANT' && message.status !== 'FAILED'" → v-if="metadata(message).citations?.length" → v-for="citation in metadata(message).citations" | v-for="citation in metadata(message).citations" ; :key="citation.evidence_id" ; type="button" ; @click="showEvidence(citation)" |
| AgentResearchWorkbench-014 / 811 | button · 生成研究报告 | v-for="message in messages" → v-if="message.role === 'ASSISTANT' && message.status !== 'FAILED'" → v-if="verifiedClaims(message).length" | v-if="verifiedClaims(message).length" ; type="button" ; @click="createReportFromMessage(message)" |
| AgentResearchWorkbench-015 / 812 | button · 查看证据归档 | v-for="message in messages" → v-if="message.role === 'ASSISTANT' && message.status !== 'FAILED'" | type="button" ; @click="archiveRequest = message.source_request_id &#124;&#124; null; archiveOpen = true" |
| AgentResearchWorkbench-016 / 814 | summary · 执行详情 | v-for="message in messages" → v-if="message.role === 'ASSISTANT' && message.status !== 'FAILED'" → v-if="metadata(message).tool_calls?.length &#124;&#124; metadata(message).warnings?.length" | 原生默认行为 |
| AgentResearchWorkbench-017 / 822 | button · 关闭归档面板 | v-if="archiveOpen" | type="button" ; @click="archiveOpen = false" |
| AgentResearchWorkbench-018 / 826 | button · 沿用原请求重试 | v-if="activePending" → v-if="activePending.state === 'UNKNOWN_RESULT' && activePending.normalizedContent && !blockedReplay.has(activePending.chatId)" | v-if="activePending.state === 'UNKNOWN_RESULT' && activePending.normalizedContent && !blockedReplay.has(activePending.chatId)" ; type="button" ; @click="retryUnknown" |
| AgentResearchWorkbench-019 / 827 | button · 刷新状态 | v-if="activePending" → v-if="['UNKNOWN_RESULT', 'RUNNING', 'COMPLETED'].includes(activePending.state)" | v-if="['UNKNOWN_RESULT', 'RUNNING', 'COMPLETED'].includes(activePending.state)" ; type="button" ; @click="refreshPendingStatus" |
| AgentResearchWorkbench-020 / 828 | button · 作为新消息重试 | v-if="activePending" → v-if="activePending.state === 'FAILED'" | v-if="activePending.state === 'FAILED'" ; type="button" ; @click="retryAsNewRequest" |
| AgentResearchWorkbench-021 / 833 | form · {{ sending ? "研究中" : "发送" }} | 组件内无额外条件 | @submit.prevent="submit" |
| AgentResearchWorkbench-022 / 834 | textarea · (无子文本；见属性) | 组件内无额外条件 | v-model="draft" ; aria-label="研究问题" ; rows="3" ; :disabled="!llmEnabled &#124;&#124; Boolean(activePending) &#124;&#124; activeChat?.status === 'ARCHIVED'" ; placeholder="输入需要核验的研究问题" ; @keydown.ctrl.enter.prevent="submit" |
| AgentResearchWorkbench-023 / 835 | button · {{ sending ? "研究中" : "发送" }} | 组件内无额外条件 | type="submit" ; :disabled="!draft.trim() &#124;&#124; !llmEnabled &#124;&#124; Boolean(activePending) &#124;&#124; activeChat?.status === 'ARCHIVED' &#124;&#124; !online" |
| AgentResearchWorkbench-024 / 840 | button · × | 组件内无额外条件 | type="button" ; aria-label="关闭证据详情" ; @click="evidenceOpen = false" |
| AgentResearchWorkbench-025 / 847 | button · 复制 Evidence ID | v-if="selectedCitation" | type="button" ; @click="copyEvidenceId" |
| AgentResearchWorkbench-026 / 848 | button · 打开业务详情 | v-if="selectedCitation" | type="button" ; @click="openBusinessDetail" |
| AgentResearchWorkbench-027 / 854 | button · (无子文本；见属性) | v-if="evidenceOpen" | v-if="evidenceOpen" ; type="button" ; aria-label="关闭证据详情" ; @click="evidenceOpen = false" |

## frontend/src/components/AnalyticsCompareTable.vue

脚本 SHA-256：`87d985ef684b07f222e7d7c87be70493a6d86dbad7cfe4945ac628b30b1392fb`。

| ID / 行 | 元素与文案 / 标签 | 显示、分支与循环上下文 | 原属性、事件、禁用与数据绑定 |
| --- | --- | --- | --- |
| AnalyticsCompareTable-001 / 16 | button · Annualized Return | 组件内无额外条件 | @click="sortKey = 'annualized_return'" |
| AnalyticsCompareTable-002 / 17 | button · Max Drawdown | 组件内无额外条件 | @click="sortKey = 'max_drawdown'" |
| AnalyticsCompareTable-003 / 18 | button · Sharpe | 组件内无额外条件 | @click="sortKey = 'sharpe_ratio'" |

表 frontend/src/components/AnalyticsCompareTable.vue#table-1（源码 13 行）列顺序；条件列/循环列按表达式展开：

| 序号 | 表头原文/表达式 | 条件/循环上下文 |
| --- | --- | --- |
| 1 | Run |  |
| 2 | Annualized Return |  |
| 3 | Max Drawdown |  |
| 4 | Sharpe |  |
| 5 | Excess |  |
| 6 | Win Rate |  |
| 7 | Profit Factor |  |
| 8 | Turnover |  |
| 9 | Cost Ratio |  |

## frontend/src/components/AnalyticsDrawdownChart.vue

脚本 SHA-256：`361938f8de2ab829846a7ae5bff27936fafdddaa9284f7662b3d91f7a1128e65`。

| ID / 行 | 元素与文案 / 标签 | 显示、分支与循环上下文 | 原属性、事件、禁用与数据绑定 |
| --- | --- | --- | --- |
| — | 无直接操作控件 | 由父组件传值/插槽驱动 | 不新增操作 |

## frontend/src/components/AnalyticsNavChart.vue

脚本 SHA-256：`3c2777da08cfc8f6e5ce5e5cb0caa2e4c18fce267efa1e0481539ebddd7a93c1`。

| ID / 行 | 元素与文案 / 标签 | 显示、分支与循环上下文 | 原属性、事件、禁用与数据绑定 |
| --- | --- | --- | --- |
| — | 无直接操作控件 | 由父组件传值/插槽驱动 | 不新增操作 |

## frontend/src/components/AnalyticsPeriodTable.vue

脚本 SHA-256：`2675dd015367a868a7e21de038795aa7e167cd75011e9ebc76dc3197b2dace8e`。

| ID / 行 | 元素与文案 / 标签 | 显示、分支与循环上下文 | 原属性、事件、禁用与数据绑定 |
| --- | --- | --- | --- |
| — | 无直接操作控件 | 由父组件传值/插槽驱动 | 不新增操作 |

表 frontend/src/components/AnalyticsPeriodTable.vue#table-1（源码 10 行）列顺序；条件列/循环列按表达式展开：

| 序号 | 表头原文/表达式 | 条件/循环上下文 |
| --- | --- | --- |
| 1 | Period |  |
| 2 | Strategy |  |
| 3 | Benchmark |  |
| 4 | Relative |  |
| 5 | Turnover |  |
| 6 | Total Cost |  |
| 7 | Closed |  |
| 8 | Win Rate |  |

## frontend/src/components/AnalyticsSummaryCards.vue

脚本 SHA-256：`7809431d2b7b5ed06ad1ac7f1ac3e3c0e1762f7c2addad677243a808fee24bf8`。

| ID / 行 | 元素与文案 / 标签 | 显示、分支与循环上下文 | 原属性、事件、禁用与数据绑定 |
| --- | --- | --- | --- |
| — | 无直接操作控件 | 由父组件传值/插槽驱动 | 不新增操作 |

## frontend/src/components/BacktestAnalyticsView.vue

脚本 SHA-256：`ec58f54f42ab13f4287c6c9540f906d8855637110b970107d15bf7baab69dc3d`。

| ID / 行 | 元素与文案 / 标签 | 显示、分支与循环上下文 | 原属性、事件、禁用与数据绑定 |
| --- | --- | --- | --- |
| BacktestAnalyticsView-001 / 256 | select · {{ run.name &#124;&#124; run.id.slice(0, 8) }} · {{ run.start_date }} ~ {{ run.end_date }} | 组件内无额外条件 | v-model="selectedRunId" ; :disabled="loading" |
| BacktestAnalyticsView-002 / 262 | button · 带入智能研究 | v-if="selectedRunId" | v-if="selectedRunId" ; type="button" ; @click="emit('research', { run_id: selectedRunId })" |
| BacktestAnalyticsView-003 / 280 | button · 月度 | preceding branches: v-if="loading" ; v-else-if="error" ; v-else-if="!selectedRunId" → v-else-if="summary" | :class="{ active: periodType === 'MONTH' }" ; @click="periodType = 'MONTH'" |
| BacktestAnalyticsView-004 / 280 | button · 年度 | preceding branches: v-if="loading" ; v-else-if="error" ; v-else-if="!selectedRunId" → v-else-if="summary" | :class="{ active: periodType === 'YEAR' }" ; @click="periodType = 'YEAR'" |
| BacktestAnalyticsView-005 / 284 | button · {{ periodJobRunning ? "生成中" : "生成周期分析" }} | preceding branches: v-if="loading" ; v-else-if="error" ; v-else-if="!selectedRunId" → v-else-if="summary" → v-if="periodMissing" | :disabled="periodJobRunning" ; @click="generatePeriods" |
| BacktestAnalyticsView-006 / 292 | select · 全部状态 OPEN CLOSED | preceding branches: v-if="loading" ; v-else-if="error" ; v-else-if="!selectedRunId" → v-else-if="summary" | v-model="episodeStatus" |
| BacktestAnalyticsView-007 / 293 | select · 全部分类 WIN LOSS BREAKEVEN | preceding branches: v-if="loading" ; v-else-if="error" ; v-else-if="!selectedRunId" → v-else-if="summary" | v-model="episodeClassification" |
| BacktestAnalyticsView-008 / 294 | input · (无子文本；见属性) | preceding branches: v-if="loading" ; v-else-if="error" ; v-else-if="!selectedRunId" → v-else-if="summary" | v-model="episodeCode" ; placeholder="股票代码" |
| BacktestAnalyticsView-009 / 295 | button · 查询 | preceding branches: v-if="loading" ; v-else-if="error" ; v-else-if="!selectedRunId" → v-else-if="summary" | @click="episodePage = 0; loadEpisodes()" |
| BacktestAnalyticsView-010 / 298 | button · 上一页 | preceding branches: v-if="loading" ; v-else-if="error" ; v-else-if="!selectedRunId" → v-else-if="summary" | :disabled="episodePage === 0" ; @click="episodePage -= 1; loadEpisodes()" |
| BacktestAnalyticsView-011 / 298 | button · 下一页 | preceding branches: v-if="loading" ; v-else-if="error" ; v-else-if="!selectedRunId" → v-else-if="summary" | :disabled="episodePage * episodeLimit + episodes.length >= episodeTotal" ; @click="episodePage += 1; loadEpisodes()" |
| BacktestAnalyticsView-012 / 302 | button · 开始对比 | preceding branches: v-if="loading" ; v-else-if="error" ; v-else-if="!selectedRunId" → v-else-if="summary" | :disabled="compareSelection.length < 2 &#124;&#124; compareSelection.length > 10" ; @click="runCompare" |
| BacktestAnalyticsView-013 / 303 | input · {{ run.name &#124;&#124; run.id.slice(0, 8) }} | preceding branches: v-if="loading" ; v-else-if="error" ; v-else-if="!selectedRunId" → v-else-if="summary" → v-for="run in successRuns" | v-model="compareSelection" ; type="checkbox" ; :value="run.id" ; :disabled="compareSelection.length >= 10 && !compareSelection.includes(run.id)" |

表 frontend/src/components/BacktestAnalyticsView.vue#table-1（源码 297 行）列顺序；条件列/循环列按表达式展开：

| 序号 | 表头原文/表达式 | 条件/循环上下文 |
| --- | --- | --- |
| 1 | 代码 | preceding branches: v-if="loading" ; v-else-if="error" ; v-else-if="!selectedRunId" → v-else-if="summary" |
| 2 | # | preceding branches: v-if="loading" ; v-else-if="error" ; v-else-if="!selectedRunId" → v-else-if="summary" |
| 3 | 状态 | preceding branches: v-if="loading" ; v-else-if="error" ; v-else-if="!selectedRunId" → v-else-if="summary" |
| 4 | Entry | preceding branches: v-if="loading" ; v-else-if="error" ; v-else-if="!selectedRunId" → v-else-if="summary" |
| 5 | Exit | preceding branches: v-if="loading" ; v-else-if="error" ; v-else-if="!selectedRunId" → v-else-if="summary" |
| 6 | 持有日 | preceding branches: v-if="loading" ; v-else-if="error" ; v-else-if="!selectedRunId" → v-else-if="summary" |
| 7 | Realized PnL | preceding branches: v-if="loading" ; v-else-if="error" ; v-else-if="!selectedRunId" → v-else-if="summary" |
| 8 | Unrealized | preceding branches: v-if="loading" ; v-else-if="error" ; v-else-if="!selectedRunId" → v-else-if="summary" |
| 9 | Return | preceding branches: v-if="loading" ; v-else-if="error" ; v-else-if="!selectedRunId" → v-else-if="summary" |
| 10 | Cost | preceding branches: v-if="loading" ; v-else-if="error" ; v-else-if="!selectedRunId" → v-else-if="summary" |
| 11 | 分类 | preceding branches: v-if="loading" ; v-else-if="error" ; v-else-if="!selectedRunId" → v-else-if="summary" |

## frontend/src/components/ChangePasswordView.vue

脚本 SHA-256：`d75cbdb9c1b18b839209c78916524d6875d99d054874a2d522932f84606d691f`。

| ID / 行 | 元素与文案 / 标签 | 显示、分支与循环上下文 | 原属性、事件、禁用与数据绑定 |
| --- | --- | --- | --- |
| ChangePasswordView-001 / 39 | form · 空 修改密码 {{ username }} 首次登录必须修改初始密码。 当前密码 新密码 确认新密码 {{ error }} 取消 {{ submitting ? "提交中" : "修改密码" }} | 组件内无额外条件 | @submit.prevent="submit" |
| ChangePasswordView-002 / 42 | input · 当前密码 | 组件内无额外条件 | v-model="currentPassword" ; type="password" ; autocomplete="current-password" ; required |
| ChangePasswordView-003 / 43 | input · 新密码 | 组件内无额外条件 | v-model="newPassword" ; type="password" ; autocomplete="new-password" ; required |
| ChangePasswordView-004 / 44 | input · 确认新密码 | 组件内无额外条件 | v-model="confirmPassword" ; type="password" ; autocomplete="new-password" ; required |
| ChangePasswordView-005 / 47 | button · 取消 | v-if="!required" | v-if="!required" ; type="button" ; @click="emit('cancel')" |
| ChangePasswordView-006 / 48 | button · {{ submitting ? "提交中" : "修改密码" }} | 组件内无额外条件 | type="submit" ; :disabled="submitting" |

## frontend/src/components/ContractArchivePanel.vue

脚本 SHA-256：`45267ead0d3cd1e2e83fb603651f4812e001b9adb6026c6d54132d119e5c7446`。

| ID / 行 | 元素与文案 / 标签 | 显示、分支与循环上下文 | 原属性、事件、禁用与数据绑定 |
| --- | --- | --- | --- |
| ContractArchivePanel-001 / 67 | button · 复核合同 | v-if="reference" | v-if="reference" ; type="button" ; :disabled="loading &#124;&#124; busy" ; @click="verify" |
| ContractArchivePanel-002 / 79 | button · 重新加载 | preceding branches: v-if="!reference" → v-else → v-if="error" | type="button" ; @click="load(offset)" |
| ContractArchivePanel-003 / 82 | button · {{ row.contract_kind }} | preceding branches: v-if="!reference" → v-else → v-for="row in rows" | type="button" ; @click="openDetail(row.contract_id)" |
| ContractArchivePanel-004 / 84 | button · ‹ | preceding branches: v-if="!reference" → v-else → v-if="total" | type="button" ; title="上一页" ; aria-label="上一页" ; :disabled="loading &#124;&#124; offset === 0" ; @click="load(Math.max(0, offset - 20))" |
| ContractArchivePanel-005 / 84 | button · › | preceding branches: v-if="!reference" → v-else → v-if="total" | type="button" ; title="下一页" ; aria-label="下一页" ; :disabled="loading &#124;&#124; offset + rows.length >= total" ; @click="load(offset + 20)" |
| ContractArchivePanel-006 / 85 | summary · {{ detail.role }} · {{ detail.contract_kind }} · 明细 | preceding branches: v-if="!reference" → v-else → v-if="detail" | 原生默认行为 |

表 frontend/src/components/ContractArchivePanel.vue#table-1（源码 81 行）列顺序；条件列/循环列按表达式展开：

| 序号 | 表头原文/表达式 | 条件/循环上下文 |
| --- | --- | --- |
| 1 | 来源 / 角色 | preceding branches: v-if="!reference" → v-else |
| 2 | 合同 | preceding branches: v-if="!reference" → v-else |
| 3 | 冻结状态 | preceding branches: v-if="!reference" → v-else |
| 4 | Hash | preceding branches: v-if="!reference" → v-else |

## frontend/src/components/DashboardView.vue

脚本 SHA-256：`6667e5189e09f646c14336de3c888132f24f19d49a291fb234d1909c01c8817f`。

| ID / 行 | 元素与文案 / 标签 | 显示、分支与循环上下文 | 原属性、事件、禁用与数据绑定 |
| --- | --- | --- | --- |
| — | 无直接操作控件 | 由父组件传值/插槽驱动 | 不新增操作 |

## frontend/src/components/DataQuality.vue

脚本 SHA-256：`bcaf51bcf389e9beebff8f2eb677bf540fd069b6b06cbd1c7328934ce0ff1722`。

| ID / 行 | 元素与文案 / 标签 | 显示、分支与循环上下文 | 原属性、事件、禁用与数据绑定 |
| --- | --- | --- | --- |
| DataQuality-001 / 43 | button · 数据覆盖日历 | 组件内无额外条件 | type="button" ; :aria-expanded="!collapsed" ; @click="$emit('toggle')" |
| DataQuality-002 / 50 | button · 上月 | 组件内无额外条件 | type="button" ; @click="$emit('previousMonth')" |
| DataQuality-003 / 52 | button · 下月 | 组件内无额外条件 | type="button" ; @click="$emit('nextMonth')" |
| DataQuality-004 / 64 | button · {{ cell.day &#124;&#124; "" }} {{ statusLabel(cell.row.coverage_status) }} | v-show="!collapsed" → v-for="cell in cells" | v-for="cell in cells" ; :key="cell.key" ; :class="[cell.row?.coverage_status.toLowerCase(), { blank: !cell.row, selected: selectedDate === cell.row?.date }]" ; type="button" ; :disabled="!cell.row" ; :title="cell.row ? `${cell.row.date} ${statusLabel(cell.row.coverage_status)}` : ''" ; @click="$emit('selectDate', cell.row)" |
| DataQuality-005 / 97 | select · {{ size }} | v-show="!collapsed" | :value="pageSize" ; aria-label="覆盖明细每页条数" ; @change="updatePageSize" |
| DataQuality-006 / 101 | button · 上一页 | v-show="!collapsed" | type="button" ; :disabled="page <= 1" ; @click="$emit('setPage', page - 1)" |
| DataQuality-007 / 103 | button · 下一页 | v-show="!collapsed" | type="button" ; :disabled="page >= totalPages" ; @click="$emit('setPage', page + 1)" |

表 frontend/src/components/DataQuality.vue#table-1（源码 107 行）列顺序；条件列/循环列按表达式展开：

| 序号 | 表头原文/表达式 | 条件/循环上下文 |
| --- | --- | --- |
| 1 | 日期 | v-show="!collapsed" |
| 2 | 日线 | v-show="!collapsed" |
| 3 | 指标 | v-show="!collapsed" |
| 4 | 复权 | v-show="!collapsed" |
| 5 | 指数 | v-show="!collapsed" |
| 6 | 因子 | v-show="!collapsed" |
| 7 | 市场 | v-show="!collapsed" |
| 8 | 行业 | v-show="!collapsed" |
| 9 | 状态 | v-show="!collapsed" |
| 10 | 信号 | v-show="!collapsed" |
| 11 | 后验 | v-show="!collapsed" |

## frontend/src/components/DecisionPaperWorkbench.vue

脚本 SHA-256：`9154716f8e87a2b81cf5197229d3283bfc66b9fbe2da200c25707a12c1b66059`。

| ID / 行 | 元素与文案 / 标签 | 显示、分支与循环上下文 | 原属性、事件、禁用与数据绑定 |
| --- | --- | --- | --- |
| DecisionPaperWorkbench-001 / 175 | button · (无子文本；见属性) | 组件内无额外条件 | aria-label="刷新" ; title="刷新" ; :disabled="busy &#124;&#124; loading" ; @click="error = ''; load()" |
| DecisionPaperWorkbench-002 / 175 | button · 新建账户 | 组件内无额外条件 | :disabled="!enabled &#124;&#124; busy" ; @click="modal = 'create'" |
| DecisionPaperWorkbench-003 / 179 | select · 选择账户 {{ item.name }} · {{ item.state }} | 组件内无额外条件 | v-model="accountId" ; :disabled="busy &#124;&#124; loading" ; @change="selectAccount" |
| DecisionPaperWorkbench-004 / 180 | button · 上一组账户 | v-if="accountOffset > 0" | v-if="accountOffset > 0" ; :disabled="busy &#124;&#124; loading" ; @click="accountOffset -= 20; load()" |
| DecisionPaperWorkbench-005 / 180 | button · 下一组账户 | v-if="accountOffset + 20 < accountTotal" | v-if="accountOffset + 20 < accountTotal" ; :disabled="busy &#124;&#124; loading" ; @click="accountOffset += 20; load()" |
| DecisionPaperWorkbench-006 / 181 | button · 激活 | v-if="account" → v-if="account.state === 'PAUSED'" | v-if="account.state === 'PAUSED'" ; :disabled="!enabled &#124;&#124; busy" ; @click="perform('activate', `/paper/accounts/${accountId}/activate`, {})" |
| DecisionPaperWorkbench-007 / 181 | button · 暂停 | v-if="account" → v-if="account.state === 'ACTIVE'" | v-if="account.state === 'ACTIVE'" ; :disabled="busy" ; @click="perform('pause', `/paper/accounts/${accountId}/pause`, {})" |
| DecisionPaperWorkbench-008 / 181 | button · 关闭账户 | v-if="account" → v-if="account.state !== 'CLOSED'" | v-if="account.state !== 'CLOSED'" ; :disabled="busy" ; @click="modal = 'close'" |
| DecisionPaperWorkbench-009 / 186 | button · {{ item.title }} | v-if="account" → v-for="item in [{ key: 'journal', title: '决策日志' }, { key: 'portfolio', title: '模拟组合' }, { key: 'ledger', title: '执行与账本' }, { key: 'review', title: '后验复盘' }]" | v-for="item in [{ key: 'journal', title: '决策日志' }, { key: 'portfolio', title: '模拟组合' }, { key: 'ledger', title: '执行与账本' }, { key: 'review', title: '后验复盘' }]" ; :key="item.key" ; :aria-current="tab === item.key ? 'page' : undefined" ; @click="switchTab(item.key as typeof tab)" |
| DecisionPaperWorkbench-010 / 187 | input · 信号日 | v-if="account" → v-if="tab === 'journal'" | v-model="signalDate" ; type="date" |
| DecisionPaperWorkbench-011 / 187 | button · 生成观察快照 | v-if="account" → v-if="tab === 'journal'" | :disabled="!enabled &#124;&#124; busy &#124;&#124; account.state === 'CLOSED'" ; @click="perform('observe', '/decisions/observations', { signal_date: signalDate, account_id: accountId }, `${accountId}:${signalDate}`)" |
| DecisionPaperWorkbench-012 / 189 | select · {{ item.signal_date }} · {{ item.id.slice(0, 8) }} | v-if="account" → v-if="tab === 'journal'" | v-model="selectedObservation" |
| DecisionPaperWorkbench-013 / 189 | button · 较新观察 | v-if="account" → v-if="tab === 'journal'" | :disabled="loading &#124;&#124; observationOffset === 0" ; @click="observationOffset -= 20; load()" |
| DecisionPaperWorkbench-014 / 189 | button · 更早观察 | v-if="account" → v-if="tab === 'journal'" | :disabled="loading &#124;&#124; observationOffset + 20 >= observationTotal" ; @click="observationOffset += 20; load()" |
| DecisionPaperWorkbench-015 / 190 | summary · 冻结理由与来源 | v-if="account" → v-if="tab === 'journal'" → v-for="row in candidates" | 原生默认行为 |
| DecisionPaperWorkbench-016 / 190 | button · 记录决策 | v-if="account" → v-if="tab === 'journal'" → v-for="row in candidates" | :disabled="!enabled &#124;&#124; busy &#124;&#124; account.state === 'CLOSED'" ; @click="openProposal(row)" |
| DecisionPaperWorkbench-017 / 191 | input · 开始 | v-if="account" → v-if="tab === 'journal'" | v-model="start" ; type="date" |
| DecisionPaperWorkbench-018 / 191 | input · 结束 | v-if="account" → v-if="tab === 'journal'" | v-model="end" ; type="date" |
| DecisionPaperWorkbench-019 / 191 | select · 全部 PENDING_REVIEW APPROVED REJECTED EXPIRED | v-if="account" → v-if="tab === 'journal'" | v-model="proposalState" |
| DecisionPaperWorkbench-020 / 191 | select · 全部 {{ item }} | v-if="account" → v-if="tab === 'journal'" | v-model="stage" |
| DecisionPaperWorkbench-021 / 191 | button · 筛选 | v-if="account" → v-if="tab === 'journal'" | :disabled="loading &#124;&#124; busy" ; @click="offset = 0; load()" |
| DecisionPaperWorkbench-022 / 192 | button · 人工审批 | v-if="account" → v-if="tab === 'journal'" → v-for="row in proposals" | :disabled="!enabled &#124;&#124; busy &#124;&#124; loading &#124;&#124; row.state !== 'PENDING_REVIEW' &#124;&#124; row.action === 'WATCH' &#124;&#124; account.state !== 'ACTIVE'" ; @click="openDecision(row, 'approve')" |
| DecisionPaperWorkbench-023 / 192 | button · 驳回 | v-if="account" → v-if="tab === 'journal'" → v-for="row in proposals" | :disabled="!enabled &#124;&#124; busy &#124;&#124; loading &#124;&#124; row.state !== 'PENDING_REVIEW' &#124;&#124; account.state === 'CLOSED'" ; @click="openDecision(row, 'reject')" |
| DecisionPaperWorkbench-024 / 192 | summary · 决策证据 | v-if="account" → v-if="tab === 'journal'" → v-for="row in proposals" | 原生默认行为 |
| DecisionPaperWorkbench-025 / 194 | summary · 冻结配置与金融摘要 | v-if="account" → v-if="tab === 'portfolio' && performance" | 原生默认行为 |
| DecisionPaperWorkbench-026 / 196 | select · 模拟委托 人工审批 执行尝试 模拟成交 资金与股数流水 日终持仓 日终净值 结算与复核状态 账户审计 | v-if="account" → v-if="tab === 'ledger'" | v-model="collection" ; @change="offset = 0; load()" |
| DecisionPaperWorkbench-027 / 196 | input · 估值日 | v-if="account" → v-if="tab === 'ledger'" → v-if="collection === 'positions'" | v-model="valuationDate" ; type="date" ; @change="offset = 0; load()" |
| DecisionPaperWorkbench-028 / 196 | input · 开始 | v-if="account" → v-if="tab === 'ledger'" | v-model="start" ; type="date" |
| DecisionPaperWorkbench-029 / 196 | input · 结束 | v-if="account" → v-if="tab === 'ledger'" | v-model="end" ; type="date" |
| DecisionPaperWorkbench-030 / 196 | button · 筛选 | v-if="account" → v-if="tab === 'ledger'" | :disabled="loading &#124;&#124; busy" ; @click="offset = 0; load()" |
| DecisionPaperWorkbench-031 / 200 | input · 复盘日 | v-if="account" → v-if="tab === 'review'" | v-model="valuationDate" ; type="date" |
| DecisionPaperWorkbench-032 / 200 | select · 1 个交易日 5 个交易日 20 个交易日 | v-if="account" → v-if="tab === 'review'" | v-model.number="reviewWindow" |
| DecisionPaperWorkbench-033 / 200 | button · 生成后验复盘 | v-if="account" → v-if="tab === 'review'" | :disabled="!enabled &#124;&#124; busy &#124;&#124; !valuationDate" ; @click="perform('review', `/paper/accounts/${accountId}/review-day`, { asof_date: valuationDate, window_days: reviewWindow }, `${accountId}:${valuationDate}:${reviewWindow}`)" |
| DecisionPaperWorkbench-034 / 201 | button · 上一页 | v-if="account" → v-if="tab !== 'portfolio'" | :disabled="busy &#124;&#124; loading &#124;&#124; offset === 0" ; @click="changePage(-1)" |
| DecisionPaperWorkbench-035 / 201 | button · 下一页 | v-if="account" → v-if="tab !== 'portfolio'" | :disabled="busy &#124;&#124; loading &#124;&#124; offset + 20 >= total" ; @click="changePage(1)" |
| DecisionPaperWorkbench-036 / 204 | button · 结算下一交易日 | v-if="account" | :disabled="!enabled &#124;&#124; busy &#124;&#124; account.state !== 'ACTIVE' &#124;&#124; !account.next_trade_date &#124;&#124; activeJobCount > 0" ; @click="perform('advance', `/paper/accounts/${accountId}/advance`, { trade_date: account.next_trade_date }, `${accountId}:${account.next_trade_date}`)" |
| DecisionPaperWorkbench-037 / 205 | button · (无子文本；见属性) | v-if="account" → v-for="job in jobs" → v-if="['QUEUED','RUNNING'].includes(job.status)" | v-if="['QUEUED','RUNNING'].includes(job.status)" ; aria-label="取消任务" ; :title="job.cancel_requested ? '取消处理中' : '取消模拟任务'" ; :disabled="!enabled &#124;&#124; busy &#124;&#124; job.cancel_requested" ; @click="perform('cancel-job', `/paper/accounts/${accountId}/jobs/${job.id}/cancel`, {}, job.id)" |
| DecisionPaperWorkbench-038 / 206 | button · (无子文本；见属性) | v-if="account" | aria-label="任务上一页" ; title="任务上一页" ; :disabled="busy &#124;&#124; loading &#124;&#124; jobOffset === 0" ; @click="jobOffset = Math.max(0, jobOffset - 20); load()" |
| DecisionPaperWorkbench-039 / 206 | button · (无子文本；见属性) | v-if="account" | aria-label="任务下一页" ; title="任务下一页" ; :disabled="busy &#124;&#124; loading &#124;&#124; jobOffset + 20 >= jobTotal" ; @click="jobOffset += 20; load()" |
| DecisionPaperWorkbench-040 / 210 | div · {{ modal === 'create' ? '新建模拟账户' : modal === 'proposal' ? '记录决策' : modal === 'approve' ? '人工审批' : modal === 'reject' ? '驳回决策' : '关闭账户' }} 取消 账户名称 初始资金 基准指数 最大持仓数 每日新开仓数 {{ item.title }} 创建 PAPER 账户 {{ candidate?.name }} · {{ candidate?.ts_code }} {{ candidate.risk_codes.join(' / ') }} 研究动作 仅观察 拟买入 拟减仓 拟退出 目标权重 研究备注 冻结研究报告 不绑定 {{ report.title }} 保存人工草案 {{ selectedProposal?.ts_code }} · {{ selectedProposal?.action }} PAPER 事后模拟，不连接证券账户；批准只生成待执行委托。 批准目标权重 {{ modal === 'reject' ? '驳回原因' : '审批备注' }} 单票上限 {{ account.config_snapshot_json.paper.risk.max_single_position_weight }} · 现金底线 {{ account.config_snapshot_json.paper.risk.min_cash_ratio }} 我已人工审阅冻结证据与风险，仅确认模拟委托 {{ modal === 'approve' ? '确认模拟委托' : '确认驳回' }} 关闭账户将取消待执行委托。历史成交、账本和净值永久保留，账户不能重新激活。 确认关闭账户 {{ error }} 提交中 | v-if="modal" | v-if="modal" ; @click.self="closeModal" |
| DecisionPaperWorkbench-041 / 211 | button · 取消 | v-if="modal" | :disabled="busy" ; @click="closeModal" |
| DecisionPaperWorkbench-042 / 212 | form · 账户名称 初始资金 基准指数 最大持仓数 每日新开仓数 {{ item.title }} 创建 PAPER 账户 | v-if="modal" → v-if="modal === 'create'" | v-if="modal === 'create'" ; @submit.prevent="create" |
| DecisionPaperWorkbench-043 / 212 | input · 账户名称 | v-if="modal" → v-if="modal === 'create'" | v-model="name" ; required ; maxlength="80" |
| DecisionPaperWorkbench-044 / 212 | input · 初始资金 | v-if="modal" → v-if="modal === 'create'" | v-model="cash" ; required ; inputmode="decimal" ; pattern="[0-9]+(\.[0-9]{1,4})?" |
| DecisionPaperWorkbench-045 / 212 | input · 基准指数 | v-if="modal" → v-if="modal === 'create'" | v-model="benchmark" ; required ; pattern="[0-9]{6}\.(SH&#124;SZ&#124;BJ)" |
| DecisionPaperWorkbench-046 / 212 | input · 最大持仓数 | v-if="modal" → v-if="modal === 'create'" → v-if="risk" | v-model.number="risk.max_positions" ; type="number" ; min="1" ; max="100" ; required |
| DecisionPaperWorkbench-047 / 212 | input · 每日新开仓数 | v-if="modal" → v-if="modal === 'create'" → v-if="risk" | v-model.number="risk.max_new_positions_per_day" ; type="number" ; min="1" ; :max="risk.max_positions" ; required |
| DecisionPaperWorkbench-048 / 212 | input · {{ item.title }} | v-if="modal" → v-if="modal === 'create'" → v-if="risk" → v-for="item in [{ key: 'max_single_position_weight', title: '单票上限' }, { key: 'min_cash_ratio', title: '现金底线' }, { key: 'max_sector_weight', title: '行业上限' }, { key: 'max_theme_weight', title: '题材上限' }, { key: 'max_daily_turnover', title: '每日换手上限' }]" | v-model="risk[item.key as keyof PaperRisk]" ; inputmode="decimal" ; required ; pattern="[0-9]+(\.[0-9]+)?" |
| DecisionPaperWorkbench-049 / 212 | button · 创建 PAPER 账户 | v-if="modal" → v-if="modal === 'create'" | :disabled="busy &#124;&#124; !enabled" |
| DecisionPaperWorkbench-050 / 213 | form · {{ candidate?.name }} · {{ candidate?.ts_code }} {{ candidate.risk_codes.join(' / ') }} 研究动作 仅观察 拟买入 拟减仓 拟退出 目标权重 研究备注 冻结研究报告 不绑定 {{ report.title }} 保存人工草案 | v-if="modal" → preceding branches: v-if="modal === 'create'" → v-else-if="modal === 'proposal'" | v-else-if="modal === 'proposal'" ; @submit.prevent="saveProposal" |
| DecisionPaperWorkbench-051 / 213 | select · 仅观察 拟买入 拟减仓 拟退出 | v-if="modal" → preceding branches: v-if="modal === 'create'" → v-else-if="modal === 'proposal'" | v-model="action" |
| DecisionPaperWorkbench-052 / 213 | input · 目标权重 | v-if="modal" → preceding branches: v-if="modal === 'create'" → v-else-if="modal === 'proposal'" → v-if="['PROPOSE_BUY', 'PROPOSE_REDUCE'].includes(action)" | v-model="weight" ; inputmode="decimal" ; required ; pattern="[0-9]+(\.[0-9]{1,8})?" |
| DecisionPaperWorkbench-053 / 213 | textarea · 研究备注 | v-if="modal" → preceding branches: v-if="modal === 'create'" → v-else-if="modal === 'proposal'" | v-model="note" ; maxlength="1000" |
| DecisionPaperWorkbench-054 / 213 | select · 不绑定 {{ report.title }} | v-if="modal" → preceding branches: v-if="modal === 'create'" → v-else-if="modal === 'proposal'" | v-model="reportId" |
| DecisionPaperWorkbench-055 / 213 | button · 保存人工草案 | v-if="modal" → preceding branches: v-if="modal === 'create'" → v-else-if="modal === 'proposal'" | :disabled="busy" |
| DecisionPaperWorkbench-056 / 214 | form · {{ selectedProposal?.ts_code }} · {{ selectedProposal?.action }} PAPER 事后模拟，不连接证券账户；批准只生成待执行委托。 批准目标权重 {{ modal === 'reject' ? '驳回原因' : '审批备注' }} 单票上限 {{ account.config_snapshot_json.paper.risk.max_single_position_weight }} · 现金底线 {{ account.config_snapshot_json.paper.risk.min_cash_ratio }} 我已人工审阅冻结证据与风险，仅确认模拟委托 {{ modal === 'approve' ? '确认模拟委托' : '确认驳回' }} | v-if="modal" → preceding branches: v-if="modal === 'create'" ; v-else-if="modal === 'proposal'" → v-else-if="modal === 'approve' &#124;&#124; modal === 'reject'" | v-else-if="modal === 'approve' &#124;&#124; modal === 'reject'" ; @submit.prevent="decide" |
| DecisionPaperWorkbench-057 / 214 | input · 批准目标权重 | v-if="modal" → preceding branches: v-if="modal === 'create'" ; v-else-if="modal === 'proposal'" → v-else-if="modal === 'approve' &#124;&#124; modal === 'reject'" → v-if="modal === 'approve'" | v-model="weight" ; inputmode="decimal" ; required ; pattern="[0-9]+(\.[0-9]{1,8})?" |
| DecisionPaperWorkbench-058 / 214 | textarea · {{ modal === 'reject' ? '驳回原因' : '审批备注' }} | v-if="modal" → preceding branches: v-if="modal === 'create'" ; v-else-if="modal === 'proposal'" → v-else-if="modal === 'approve' &#124;&#124; modal === 'reject'" | v-model="note" ; maxlength="1000" ; :required="modal === 'reject'" |
| DecisionPaperWorkbench-059 / 214 | input · 我已人工审阅冻结证据与风险，仅确认模拟委托 | v-if="modal" → preceding branches: v-if="modal === 'create'" ; v-else-if="modal === 'proposal'" → v-else-if="modal === 'approve' &#124;&#124; modal === 'reject'" → v-if="modal === 'approve'" | v-model="confirmed" ; type="checkbox" |
| DecisionPaperWorkbench-060 / 214 | button · {{ modal === 'approve' ? '确认模拟委托' : '确认驳回' }} | v-if="modal" → preceding branches: v-if="modal === 'create'" ; v-else-if="modal === 'proposal'" → v-else-if="modal === 'approve' &#124;&#124; modal === 'reject'" | :disabled="busy &#124;&#124; (modal === 'approve' && !confirmed)" |
| DecisionPaperWorkbench-061 / 215 | form · 关闭账户将取消待执行委托。历史成交、账本和净值永久保留，账户不能重新激活。 确认关闭账户 | v-if="modal" → preceding branches: v-if="modal === 'create'" ; v-else-if="modal === 'proposal'" ; v-else-if="modal === 'approve' &#124;&#124; modal === 'reject'" → v-else | v-else ; @submit.prevent="perform('close', `/paper/accounts/${accountId}/close`, {})" |
| DecisionPaperWorkbench-062 / 215 | button · 确认关闭账户 | v-if="modal" → preceding branches: v-if="modal === 'create'" ; v-else-if="modal === 'proposal'" ; v-else-if="modal === 'approve' &#124;&#124; modal === 'reject'" → v-else | :disabled="busy" |

## frontend/src/components/EvidenceArchivePanel.vue

脚本 SHA-256：`2dbd19f0c8097d7d33d371d032137af596348f866d23beaac5c8b9c99490ce69`。

| ID / 行 | 元素与文案 / 标签 | 显示、分支与循环上下文 | 原属性、事件、禁用与数据绑定 |
| --- | --- | --- | --- |
| EvidenceArchivePanel-001 / 86 | button · 从冻结证据复核 | v-if="reportId" | v-if="reportId" ; type="button" ; :disabled="busy &#124;&#124; loading &#124;&#124; !summary &#124;&#124; summary.archive_status === 'UNAVAILABLE'" ; @click="verify" |
| EvidenceArchivePanel-002 / 88 | button · 重试读取 | v-if="error" | type="button" ; :disabled="loading &#124;&#124; busy" ; @click="load()" |
| EvidenceArchivePanel-003 / 99 | summary · Manifest 与来源身份 | v-if="summary" → v-if="summary.manifest_id" | 原生默认行为 |
| EvidenceArchivePanel-004 / 105 | button · 查看冻结事实 | v-if="summary" → v-for="row in evidence" → v-if="reportId" | v-if="reportId" ; type="button" ; :disabled="busy" ; @click="openEvidence(row.evidence_id)" |
| EvidenceArchivePanel-005 / 108 | button · 更多证据 | v-if="summary" → v-if="evidence.length < total" | v-if="evidence.length < total" ; type="button" ; :disabled="loading" ; @click="load(true)" |
| EvidenceArchivePanel-006 / 110 | button · 关闭详情 | v-if="summary" → v-if="detail" | type="button" ; @click="detail = null" |

表 frontend/src/components/EvidenceArchivePanel.vue#table-1（源码 114 行）列顺序；条件列/循环列按表达式展开：

| 序号 | 表头原文/表达式 | 条件/循环上下文 |
| --- | --- | --- |
| 1 | Claim / 字段 | v-if="summary" → v-if="detail" |
| 2 | 冻结值 | v-if="summary" → v-if="detail" |
| 3 | 实体 / 日期 / 样本 | v-if="summary" → v-if="detail" |

## frontend/src/components/JobCenter.vue

脚本 SHA-256：`6420df346275ae5a6f06dda75e05621866753684a7a9ff36265ade61a893271b`。

| ID / 行 | 元素与文案 / 标签 | 显示、分支与循环上下文 | 原属性、事件、禁用与数据绑定 |
| --- | --- | --- | --- |
| JobCenter-001 / 44 | button · 拉取数据与任务 | 组件内无额外条件 | type="button" ; :aria-expanded="!collapsed" ; @click="$emit('toggle')" |
| JobCenter-002 / 51 | button · {{ submittingBasicInfo ? "提交中" : "同步基础信息" }} | 组件内无额外条件 | type="button" ; :disabled="submittingBasicInfo" ; @click="$emit('syncBasic')" |
| JobCenter-003 / 54 | form · 开始 结束 {{ submittingIngestion ? "提交中" : "拉取原始数据" }} | 组件内无额外条件 | @submit.prevent="$emit('submitBackfill')" |
| JobCenter-004 / 55 | input · 开始 | 组件内无额外条件 | :value="backfillStart" ; type="date" ; @input="updateStart" |
| JobCenter-005 / 56 | input · 结束 | 组件内无额外条件 | :value="backfillEnd" ; type="date" ; @input="updateEnd" |
| JobCenter-006 / 57 | button · {{ submittingIngestion ? "提交中" : "拉取原始数据" }} | 组件内无额外条件 | type="submit" ; :disabled="submittingIngestion" |

## frontend/src/components/LoginView.vue

脚本 SHA-256：`9c9468a6945da3c7a7ac4168e6015c27e90cdab3215b5674027b23f75ea60e6a`。

| ID / 行 | 元素与文案 / 标签 | 显示、分支与循环上下文 | 原属性、事件、禁用与数据绑定 |
| --- | --- | --- | --- |
| LoginView-001 / 30 | form · 空 空间 A 股机会研究工作台 用户名 密码 {{ error }} {{ submitting ? "登录中" : "登录" }} | 组件内无额外条件 | @submit.prevent="submit" |
| LoginView-002 / 32 | input · 用户名 | 组件内无额外条件 | v-model.trim="username" ; autocomplete="username" ; required |
| LoginView-003 / 33 | input · 密码 | 组件内无额外条件 | v-model="password" ; type="password" ; autocomplete="current-password" ; required |
| LoginView-004 / 35 | button · {{ submitting ? "登录中" : "登录" }} | 组件内无额外条件 | type="submit" ; :disabled="submitting" |

## frontend/src/components/OpportunityTable.vue

脚本 SHA-256：`29d9ba8df6f62a379e9784f3bd392319ca8f04222e3b7103df36b12fed28a739`。

| ID / 行 | 元素与文案 / 标签 | 显示、分支与循环上下文 | 原属性、事件、禁用与数据绑定 |
| --- | --- | --- | --- |
| — | 无直接操作控件 | 由父组件传值/插槽驱动 | 不新增操作 |

表 frontend/src/components/OpportunityTable.vue#table-1（源码 16 行）列顺序；条件列/循环列按表达式展开：

| 序号 | 表头原文/表达式 | 条件/循环上下文 |
| --- | --- | --- |
| 1 | 代码 |  |
| 2 | 名称 |  |
| 3 | 阶段 |  |
| 4 | Left | v-if="kind === 'left'" |
| 5 | Right | v-if="kind === 'right'" |
| 6 | Trend / Rank | v-if="kind === 'trend'" |
| 7 | 位置 / 风险 | v-if="kind === 'trend'" |
| 8 | RPS60 |  |
| 9 | 行业 |  |
| 10 | 题材 / Heat |  |
| 11 | 市场 |  |

## frontend/src/components/PaperFactsTable.vue

脚本 SHA-256：`a120dfd7be85398eb3e422ab9185c16378aaf4cb3482947a9842d69e46d2c76a`。

| ID / 行 | 元素与文案 / 标签 | 显示、分支与循环上下文 | 原属性、事件、禁用与数据绑定 |
| --- | --- | --- | --- |
| PaperFactsTable-001 / 14 | summary · 审计明细 | v-for="row in rows" | 原生默认行为 |

表 frontend/src/components/PaperFactsTable.vue#table-1（源码 12 行）列顺序；条件列/循环列按表达式展开：

| 序号 | 表头原文/表达式 | 条件/循环上下文 |
| --- | --- | --- |
| 1 | {{ column.title }} | v-for="column in columns" |
| 2 | 证据 |  |

## frontend/src/components/PaperPerformanceCharts.vue

脚本 SHA-256：`82f20a731e55d82bf3694cd031c0655ed5cfc40e065b26cc3888186db1d9a07d`。

| ID / 行 | 元素与文案 / 标签 | 显示、分支与循环上下文 | 原属性、事件、禁用与数据绑定 |
| --- | --- | --- | --- |
| PaperPerformanceCharts-001 / 44 | button · {{ item.title }} | v-for="item in [{ key: 'nav', title: '净值' }, { key: 'balance', title: '现金与持仓' }, { key: 'drawdown', title: '回撤' }, { key: 'cost', title: '成本' }]" | v-for="item in [{ key: 'nav', title: '净值' }, { key: 'balance', title: '现金与持仓' }, { key: 'drawdown', title: '回撤' }, { key: 'cost', title: '成本' }]" ; :key="item.key" ; role="tab" ; :aria-selected="mode === item.key" ; @click="mode = item.key as typeof mode" |
| PaperPerformanceCharts-002 / 49 | summary · 冻结数值 | 组件内无额外条件 | 原生默认行为 |
| PaperPerformanceCharts-003 / 49 | button · 上一页数值 | 组件内无额外条件 | :disabled="page === 0" ; @click="page--" |
| PaperPerformanceCharts-004 / 49 | button · 下一页数值 | 组件内无额外条件 | :disabled="(page + 1) * 20 >= performance.series.length" ; @click="page++" |

表 frontend/src/components/PaperPerformanceCharts.vue#table-1（源码 49 行）列顺序；条件列/循环列按表达式展开：

| 序号 | 表头原文/表达式 | 条件/循环上下文 |
| --- | --- | --- |
| 1 | 交易日 |  |
| 2 | 净值 |  |
| 3 | 基准 |  |
| 4 | 现金 |  |
| 5 | 持仓市值 |  |

## frontend/src/components/ReportSnapshotChart.vue

脚本 SHA-256：`3fdc7ec89fbdf12ea7a7bc53754121d2343e65a23cebd05c88500f4c02d6f1b3`。

| ID / 行 | 元素与文案 / 标签 | 显示、分支与循环上下文 | 原属性、事件、禁用与数据绑定 |
| --- | --- | --- | --- |
| — | 无直接操作控件 | 由父组件传值/插槽驱动 | 不新增操作 |

表 frontend/src/components/ReportSnapshotChart.vue#table-1（源码 73 行）列顺序；条件列/循环列按表达式展开：

| 序号 | 表头原文/表达式 | 条件/循环上下文 |
| --- | --- | --- |
| 1 | {{ column }} | v-for="column in chart.columns" |

## frontend/src/components/ResearchLab.vue

脚本 SHA-256：`2cfbffa1a35d4c20d793b23b086b9521638ba95d5f0c677c6930cc1694d3419a`。

| ID / 行 | 元素与文案 / 标签 | 显示、分支与循环上下文 | 原属性、事件、禁用与数据绑定 |
| --- | --- | --- | --- |
| ResearchLab-001 / 156 | form · 开始 结束 {{ loading ? "查询中" : "查询" }} {{ submitting ? "提交中" : "运行研究" }} | 组件内无额外条件 | @submit.prevent="refresh" |
| ResearchLab-002 / 157 | input · 开始 | 组件内无额外条件 | v-model="start" ; type="date" |
| ResearchLab-003 / 158 | input · 结束 | 组件内无额外条件 | v-model="end" ; type="date" |
| ResearchLab-004 / 159 | button · {{ loading ? "查询中" : "查询" }} | 组件内无额外条件 | type="submit" ; :disabled="loading" |
| ResearchLab-005 / 160 | button · {{ submitting ? "提交中" : "运行研究" }} | 组件内无额外条件 | type="button" ; :disabled="submitting" ; @click="submit" |
| ResearchLab-006 / 178 | button · {{ item.label }} | v-for="item in tabs" | v-for="item in tabs" ; :key="item.key" ; type="button" ; role="tab" ; :aria-selected="tab === item.key" ; :class="{ selected: tab === item.key }" ; @click="tab = item.key" |
| ResearchLab-007 / 183 | button · {{ days }} 日 | v-for="days in horizonOptions" | v-for="days in horizonOptions" ; :key="days" ; type="button" ; :class="{ selected: horizon === days }" ; @click="horizon = days" |

表 frontend/src/components/ResearchLab.vue#table-1（源码 192 行）列顺序；条件列/循环列按表达式展开：

| 序号 | 表头原文/表达式 | 条件/循环上下文 |
| --- | --- | --- |
| 1 | 分组 | v-for="(rows, index) in [primary, secondary, tertiary, context, fifth]" → v-if="titles[index]" |
| 2 | 事件 | v-for="(rows, index) in [primary, secondary, tertiary, context, fifth]" → v-if="titles[index]" |
| 3 | 成熟 | v-for="(rows, index) in [primary, secondary, tertiary, context, fifth]" → v-if="titles[index]" |
| 4 | 收益样本 | v-for="(rows, index) in [primary, secondary, tertiary, context, fifth]" → v-if="titles[index]" |
| 5 | 可执行收益 | v-for="(rows, index) in [primary, secondary, tertiary, context, fifth]" → v-if="titles[index]" |
| 6 | 净收益 | v-for="(rows, index) in [primary, secondary, tertiary, context, fifth]" → v-if="titles[index]" |
| 7 | 持仓市值收益 | v-for="(rows, index) in [primary, secondary, tertiary, context, fifth]" → v-if="titles[index]" |
| 8 | 最终可退出收益 | v-for="(rows, index) in [primary, secondary, tertiary, context, fifth]" → v-if="titles[index]" |
| 9 | 最终可退出净收益 | v-for="(rows, index) in [primary, secondary, tertiary, context, fifth]" → v-if="titles[index]" |
| 10 | 平均退出延迟 | v-for="(rows, index) in [primary, secondary, tertiary, context, fifth]" → v-if="titles[index]" |
| 11 | 真实延迟率 | v-for="(rows, index) in [primary, secondary, tertiary, context, fifth]" → v-if="titles[index]" |
| 12 | 最终退出成功率 | v-for="(rows, index) in [primary, secondary, tertiary, context, fifth]" → v-if="titles[index]" |
| 13 | 未解决退出率 | v-for="(rows, index) in [primary, secondary, tertiary, context, fifth]" → v-if="titles[index]" |
| 14 | 待观察退出率 | v-for="(rows, index) in [primary, secondary, tertiary, context, fifth]" → v-if="titles[index]" |
| 15 | 数据不完整率 | v-for="(rows, index) in [primary, secondary, tertiary, context, fifth]" → v-if="titles[index]" |
| 16 | 不可退出率 | v-for="(rows, index) in [primary, secondary, tertiary, context, fifth]" → v-if="titles[index]" |
| 17 | 超额 | v-for="(rows, index) in [primary, secondary, tertiary, context, fifth]" → v-if="titles[index]" |
| 18 | 胜率 | v-for="(rows, index) in [primary, secondary, tertiary, context, fifth]" → v-if="titles[index]" |
| 19 | MFE20 | v-for="(rows, index) in [primary, secondary, tertiary, context, fifth]" → v-if="titles[index]" |
| 20 | MAE20 | v-for="(rows, index) in [primary, secondary, tertiary, context, fifth]" → v-if="titles[index]" |
| 21 | S3@ {{ days }} | v-for="(rows, index) in [primary, secondary, tertiary, context, fifth]" → v-if="titles[index]" → v-if="(tab === 'left' &#124;&#124; tab === 'right') && index === 0" → v-for="days in [5, 10, 20]" |
| 22 | S4+@ {{ days }} | v-for="(rows, index) in [primary, secondary, tertiary, context, fifth]" → v-if="titles[index]" → v-if="(tab === 'left' &#124;&#124; tab === 'right') && index === 0" → v-for="days in [5, 10, 20]" |
| 23 | S5@ {{ days }} | v-for="(rows, index) in [primary, secondary, tertiary, context, fifth]" → v-if="titles[index]" → v-if="(tab === 'left' &#124;&#124; tab === 'right') && index === 0" → v-for="days in [5, 10, 20]" |
| 24 | 跌回S3以下 | v-for="(rows, index) in [primary, secondary, tertiary, context, fifth]" → v-if="titles[index]" → v-if="tab === 'right' && index === 0" |
| 25 | S6@20 | v-for="(rows, index) in [primary, secondary, tertiary, context, fifth]" → v-if="titles[index]" → v-if="(tab === 'left' &#124;&#124; tab === 'right') && index === 0" |
| 26 | 到S3天数 | v-for="(rows, index) in [primary, secondary, tertiary, context, fifth]" → v-if="titles[index]" → v-if="tab === 'left' && index === 0" |
| 27 | 到S4+天数 | v-for="(rows, index) in [primary, secondary, tertiary, context, fifth]" → v-if="titles[index]" → v-if="(tab === 'left' &#124;&#124; tab === 'right') && index === 0" |
| 28 | 到S5天数 | v-for="(rows, index) in [primary, secondary, tertiary, context, fifth]" → v-if="titles[index]" → v-if="(tab === 'left' &#124;&#124; tab === 'right') && index === 0" |

## frontend/src/components/ResearchSummary.vue

脚本 SHA-256：`d7884d1439a1fa10096e22fec8fbfb6de7e2b15c366116a2516d2613d440d1a4`。

| ID / 行 | 元素与文案 / 标签 | 显示、分支与循环上下文 | 原属性、事件、禁用与数据绑定 |
| --- | --- | --- | --- |
| — | 无直接操作控件 | 由父组件传值/插槽驱动 | 不新增操作 |

## frontend/src/components/SectorHeat.vue

脚本 SHA-256：`923d6ed3c5623fa6ae16151f6a5c4cb94dec5e368d86d4677f1db92e6b717ad2`。

| ID / 行 | 元素与文案 / 标签 | 显示、分支与循环上下文 | 原属性、事件、禁用与数据绑定 |
| --- | --- | --- | --- |
| SectorHeat-001 / 24 | button · {{ row.name &#124;&#124; row.sector_name &#124;&#124; row.sector_id }} | v-for="row in rows" | type="button" ; title="带入智能研究" ; @click="$emit('research', { view: 'long', sector_id: String(row.sector_id), trade_date: row.trade_date, source_tool: 'ui.sector_heat' })" |

## frontend/src/components/StockPool.vue

脚本 SHA-256：`2e3778166f551e0ce7cf6d1d5a9ea60c5545ccfbe8fb5d90e66beb808b2408cb`。

| ID / 行 | 元素与文案 / 标签 | 显示、分支与循环上下文 | 原属性、事件、禁用与数据绑定 |
| --- | --- | --- | --- |
| StockPool-001 / 41 | button · {{ row.ts_code }} | v-for="row in rows" | type="button" ; @click="$emit('select', row)" |
| StockPool-002 / 52 | button · ↗ | v-for="row in rows" | type="button" ; title="带入智能研究" ; @click="$emit('research', { view: 'long', ts_code: row.ts_code, trade_date: row.trade_date, source_tool: 'ui.stock_pool' })" |

表 frontend/src/components/StockPool.vue#table-1（源码 31 行）列顺序；条件列/循环列按表达式展开：

| 序号 | 表头原文/表达式 | 条件/循环上下文 |
| --- | --- | --- |
| 1 | 代码 |  |
| 2 | 名称 |  |
| 3 | 状态 |  |
| 4 | 机会 |  |
| 5 | 右侧 |  |
| 6 | 趋势 |  |
| 7 | 行业 |  |
| 8 | 原因 |  |
| 9 | 研究 |  |

## frontend/src/components/ThemeDetail.vue

脚本 SHA-256：`d63d3cd26d4379c0672adabbfa9273d3c33494cafded118076e3c9e754cbbebd`。

| ID / 行 | 元素与文案 / 标签 | 显示、分支与循环上下文 | 原属性、事件、禁用与数据绑定 |
| --- | --- | --- | --- |
| ThemeDetail-001 / 9 | div · 题材详情 {{ data?.theme?.name &#124;&#124; "加载中" }} × 加载中 成员口径使用历史快照 {{ data.member_context.member_context_mode === "INTERVAL_SNAPSHOT" ? "补充" : "" }} {{ data.member_context.source_snapshot_date &#124;&#124; "--" }} · {{ data.member_context.member_context_coverage == null ? "--" : `${(data.member_context.member_context_coverage * 100).toFixed(1)}%` }} Heat {{ data.factor?.heat_score?.toFixed(1) &#124;&#124; "--" }} 阶段 {{ data.factor?.lifecycle &#124;&#124; "--" }} 成员覆盖 {{ data.factor?.eligible_member_count ?? "--" }} / {{ data.factor?.member_count ?? "--" }} 数据覆盖 {{ data.factor?.data_coverage == null ? "--" : `${(data.factor.data_coverage * 100).toFixed(0)}%` }} 成员状态 {{ row.stage }} {{ row.count }} 趋势成员 {{ row.name &#124;&#124; row.ts_code }} {{ row.state }} · {{ row.trend_rank_score?.toFixed(1) &#124;&#124; "--" }} | 组件内无额外条件 | @click.self="$emit('close')" |
| ThemeDetail-002 / 11 | button · × | 组件内无额外条件 | aria-label="关闭" ; @click="$emit('close')" |

## frontend/src/components/ThemeHeatTable.vue

脚本 SHA-256：`3a9c32c7b5d0ab31533392e9580733e5bc544c980a3894f3c1d436f2b77d8ccd`。

| ID / 行 | 元素与文案 / 标签 | 显示、分支与循环上下文 | 原属性、事件、禁用与数据绑定 |
| --- | --- | --- | --- |
| ThemeHeatTable-001 / 15 | tr · {{ row.heat_rank ?? "--" }} {{ row.name }} {{ formatNumber(row.heat_score, 1) }} {{ row.lifecycle &#124;&#124; "--" }} {{ formatNumber(row.heat_momentum3, 1) }} {{ formatNumber(row.rank_change, 0) }} {{ formatNumber(row.return1 == null ? null : row.return1 * 100, 2) }} % {{ formatNumber(row.net_amount, 0) }} {{ row.limit_up_count ?? "--" }} / {{ row.continuous_limit_count ?? "--" }} {{ formatNumber(row.breadth20 == null ? null : row.breadth20 * 100, 1) }} % {{ formatNumber(row.rps60_median, 1) }} | v-for="row in rows" | v-for="row in rows" ; :key="row.theme_code" ; @click="$emit('select', row)" |

表 frontend/src/components/ThemeHeatTable.vue#table-1（源码 12 行）列顺序；条件列/循环列按表达式展开：

| 序号 | 表头原文/表达式 | 条件/循环上下文 |
| --- | --- | --- |
| 1 | 排名 |  |
| 2 | 题材 |  |
| 3 | Heat |  |
| 4 | 阶段 |  |
| 5 | 3日变化 |  |
| 6 | 排名变化 |  |
| 7 | 涨跌 |  |
| 8 | 净流入 |  |
| 9 | 涨停/连板 |  |
| 10 | Breadth20 |  |
| 11 | RPS60 |  |

## frontend/src/components/UserMenu.vue

脚本 SHA-256：`bd799cdea7f6343ae80808daebf498067a78be9d2219c8b057aec319a256ffac`。

| ID / 行 | 元素与文案 / 标签 | 显示、分支与循环上下文 | 原属性、事件、禁用与数据绑定 |
| --- | --- | --- | --- |
| UserMenu-001 / 11 | button · {{ username }} | 组件内无额外条件 | type="button" ; @click="open = !open" |
| UserMenu-002 / 13 | button · 修改密码 | v-if="open" | type="button" ; @click="emit('changePassword'); open = false" |
| UserMenu-003 / 14 | button · 退出登录 | v-if="open" | type="button" ; @click="emit('logout'); open = false" |

## frontend/src/components/WalkForwardEvidenceView.vue

脚本 SHA-256：`aa6465f32b6c5e970874882c9cf1891797ef2b559af13451848f9b45959300fd`。

| ID / 行 | 元素与文案 / 标签 | 显示、分支与循环上下文 | 原属性、事件、禁用与数据绑定 |
| --- | --- | --- | --- |
| WalkForwardEvidenceView-001 / 92 | button · 返回智能研究 | 组件内无额外条件 | type="button" ; @click="$emit('back')" |
