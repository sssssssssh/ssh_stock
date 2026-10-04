<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { ApiError } from "../services/api";
import {
  calculatePeriods,
  compareAnalytics,
  fetchAllAnalyticsSeries,
  fetchAnalyticsSummary,
  fetchBacktests,
  fetchPeriods,
  fetchTradeEpisodes
} from "../services/analytics";
import type {
  AnalyticsPeriod,
  AnalyticsSeries,
  AnalyticsSummary,
  BacktestRun,
  TradeEpisode
} from "../types";
import AnalyticsCompareTable from "./AnalyticsCompareTable.vue";
import AnalyticsDrawdownChart from "./AnalyticsDrawdownChart.vue";
import AnalyticsNavChart from "./AnalyticsNavChart.vue";
import AnalyticsPeriodTable from "./AnalyticsPeriodTable.vue";
import AnalyticsSummaryCards from "./AnalyticsSummaryCards.vue";

const runs = ref<BacktestRun[]>([]);
const selectedRunId = ref("");
const summary = ref<AnalyticsSummary | null>(null);
const series = ref<AnalyticsSeries[]>([]);
const monthPeriods = ref<AnalyticsPeriod[]>([]);
const yearPeriods = ref<AnalyticsPeriod[]>([]);
const periodType = ref<"MONTH" | "YEAR">("MONTH");
const loading = ref(true);
const error = ref("");
const periodMissing = ref(false);
const periodJobRunning = ref(false);
const compareSelection = ref<string[]>([]);
const compareRows = ref<AnalyticsSummary[]>([]);
const compareError = ref("");
const episodeStatus = ref("");
const episodeClassification = ref("");
const episodeCode = ref("");
const episodePage = ref(0);
const episodes = ref<TradeEpisode[]>([]);
const episodeTotal = ref(0);
const episodeLimit = 20;
let workspaceReady = false;
let loadGeneration = 0;
let episodeGeneration = 0;

const successRuns = computed(() => runs.value.filter((row) => row.status === "SUCCESS"));
const visiblePeriods = computed(() => periodType.value === "MONTH" ? monthPeriods.value : yearPeriods.value);

function errorText(value: unknown): string {
  if (!(value instanceof Error)) return "分析数据加载失败";
  const labels: Record<string, string> = {
    ANALYTICS_BASE_NOT_FOUND: "回测尚未成功或不存在",
    ANALYTICS_ARTIFACT_BUNDLE_INCOMPLETE: "Performance、Risk 或 Trade 分析尚未生成",
    ANALYTICS_ARTIFACT_BUNDLE_MISMATCH: "分析产物来源不一致，请重新生成",
    ANALYTICS_SERIES_DATE_MISMATCH: "Performance 与 Risk 每日序列不一致",
    PERIOD_SOURCE_DATE_MISMATCH: "周期分析的每日数据日期不一致",
    PERIOD_CALCULATION_CONFLICT: "周期分析任务正在运行"
  };
  return labels[value.message] || value.message;
}

async function loadWorkspace() {
  loading.value = true;
  error.value = "";
  try {
    runs.value = await fetchBacktests();
    if (!selectedRunId.value) selectedRunId.value = successRuns.value[0]?.id || "";
    if (selectedRunId.value) await loadSelectedRun();
  } catch (value) {
    error.value = errorText(value);
  } finally {
    loading.value = false;
  }
}

async function loadSelectedRun() {
  if (!selectedRunId.value) return;
  const runId = selectedRunId.value;
  const current = ++loadGeneration;
  loading.value = true;
  error.value = "";
  periodMissing.value = false;
  try {
    const nextSummary = await fetchAnalyticsSummary(runId);
    const identity = nextSummary.identity;
    const nextSeries = fetchAllAnalyticsSeries(runId, identity);
    const nextEpisodes = fetchTradeEpisodes(runId, identity, episodeOptions());
    let nextMonths: AnalyticsPeriod[] = [];
    let nextYears: AnalyticsPeriod[] = [];
    if (identity.period_id) {
      [nextMonths, nextYears] = await Promise.all([
        fetchPeriods(runId, "MONTH", identity),
        fetchPeriods(runId, "YEAR", identity)
      ]);
    }
    const [nextSeriesRows, nextEpisodePage] = await Promise.all([
      nextSeries,
      nextEpisodes
    ]);
    if (current !== loadGeneration || runId !== selectedRunId.value) return;
    summary.value = nextSummary;
    series.value = nextSeriesRows;
    monthPeriods.value = nextMonths;
    yearPeriods.value = nextYears;
    periodMissing.value = !identity.period_id;
    episodes.value = nextEpisodePage.data;
    episodeTotal.value = nextEpisodePage.meta.total;
  } catch (value) {
    if (current !== loadGeneration) return;
    summary.value = null;
    error.value = errorText(value);
  } finally {
    if (current === loadGeneration) loading.value = false;
  }
}

async function generatePeriods() {
  if (!selectedRunId.value) return;
  const anchor = summary.value?.identity;
  if (!anchor) return;
  periodJobRunning.value = true;
  error.value = "";
  const runId = selectedRunId.value;
  const current = ++loadGeneration;
  try {
    await calculatePeriods(runId, anchor);
    for (let attempt = 0; attempt < 30; attempt += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 1000));
      if (current !== loadGeneration || runId !== selectedRunId.value) return;
      const refreshed = await fetchAnalyticsSummary(runId, anchor);
      if (refreshed.identity.period_id) {
        const [nextSeries, nextMonths, nextYears] = await Promise.all([
          fetchAllAnalyticsSeries(runId, refreshed.identity),
          fetchPeriods(runId, "MONTH", refreshed.identity),
          fetchPeriods(runId, "YEAR", refreshed.identity)
        ]);
        if (current !== loadGeneration || runId !== selectedRunId.value) return;
        summary.value = refreshed;
        series.value = nextSeries;
        periodMissing.value = false;
        monthPeriods.value = nextMonths;
        yearPeriods.value = nextYears;
        return;
      }
    }
    error.value = "周期分析仍在运行，可稍后刷新";
  } catch (value) {
    error.value = errorText(value);
  } finally {
    periodJobRunning.value = false;
  }
}

async function runCompare() {
  if (compareSelection.value.length < 2) return;
  compareError.value = "";
  try {
    const result = await compareAnalytics(compareSelection.value.map((run_id) => ({ run_id })));
    compareRows.value = result.items;
  } catch (value) {
    if (value instanceof ApiError && value.code === "ANALYTICS_COMPARE_INCOMPATIBLE") {
      const fields = value.detail?.mismatch_fields;
      compareError.value = `所选回测不可比较：${Array.isArray(fields) ? fields.join("、") : "分析口径不同"}`;
    } else {
      compareError.value = errorText(value);
    }
  }
}

async function loadEpisodes() {
  if (!selectedRunId.value || !summary.value) return;
  const current = ++episodeGeneration;
  const runId = selectedRunId.value;
  const identity = summary.value.identity;
  const page = await fetchTradeEpisodes(runId, identity, episodeOptions());
  if (
    current !== episodeGeneration ||
    runId !== selectedRunId.value ||
    identity !== summary.value?.identity
  ) return;
  episodes.value = page.data;
  episodeTotal.value = page.meta.total;
}

function episodeOptions() {
  return {
    status: episodeStatus.value || undefined,
    classification: episodeClassification.value || undefined,
    tsCode: episodeCode.value || undefined,
    limit: episodeLimit,
    offset: episodePage.value * episodeLimit
  };
}

watch(selectedRunId, () => {
  if (!workspaceReady) return;
  episodePage.value = 0;
  void loadSelectedRun();
});
onMounted(async () => {
  await loadWorkspace();
  workspaceReady = true;
});
</script>

<template>
  <section class="analytics-view">
    <header class="analytics-toolbar">
      <div><h2>回测分析</h2><p>Performance / Risk / Trade / Period 的兼容事实视图</p></div>
      <label>回测
        <select v-model="selectedRunId" :disabled="loading">
          <option v-for="run in successRuns" :key="run.id" :value="run.id">
            {{ run.name || run.id.slice(0, 8) }} · {{ run.start_date }} ~ {{ run.end_date }}
          </option>
        </select>
      </label>
    </header>

    <div v-if="loading" class="analytics-state">正在加载分析数据</div>
    <div v-else-if="error" class="analytics-state analytics-error">{{ error }}</div>
    <div v-else-if="!selectedRunId" class="analytics-state">暂无 SUCCESS Backtest</div>
    <template v-else-if="summary">
      <AnalyticsSummaryCards :summary="summary" />
      <div v-if="summary.warnings.length" class="analytics-warning">{{ summary.warnings.join(" · ") }}</div>
      <section class="analytics-chart-grid">
        <article class="panel"><div class="panel-title"><h2>NAV / Benchmark</h2></div><AnalyticsNavChart :rows="series" /></article>
        <article class="panel"><div class="panel-title"><h2>Drawdown</h2></div><AnalyticsDrawdownChart :rows="series" :summary="summary" /></article>
      </section>

      <article class="panel analytics-section">
        <div class="analytics-section-heading">
          <div><h2>周期表现</h2><span>{{ summary.source_versions.period }}</span></div>
          <div class="segmented"><button :class="{ active: periodType === 'MONTH' }" @click="periodType = 'MONTH'">月度</button><button :class="{ active: periodType === 'YEAR' }" @click="periodType = 'YEAR'">年度</button></div>
        </div>
        <div v-if="periodMissing" class="analytics-state compact">
          周期分析尚未生成
          <button class="primary-button" :disabled="periodJobRunning" @click="generatePeriods">{{ periodJobRunning ? "生成中" : "生成周期分析" }}</button>
        </div>
        <AnalyticsPeriodTable v-else :rows="visiblePeriods" />
      </article>

      <article class="panel analytics-section">
        <div class="analytics-section-heading"><div><h2>Trade Episodes</h2><span>直接读取 trade_v1，不在前端重算 PnL</span></div></div>
        <div class="analytics-filters">
          <select v-model="episodeStatus"><option value="">全部状态</option><option>OPEN</option><option>CLOSED</option></select>
          <select v-model="episodeClassification"><option value="">全部分类</option><option>WIN</option><option>LOSS</option><option>BREAKEVEN</option></select>
          <input v-model="episodeCode" placeholder="股票代码" />
          <button @click="episodePage = 0; loadEpisodes()">查询</button>
        </div>
        <div class="analytics-table-wrap"><table class="analytics-table"><thead><tr><th>代码</th><th>#</th><th>状态</th><th>Entry</th><th>Exit</th><th>持有日</th><th>Realized PnL</th><th>Unrealized</th><th>Return</th><th>Cost</th><th>分类</th></tr></thead><tbody><tr v-for="row in episodes" :key="`${row.ts_code}-${row.episode_no}`"><td>{{ row.ts_code }}</td><td>{{ row.episode_no }}</td><td>{{ row.status }}</td><td>{{ row.entry_date }}</td><td>{{ row.exit_date || '--' }}</td><td>{{ row.holding_trade_days }}</td><td>{{ row.realized_pnl }}</td><td>{{ row.unrealized_pnl_end }}</td><td>{{ row.episode_return ?? '--' }}</td><td>{{ row.total_execution_cost }}</td><td>{{ row.classification || '--' }}</td></tr><tr v-if="!episodes.length"><td colspan="11" class="analytics-empty">暂无 Episode</td></tr></tbody></table></div>
        <div class="analytics-pagination"><button :disabled="episodePage === 0" @click="episodePage -= 1; loadEpisodes()">上一页</button><span>第 {{ episodePage + 1 }} 页 · 共 {{ episodeTotal }} 条</span><button :disabled="episodePage * episodeLimit + episodes.length >= episodeTotal" @click="episodePage += 1; loadEpisodes()">下一页</button></div>
      </article>

      <article class="panel analytics-section">
        <div class="analytics-section-heading"><div><h2>策略对比</h2><span>选择 2~10 个同口径回测；排序仅发生在浏览器</span></div><button class="primary-button" :disabled="compareSelection.length < 2 || compareSelection.length > 10" @click="runCompare">开始对比</button></div>
        <div class="analytics-run-picker"><label v-for="run in successRuns" :key="run.id"><input v-model="compareSelection" type="checkbox" :value="run.id" :disabled="compareSelection.length >= 10 && !compareSelection.includes(run.id)" />{{ run.name || run.id.slice(0, 8) }}</label></div>
        <div v-if="compareError" class="analytics-state analytics-error compact">{{ compareError }}</div>
        <AnalyticsCompareTable v-if="compareRows.length" :items="compareRows" />
      </article>
    </template>
  </section>
</template>
