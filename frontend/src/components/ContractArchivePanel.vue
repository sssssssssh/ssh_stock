<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { fetchReportContract, fetchReportContracts, verifyReportContracts,
  type ContractManifestReference, type ContractVerification, type FrozenContractDetail,
  type FrozenContractReference } from "../services/agentReports";

const props = defineProps<{ reportId: string; reference?: ContractManifestReference | null }>();
const rows = ref<FrozenContractReference[]>([]);
const total = ref(0), offset = ref(0);
const check = ref<ContractVerification | null>(null);
const detail = ref<FrozenContractDetail | null>(null);
const loading = ref(false), busy = ref(false), error = ref("");
let generation = 0, detailGeneration = 0;
let pageController = new AbortController(), actionController = new AbortController();
const formatted = computed(() => detail.value?.projection ? JSON.stringify(detail.value.projection, null, 2) : "");
const statusLabels: Record<string, string> = { VERIFIED: "通过", UNVERIFIABLE: "不可核验", MISMATCH: "冲突" };
const statusText = (value?: string) => statusLabels[value || ""] || "待核验";

async function load(nextOffset = 0) {
  const current = ++generation;
  pageController.abort(); actionController.abort();
  pageController = new AbortController(); actionController = new AbortController();
  check.value = null; detail.value = null; busy.value = false;
  loading.value = true; error.value = "";
  try {
    const page = await fetchReportContracts(props.reportId, nextOffset, pageController.signal);
    if (current !== generation) return;
    rows.value = page.data; total.value = page.meta.total; offset.value = nextOffset;
    check.value = page.meta.check;
  } catch (value) {
    if (current === generation) error.value = value instanceof Error ? value.message : "合同读取未完成";
  } finally { if (current === generation) loading.value = false; }
}
async function openDetail(contractId: string) {
  const current = generation, selected = ++detailGeneration;
  actionController.abort(); actionController = new AbortController();
  detail.value = null; busy.value = true; error.value = "";
  try {
    const value = await fetchReportContract(props.reportId, contractId, actionController.signal);
    if (current === generation && selected === detailGeneration) detail.value = value;
  } catch (value) {
    if (current === generation && selected === detailGeneration) error.value = value instanceof Error ? value.message : "合同明细读取未完成";
  } finally { if (current === generation && selected === detailGeneration) busy.value = false; }
}
async function verify() {
  const current = generation, selected = ++detailGeneration;
  actionController.abort(); actionController = new AbortController();
  check.value = null; detail.value = null; busy.value = true; error.value = "";
  try {
    const value = await verifyReportContracts(props.reportId, actionController.signal);
    if (current === generation && selected === detailGeneration) check.value = value;
  } catch (value) {
    if (current === generation && selected === detailGeneration) error.value = value instanceof Error ? value.message : "合同复核未完成";
  } finally { if (current === generation && selected === detailGeneration) busy.value = false; }
}
watch(() => [props.reportId, props.reference?.manifest_id, props.reference?.manifest_hash], () => {
  generation++; detailGeneration++; pageController.abort(); actionController.abort();
  rows.value = []; total.value = offset.value = 0; check.value = detail.value = null;
  loading.value = busy.value = false; error.value = "";
  if (props.reference) void load();
}, { immediate: true });
onBeforeUnmount(() => { generation++; pageController.abort(); actionController.abort(); });
</script>

<template>
  <section class="contract-panel" aria-label="冻结研究合同">
    <header><h3>研究合同</h3><span>算法未重跑</span><button v-if="reference" type="button" :disabled="loading || busy" @click="verify">复核合同</button></header>
    <p v-if="!reference" class="contract-empty">无合同归档 · 历史快照</p>
    <template v-else>
      <p class="contract-anchor" :title="reference.manifest_hash">{{ reference.policy_version }} · <code>{{ reference.manifest_hash }}</code></p>
      <div class="contract-statuses" aria-live="polite">
        <span>内容完整 <strong>{{ statusText(check?.archive_integrity?.status) }}</strong></span>
        <span>字段事实 <strong>{{ statusText(check?.frozen_fact_recheck?.status) }}</strong></span>
        <span>合同完整 <strong>{{ statusText(check?.contract_integrity.status) }}</strong></span>
        <span>合同口径 <strong>{{ statusText(check?.contract_semantics.status) }}</strong></span>
        <span>比较许可 <strong>{{ check?.comparison_permission.allowed ? "已授权" : "待场景校验" }}</strong></span>
      </div>
      <p v-if="loading || busy" role="status">{{ loading ? "正在读取合同" : "正在核验或读取明细" }}</p>
      <div v-if="error" class="contract-error" role="alert">{{ error }}<button type="button" @click="load(offset)">重新加载</button></div>
      <p v-for="reason in check?.contract_semantics.reason_codes || []" :key="reason" class="contract-reason">{{ reason }}</p>
      <div class="contract-table"><table><thead><tr><th>来源 / 角色</th><th>合同</th><th>冻结状态</th><th>Hash</th></tr></thead><tbody>
        <tr v-for="row in rows" :key="row.contract_id"><td><strong>{{ row.role }}</strong><small :title="row.subject_id">{{ row.subject_id }}</small></td><td><button type="button" @click="openDetail(row.contract_id)">{{ row.contract_kind }}</button><small>{{ row.schema_version }}</small></td><td :title="row.reason_codes.join(' / ')">{{ statusText(row.status) }}<small>{{ row.reason_codes.join(' / ') }}</small></td><td><code :title="row.contract_hash">{{ row.contract_hash.slice(0, 12) }}</code></td></tr>
      </tbody></table></div>
      <nav v-if="total" class="contract-pagination" aria-label="合同分页"><button type="button" title="上一页" aria-label="上一页" :disabled="loading || offset === 0" @click="load(Math.max(0, offset - 20))">‹</button><span>{{ offset + 1 }}–{{ Math.min(offset + rows.length, total) }} / {{ total }}</span><button type="button" title="下一页" aria-label="下一页" :disabled="loading || offset + rows.length >= total" @click="load(offset + 20)">›</button></nav>
      <details v-if="detail" open class="contract-detail"><summary>{{ detail.role }} · {{ detail.contract_kind }} · 明细</summary><code>{{ detail.contract_hash }}</code><pre v-if="formatted">{{ formatted }}</pre><p v-else>该版本无法解释 · {{ detail.reason_codes.join(' / ') }}</p></details>
    </template>
  </section>
</template>

<style scoped>
.contract-panel { min-width: 0; margin-top: 14px; border-top: 1px solid #d8e0e8; padding-top: 12px; font-size: 12px; }
header { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
h3 { margin: 0; font-size: 14px; } header > span { color: #64748b; } header > button { margin-left: auto; }
button { min-height: 32px; border: 1px solid #cbd5e1; border-radius: 4px; background: #fff; color: #1e293b; padding: 4px 8px; cursor: pointer; }
button:disabled { opacity: .5; cursor: not-allowed; } button:focus-visible { outline: 2px solid #2563eb; outline-offset: 2px; }
.contract-empty { color: #64748b; } .contract-anchor { display: flex; gap: 8px; min-width: 0; color: #64748b; flex-wrap: wrap; }
.contract-anchor code { overflow-wrap: anywhere; } .contract-statuses { display: flex; flex-wrap: wrap; gap: 8px 16px; padding: 8px 0; }
.contract-statuses span { display: flex; gap: 5px; } .contract-statuses strong { color: #0f766e; font-weight: 500; }
.contract-error { color: #b91c1c; background: #fff1f2; padding: 8px; overflow-wrap: anywhere; } .contract-error button { margin-left: 8px; }
.contract-reason { color: #9a6700; overflow-wrap: anywhere; } .contract-table { overflow: auto; max-height: 340px; }
table { width: 100%; border-collapse: collapse; table-layout: fixed; } th, td { padding: 8px 6px; border-bottom: 1px solid #e2e8f0; text-align: left; vertical-align: top; overflow-wrap: anywhere; }
th:first-child { width: 32%; } th:last-child { width: 16%; } td small { display: block; margin-top: 4px; color: #64748b; overflow-wrap: anywhere; } td button { width: 100%; text-align: left; overflow-wrap: anywhere; }
.contract-pagination { display: flex; align-items: center; justify-content: flex-end; gap: 10px; padding-top: 8px; } .contract-pagination button { width: 32px; }
.contract-detail { margin-top: 12px; min-width: 0; } summary { cursor: pointer; overflow-wrap: anywhere; } .contract-detail > code { display: block; margin-top: 8px; overflow-wrap: anywhere; }
pre { margin: 8px 0 0; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 4px; padding: 10px; max-height: 400px; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; font-size: 11px; }
@media (max-width: 600px) { .contract-table table { min-width: 480px; } .contract-statuses { gap: 8px 12px; } header > button { margin-left: 0; } }
</style>
