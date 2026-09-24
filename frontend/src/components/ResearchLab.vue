<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";

import {
  fetchContext, fetchLeftThresholds, fetchOpportunityBuckets, fetchPositionStats,
  fetchResearchStatus, fetchRightTransitions, fetchThemeBuckets, fetchThemeLifecycle,
  fetchThemeStats, fetchThemeTopN, fetchTrendTopN, queueResearchEvaluation,
  type ResearchWindow
} from "../services/research";
import type { ResearchBucketRow, ResearchHorizonStats, ResearchStatus } from "../types";
import { businessDaysAgoIso, businessTodayIso } from "../utils/businessTime";

type Tab = "theme" | "left" | "right" | "trend" | "position";
type Row = ResearchBucketRow & Record<string, unknown>;

const tabs: Array<{ key: Tab; label: string }> = [
  { key: "theme", label: "题材" },
  { key: "left", label: "左侧" },
  { key: "right", label: "右侧" },
  { key: "trend", label: "趋势" },
  { key: "position", label: "位置" }
];
const horizonOptions = [5, 10, 20, 60];
const start = ref(businessDaysAgoIso(365));
const end = ref(businessTodayIso());
const tab = ref<Tab>("theme");
const horizon = ref(20);
const status = ref<ResearchStatus | null>(null);
const primary = ref<Row[]>([]);
const secondary = ref<Row[]>([]);
const tertiary = ref<Row[]>([]);
const context = ref<Row[]>([]);
const fifth = ref<Row[]>([]);
const loading = ref(false);
const submitting = ref(false);
const error = ref("");
const message = ref("");
let requestId = 0;

const titles = computed(() => {
  switch (tab.value) {
    case "theme": return ["题材整体", "热度分层", "TopN", "生命周期", "热度动量"];
    case "left": return ["阈值触发", "市场环境", "", ""];
    case "right": return ["右侧状态转化", "市场环境", "", ""];
    case "trend": return ["TopN", "排名分层", "市场环境", ""];
    default: return ["位置风险", "市场环境", "", ""];
  }
});

function stats(row: Row, selected = horizon.value): ResearchHorizonStats | undefined {
  return row.horizons?.find((item) => item.horizon === selected);
}

function percent(value: number | null | undefined): string {
  return value == null ? "--" : `${(value * 100).toFixed(1)}%`;
}

function number(value: number | null | undefined): string {
  return value == null ? "--" : value.toFixed(1);
}

function extra(row: Row, key: string): string {
  const value = row[key];
  return typeof value === "number" ? percent(value) : "--";
}

function windowValue(): ResearchWindow {
  return { start: start.value, end: end.value };
}

async function refresh(): Promise<void> {
  const current = ++requestId;
  if (!start.value || !end.value || start.value > end.value) {
    error.value = "日期范围无效";
    return;
  }
  loading.value = true;
  error.value = "";
  try {
    const window = windowValue();
    const nextStatus = await fetchResearchStatus();
    let groups: ResearchBucketRow[][];
    switch (tab.value) {
      case "theme":
        groups = await Promise.all([
          fetchThemeStats(window), fetchThemeBuckets(window, "heat_score"),
          fetchThemeTopN(window), fetchThemeLifecycle(window),
          fetchThemeBuckets(window, "heat_momentum3")
        ]);
        break;
      case "left":
        groups = await Promise.all([fetchLeftThresholds(window), fetchContext(window, "market_regime", "LEFT")]);
        break;
      case "right":
        groups = await Promise.all([fetchRightTransitions(window), fetchContext(window, "market_regime", "RIGHT")]);
        break;
      case "trend":
        groups = await Promise.all([
          fetchTrendTopN(window), fetchOpportunityBuckets(window, "trend_rank_score", "TREND"),
          fetchContext(window, "market_regime", "TREND")
        ]);
        break;
      default:
        groups = await Promise.all([fetchPositionStats(window), fetchContext(window, "extension_risk", "POSITION")]);
    }
    if (current !== requestId) return;
    status.value = nextStatus;
    [primary.value, secondary.value, tertiary.value, context.value, fifth.value] = [
      (groups[0] || []) as Row[], (groups[1] || []) as Row[],
      (groups[2] || []) as Row[], (groups[3] || []) as Row[],
      (groups[4] || []) as Row[]
    ];
  } catch (cause) {
    if (current === requestId) error.value = cause instanceof Error ? cause.message : "研究数据读取失败";
  } finally {
    if (current === requestId) loading.value = false;
  }
}

async function submit(): Promise<void> {
  if (!start.value || !end.value || start.value > end.value) {
    error.value = "日期范围无效";
    return;
  }
  submitting.value = true;
  message.value = "";
  error.value = "";
  try {
    const job = await queueResearchEvaluation(windowValue());
    message.value = `研究任务已入队 · ${job.id}`;
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : "提交失败";
  } finally {
    submitting.value = false;
  }
}

watch(tab, refresh);
onMounted(refresh);
</script>

<template>
  <section class="research-lab">
    <div class="research-toolbar">
      <div class="research-title">
        <h2>历史效果验证</h2>
        <span>{{ status?.benchmark_code || "--" }} · {{ status?.research_version || "--" }}</span>
      </div>
      <form class="research-filters" @submit.prevent="refresh">
        <label>开始 <input v-model="start" type="date" /></label>
        <label>结束 <input v-model="end" type="date" /></label>
        <button type="submit" :disabled="loading">{{ loading ? "查询中" : "查询" }}</button>
        <button type="button" class="research-run" :disabled="submitting" @click="submit">
          {{ submitting ? "提交中" : "运行研究" }}
        </button>
      </form>
    </div>
    <p v-if="error" class="research-error" role="alert">{{ error }}</p>
    <p v-if="message" class="research-message" role="status">{{ message }}</p>

    <div class="research-status">
      <div><span>机会样本</span><strong>{{ status?.opportunity_eval_rows ?? "--" }}</strong></div>
      <div><span>题材样本</span><strong>{{ status?.theme_eval_rows ?? "--" }}</strong></div>
      <div><span>转化事件</span><strong>{{ status?.transition_eval_rows ?? "--" }}</strong></div>
      <div><span>20日成熟</span><strong>{{ status?.mature20_rows ?? "--" }}</strong></div>
      <div><span>最新评估日</span><strong>{{ status?.latest_evaluated_market_date || "--" }}</strong></div>
    </div>

    <div class="research-controls">
      <div class="research-segment" role="tablist" aria-label="研究类型">
        <button v-for="item in tabs" :key="item.key" type="button" role="tab"
          :aria-selected="tab === item.key" :class="{ selected: tab === item.key }"
          @click="tab = item.key">{{ item.label }}</button>
      </div>
      <div class="research-segment" role="group" aria-label="评估周期">
        <button v-for="days in horizonOptions" :key="days" type="button"
          :class="{ selected: horizon === days }" @click="horizon = days">{{ days }}日</button>
      </div>
    </div>

    <template v-for="(rows, index) in [primary, secondary, tertiary, context, fifth]" :key="index">
      <section v-if="titles[index]" class="research-section">
        <div class="research-section-title"><h3>{{ titles[index] }}</h3><span>{{ rows.length }} 组</span></div>
        <div class="research-table-wrap">
          <table class="research-table">
            <thead><tr>
              <th>分组</th><th>事件</th><th>成熟</th><th>收益样本</th>
              <th>收益</th><th>超额</th><th>胜率</th><th>MFE20</th><th>MAE20</th>
              <template v-if="(tab === 'left' || tab === 'right') && index === 0">
                <th v-for="days in [5, 10, 20]" :key="`s3-${days}`">S3@{{ days }}</th>
                <th v-for="days in [5, 10, 20]" :key="`s4-${days}`">S4+@{{ days }}</th>
                <th v-for="days in [5, 10, 20]" :key="`s5-${days}`">S5@{{ days }}</th>
              </template>
              <th v-if="tab === 'right' && index === 0">跌回S3以下</th>
              <th v-if="(tab === 'left' || tab === 'right') && index === 0">S6@20</th>
              <th v-if="tab === 'left' && index === 0">到S3天数</th>
              <th v-if="(tab === 'left' || tab === 'right') && index === 0">到S4+天数</th>
              <th v-if="(tab === 'left' || tab === 'right') && index === 0">到S5天数</th>
            </tr></thead>
            <tbody>
              <tr v-for="row in rows" :key="row.group">
                <td class="research-group">{{ row.group }}</td>
                <td>{{ row.event_count }}</td>
                <td>{{ stats(row)?.mature_count ?? 0 }}</td>
                <td :class="{ 'sample-low': stats(row)?.sample_warning }">
                  {{ stats(row)?.return_sample_count ?? 0 }}<span v-if="stats(row)?.sample_warning"> · 少</span>
                </td>
                <td>{{ percent(stats(row)?.avg_return) }}</td>
                <td>{{ percent(stats(row)?.avg_excess_return) }}</td>
                <td>{{ percent(stats(row)?.win_rate) }}</td>
                <td>{{ percent(stats(row, 20)?.avg_mfe20) }}</td>
                <td>{{ percent(stats(row, 20)?.avg_mae20) }}</td>
                <template v-if="(tab === 'left' || tab === 'right') && index === 0">
                  <td v-for="days in [5, 10, 20]" :key="`s3-${days}`">{{ extra(row, `reached_s3_${days}`) }}</td>
                  <td v-for="days in [5, 10, 20]" :key="`s4-${days}`">{{ extra(row, `reached_s4plus_${days}`) }}</td>
                  <td v-for="days in [5, 10, 20]" :key="`s5-${days}`">{{ extra(row, `reached_s5_${days}`) }}</td>
                </template>
                <td v-if="tab === 'right' && index === 0">{{ extra(row, 'fell_below_s3_20') }}</td>
                <td v-if="(tab === 'left' || tab === 'right') && index === 0">{{ extra(row, 'hit_s6_20') }}</td>
                <td v-if="tab === 'left' && index === 0">{{ number(row.avg_days_to_s3 as number | null) }}</td>
                <td v-if="(tab === 'left' || tab === 'right') && index === 0">{{ number(row.avg_days_to_s4plus as number | null) }}</td>
                <td v-if="(tab === 'left' || tab === 'right') && index === 0">{{ number(row.avg_days_to_s5 as number | null) }}</td>
              </tr>
              <tr v-if="!rows.length"><td :colspan="16" class="research-empty">暂无研究样本</td></tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </section>
</template>
