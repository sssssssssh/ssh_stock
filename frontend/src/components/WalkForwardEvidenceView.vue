<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";

import {
  fetchWalkForwardStudy,
  fetchWalkForwardValidation,
  fetchWalkForwardValidationWindow,
  type ResearchNavigationContext,
  type WalkForwardDetail
} from "../services/agent";

const props = defineProps<{ navigation: ResearchNavigationContext | null }>();
defineEmits<{ back: [] }>();

const loading = ref(false);
const error = ref("");
const study = ref<WalkForwardDetail | null>(null);
const validation = ref<WalkForwardDetail | null>(null);
const windowDetail = ref<WalkForwardDetail | null>(null);
let generation = 0;
onBeforeUnmount(() => { generation += 1; });

const identityRows = computed(() => [
  ["Study", props.navigation?.study_id],
  ["Validation", props.navigation?.validation_id],
  ["Window", props.navigation?.window_no],
  ["证据工具", props.navigation?.source_tool]
]);

const detailRows = computed(() => {
  if (!windowDetail.value) return [];
  const preferred = [
    "window_no", "train_start_date", "train_end_date", "test_start_date", "test_end_date",
    "selected_train_run_id", "oos_run_id", "train_experiment_id", "train_evaluation_id", "selected_trial_id",
    "train_performance_id", "train_risk_id", "train_trade_id", "train_period_id",
    "oos_performance_id", "oos_risk_id", "oos_trade_id", "oos_period_id",
    "train_date_hash", "test_date_hash", "selected_parameter_hash", "status"
  ];
  const ordered = preferred.filter((key) => key in windowDetail.value!);
  return ordered.map((key) => [key, formatValue(windowDetail.value![key])]);
});

watch(
  () => props.navigation,
  (value) => {
    if (value?.view === "walk_forward") void load(value);
  },
  { immediate: true, deep: true }
);

async function load(target: ResearchNavigationContext) {
  const current = ++generation;
  error.value = "";
  study.value = null;
  validation.value = null;
  windowDetail.value = null;
  if (!target.study_id || !target.validation_id || !target.window_no) {
    error.value = "该证据暂不支持精准定位。";
    return;
  }
  loading.value = true;
  try {
    const [nextStudy, nextValidation, page] = await Promise.all([
      fetchWalkForwardStudy(target.study_id),
      fetchWalkForwardValidation(target.study_id, target.validation_id),
      fetchWalkForwardValidationWindow(target.study_id, target.validation_id, target.window_no)
    ]);
    if (current !== generation) return;
    study.value = nextStudy;
    validation.value = nextValidation;
    windowDetail.value = page.data.find((item) => Number(item.window_no) === target.window_no) || null;
    if (!windowDetail.value) error.value = `Validation 中未找到 Window ${target.window_no}。`;
  } catch (value) {
    if (current !== generation) return;
    error.value = value instanceof Error ? value.message : "Walk-forward 明细加载失败";
  } finally {
    if (current === generation) loading.value = false;
  }
}

function formatValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "--";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
</script>

<template>
  <section class="wf-evidence-view">
    <header class="wf-header">
      <div><h2>Walk-forward 窗口明细</h2><p>已验证的 Study / Validation / Window 定位</p></div>
      <button type="button" class="wf-back" @click="$emit('back')">返回智能研究</button>
    </header>

    <div class="wf-identity" aria-label="证据定位身份">
      <div v-for="row in identityRows" :key="String(row[0])"><span>{{ row[0] }}</span><strong>{{ row[1] || "--" }}</strong></div>
    </div>

    <div v-if="loading" class="wf-state">正在加载窗口明细</div>
    <div v-else-if="error" class="wf-state error" role="alert">{{ error }}</div>
    <template v-else-if="windowDetail">
      <section class="wf-summary">
        <div><span>Study 状态</span><strong>{{ study?.status || "--" }}</strong></div>
        <div><span>Validation 状态</span><strong>{{ validation?.status || "--" }}</strong></div>
        <div><span>窗口数量</span><strong>{{ validation?.window_count || "--" }}</strong></div>
        <div><span>当前窗口</span><strong>#{{ navigation?.window_no }}</strong></div>
      </section>
      <section class="wf-detail">
        <h3>窗口来源身份</h3>
        <dl><template v-for="row in detailRows" :key="String(row[0])"><dt>{{ row[0] }}</dt><dd>{{ row[1] }}</dd></template></dl>
      </section>
    </template>
  </section>
</template>

<style scoped>
.wf-evidence-view { display: grid; gap: 14px; min-width: 0; }
.wf-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.wf-header h2, .wf-header p { margin: 0; }
.wf-header p { margin-top: 4px; color: #64748b; font-size: 12px; }
.wf-back { min-height: 34px; border: 1px solid #cbd5e1; border-radius: 5px; background: #fff; padding: 0 12px; color: #1e293b; cursor: pointer; }
.wf-identity, .wf-summary { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); border: 1px solid #d8e0e8; border-radius: 7px; background: #fff; }
.wf-identity > div, .wf-summary > div { display: grid; gap: 5px; min-width: 0; padding: 12px; border-right: 1px solid #e2e8f0; }
.wf-identity > div:last-child, .wf-summary > div:last-child { border-right: 0; }
.wf-identity span, .wf-summary span { color: #64748b; font-size: 11px; }
.wf-identity strong { overflow: hidden; font-family: ui-monospace, monospace; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.wf-state, .wf-detail { border: 1px solid #d8e0e8; border-radius: 7px; background: #fff; padding: 18px; }
.wf-state { color: #64748b; text-align: center; }
.wf-state.error { border-color: #fecaca; background: #fef2f2; color: #b91c1c; }
.wf-detail h3 { margin: 0 0 12px; font-size: 15px; }
.wf-detail dl { display: grid; grid-template-columns: 190px minmax(0, 1fr); gap: 0; margin: 0; }
.wf-detail dt, .wf-detail dd { margin: 0; border-top: 1px solid #eef2f6; padding: 8px; overflow-wrap: anywhere; }
.wf-detail dt { color: #64748b; font-size: 12px; }
.wf-detail dd { font-family: ui-monospace, monospace; font-size: 12px; }
@media (max-width: 760px) {
  .wf-header { align-items: flex-start; }
  .wf-identity, .wf-summary { grid-template-columns: 1fr 1fr; }
  .wf-identity > div:nth-child(2), .wf-summary > div:nth-child(2) { border-right: 0; }
  .wf-detail dl { grid-template-columns: 1fr; }
  .wf-detail dd { border-top: 0; padding-top: 0; }
}
</style>
