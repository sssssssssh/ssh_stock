<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from "vue";
import { fetchEvidenceDetail, fetchReportEvidence, fetchTurnArchive, unavailableArchive,
  verifyFrozenReport, type ArchiveDetail, type ArchiveEvidence, type ArchiveSummary,
  type ArchiveVerification } from "../services/agentArchive";

const props = defineProps<{ reportId?: string; chatId?: string; requestId?: string | null }>();
const summary = ref<ArchiveSummary | null>(null);
const evidence = ref<ArchiveEvidence[]>([]);
const total = ref(0);
const detail = ref<ArchiveDetail | null>(null);
const verification = ref<ArchiveVerification | null>(null);
const loading = ref(false);
const busy = ref(false);
const error = ref("");
let generation = 0;
let controller = new AbortController();
let detailGeneration = 0;

function errorMessage(value: unknown) {
  return `归档读取或复核未完成：${value instanceof Error ? value.message : "网络错误"}。不能标记为已验证。`;
}
async function load(more = false) {
  const current = generation;
  loading.value = true;
  error.value = "";
  try {
    if (props.reportId) {
      const page = await fetchReportEvidence(props.reportId, more ? evidence.value.length : 0, controller.signal);
      if (current !== generation) return;
      summary.value = page.meta;
      evidence.value = more ? [...evidence.value, ...page.data] : page.data;
      total.value = page.meta.total;
    } else if (props.chatId && props.requestId) {
      const result = await fetchTurnArchive(props.chatId, props.requestId, controller.signal);
      if (current !== generation) return;
      summary.value = result;
      evidence.value = result.evidence;
      total.value = result.evidence.length;
    } else summary.value = unavailableArchive;
  } catch (value) {
    if (current === generation) { error.value = errorMessage(value); summary.value = null; }
  } finally { if (current === generation) loading.value = false; }
}
async function openEvidence(eid: string) {
  if (!props.reportId) return;
  const current = generation, selected = ++detailGeneration;
  detail.value = null;
  busy.value = true;
  error.value = "";
  try {
    const result = await fetchEvidenceDetail(props.reportId, eid, controller.signal);
    if (current === generation && selected === detailGeneration) detail.value = result;
  } catch (value) {
    if (current === generation && selected === detailGeneration) error.value = errorMessage(value);
  } finally { if (current === generation && selected === detailGeneration) busy.value = false; }
}
async function verify() {
  if (!props.reportId) return;
  const current = generation;
  busy.value = true;
  error.value = "";
  verification.value = null;
  try {
    const result = await verifyFrozenReport(props.reportId, controller.signal);
    if (current === generation) verification.value = result;
  } catch (value) {
    if (current === generation) error.value = errorMessage(value);
  } finally { if (current === generation) busy.value = false; }
}
watch(() => [props.reportId, props.chatId, props.requestId], () => {
  generation++;
  controller.abort();
  controller = new AbortController();
  summary.value = detail.value = verification.value = null;
  evidence.value = []; total.value = 0; busy.value = false;
  void load();
}, { immediate: true });
onBeforeUnmount(() => { generation++; controller.abort(); });
</script>

<template>
  <section class="archive-panel" aria-label="冻结证据归档">
    <header><h3>冻结证据归档</h3><button v-if="reportId" type="button" :disabled="busy || loading || !summary || summary.archive_status === 'UNAVAILABLE'" @click="verify">从冻结证据复核</button></header>
    <p v-if="loading" role="status">正在加载冻结证据</p>
    <div v-if="error" role="alert"><p>{{ error }}</p><button type="button" :disabled="loading || busy" @click="load()">重试读取</button></div>
    <template v-if="summary">
      <div class="archive-states">
        <span>归档：{{ summary.archive_status }}</span>
        <span>完整性：{{ verification?.integrity.status || summary.integrity.status }}</span>
        <span>冻结事实字段：{{ verification?.fact_recheck.status || '尚未执行' }}</span>
        <span v-if="verification?.claim_recheck_summary">结论支持：{{ verification.claim_recheck_summary.status }}</span>
      </div>
      <p>复核等级：{{ verification?.reproduction_level || summary.reproduction_level }} · {{ summary.archived_evidence_count }}/{{ summary.required_evidence_count }} 条证据</p>
      <p>冻结事实核对不是行情重拉或原回测算法重跑，也不代表比较已获差值授权。</p>
      <p v-if="summary.archive_status === 'UNAVAILABLE'">历史报告仅含 Claim 快照，无法恢复当次工具原始响应</p>
      <details v-if="summary.manifest_id"><summary>Manifest 与来源身份</summary><p>Turn <code>{{ summary.source_turn_id }}</code></p><p><code>{{ summary.manifest_id }}</code> · {{ summary.manifest_version }}</p><code>{{ summary.manifest_hash }}</code></details>
      <p v-for="warning in summary.warnings" :key="warning"><code>{{ warning }}</code></p>
      <div class="archive-evidence">
        <article v-for="row in evidence" :key="row.evidence_id">
          <code>{{ row.evidence_id }}</code><span>{{ row.tool_name }} / {{ row.tool_version }} · {{ row.entity_id }} · {{ row.as_of_date }}</span>
          <small>{{ row.tool_call_id }} · {{ row.record_path }} · {{ row.created_at }}</small>
          <button v-if="reportId" type="button" :disabled="busy" @click="openEvidence(row.evidence_id)">查看冻结事实</button>
        </article>
      </div>
      <button v-if="evidence.length < total" type="button" :disabled="loading" @click="load(true)">更多证据</button>
      <div v-if="detail" class="archive-detail" role="region" aria-label="冻结事实详情">
        <header><h4>冻结事实详情</h4><button type="button" @click="detail = null">关闭详情</button></header>
        <code>{{ detail.evidence_id }}</code>
        <p>参数摘要：{{ JSON.stringify(detail.arguments_summary) }}</p>
        <p v-for="key in ['config_hash', 'source_hash', 'content_hash', 'arguments_hash', 'registry_schema_hash', 'projection_version'] as const" :key="key">{{ key }}：<code>{{ detail[key] || '未提供' }}</code></p>
        <div class="archive-table"><table><thead><tr><th>Claim / 字段</th><th>冻结值</th><th>实体 / 日期 / 样本</th></tr></thead><tbody><tr v-for="(fact, index) in detail.frozen_facts" :key="index"><td data-label="Claim / 字段">{{ fact.claim_id }} <code>{{ fact.path }}</code></td><td data-label="冻结值">{{ fact.value }} {{ fact.unit }}</td><td data-label="实体 / 日期 / 样本">{{ fact.entity }} / {{ fact.trade_date }} / {{ fact.sample_role }}</td></tr></tbody></table></div>
        <p v-if="!detail.frozen_facts.length">没有可安全发布的已验证字段。</p>
      </div>
      <div v-if="verification" class="archive-verification" role="status">
        <strong>冻结事实复核：{{ verification.verification_level }} · {{ verification.fact_recheck.checked_claim_count }} 项</strong>
        <p v-for="row in verification.fact_recheck.results" :key="row.claim_id">
          {{ row.claim_id }} · {{ row.check_kind === 'INFERENCE_SUPPORT' ? '有限推断支持' : row.check_kind === 'COMPARISON_CONTEXT' ? '策略比较' : '直接事实' }}：{{ row.status }}
          <span v-if="row.facts_applicable !== false"> · 原数值：{{ row.facts_status || row.status }}</span>
          <span v-if="row.check_kind === 'INFERENCE_SUPPORT'"> · 支持关系：{{ row.support_status || 'UNVERIFIABLE' }}（不代表因果被证实）</span>
          <span v-if="row.comparison_state"> · 比较许可：{{ row.comparison_state }}（不代表收益差值已获授权）</span>
          <span v-if="row.reason_codes.length"> · {{ row.reason_codes.join(' / ') }}</span>
          <span v-for="field in row.failed_fields" :key="field.path"> · {{ field.path }}：{{ field.code }}</span>
        </p>
        <p v-for="warning in verification.warnings" :key="warning"><code>{{ warning }}</code></p>
      </div>
    </template>
  </section>
</template>

<style scoped>
.archive-panel { min-width: 0; display: grid; gap: 8px; margin: 12px 0; padding: 12px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 12px; color: #334155; }
header, .archive-states { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; }
h3, h4, p { margin: 0; } code, p, small { overflow-wrap: anywhere; }
.archive-states { justify-content: flex-start; } .archive-states span { background: #f1f5f9; padding: 4px 6px; border-radius: 4px; }
button { max-width: 100%; min-height: 34px; border: 1px solid #cbd5e1; border-radius: 5px; background: #fff; cursor: pointer; color: #334155; }
button:disabled { opacity: .5; cursor: not-allowed; }
.archive-evidence { display: grid; gap: 8px; grid-template-columns: repeat(2, minmax(0, 1fr)); }
article, .archive-detail, .archive-verification { min-width: 0; display: grid; gap: 6px; padding: 8px; border: 1px solid #e2e8f0; border-radius: 4px; }
.archive-table { overflow-x: auto; } table { width: 100%; border-collapse: collapse; } th, td { text-align: left; padding: 6px; border-bottom: 1px solid #e2e8f0; }
[role="alert"] { color: #9f1239; }
@media (max-width: 720px) {
  .archive-evidence { grid-template-columns: 1fr; }
  .archive-table table, .archive-table tbody, .archive-table tr, .archive-table td { display: block; width: auto; overflow-wrap: anywhere; }
  .archive-table thead { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
  .archive-table td::before { content: attr(data-label); display: block; font-weight: 600; color: #64748b; margin-bottom: 4px; }
}
</style>
