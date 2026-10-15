<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { ChevronLeft, ChevronRight, Plus, RefreshCw, Square } from "@lucide/vue";
import { ApiError } from "../services/api";
import { fetchResearchReports, type ResearchReportSummary } from "../services/agentReports";
import { clearPaperRequest, paperAccount, paperAccounts, paperJobs, paperPage, paperPerformance,
  paperRequestId, paperStatus, paperWrite, type PaperAccount, type PaperCandidate, type PaperFacts,
  type PaperJob, type PaperPerformance, type PaperRisk, type PaperStatus } from "../services/decisionPaper";
import PaperFactsTable from "./PaperFactsTable.vue";
import PaperPerformanceCharts from "./PaperPerformanceCharts.vue";

const props = withDefaults(defineProps<{ ownerId: string; visible?: boolean }>(), { visible: true });
const status = ref<PaperStatus | null>(null), accounts = ref<PaperAccount[]>([]), account = ref<PaperAccount | null>(null);
const accountId = ref(""), accountOffset = ref(0), accountTotal = ref(0);
const performance = ref<PaperPerformance | null>(null), jobs = ref<PaperJob[]>([]);
const jobOffset = ref(0), jobTotal = ref(0), activeJobCount = ref(0);
const observations = ref<PaperFacts[]>([]), selectedObservation = ref<PaperFacts | null>(null);
const observationOffset = ref(0), observationTotal = ref(0);
const proposals = ref<PaperFacts[]>([]), rows = ref<PaperFacts[]>([]), total = ref(0), offset = ref(0);
const tab = ref<"journal" | "portfolio" | "ledger" | "review">("journal");
const collection = ref("orders"), start = ref(""), end = ref(""), stage = ref(""), proposalState = ref("");
const signalDate = ref(""), valuationDate = ref(""), reviewWindow = ref(1);
const loading = ref(false), busy = ref(false), error = ref(""), notice = ref("");
const modal = ref<"create" | "proposal" | "approve" | "reject" | "close" | null>(null);
const candidate = ref<PaperCandidate | null>(null), selectedProposal = ref<PaperFacts | null>(null);
const name = ref(""), cash = ref("1000000"), benchmark = ref("000300.SH"), risk = ref<PaperRisk | null>(null);
const action = ref("WATCH"), weight = ref("0.08"), note = ref(""), confirmed = ref(false);
const reports = ref<ResearchReportSummary[]>([]), reportId = ref("");
let generation = 0, controller = new AbortController(), timer: ReturnType<typeof setTimeout> | null = null;

const enabled = computed(() => status.value?.enabled && status.value?.schema_ready);
const candidates = computed(() => (selectedObservation.value?.data.candidates || []) as PaperCandidate[]);
const columnSets: Record<string, { key: string; title: string }[]> = {
  orders: [{ key: "ts_code", title: "证券" }, { key: "side", title: "方向" }, { key: "quantity", title: "计划股数" }, { key: "scheduled_date", title: "模拟日期" }, { key: "status", title: "状态" }, { key: "reason_code", title: "阻断原因" }],
  fills: [{ key: "trade_date", title: "交易日" }, { key: "ts_code", title: "证券" }, { key: "side", title: "方向" }, { key: "quantity", title: "股数" }, { key: "simulated_price", title: "模拟价格" }, { key: "total_cost", title: "成本" }, { key: "cash_delta", title: "现金变化" }],
  ledger: [{ key: "trade_date", title: "交易日" }, { key: "entry_type", title: "类型" }, { key: "instrument", title: "证券" }, { key: "cash_delta", title: "现金变化" }, { key: "quantity_delta", title: "股数变化" }],
  positions: [{ key: "trade_date", title: "交易日" }, { key: "ts_code", title: "证券" }, { key: "quantity", title: "持仓股数" }, { key: "available_quantity", title: "可卖股数" }, { key: "avg_cost", title: "成本" }, { key: "close_price", title: "收盘价" }, { key: "unrealized_pnl", title: "未实现盈亏" }],
  reviews: [{ key: "asof_date", title: "复盘日" }, { key: "window_days", title: "交易日窗口" }, { key: "data.stage", title: "冻结阶段" }, { key: "data.action", title: "原动作" }, { key: "data.counterfactual", title: "反事实观察" }, { key: "data.forward_mark_return", title: "标记收益（非 NAV）" }, { key: "status", title: "评价状态" }],
  events: [{ key: "created_at", title: "时间" }, { key: "data.kind", title: "事件" }, { key: "data.trade_date", title: "交易日" }, { key: "data.reason_code", title: "原因" }, { key: "to_state", title: "账户状态" }],
  attempts: [{ key: "trade_date", title: "交易日" }, { key: "outcome", title: "结果" }, { key: "reason_code", title: "原因" }, { key: "execution_policy_version", title: "执行版本" }],
  approvals: [{ key: "event_at", title: "审批时间" }, { key: "decision", title: "人工动作" }, { key: "approved_target_weight", title: "批准权重" }, { key: "data.note", title: "备注" }, { key: "proposal_id", title: "决策编号" }],
  runs: [{ key: "trade_date", title: "交易日" }, { key: "phase", title: "结算阶段" }, { key: "status", title: "复核状态" }, { key: "error_code", title: "原因" }, { key: "source_hash", title: "冻结来源" }],
  days: [{ key: "trade_date", title: "交易日" }, { key: "cash", title: "现金" }, { key: "market_value", title: "持仓市值" }, { key: "total_assets", title: "资产" }, { key: "nav", title: "净值" }, { key: "benchmark_nav", title: "基准" }],
};
const columns = computed(() => columnSets[tab.value === "review" ? "reviews" : collection.value]);
const title = computed(() => ({ journal: "决策日志", portfolio: "模拟组合", ledger: "执行与账本", review: "后验复盘" })[tab.value]);
function errorText(value: unknown) { return value instanceof ApiError ? value.code : "NETWORK_OR_REQUEST_FAILED"; }
function requestId(operation: string, subject = accountId.value) { return paperRequestId(props.ownerId, operation, subject); }
function closeModal() { if (!busy.value) { modal.value = null; confirmed.value = false; } }
function percent(value: unknown) {
  if (typeof value !== "string" || !/^-?\d+(\.\d+)?$/.test(value)) return "--";
  const number = Number(value); return Number.isFinite(number) ? `${(number * 100).toFixed(2)}%` : "--";
}
function elapsed(job: PaperJob) {
  const finish = job.finished_at ? Date.parse(job.finished_at) : Date.now();
  const seconds = Math.max(0, Math.floor((finish - Date.parse(job.started_at)) / 1000));
  return Number.isFinite(seconds) ? `${Math.floor(seconds / 60)}分${seconds % 60}秒` : "--";
}

async function load() {
  if (!props.visible) return;
  const current = ++generation;
  controller.abort(); controller = new AbortController();
  if (timer) clearTimeout(timer);
  loading.value = true;
  try {
    const currentStatus = await paperStatus(controller.signal);
    if (generation !== current) return;
    status.value = currentStatus;
    signalDate.value ||= currentStatus.latest_raw_date || currentStatus.business_date;
    risk.value ||= { ...currentStatus.default_risk };
    if (!currentStatus.schema_ready) { accounts.value = []; account.value = null; return; }
    const list = await paperAccounts(accountOffset.value, controller.signal);
    if (generation !== current) return;
    accounts.value = list.data; accountTotal.value = list.meta.total;
    if (!accountId.value && list.data.length) accountId.value = list.data[0].id;
    if (!accountId.value) { account.value = null; return; }
    const selectedId = accountId.value;
    const [selected, summary, jobPage] = await Promise.all([
      paperAccount(selectedId, controller.signal), paperPerformance(selectedId, controller.signal),
      paperJobs(selectedId, controller.signal, jobOffset.value),
    ]);
    if (current !== generation || selectedId !== accountId.value) return;
    account.value = selected; performance.value = summary; jobs.value = jobPage.data;
    jobTotal.value = jobPage.meta.total;
    activeJobCount.value = jobPage.meta.active_count ?? jobPage.data.filter(job => ['QUEUED', 'RUNNING'].includes(job.status)).length;
    valuationDate.value ||= selected.latest_trade_date || "";
    if (tab.value === "journal") {
      const [snapshotPage, proposalPage] = await Promise.all([
        paperPage("observations", selectedId, { offset: observationOffset.value, start: start.value, end: end.value }, controller.signal),
        paperPage("proposals", selectedId, { offset: offset.value, start: start.value, end: end.value,
          stage: stage.value, state: proposalState.value }, controller.signal),
      ]);
      if (generation !== current) return;
      observations.value = snapshotPage.data; proposals.value = proposalPage.data; total.value = proposalPage.meta.total;
      observationTotal.value = snapshotPage.meta.total;
      selectedObservation.value = snapshotPage.data.find(row => row.id === selectedObservation.value?.id) || snapshotPage.data[0] || null;
    } else if (tab.value === "ledger" || tab.value === "review") {
      const kind = tab.value === "review" ? "reviews" : collection.value;
      const page = await paperPage(kind, selectedId, { offset: offset.value, start: start.value, end: end.value,
        ...(kind === "positions" && valuationDate.value ? { trade_date: valuationDate.value } : {}) }, controller.signal);
      if (generation !== current) return;
      rows.value = page.data; total.value = page.meta.total;
    }
  } catch (value) { if (current === generation) error.value = errorText(value); }
  finally {
    if (current === generation) {
      loading.value = false;
      if (props.visible && activeJobCount.value) timer = setTimeout(() => { if (!busy.value) void load(); }, 5000);
    }
  }
}
async function perform(operation: string, path: string, payload: Record<string, unknown>, subject = accountId.value) {
  if (busy.value) return;
  busy.value = true; error.value = ""; notice.value = "";
  try {
    const result = await paperWrite<PaperFacts | PaperJob>(path, { ...payload, request_id: requestId(operation, subject) });
    clearPaperRequest(props.ownerId, operation, subject);
    if (operation === "create") { accountId.value = result.id; name.value = ""; }
    if (operation === "observe") selectedObservation.value = null;
    modal.value = null; confirmed.value = false;
    notice.value = ["advance", "review"].includes(operation) ? "任务已入队，等待 Worker" : "已保存";
    await load();
  } catch (value) {
    error.value = errorText(value);
    await load(); // Only GETs reconcile a possibly lost POST response.
  } finally { busy.value = false; }
}
async function selectAccount() {
  offset.value = 0; selectedObservation.value = null; performance.value = null;
  observationOffset.value = 0;
  jobOffset.value = 0; jobTotal.value = 0; activeJobCount.value = 0;
  account.value = null; proposals.value = []; observations.value = []; rows.value = []; jobs.value = [];
  modal.value = null; selectedProposal.value = null;
  valuationDate.value = ""; error.value = ""; await load();
}
async function openProposal(row: PaperCandidate) {
  candidate.value = row; action.value = row.risk_codes.length ? "WATCH" : "PROPOSE_BUY";
  note.value = ""; reportId.value = ""; modal.value = "proposal";
  try { reports.value = (await fetchResearchReports(20, 0, false)).data; }
  catch (value) { reports.value = []; error.value = errorText(value); }
}
function saveProposal() {
  if (!candidate.value || !selectedObservation.value) return;
  const source = reports.value.find(report => report.report_id === reportId.value);
  const payload = { account_id: accountId.value, observation_id: selectedObservation.value.id,
    ts_code: candidate.value.ts_code, action: action.value,
    target_weight: ["WATCH", "PROPOSE_EXIT"].includes(action.value) ? "0" : weight.value, note: note.value,
    ...(source ? { source_report_id: source.report_id, source_report_hash: source.snapshot_hash } : {}) };
  void perform("propose", "/decisions/proposals", payload, `${selectedObservation.value.id}:${candidate.value.ts_code}:${action.value}`);
}
function openDecision(row: PaperFacts, decision: "approve" | "reject") {
  selectedProposal.value = row; modal.value = decision; confirmed.value = false;
  note.value = ""; weight.value = String(row.target_weight || "0");
}
function decide() {
  if (!selectedProposal.value || !modal.value || !["approve", "reject"].includes(modal.value)) return;
  if (modal.value === "approve" && !confirmed.value) return;
  void perform(modal.value, `/decisions/proposals/${selectedProposal.value.id}/${modal.value}`,
    modal.value === "approve" ? { target_weight: weight.value, confirmed: true, note: note.value }
      : { reason: note.value }, selectedProposal.value.id);
}
function switchTab(next: typeof tab.value) { tab.value = next; offset.value = 0; error.value = ""; void load(); }
function changePage(delta: number) { offset.value = Math.max(0, offset.value + delta * 20); void load(); }
function create() { if (name.value.trim() && risk.value) void perform("create", "/paper/accounts", {
  name: name.value.trim(), initial_cash: cash.value, benchmark_code: benchmark.value, risk: risk.value,
}, "new-account"); }
watch(() => props.visible, visible => { if (visible) void load(); else { generation++; controller.abort(); if (timer) clearTimeout(timer); } }, { immediate: true });
onBeforeUnmount(() => { generation++; controller.abort(); if (timer) clearTimeout(timer); });
</script>

<template>
  <div class="paper-workbench" :aria-busy="loading || busy">
    <header class="paper-heading"><div><h2>决策与模拟组合</h2><span class="paper-badge">PAPER · 事后模拟 · 非实盘 · 非收益承诺</span></div>
      <div class="paper-controls"><button aria-label="刷新" title="刷新" :disabled="busy || loading" @click="error = ''; load()"><RefreshCw :size="16" /></button><button class="paper-primary" :disabled="!enabled || busy" @click="modal = 'create'"><Plus :size="16" />新建账户</button></div></header>
    <p v-if="status && !status.schema_ready" class="paper-warning" role="status">PAPER 表结构尚未部署，需升级至 0053。</p>
    <p v-else-if="status && !status.enabled" class="paper-warning" role="status">PAPER 功能未启用，历史记录只读。</p>
    <p v-if="error" class="paper-error" role="alert">{{ error }}</p><p v-if="notice" class="paper-notice" role="status">{{ notice }}</p>
    <div class="paper-controls paper-account-picker"><label>模拟账户<select v-model="accountId" :disabled="busy || loading" @change="selectAccount"><option value="" disabled>选择账户</option><option v-for="item in accounts" :key="item.id" :value="item.id">{{ item.name }} · {{ item.state }}</option></select></label>
      <button v-if="accountOffset > 0" :disabled="busy || loading" @click="accountOffset -= 20; load()">上一组账户</button><button v-if="accountOffset + 20 < accountTotal" :disabled="busy || loading" @click="accountOffset += 20; load()">下一组账户</button>
      <template v-if="account"><span class="paper-account-state">{{ account.state }}</span><button v-if="account.state === 'PAUSED'" :disabled="!enabled || busy" @click="perform('activate', `/paper/accounts/${accountId}/activate`, {})">激活</button><button v-if="account.state === 'ACTIVE'" :disabled="busy" @click="perform('pause', `/paper/accounts/${accountId}/pause`, {})">暂停</button><button v-if="account.state !== 'CLOSED'" :disabled="busy" @click="modal = 'close'">关闭账户</button></template></div>
    <div v-if="loading && !account" class="paper-empty" role="status">加载中</div>
    <div v-else-if="!account" class="paper-empty">暂无模拟账户</div>
    <template v-if="account">
      <div class="paper-account-meta"><span>起始日 {{ account.first_trade_date }}</span><span>最近结算 {{ account.latest_trade_date || '--' }}</span><span>基准 {{ account.benchmark_code }}</span><span>初始资金 {{ account.initial_cash }}</span></div>
      <nav class="paper-tabs" aria-label="决策与模拟视图"><button v-for="item in [{ key: 'journal', title: '决策日志' }, { key: 'portfolio', title: '模拟组合' }, { key: 'ledger', title: '执行与账本' }, { key: 'review', title: '后验复盘' }]" :key="item.key" :aria-current="tab === item.key ? 'page' : undefined" @click="switchTab(item.key as typeof tab)">{{ item.title }}</button></nav>
      <section class="paper-section"><div class="paper-section-heading"><h3>{{ title }}</h3><div class="paper-controls" v-if="tab === 'journal'"><label>信号日<input v-model="signalDate" type="date" /></label><button class="paper-primary" :disabled="!enabled || busy || account.state === 'CLOSED'" @click="perform('observe', '/decisions/observations', { signal_date: signalDate, account_id: accountId }, `${accountId}:${signalDate}`)">生成观察快照</button></div></div>
        <template v-if="tab === 'journal'">
          <div class="paper-controls"><label>冻结观察<select v-model="selectedObservation"><option v-for="item in observations" :key="item.id" :value="item">{{ item.signal_date }} · {{ item.id.slice(0, 8) }}</option></select></label><button :disabled="loading || observationOffset === 0" @click="observationOffset -= 20; load()">较新观察</button><button :disabled="loading || observationOffset + 20 >= observationTotal" @click="observationOffset += 20; load()">更早观察</button></div>
          <div class="paper-candidates"><article v-for="row in candidates" :key="row.ts_code" class="paper-candidate"><div class="paper-candidate-title"><strong>{{ row.name }} <span>{{ row.ts_code }}</span></strong><b>{{ row.opportunity_score }}</b></div><div class="paper-candidate-meta"><span>{{ row.opportunity_stage }}</span><span>行业 {{ row.industry_sector_id ?? '--' }}</span><span>题材 {{ row.primary_theme_code || '--' }}</span></div><p v-if="row.risk_codes.length" class="paper-warning-text">{{ row.risk_codes.join(' / ') }}</p><details><summary>冻结理由与来源</summary><pre>{{ JSON.stringify(row, null, 2) }}</pre></details><button :disabled="!enabled || busy || account.state === 'CLOSED'" @click="openProposal(row)">记录决策</button></article><p v-if="!candidates.length" class="paper-empty">暂无冻结候选</p></div>
          <div class="paper-controls paper-filters"><label>开始<input v-model="start" type="date" /></label><label>结束<input v-model="end" type="date" /></label><label>状态<select v-model="proposalState"><option value="">全部</option><option>PENDING_REVIEW</option><option>APPROVED</option><option>REJECTED</option><option>EXPIRED</option></select></label><label>阶段<select v-model="stage"><option value="">全部</option><option v-for="item in ['LEFT_WATCH','LEFT_REVERSAL','RIGHT_SIDE_NEW','RIGHT_SIDE','TREND','STRONG_TREND']" :key="item">{{ item }}</option></select></label><button :disabled="loading || busy" @click="offset = 0; load()">筛选</button></div>
          <div class="paper-proposals"><article v-for="row in proposals" :key="row.id" class="paper-proposal"><div><strong>{{ row.ts_code }}</strong><span>{{ row.stage }} · {{ row.action }}</span><span>{{ row.state }} · 权重 {{ row.target_weight }}</span><small>截止 {{ row.expires_at }}</small></div><div class="paper-controls"><button :disabled="!enabled || busy || loading || row.state !== 'PENDING_REVIEW' || row.action === 'WATCH' || account.state !== 'ACTIVE'" @click="openDecision(row, 'approve')">人工审批</button><button :disabled="!enabled || busy || loading || row.state !== 'PENDING_REVIEW' || account.state === 'CLOSED'" @click="openDecision(row, 'reject')">驳回</button><details><summary>决策证据</summary><pre>{{ JSON.stringify(row, null, 2) }}</pre></details></div></article><p v-if="!proposals.length" class="paper-empty">暂无决策记录</p></div>
        </template>
        <template v-if="tab === 'portfolio' && performance"><div class="paper-metrics"><div v-for="metric in [{ label: '现金', value: performance.latest?.cash ?? account.initial_cash }, { label: '持仓市值', value: performance.latest?.market_value ?? '--' }, { label: '模拟资产', value: performance.latest?.total_assets ?? account.initial_cash }, { label: '模拟净值', value: performance.latest?.nav ?? '--' }, { label: '已实现盈亏', value: performance.realized_pnl }, { label: '未实现盈亏', value: performance.unrealized_pnl }, { label: '累计模拟收益', value: percent(performance.cumulative_return) }, { label: '最大回撤', value: percent(performance.maximum_drawdown) }, { label: '累计模拟成本', value: performance.cumulative_cost }]" :key="metric.label"><span>{{ metric.label }}</span><strong>{{ metric.value }}</strong></div></div><PaperPerformanceCharts :performance="performance" /><details><summary>冻结配置与金融摘要</summary><pre>{{ JSON.stringify({ configuration: account.config_snapshot_json, source_hash: performance.financial_source_hash }, null, 2) }}</pre></details></template>
        <template v-if="tab === 'ledger'">
          <div class="paper-controls paper-filters"><label>明细<select v-model="collection" @change="offset = 0; load()"><option value="orders">模拟委托</option><option value="approvals">人工审批</option><option value="attempts">执行尝试</option><option value="fills">模拟成交</option><option value="ledger">资金与股数流水</option><option value="positions">日终持仓</option><option value="days">日终净值</option><option value="runs">结算与复核状态</option><option value="events">账户审计</option></select></label><label v-if="collection === 'positions'">估值日<input v-model="valuationDate" type="date" @change="offset = 0; load()" /></label><label>开始<input v-model="start" type="date" /></label><label>结束<input v-model="end" type="date" /></label><button :disabled="loading || busy" @click="offset = 0; load()">筛选</button></div>
          <PaperFactsTable :rows="loading || error ? [] : rows" :columns="columns" :loading="loading" :failed="Boolean(error)" />
        </template>
        <div v-if="tab === 'review' && performance?.decision_metrics" class="paper-attribution"><span>合法草案（含观察） {{ performance.decision_metrics.denominator.legal_proposals }} · 人工批准率 {{ percent(performance.decision_metrics.approval_rate) }}</span><span v-for="(value, state) in performance.decision_metrics.counts" :key="state">{{ state }} · {{ value }}</span><span>累计换手 {{ percent(performance.cumulative_turnover) }}</span></div>
        <template v-if="tab === 'review'"><div class="paper-controls paper-filters"><label>复盘日<input v-model="valuationDate" type="date" /></label><label>窗口<select v-model.number="reviewWindow"><option :value="1">1 个交易日</option><option :value="5">5 个交易日</option><option :value="20">20 个交易日</option></select></label><button :disabled="!enabled || busy || !valuationDate" @click="perform('review', `/paper/accounts/${accountId}/review-day`, { asof_date: valuationDate, window_days: reviewWindow }, `${accountId}:${valuationDate}:${reviewWindow}`)">生成后验复盘</button></div><p class="paper-warning-text">后验标记收益不计入 NAV；观察与驳回为反事实样本，不代表可成交或因果结论。</p><template v-if="performance"><div class="paper-attribution"><span>事后模拟成交 {{ performance.execution.filled_orders }}/{{ performance.execution.reached_orders }}</span><span>假设成交率 {{ percent(performance.execution.hypothetical_fill_rate) }}</span><span v-for="(value, reason) in performance.execution.blocked_reasons" :key="reason">{{ reason }} · {{ value }}</span><span v-for="(value, sourceStage) in performance.execution.stages" :key="sourceStage">{{ sourceStage }} · 成交 {{ value.filled }}/委托 {{ value.orders }}</span></div><div class="paper-attribution"><span v-for="(value, window) in performance.observation_metrics?.windows || {}" :key="window">观察 {{ window }} 日 · 有效 {{ value.valid_marks }}/{{ value.reviewed }} · 正收益 {{ value.positive_marks }} · 命中率 {{ percent(value.hit_rate) }}</span><span v-for="(value, sourceStage) in performance.stage_attribution?.groups || {}" :key="sourceStage">{{ sourceStage }} · 已实现 {{ value.realized_pnl }} · 未实现 {{ value.unrealized_pnl }} · 成本 {{ value.trading_cost }}</span></div></template><PaperFactsTable :rows="loading || error ? [] : rows" :columns="columns" :loading="loading" :failed="Boolean(error)" /></template>
        <footer v-if="tab !== 'portfolio'" class="paper-pagination"><span>{{ loading ? '加载中' : total ? `${total} 条 · ${offset + 1}–${Math.min(offset + 20, total)}` : '0 条' }}</span><button :disabled="busy || loading || offset === 0" @click="changePage(-1)">上一页</button><button :disabled="busy || loading || offset + 20 >= total" @click="changePage(1)">下一页</button></footer>
      </section>
      <section class="paper-section paper-run-section">
        <div class="paper-section-heading"><h3>模拟任务</h3><div class="paper-controls"><span>下一结算 {{ account.next_trade_date || '--' }}</span><button :disabled="!enabled || busy || account.state !== 'ACTIVE' || !account.next_trade_date || activeJobCount > 0" @click="perform('advance', `/paper/accounts/${accountId}/advance`, { trade_date: account.next_trade_date }, `${accountId}:${account.next_trade_date}`)">结算下一交易日</button></div></div>
        <div class="paper-job-list"><article v-for="job in jobs" :key="job.id"><div><strong>{{ ({ PAPER_DAILY: '日终结算', PAPER_REVIEW: '后验复盘', PAPER_OBSERVATION: '规则观察' } as Record<string, string>)[job.job_type] || '模拟任务' }} · {{ job.trade_date }}</strong><div class="paper-controls"><span>{{ job.status }} · {{ elapsed(job) }}</span><button v-if="['QUEUED','RUNNING'].includes(job.status)" aria-label="取消任务" :title="job.cancel_requested ? '取消处理中' : '取消模拟任务'" :disabled="!enabled || busy || job.cancel_requested" @click="perform('cancel-job', `/paper/accounts/${accountId}/jobs/${job.id}/cancel`, {}, job.id)"><Square :size="14" /></button></div></div><progress v-if="['QUEUED','RUNNING'].includes(job.status)" :value="job.progress_pct" max="100" /><span>{{ ({ queued: '等待执行', source: '核验盘后数据', execution: '模拟执行与记账', close: '日终估值与对账', committing: '提交完整日账', success: '任务完成', failed: '任务失败，需手动重试', cancelled: '任务已取消' } as Record<string, string>)[job.stage || ''] || job.step }}</span><p v-if="job.error_code" class="paper-error">{{ job.error_code }}</p></article><p v-if="!jobs.length" class="paper-empty">暂无模拟任务</p></div>
        <footer class="paper-pagination"><span>{{ jobTotal }} 条 · 运行中 {{ activeJobCount }}</span><button aria-label="任务上一页" title="任务上一页" :disabled="busy || loading || jobOffset === 0" @click="jobOffset = Math.max(0, jobOffset - 20); load()"><ChevronLeft :size="16" /></button><button aria-label="任务下一页" title="任务下一页" :disabled="busy || loading || jobOffset + 20 >= jobTotal" @click="jobOffset += 20; load()"><ChevronRight :size="16" /></button></footer>
      </section>
    </template>

    <div v-if="modal" class="paper-modal-backdrop" @click.self="closeModal"><section class="paper-modal" role="dialog" aria-modal="true" :aria-label="modal === 'create' ? '新建模拟账户' : modal === 'proposal' ? '记录决策' : modal === 'approve' ? '人工审批' : modal === 'reject' ? '驳回决策' : '关闭账户'">
      <header><h3>{{ modal === 'create' ? '新建模拟账户' : modal === 'proposal' ? '记录决策' : modal === 'approve' ? '人工审批' : modal === 'reject' ? '驳回决策' : '关闭账户' }}</h3><button :disabled="busy" @click="closeModal">取消</button></header>
      <form v-if="modal === 'create'" @submit.prevent="create"><label>账户名称<input v-model="name" required maxlength="80" /></label><label>初始资金<input v-model="cash" required inputmode="decimal" pattern="[0-9]+(\.[0-9]{1,4})?" /></label><label>基准指数<input v-model="benchmark" required pattern="[0-9]{6}\.(SH|SZ|BJ)" /></label><div v-if="risk" class="paper-risk-form"><label>最大持仓数<input v-model.number="risk.max_positions" type="number" min="1" max="100" required /></label><label>每日新开仓数<input v-model.number="risk.max_new_positions_per_day" type="number" min="1" :max="risk.max_positions" required /></label><label v-for="item in [{ key: 'max_single_position_weight', title: '单票上限' }, { key: 'min_cash_ratio', title: '现金底线' }, { key: 'max_sector_weight', title: '行业上限' }, { key: 'max_theme_weight', title: '题材上限' }, { key: 'max_daily_turnover', title: '每日换手上限' }]" :key="item.key">{{ item.title }}<input v-model="risk[item.key as keyof PaperRisk]" inputmode="decimal" required pattern="[0-9]+(\.[0-9]+)?" /></label></div><button class="paper-primary" :disabled="busy || !enabled">创建 PAPER 账户</button></form>
      <form v-else-if="modal === 'proposal'" @submit.prevent="saveProposal"><strong>{{ candidate?.name }} · {{ candidate?.ts_code }}</strong><p v-if="candidate?.risk_codes.length" class="paper-warning-text">{{ candidate.risk_codes.join(' / ') }}</p><label>研究动作<select v-model="action"><option value="WATCH">仅观察</option><option value="PROPOSE_BUY">拟买入</option><option value="PROPOSE_REDUCE">拟减仓</option><option value="PROPOSE_EXIT">拟退出</option></select></label><label v-if="['PROPOSE_BUY', 'PROPOSE_REDUCE'].includes(action)">目标权重<input v-model="weight" inputmode="decimal" required pattern="[0-9]+(\.[0-9]{1,8})?" /></label><label>研究备注<textarea v-model="note" maxlength="1000" /></label><label>冻结研究报告<select v-model="reportId"><option value="">不绑定</option><option v-for="report in reports" :key="report.report_id" :value="report.report_id">{{ report.title }}</option></select></label><button class="paper-primary" :disabled="busy">保存人工草案</button></form>
      <form v-else-if="modal === 'approve' || modal === 'reject'" @submit.prevent="decide"><strong>{{ selectedProposal?.ts_code }} · {{ selectedProposal?.action }}</strong><p class="paper-warning-text">PAPER 事后模拟，不连接证券账户；批准只生成待执行委托。</p><label v-if="modal === 'approve'">批准目标权重<input v-model="weight" inputmode="decimal" required pattern="[0-9]+(\.[0-9]{1,8})?" /></label><label>{{ modal === 'reject' ? '驳回原因' : '审批备注' }}<textarea v-model="note" maxlength="1000" :required="modal === 'reject'" /></label><p v-if="account">单票上限 {{ account.config_snapshot_json.paper.risk.max_single_position_weight }} · 现金底线 {{ account.config_snapshot_json.paper.risk.min_cash_ratio }}</p><label v-if="modal === 'approve'" class="paper-checkbox"><input v-model="confirmed" type="checkbox" />我已人工审阅冻结证据与风险，仅确认模拟委托</label><button class="paper-primary" :disabled="busy || (modal === 'approve' && !confirmed)">{{ modal === 'approve' ? '确认模拟委托' : '确认驳回' }}</button></form>
      <form v-else @submit.prevent="perform('close', `/paper/accounts/${accountId}/close`, {})"><p>关闭账户将取消待执行委托。历史成交、账本和净值永久保留，账户不能重新激活。</p><button class="paper-danger" :disabled="busy">确认关闭账户</button></form>
      <p v-if="error" role="alert" class="paper-error">{{ error }}</p><p v-if="busy" role="status">提交中</p>
    </section></div>
  </div>
</template>

<style scoped>
.paper-workbench { min-width: 0; display: grid; gap: 14px; color: #253342; }
h2, h3, p { margin: 0; } h2 { font-size: 19px; } h3 { font-size: 15px; } button, input, select, textarea { font: inherit; font-size: 12px; }
button { border: 1px solid #cdd6df; background: #fff; color: #354454; border-radius: 5px; min-height: 34px; padding: 6px 12px; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; gap: 6px; } button:disabled { opacity: .45; cursor: default; }
button.paper-primary { background: #087f72; border-color: #087f72; color: #fff; } button.paper-danger { color: #ad3030; border-color: #e9b9b9; }
input, select, textarea { border: 1px solid #cdd6df; background: #fff; padding: 7px 8px; border-radius: 4px; color: #253342; max-width: 100%; min-width: 0; }
input[type=date] { width: 142px; } textarea { min-height: 74px; resize: vertical; }
.paper-heading, .paper-section-heading, .paper-modal header { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
.paper-badge { color: #087f72; font-size: 11px; display: block; margin-top: 5px; }
.paper-controls { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; min-width: 0; }
label { display: flex; gap: 6px; align-items: center; color: #596675; font-size: 12px; min-width: 0; }
.paper-account-picker { padding: 12px 0; border-top: 1px solid #dce3e9; border-bottom: 1px solid #dce3e9; }
.paper-account-picker select { width: 260px; } .paper-account-state { font-size: 12px; font-weight: 600; }
.paper-account-meta { display: flex; flex-wrap: wrap; gap: 7px 20px; color: #697481; font-size: 12px; }
.paper-tabs { display: flex; flex-wrap: wrap; gap: 4px; border-bottom: 1px solid #dce3e9; } .paper-tabs button { border: 0; border-bottom: 2px solid transparent; background: transparent; border-radius: 0; min-height: 40px; } .paper-tabs button[aria-current] { border-color: #087f72; color: #087f72; font-weight: 600; }
.paper-section { min-width: 0; display: grid; gap: 14px; } .paper-filters { padding: 10px 0; border-bottom: 1px solid #dce3e9; }
.paper-candidates { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 270px), 1fr)); gap: 10px; }
.paper-candidate { border: 1px solid #dce3e9; border-radius: 6px; background: #fff; padding: 13px; display: grid; gap: 10px; min-width: 0; }
.paper-candidate-title { display: flex; justify-content: space-between; gap: 10px; font-size: 13px; } .paper-candidate-title strong span { color: #697481; font-weight: 400; display: block; margin-top: 4px; font-size: 12px; } .paper-candidate-title b { color: #087f72; }
.paper-candidate-meta, .paper-attribution { display: flex; flex-wrap: wrap; gap: 6px 12px; color: #697481; font-size: 11px; overflow-wrap: anywhere; }
.paper-warning, .paper-error, .paper-notice { padding: 8px 10px; border-left: 3px solid; background: #fff; font-size: 12px; overflow-wrap: anywhere; } .paper-warning, .paper-warning-text { color: #976515; } .paper-error { color: #b33232; } .paper-notice { color: #087f72; } .paper-warning-text { font-size: 12px; overflow-wrap: anywhere; }
.paper-proposal { border-bottom: 1px solid #dce3e9; padding: 12px 0; display: flex; gap: 16px; align-items: start; justify-content: space-between; } .paper-proposal > div:first-child { display: grid; gap: 5px; min-width: 0; } .paper-proposal strong { font-size: 13px; } .paper-proposal span, .paper-proposal small { color: #697481; font-size: 12px; overflow-wrap: anywhere; }
.paper-proposal .paper-controls { max-width: 60%; align-items: start; }
details { font-size: 11px; min-width: 0; overflow-wrap: anywhere; } summary { cursor: pointer; color: #087f72; } pre { white-space: pre-wrap; overflow-wrap: anywhere; max-height: 260px; overflow: auto; font-size: 11px; max-width: 100%; margin: 8px 0 0; }
.paper-empty { padding: 22px 0; color: #697481; font-size: 13px; text-align: center; }
.paper-metrics { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); border-top: 1px solid #dce3e9; border-bottom: 1px solid #dce3e9; } .paper-metrics > div { padding: 12px 8px; display: grid; gap: 5px; min-width: 0; } .paper-metrics span { font-size: 11px; color: #697481; } .paper-metrics strong { font-size: 15px; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
.paper-pagination { display: flex; justify-content: flex-end; gap: 8px; align-items: center; font-size: 12px; color: #697481; flex-wrap: wrap; }
.paper-run-section { border-top: 1px solid #dce3e9; padding-top: 16px; } .paper-job-list article { display: grid; gap: 6px; border-bottom: 1px solid #dce3e9; padding: 12px 0; font-size: 12px; min-width: 0; overflow-wrap: anywhere; } .paper-job-list article > div { display: flex; justify-content: space-between; gap: 10px; flex-wrap: wrap; } progress { width: 100%; height: 6px; accent-color: #087f72; }
.paper-modal-backdrop { position: fixed; inset: 0; z-index: 60; background: #13212b80; display: flex; justify-content: center; align-items: center; padding: 16px; }
.paper-modal { background: #fff; border-radius: 7px; padding: 20px; width: 520px; max-width: 100%; max-height: calc(100dvh - 32px); overflow: auto; box-shadow: 0 12px 40px #0002; min-width: 0; } .paper-modal form { display: grid; gap: 14px; margin-top: 18px; } .paper-modal form > label { display: grid; gap: 7px; } .paper-modal p { font-size: 12px; line-height: 1.6; overflow-wrap: anywhere; } .paper-modal .paper-checkbox { display: flex; align-items: start; } .paper-risk-form { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; } .paper-risk-form label { display: grid; gap: 6px; }
@media (max-width: 650px) { .paper-controls label { flex-wrap: wrap; } .paper-account-picker > label { display: grid; width: 100%; } .paper-account-picker select { width: 100%; } .paper-controls input, .paper-controls select { max-width: 100%; } .paper-proposal { display: grid; gap: 10px; } .paper-proposal .paper-controls { max-width: 100%; } .paper-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); } .paper-modal { padding: 15px; } .paper-risk-form { grid-template-columns: 1fr; } }
</style>
