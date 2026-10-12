<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import type { ResearchNavigationContext } from "../services/agent";

import {
  archiveResearchReport,
  createReportComparison,
  createResearchReport,
  downloadResearchReport,
  fetchResearchReport,
  fetchResearchReports,
  type ReportComparison,
  type ReportSourceSelection,
  type ReportType,
  type ResearchReport,
  type ResearchReportSummary
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
const error = ref("");
const includeArchived = ref(false);
const reportFilter = ref<ReportType | "">("");
const sourceChatId = ref("");
const sourceMessageId = ref("");
const reportType = ref<ReportType>("market_review");
const title = ref("");
const leftReportId = ref("");
const rightReportId = ref("");
const pendingCreate = ref<{ fingerprint: string; requestId: string } | null>(null);
const pendingComparison = ref<{ fingerprint: string; requestId: string } | null>(null);

const claimsById = computed(() =>
  new Map((selected.value?.snapshot.claims || []).map((claim) => [claim.claim_id, claim]))
);

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
  if (reset) loading.value = true;
  error.value = "";
  try {
    const offset = reset ? 0 : reports.value.length;
    const page = await fetchResearchReports(
      reportLimit,
      offset,
      includeArchived.value,
      reportFilter.value || undefined
    );
    reports.value = reset ? page.data : [...reports.value, ...page.data];
    reportTotal.value = page.meta.total;
    if (selected.value) {
      const current = reports.value.find((row) => row.report_id === selected.value?.report_id);
      if (!current && !includeArchived.value) selected.value = null;
    }
  } catch (value) {
    error.value = errorText(value);
  } finally {
    if (reset) loading.value = false;
  }
}

async function openReport(reportId: string) {
  error.value = "";
  try {
    selected.value = await fetchResearchReport(reportId);
  } catch (value) {
    error.value = errorText(value);
  }
}

async function createReport() {
  if (!sourceChatId.value || !sourceMessageId.value) return;
  working.value = true;
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
  working.value = true;
  error.value = "";
  try {
    const fingerprint = `${leftReportId.value}:${rightReportId.value}`;
    if (pendingComparison.value?.fingerprint !== fingerprint) {
      pendingComparison.value = { fingerprint, requestId: newRequestId() };
    }
    comparison.value = await createReportComparison({
      left_report_id: leftReportId.value,
      right_report_id: rightReportId.value,
      request_id: pendingComparison.value.requestId
    });
    pendingComparison.value = null;
  } catch (value) {
    error.value = errorText(value);
  } finally {
    working.value = false;
  }
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
          <section v-for="section in selected.snapshot.sections" :key="section.section_id" class="report-section"><h3>{{ section.title }}</h3><p v-for="item in section.items || []" :key="item" class="section-item">{{ item }}</p><article v-for="claimId in section.claim_ids" :key="claimId"><template v-if="claimsById.get(claimId)"><strong>{{ claimsById.get(claimId)?.claim_type }}</strong><p>{{ claimsById.get(claimId)?.text }}</p><small>证据：{{ claimsById.get(claimId)?.evidence_ids.join(" / ") }}</small></template></article></section>
          <section v-if="selected.snapshot.charts.length" class="report-section"><h3>指标视图</h3><div v-for="chart in selected.snapshot.charts" :key="chart.chart_id" class="report-chart"><strong>{{ chart.title }}</strong><div class="table-scroll"><table><thead><tr><th v-for="column in chart.columns" :key="column">{{ column }}</th></tr></thead><tbody><tr v-for="(row, index) in chart.rows" :key="index"><td v-for="(cell, cellIndex) in row" :key="cellIndex">{{ cell }}</td></tr></tbody></table></div></div></section>
          <section class="report-section"><h3>证据索引</h3><div class="evidence-grid"><article v-for="citation in selected.snapshot.citations" :key="citation.evidence_id"><code>{{ citation.evidence_id }}</code><span>{{ citation.tool_name }}</span><small>{{ citation.entity_id }} · {{ citation.as_of_date || "日期未提供" }}</small><button v-if="citation.navigation" type="button" @click="emit('navigate', citation.navigation)">打开业务详情</button></article></div></section>
          <details><summary>限制、警告与未纳入主张</summary><p v-for="warning in selected.snapshot.warnings" :key="warning"><code>{{ warning }}</code></p><p v-for="claim in selected.snapshot.rejected_claims" :key="claim.claim_id"><code>{{ claim.claim_id }}</code> · {{ claim.reason_codes.join(" / ") }}</p></details>
        </template>
      </main>
    </div>

    <section class="report-compare panel-box">
      <div><strong>冻结快照比较</strong><small>只有 COMPARABLE 才显示 Decimal 差值</small></div>
      <select v-model="leftReportId"><option value="">选择左侧报告</option><option v-for="report in reports" :key="report.report_id" :value="report.report_id">{{ report.title }}</option></select>
      <select v-model="rightReportId"><option value="">选择右侧报告</option><option v-for="report in reports" :key="report.report_id" :value="report.report_id">{{ report.title }}</option></select>
      <button type="button" :disabled="working || !leftReportId || !rightReportId || leftReportId === rightReportId" @click="compareReports">比较</button>
      <div v-if="comparison" class="comparison-result"><strong :class="comparison.state.toLowerCase()">{{ comparison.state }}</strong><span>{{ comparison.reason_codes.join(" / ") || "口径一致" }}</span><div class="table-scroll"><table><thead><tr><th>metric</th><th>left</th><th>right</th><th v-if="comparison.state === 'COMPARABLE'">delta</th></tr></thead><tbody><tr v-for="fact in comparison.result.facts || []" :key="fact.metric_key"><td>{{ fact.metric_key }}</td><td>{{ fact.left }}</td><td>{{ fact.right }}</td><td v-if="comparison.state === 'COMPARABLE'">{{ fact.delta ?? "--" }}</td></tr></tbody></table></div></div>
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
input, select, button { min-height: 34px; box-sizing: border-box; border: 1px solid #cbd5e1; border-radius: 5px; background: #fff; padding: 0 9px; }
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
.section-item { margin: 5px 0; color: #475569; }
.report-chart { margin-top: 10px; }
.table-scroll { overflow-x: auto; margin-top: 7px; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th, td { border-bottom: 1px solid #e2e8f0; padding: 7px; text-align: left; white-space: nowrap; }
.evidence-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 7px; }
.evidence-grid article { display: grid; gap: 3px; border: 1px solid #e2e8f0; border-radius: 5px; padding: 8px; }
.evidence-grid code { overflow-wrap: anywhere; }
.report-compare { display: grid; grid-template-columns: 1.2fr 1fr 1fr auto; align-items: end; gap: 10px; padding: 12px; }
.comparison-result { grid-column: 1 / -1; display: grid; gap: 7px; border-top: 1px solid #e2e8f0; padding-top: 12px; }
.comparison-result > strong { width: fit-content; border-radius: 999px; padding: 3px 8px; }
.comparison-result > strong.comparable { background: #dcfce7; color: #166534; }
.comparison-result > strong.context_required { background: #fef3c7; color: #92400e; }
.comparison-result > strong.incompatible { background: #fee2e2; color: #991b1b; }
@media (max-width: 1100px) { .report-create { grid-template-columns: repeat(2, minmax(0, 1fr)); } .report-create > div { grid-column: 1 / -1; } .report-compare { grid-template-columns: 1fr 1fr; } }
@media (max-width: 720px) { .report-create, .report-compare, .report-layout { grid-template-columns: 1fr; } .report-list { max-height: 260px; overflow-y: auto; } .evidence-grid { grid-template-columns: 1fr; } .detail-title { display: grid; } .snapshot-meta { display: grid; } }
</style>
