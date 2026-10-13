<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { ResearchNavigationContext } from "../services/agent";
import ReportSnapshotChart from "./ReportSnapshotChart.vue";
import EvidenceArchivePanel from "./EvidenceArchivePanel.vue";

import {
  archiveResearchReport,
  createReportComparison,
  createResearchReport,
  downloadResearchReport,
  downloadReportComparison,
  fetchResearchReport,
  fetchResearchReports,
  type ReportComparison,
  type ReportSourceSelection,
  type ReportType,
  type ResearchReport,
  type ResearchReportSummary,
  type ResearchComparisonMode
} from "../services/agentReports";

const props = defineProps<{ initialSource?: ReportSourceSelection | null }>();
const emit = defineEmits<{ navigate: [target: ResearchNavigationContext] }>();
const reports = ref<ResearchReportSummary[]>([]);
const reportTotal = ref(0);
const reportLimit = 20;
const selected = ref<ResearchReport | null>(null);
const comparison = ref<ReportComparison | null>(null);
const loading = ref(true);
const working = ref(false);
const comparing = ref(false);
const error = ref("");
const includeArchived = ref(false);
const reportFilter = ref<ReportType | "">("");
const sourceChatId = ref("");
const sourceMessageId = ref("");
const reportType = ref<ReportType>("market_review");
const title = ref("");
const leftReportId = ref("");
const rightReportId = ref("");
const comparisonMode = ref<ResearchComparisonMode>("AUTO");
const pendingCreate = ref<{ fingerprint: string; requestId: string } | null>(null);
const pendingComparison = ref<{ fingerprint: string; requestId: string } | null>(null);
let reportGeneration = 0;
let listGeneration = 0, comparisonGeneration = 0;
let reportController = new AbortController(), listController = new AbortController(), comparisonController = new AbortController();
onBeforeUnmount(() => {
  reportGeneration++; listGeneration++; comparisonGeneration++;
  reportController.abort(); listController.abort(); comparisonController.abort();
});

const claimsById = computed(() =>
  new Map((selected.value?.snapshot.claims || []).map((claim) => [claim.claim_id, claim]))
);
// Frozen result is audit data, never a UI fallback (including older API responses).
const comparisonDisplay = computed(() => comparison.value?.display_result);
const deltaAllowed = computed(() => comparison.value?.state === "COMPARABLE"
  && ["m16.5-report-comparison-v3", "m16.6-report-comparison-v4"].includes(comparison.value?.policy_version || "")
  && comparison.value?.display_safety?.legacy_policy === false
  && comparison.value?.display_safety?.delta_allowed === true
  && (comparison.value?.policy_version !== "m16.6-report-comparison-v4"
    || comparisonDisplay.value?.comparison_permissions?.allowed === true));
const windowComparison = computed(() => comparisonDisplay.value?.comparison_mode === "WINDOW_DEGRADATION");
function pairAllowed(fact: NonNullable<ReportComparison["result"]["facts"]>[number]) {
  return deltaAllowed.value && fact.pair_status === "COMPARABLE"
    && (comparison.value?.policy_version !== "m16.6-report-comparison-v4"
      || (fact.comparison_permission?.allowed === true
        && ["RIGHT_MINUS_LEFT", "TRAIN_MINUS_OOS", "OOS_MINUS_TRAIN"].includes(fact.formula || "")));
}
function formulaLabel(formula?: string) {
  return ({ RIGHT_MINUS_LEFT: "右 − 左", TRAIN_MINUS_OOS: "TRAIN − OOS", OOS_MINUS_TRAIN: "OOS − TRAIN" } as Record<string, string>)[formula || ""] || "右 − 左";
}
function sampleRange(side: string) {
  const value = comparisonDisplay.value?.sample_context?.[side];
  if (!value || typeof value !== "object") return "";
  const sample = value as Record<string, unknown>;
  return `${sample.start_date || '--'} 至 ${sample.end_date || '--'} · ${sample.trade_days ?? '--'} 个交易日`;
}
watch(() => [leftReportId.value, rightReportId.value, comparisonMode.value], () => {
  comparisonGeneration++; comparisonController.abort(); comparing.value = false; comparison.value = null;
});

watch(
  () => props.initialSource,
  (source) => {
    if (!source) return;
    sourceChatId.value = source.chatId;
    sourceMessageId.value = source.messageId;
  },
  { immediate: true, deep: true }
);

onMounted(() => loadReports());

async function loadReports(reset = true) {
  const current = ++listGeneration;
  listController.abort(); listController = new AbortController();
  if (reset) loading.value = true;
  error.value = "";
  try {
    const offset = reset ? 0 : reports.value.length;
    const page = await fetchResearchReports(
      reportLimit,
      offset,
      includeArchived.value,
      reportFilter.value || undefined,
      listController.signal
    );
    if (current !== listGeneration) return;
    reports.value = reset ? page.data : [...reports.value, ...page.data];
    reportTotal.value = page.meta.total;
    if (selected.value) {
      const current = reports.value.find((row) => row.report_id === selected.value?.report_id);
      if (!current && !includeArchived.value) selected.value = null;
    }
  } catch (value) {
    if (current === listGeneration) error.value = errorText(value);
  } finally {
    if (reset && current === listGeneration) loading.value = false;
  }
}

async function openReport(reportId: string) {
  const current = ++reportGeneration;
  reportController.abort(); reportController = new AbortController();
  selected.value = null;
  error.value = "";
  try {
    const report = await fetchResearchReport(reportId, reportController.signal);
    if (current === reportGeneration) selected.value = report;
  } catch (value) {
    if (current === reportGeneration) error.value = errorText(value);
  }
}

async function createReport() {
  if (!sourceChatId.value || !sourceMessageId.value) return;
  working.value = true;
  reportGeneration++;
  error.value = "";
  try {
    const fingerprint = JSON.stringify([
      sourceChatId.value,
      sourceMessageId.value,
      reportType.value,
      title.value.trim()
    ]);
    if (pendingCreate.value?.fingerprint !== fingerprint) {
      pendingCreate.value = { fingerprint, requestId: newRequestId() };
    }
    selected.value = await createResearchReport({
      source_chat_id: sourceChatId.value,
      source_message_id: sourceMessageId.value,
      report_type: reportType.value,
      request_id: pendingCreate.value.requestId,
      title: title.value.trim() || undefined
    });
    title.value = "";
    pendingCreate.value = null;
    await loadReports();
  } catch (value) {
    error.value = errorText(value);
  } finally {
    working.value = false;
  }
}

async function archiveSelected() {
  if (!selected.value) return;
  working.value = true;
  try {
    selected.value = await archiveResearchReport(selected.value.report_id);
    await loadReports();
  } catch (value) {
    error.value = errorText(value);
  } finally {
    working.value = false;
  }
}

async function compareReports() {
  if (!leftReportId.value || !rightReportId.value || leftReportId.value === rightReportId.value) return;
  const current = ++comparisonGeneration;
  comparisonController.abort(); comparisonController = new AbortController();
  comparing.value = true;
  error.value = "";
  try {
    const fingerprint = `${leftReportId.value}:${rightReportId.value}:${comparisonMode.value}`;
    if (pendingComparison.value?.fingerprint !== fingerprint) {
      pendingComparison.value = { fingerprint, requestId: newRequestId() };
    }
    const mode = comparisonMode.value;
    const result = await createReportComparison({
      left_report_id: leftReportId.value,
      right_report_id: rightReportId.value,
      request_id: pendingComparison.value.requestId,
      ...(mode === "AUTO" ? {} : {
        comparison_mode: mode,
        comparison_intent: mode === "WINDOW_DEGRADATION" ? "TRAIN_VS_OOS" as const : "INDEPENDENT_BACKTESTS" as const
      })
    }, comparisonController.signal);
    if (current !== comparisonGeneration) return;
    comparison.value = result;
    pendingComparison.value = null;
  } catch (value) {
    if (current === comparisonGeneration) error.value = errorText(value);
  } finally {
    if (current === comparisonGeneration) comparing.value = false;
  }
}

async function downloadComparison(format: "markdown" | "html") {
  if (!comparison.value) return;
  try { await downloadReportComparison(comparison.value.comparison_id, format); }
  catch (value) { error.value = errorText(value); }
}

async function download(format: "markdown" | "html") {
  if (!selected.value) return;
  error.value = "";
  try {
    await downloadResearchReport(selected.value.report_id, format);
  } catch (value) {
    error.value = errorText(value);
  }
}

function newRequestId() {
  return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function errorText(value: unknown) {
  return value instanceof Error ? value.message : "操作失败";
}
</script>

<template>
  <section class="report-workbench">
    <header class="report-header">
      <div><h2>研究报告</h2><p>基于已验证结论生成的不可变证据快照</p></div>
      <div class="report-filters"><select v-model="reportFilter" aria-label="报告类型筛选" @change="loadReports()"><option value="">全部类型</option><option value="market_review">市场复盘</option><option value="opportunity_review">机会复盘</option><option value="strategy_review">策略复盘</option><option value="oos_review">样本外验证复盘</option></select><label class="archive-toggle"><input v-model="includeArchived" type="checkbox" @change="loadReports()" />显示已归档</label></div>
    </header>
    <div v-if="error" class="report-error" role="alert">{{ error }}</div>

    <section class="report-create panel-box">
      <div><strong>从研究回答生成</strong><small>不调用模型，不重跑工具，仅冻结已保存的 claims 与 citations</small></div>
      <label>会话 ID<input v-model.trim="sourceChatId" placeholder="从智能研究消息带入" /></label>
      <label>消息 ID<input v-model.trim="sourceMessageId" placeholder="助手消息 UUID" /></label>
      <label>报告类型<select v-model="reportType"><option value="market_review">市场复盘</option><option value="opportunity_review">机会复盘</option><option value="strategy_review">策略复盘</option><option value="oos_review">样本外验证复盘</option></select></label>
      <label>标题<input v-model.trim="title" placeholder="可选，默认按类型与日期生成" /></label>
      <button type="button" :disabled="working || !sourceChatId || !sourceMessageId" @click="createReport">生成报告</button>
    </section>

    <div class="report-layout">
      <aside class="report-list panel-box">
        <div class="pane-title"><strong>报告列表</strong><span>{{ reports.length }} / {{ reportTotal }}</span></div>
        <div v-if="loading" class="report-empty">正在加载</div>
        <button v-for="report in reports" :key="report.report_id" type="button" :class="{ active: selected?.report_id === report.report_id }" @click="openReport(report.report_id)">
          <strong>{{ report.title }}</strong><span>{{ report.as_of_date || "日期未提供" }} · {{ report.report_type }}</span><small>{{ report.archived_at ? "已归档" : report.source_answer_status }} · 来源 {{ report.source_chat_id }}</small>
        </button>
        <div v-if="!loading && !reports.length" class="report-empty">暂无研究报告</div>
        <button v-if="reports.length < reportTotal" type="button" class="load-more" @click="loadReports(false)">加载更多</button>
      </aside>

      <main class="report-detail panel-box">
        <div v-if="!selected" class="report-empty">选择报告查看冻结快照</div>
        <template v-else>
          <header class="detail-title"><div><small>{{ selected.report_type }} · {{ selected.report_version }}</small><h2>{{ selected.title }}</h2><p>{{ selected.as_of_date || "日期未提供" }} · {{ selected.source_answer_status }}</p><small>来源 {{ selected.source_chat_id }} / {{ selected.source_message_id }}</small></div><div class="detail-actions"><button type="button" @click="download('markdown')">Markdown</button><button type="button" @click="download('html')">HTML</button><button v-if="!selected.archived_at" type="button" :disabled="working" @click="archiveSelected">归档</button></div></header>
          <div class="snapshot-meta"><code>{{ selected.snapshot_hash }}</code><span>{{ selected.source_contract.snapshot_level }}</span></div>
          <EvidenceArchivePanel :key="selected.report_id" :report-id="selected.report_id" :contract-reference="selected.snapshot.contract_reference" />
          <section v-for="section in selected.snapshot.sections" :key="section.section_id" class="report-section"><h3>{{ section.title }}</h3><p v-for="item in section.items || []" :key="item" class="section-item">{{ item }}</p><article v-for="claimId in section.claim_ids" :key="claimId"><template v-if="claimsById.get(claimId)"><strong>{{ claimsById.get(claimId)?.claim_type }}</strong><p>{{ claimsById.get(claimId)?.text }}</p><small>证据：{{ claimsById.get(claimId)?.evidence_ids.join(" / ") }}</small></template></article></section>
          <section v-if="selected.snapshot.charts.length" class="report-section"><h3>指标视图</h3><ReportSnapshotChart v-for="chart in selected.snapshot.charts" :key="`${selected.report_id}:${chart.chart_id}`" :chart="chart" :snapshot="selected.snapshot" /></section>
          <section class="report-section"><h3>证据索引</h3><div class="evidence-grid"><article v-for="citation in selected.snapshot.citations" :key="citation.evidence_id"><code>{{ citation.evidence_id }}</code><span>{{ citation.tool_name }}</span><small>{{ citation.entity_id }} · {{ citation.as_of_date || "日期未提供" }}</small><button v-if="citation.navigation" type="button" @click="emit('navigate', citation.navigation)">打开业务详情</button></article></div></section>
          <details><summary>限制、警告与未纳入主张</summary><p v-for="warning in selected.snapshot.warnings" :key="warning"><code>{{ warning }}</code></p><p v-for="claim in selected.snapshot.rejected_claims" :key="claim.claim_id"><code>{{ claim.claim_id }}</code> · {{ claim.reason_codes.join(" / ") }}</p></details>
        </template>
      </main>
    </div>

    <section class="report-compare panel-box">
      <div><strong>冻结快照比较</strong><small>只有 COMPARABLE 才显示 Decimal 差值</small></div>
      <select v-model="leftReportId"><option value="">选择左侧报告</option><option v-for="report in reports" :key="report.report_id" :value="report.report_id">{{ report.title }}</option></select>
      <select v-model="rightReportId"><option value="">选择右侧报告</option><option v-for="report in reports" :key="report.report_id" :value="report.report_id">{{ report.title }}</option></select>
      <select v-model="comparisonMode" aria-label="比较模式"><option value="AUTO">原事实口径</option><option value="STRICT_SAME_SAMPLE">同样本回测</option><option value="DIFFERENT_ASSUMPTIONS">假设敏感性</option><option value="WINDOW_DEGRADATION">窗口 TRAIN/OOS</option></select>
      <button type="button" :disabled="working || comparing || !leftReportId || !rightReportId || leftReportId === rightReportId" @click="compareReports">{{ comparing ? '比较中' : '比较' }}</button>
      <div v-if="comparison" class="comparison-result"><strong>{{ comparison.state }}</strong><span>{{ comparison.reason_codes.join(" / ") || "口径一致" }}</span>
        <p v-if="comparison.display_safety?.legacy_policy !== false" role="alert">旧版比较策略 · 差值已隐藏</p>
        <div class="comparison-actions"><button type="button" @click="downloadComparison('markdown')">导出比较 Markdown</button><button type="button" @click="downloadComparison('html')">导出比较 HTML</button></div>
        <div v-for="(check, side) in comparisonDisplay?.contract_check || {}" :key="side" class="comparison-checks"><strong>{{ side }}</strong><span>内容 {{ check.archive_integrity?.status || 'UNVERIFIABLE' }}</span><span>事实 {{ check.frozen_fact_recheck?.status || 'UNVERIFIABLE' }}</span><span>合同 {{ check.contract_integrity.status }}</span><span>口径 {{ check.contract_semantics.status }}</span><span>算法未重跑</span></div>
        <p v-if="windowComparison">窗口 {{ comparisonDisplay?.sample_context?.window_no }} · 训练 {{ comparisonDisplay?.sample_context?.train_start_date }} 至 {{ comparisonDisplay?.sample_context?.train_end_date }} · 样本外 {{ comparisonDisplay?.sample_context?.oos_start_date }} 至 {{ comparisonDisplay?.sample_context?.oos_end_date }}</p>
        <p v-else-if="sampleRange('left') || sampleRange('right')">左 {{ sampleRange('left') }} / 右 {{ sampleRange('right') }}</p>
        <p v-if="!deltaAllowed">当前仅并列展示事实，不输出差值或优劣排序。</p>
        <div class="table-scroll"><table><thead><tr><th>指标</th><th>{{ windowComparison ? 'TRAIN' : '左值' }}</th><th>{{ windowComparison ? 'OOS' : '右值' }}</th><th>逐项许可</th><th v-if="deltaAllowed">{{ windowComparison ? '窗口退化' : '授权差值' }}</th></tr></thead><tbody><tr v-for="fact in comparisonDisplay?.facts || []" :key="fact.metric_key"><td>{{ fact.metric_key }}</td><td>{{ fact.left }} <small>{{ fact.left_fact?.trade_date }} · {{ fact.left_fact?.metric_identity?.sample_role }}</small></td><td>{{ fact.right }} <small>{{ fact.right_fact?.trade_date }} · {{ fact.right_fact?.metric_identity?.sample_role }}</small></td><td>{{ fact.pair_status || '旧策略未逐项验证' }} {{ fact.decision_reason_codes?.join(' / ') }}</td><td v-if="deltaAllowed">{{ pairAllowed(fact) ? fact.delta ?? '--' : '--' }}<small v-if="pairAllowed(fact)">{{ formulaLabel(fact.formula) }} · {{ fact.left_fact?.metric_identity?.unit }}</small></td></tr></tbody></table></div>
        <details v-if="comparisonDisplay?.explain_reasons?.length"><summary>口径差异</summary><p v-for="row in comparisonDisplay.explain_reasons" :key="row.field">{{ row.field }}<code>{{ row.left }}</code><code>{{ row.right }}</code></p></details>
        <details v-if="comparisonDisplay?.contract_refs"><summary>比较合同身份</summary><div v-for="(refs, side) in comparisonDisplay.contract_refs" :key="side"><p v-for="ref in refs" :key="ref.contract_id">{{ side }} · {{ ref.role }} · {{ ref.subject_id }}<code>{{ ref.contract_hash }}</code></p></div></details>
        <div v-for="(facts, side) in comparisonDisplay?.unmatched_facts || {}" :key="side"><strong>{{ side }} · 未配对事实</strong><p v-for="(fact, index) in facts" :key="index">{{ fact.metric_identity.entity_id }} · {{ fact.metric_identity.metric_id }} · {{ fact.value }} {{ fact.metric_identity.unit }} · {{ fact.trade_date }} · {{ fact.metric_identity.sample_role }}</p></div>
        <div v-for="(facts, side) in comparisonDisplay?.context_facts || {}" :key="`context-${side}`"><strong>{{ side }} · 日期与标识上下文（不作差值）</strong><p v-for="(fact, index) in facts" :key="index">{{ fact.metric_identity.entity_id }} · {{ fact.metric_identity.metric_id }} · {{ fact.value }} · {{ fact.trade_date }} · {{ fact.metric_identity.sample_role }}</p></div>
        <p v-if="!comparisonDisplay">旧接口未提供安全展示投影。审计 result 不用于展示或绘图。</p>
      </div>
    </section>
  </section>
</template>

<style scoped>
.report-workbench { display: grid; gap: 12px; min-width: 0; }
.report-header, .detail-title, .pane-title, .report-filters { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.report-header h2, .report-header p, .detail-title h2, .detail-title p { margin: 0; }
.report-header p, .detail-title p, small { color: #64748b; }
.panel-box { border: 1px solid #d8e0e8; border-radius: 7px; background: #fff; }
.report-error { border: 1px solid #fecaca; border-radius: 6px; background: #fef2f2; padding: 10px; color: #b91c1c; }
.archive-toggle { display: flex; gap: 6px; color: #475569; font-size: 13px; }
.report-create { display: grid; grid-template-columns: 1.4fr 1fr 1fr 1fr 1fr auto; align-items: end; gap: 10px; padding: 12px; }
.report-create > div, .report-compare > div:first-child { display: grid; gap: 4px; }
label { display: grid; gap: 4px; color: #64748b; font-size: 12px; }
input, select, button { min-width: 0; max-width: 100%; min-height: 34px; box-sizing: border-box; border: 1px solid #cbd5e1; border-radius: 5px; background: #fff; padding: 0 9px; }
button { cursor: pointer; color: #1e293b; }
button:disabled { cursor: not-allowed; opacity: .5; }
.report-create > button, .report-compare > button { border-color: #111827; background: #111827; color: #fff; }
.report-layout { display: grid; grid-template-columns: 280px minmax(0, 1fr); gap: 12px; min-height: 560px; }
.report-list { overflow: hidden; }
.pane-title { padding: 12px; border-bottom: 1px solid #e2e8f0; }
.report-list > button { display: grid; width: 100%; gap: 5px; border: 0; border-bottom: 1px solid #e2e8f0; border-radius: 0; padding: 11px 12px; text-align: left; }
.report-list > button.active { background: #e8f0fb; box-shadow: inset 3px 0 #2563eb; }
.report-list > button.load-more { display: block; width: auto; margin: 10px auto; border: 1px solid #cbd5e1; border-radius: 5px; }
.report-list > button span { overflow: hidden; color: #475569; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.report-detail { min-width: 0; padding: 16px; }
.report-empty { padding: 30px 12px; color: #64748b; text-align: center; }
.detail-title { align-items: flex-start; border-bottom: 1px solid #e2e8f0; padding-bottom: 12px; }
.detail-actions { display: flex; flex-wrap: wrap; gap: 6px; }
.snapshot-meta { display: flex; justify-content: space-between; gap: 8px; margin-top: 10px; color: #64748b; font-size: 11px; }
.snapshot-meta code { min-width: 0; overflow: hidden; text-overflow: ellipsis; }
.report-section { margin-top: 18px; }
.report-section h3 { margin: 0 0 8px; }
.report-section > article { border-left: 3px solid #bfdbfe; margin-bottom: 8px; padding: 7px 10px; }
.report-section article p { margin: 4px 0; line-height: 1.5; }
.report-section article small, .report-section p, .detail-title small, .report-list small, .comparison-result p, .comparison-result span { overflow-wrap: anywhere; }
.section-item { margin: 5px 0; color: #475569; }
.report-chart { margin-top: 10px; }
.table-scroll { overflow-x: auto; margin-top: 7px; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th, td { border-bottom: 1px solid #e2e8f0; padding: 7px; text-align: left; white-space: nowrap; }
.evidence-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 7px; }
.evidence-grid article { display: grid; gap: 3px; border: 1px solid #e2e8f0; border-radius: 5px; padding: 8px; }
.evidence-grid code { overflow-wrap: anywhere; }
.report-compare { display: grid; grid-template-columns: 1.2fr 1fr 1fr 1fr auto; align-items: end; gap: 10px; padding: 12px; }
.comparison-result { grid-column: 1 / -1; display: grid; gap: 7px; border-top: 1px solid #e2e8f0; padding-top: 12px; }
.comparison-result > strong { width: fit-content; border-radius: 999px; padding: 3px 8px; }
.comparison-result > strong { background: #e2e8f0; color: #334155; }
.comparison-actions, .comparison-checks { display: flex; flex-wrap: wrap; gap: 8px 12px; }
.comparison-result code { display: block; overflow-wrap: anywhere; white-space: pre-wrap; }
@media (max-width: 1100px) { .report-create { grid-template-columns: repeat(2, minmax(0, 1fr)); } .report-create > div { grid-column: 1 / -1; } .report-compare { grid-template-columns: 1fr 1fr; } }
@media (max-width: 720px) { .report-create, .report-compare, .report-layout { grid-template-columns: 1fr; } .report-list { max-height: 260px; overflow-y: auto; } .evidence-grid { grid-template-columns: 1fr; } .detail-title { display: grid; } .snapshot-meta { display: grid; } }
</style>
