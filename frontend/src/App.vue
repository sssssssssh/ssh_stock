<script setup lang="ts">
import { BarChart, PieChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { init, use, type EChartsType } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { computed, nextTick, onMounted, onUnmounted, ref } from "vue";

import {
  enqueueBackfillJob,
  fetchDashboardSummary,
  fetchDataCoverage,
  fetchDecayPool,
  fetchJobs,
  fetchResearchStats,
  fetchRightSidePool,
  fetchSectorHeat,
  fetchSystemStatus,
  fetchTrendPool
} from "./services/api";
import type {
  DashboardSummary,
  DataCoverageRow,
  JobRun,
  ResearchStats,
  SectorHeat,
  StockPoolItem,
  SystemStatus
} from "./types";

type PoolTab = "right" | "trend" | "decay";

use([BarChart, PieChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer]);

const loading = ref(true);
const submittingIngestion = ref(false);
const errorMessage = ref("");
const jobMessage = ref("");
const activePool = ref<PoolTab>("right");
const backfillStart = ref(daysAgoIso(30));
const backfillEnd = ref(todayIso());
const evaluateSignals = ref(false);
const status = ref<SystemStatus | null>(null);
const summary = ref<DashboardSummary | null>(null);
const sectorHeat = ref<SectorHeat[]>([]);
const dataCoverage = ref<DataCoverageRow[]>([]);
const jobs = ref<JobRun[]>([]);
const rightSidePool = ref<StockPoolItem[]>([]);
const trendPool = ref<StockPoolItem[]>([]);
const decayPool = ref<StockPoolItem[]>([]);
const researchStats = ref<ResearchStats | null>(null);
const marketChartRef = ref<HTMLDivElement | null>(null);
const sectorChartRef = ref<HTMLDivElement | null>(null);
let marketChart: EChartsType | null = null;
let sectorChart: EChartsType | null = null;
let jobPollTimer: number | undefined;

const currentPool = computed(() => {
  if (activePool.value === "trend") return trendPool.value;
  if (activePool.value === "decay") return decayPool.value;
  return rightSidePool.value;
});

const activeJob = computed(() =>
  jobs.value.find((job) => ["QUEUED", "RUNNING"].includes(job.status))
);

const latestJobs = computed(() => jobs.value.slice(0, 5));

const metrics = computed(() => {
  const market = summary.value?.market;
  return [
    {
      label: "交易日",
      value: summary.value?.trade_date || status.value?.latest_state_date || "--",
      tone: "neutral"
    },
    {
      label: "市场温度",
      value: formatNumber(market?.market_score, 1),
      sub: market?.regime || "--",
      tone: scoreTone(market?.market_score)
    },
    {
      label: "上涨占比",
      value: formatPercent(market?.up_rate),
      sub: `${market?.up_count ?? 0} 涨 / ${market?.down_count ?? 0} 跌`,
      tone: "green"
    },
    {
      label: "右侧新增",
      value: `${rightSidePool.value.length}`,
      sub: "S3 new",
      tone: "amber"
    },
    {
      label: "趋势池",
      value: `${trendPool.value.length}`,
      sub: "S4/S5",
      tone: "blue"
    },
    {
      label: "后验样本",
      value: `${researchStats.value?.count ?? 0}`,
      sub: "RIGHT_SIDE_NEW",
      tone: "neutral"
    }
  ];
});

async function loadData() {
  loading.value = true;
  errorMessage.value = "";
  try {
    const [
      nextStatus,
      nextSummary,
      nextDataCoverage,
      nextJobs,
      nextRightSide,
      nextTrend,
      nextDecay,
      nextSectorHeat,
      nextResearchStats
    ] = await Promise.all([
      fetchSystemStatus(),
      fetchDashboardSummary(),
      fetchDataCoverage(),
      fetchJobs(),
      fetchRightSidePool(),
      fetchTrendPool(),
      fetchDecayPool(),
      fetchSectorHeat(),
      fetchResearchStats()
    ]);
    status.value = nextStatus;
    summary.value = nextSummary;
    dataCoverage.value = nextDataCoverage;
    jobs.value = nextJobs;
    rightSidePool.value = nextRightSide;
    trendPool.value = nextTrend;
    decayPool.value = nextDecay;
    sectorHeat.value = nextSectorHeat.length ? nextSectorHeat : nextSummary.sector_heat_top;
    researchStats.value = nextResearchStats;
    await nextTick();
    renderCharts();
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "加载失败";
  } finally {
    loading.value = false;
  }
}

async function refreshJobStatus() {
  try {
    jobs.value = await fetchJobs();
    if (activeJob.value) {
      dataCoverage.value = await fetchDataCoverage();
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "任务状态刷新失败";
  }
}

async function submitBackfill() {
  errorMessage.value = "";
  jobMessage.value = "";
  if (!backfillStart.value || !backfillEnd.value) {
    errorMessage.value = "请选择开始日期和结束日期";
    return;
  }
  if (backfillEnd.value < backfillStart.value) {
    errorMessage.value = "结束日期不能早于开始日期";
    return;
  }

  submittingIngestion.value = true;
  try {
    const job = await enqueueBackfillJob({
      start: backfillStart.value,
      end: backfillEnd.value,
      evaluate_signals: evaluateSignals.value
    });
    jobMessage.value = jobMessageText(job);
    await refreshJobStatus();
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "任务提交失败";
  } finally {
    submittingIngestion.value = false;
  }
}

function renderCharts() {
  renderMarketChart();
  renderSectorChart();
}

function renderMarketChart() {
  if (!marketChartRef.value) return;
  marketChart ||= init(marketChartRef.value);
  const market = summary.value?.market;
  marketChart.setOption({
    color: ["#16a34a", "#dc2626", "#94a3b8"],
    tooltip: { trigger: "item" },
    legend: { bottom: 0, textStyle: { color: "#64748b" } },
    series: [
      {
        type: "pie",
        radius: ["48%", "72%"],
        center: ["50%", "46%"],
        avoidLabelOverlap: true,
        label: { color: "#334155" },
        data: [
          { name: "上涨", value: market?.up_count ?? 0 },
          { name: "下跌", value: market?.down_count ?? 0 },
          { name: "平盘", value: market?.flat_count ?? 0 }
        ]
      }
    ]
  });
}

function renderSectorChart() {
  if (!sectorChartRef.value) return;
  sectorChart ||= init(sectorChartRef.value);
  const rows = sectorHeat.value.slice(0, 10).reverse();
  sectorChart.setOption({
    color: ["#2563eb"],
    grid: { left: 92, right: 18, top: 12, bottom: 24 },
    tooltip: { trigger: "axis" },
    xAxis: {
      type: "value",
      max: 100,
      axisLabel: { color: "#64748b" },
      splitLine: { lineStyle: { color: "#e2e8f0" } }
    },
    yAxis: {
      type: "category",
      data: rows.map((row) => row.name || row.sector_name || `${row.sector_id}`),
      axisLabel: { color: "#334155", width: 82, overflow: "truncate" }
    },
    series: [
      {
        type: "bar",
        data: rows.map((row) => row.heat_score ?? 0),
        barWidth: 14,
        itemStyle: { borderRadius: [0, 4, 4, 0] }
      }
    ]
  });
}

function handleResize() {
  marketChart?.resize();
  sectorChart?.resize();
}

window.addEventListener("resize", handleResize);

onMounted(() => {
  void loadData();
  jobPollTimer = window.setInterval(() => {
    void refreshJobStatus();
  }, 5000);
});

onUnmounted(() => {
  window.removeEventListener("resize", handleResize);
  if (jobPollTimer) {
    window.clearInterval(jobPollTimer);
  }
});

function formatNumber(value: number | null | undefined, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) return "--";
  return value.toFixed(digits);
}

function formatPercent(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "--";
  return `${(value * 100).toFixed(1)}%`;
}

function scoreTone(value: number | null | undefined) {
  if (value === null || value === undefined) return "neutral";
  if (value >= 70) return "green";
  if (value < 45) return "red";
  return "amber";
}

function reasonText(value: StockPoolItem["reason_codes"]) {
  if (!value) return "--";
  if (Array.isArray(value)) return value.join(", ");
  return Object.keys(value).join(", ");
}

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

function daysAgoIso(days: number) {
  const current = new Date();
  current.setDate(current.getDate() - days);
  return current.toISOString().slice(0, 10);
}

function jobMessageText(job: JobRun) {
  const shortId = job.id.slice(0, 8);
  return `任务已提交：${job.job_type} / ${job.status} / ${shortId}`;
}

function progressPct(job: JobRun | undefined) {
  if (!job) return 0;
  const value = job.metadata.progress_pct;
  if (typeof value === "number") return Math.max(0, Math.min(value, 100));
  if (typeof value === "string") return Math.max(0, Math.min(Number(value) || 0, 100));
  if (job.status === "SUCCESS") return 100;
  return 0;
}

function metadataText(job: JobRun) {
  const start = typeof job.metadata.start === "string" ? job.metadata.start : null;
  const end = typeof job.metadata.end === "string" ? job.metadata.end : null;
  const current =
    typeof job.metadata.current_trade_date === "string" ? job.metadata.current_trade_date : null;
  const completed =
    typeof job.metadata.completed_open_days === "number" ? job.metadata.completed_open_days : null;
  const currentIndex =
    typeof job.metadata.current_open_day_index === "number"
      ? job.metadata.current_open_day_index
      : null;
  const total = typeof job.metadata.open_days === "number" ? job.metadata.open_days : null;
  const datePart = start && end ? `${start} 到 ${end}` : job.target_trade_date || "--";
  const progressPart = currentIndex !== null && total !== null
    ? ` / 第 ${currentIndex}/${total} 个交易日`
    : completed !== null && total !== null
      ? ` / 已完成 ${completed}/${total} 个交易日`
      : "";
  const currentPart = current ? ` / 当前 ${current}` : "";
  return `${datePart}${progressPart}${currentPart}`;
}

function statusLabel(status: string) {
  const map: Record<string, string> = {
    QUEUED: "排队中",
    RUNNING: "运行中",
    SUCCESS: "已完成",
    FAILED: "失败",
    PARTIAL: "部分完成"
  };
  return map[status] || status;
}
</script>

<template>
  <main class="app-shell">
    <header class="topbar">
      <div>
        <h1>股票机会发现系统</h1>
        <p>
          raw {{ status?.latest_raw_date || "--" }} / factor
          {{ status?.latest_factor_date || "--" }} / state
          {{ status?.latest_state_date || "--" }}
        </p>
      </div>
      <button class="refresh-button" :disabled="loading" @click="loadData">
        {{ loading ? "刷新中" : "刷新" }}
      </button>
    </header>

    <div v-if="errorMessage" class="error-strip">{{ errorMessage }}</div>
    <div v-if="jobMessage" class="success-strip">{{ jobMessage }}</div>

    <section class="metric-grid">
      <article v-for="metric in metrics" :key="metric.label" class="metric-card" :class="metric.tone">
        <span>{{ metric.label }}</span>
        <strong>{{ metric.value }}</strong>
        <small>{{ metric.sub || "" }}</small>
      </article>
    </section>

    <section class="dashboard-grid">
      <article class="panel">
        <div class="panel-title">
          <h2>市场分布</h2>
          <span>{{ summary?.market?.regime || "NO_DATA" }}</span>
        </div>
        <div ref="marketChartRef" class="chart"></div>
      </article>

      <article class="panel wide">
        <div class="panel-title">
          <h2>行业热度</h2>
          <span>{{ sectorHeat.length }} 个行业</span>
        </div>
        <div ref="sectorChartRef" class="chart"></div>
      </article>

      <article class="panel xwide">
        <div class="panel-title">
          <h2>股票池</h2>
          <div class="segmented">
            <button :class="{ active: activePool === 'right' }" @click="activePool = 'right'">
              右侧
            </button>
            <button :class="{ active: activePool === 'trend' }" @click="activePool = 'trend'">
              趋势
            </button>
            <button :class="{ active: activePool === 'decay' }" @click="activePool = 'decay'">
              衰退
            </button>
          </div>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>代码</th>
                <th>名称</th>
                <th>状态</th>
                <th>机会</th>
                <th>右侧</th>
                <th>趋势</th>
                <th>行业</th>
                <th>原因</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in currentPool" :key="`${row.ts_code}-${row.trade_date}`">
                <td>{{ row.ts_code }}</td>
                <td>{{ row.name || "--" }}</td>
                <td><span class="state-pill">{{ row.state }}</span></td>
                <td>{{ formatNumber(row.opportunity_score, 1) }}</td>
                <td>{{ formatNumber(row.right_side_score, 1) }}</td>
                <td>{{ formatNumber(row.trend_score, 1) }}</td>
                <td>{{ row.sector_name || row.industry || "--" }}</td>
                <td class="reason-cell">{{ reasonText(row.reason_codes) }}</td>
              </tr>
              <tr v-if="!currentPool.length">
                <td colspan="8" class="empty-cell">暂无符合条件的股票</td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>

      <article class="panel">
        <div class="panel-title">
          <h2>信号后验</h2>
          <span>{{ researchStats?.latest_evaluated_until_date || "--" }}</span>
        </div>
        <div class="stats-stack">
          <div>
            <span>5日均值</span>
            <strong>{{ formatPercent(researchStats?.avg_ret5) }}</strong>
          </div>
          <div>
            <span>20日均值</span>
            <strong>{{ formatPercent(researchStats?.avg_ret20) }}</strong>
          </div>
          <div>
            <span>20日胜率</span>
            <strong>{{ formatPercent(researchStats?.win_rate20) }}</strong>
          </div>
          <div>
            <span>MFE20 / MAE20</span>
            <strong>
              {{ formatPercent(researchStats?.avg_mfe20) }} /
              {{ formatPercent(researchStats?.avg_mae20) }}
            </strong>
          </div>
        </div>
      </article>

      <article class="panel xwide">
        <div class="panel-title">
          <h2>行业列表</h2>
          <span>按热度排序</span>
        </div>
        <div class="sector-list">
          <div v-for="row in sectorHeat.slice(0, 20)" :key="row.sector_id" class="sector-row">
            <span class="sector-rank">{{ row.heat_rank ?? "--" }}</span>
            <span class="sector-name">{{ row.name || row.sector_name || row.sector_id }}</span>
            <div class="heat-track">
              <i :style="{ width: `${Math.max(0, Math.min(row.heat_score ?? 0, 100))}%` }"></i>
            </div>
            <strong>{{ formatNumber(row.heat_score, 1) }}</strong>
            <small>{{ row.lifecycle || "--" }}</small>
          </div>
          <div v-if="!sectorHeat.length" class="empty-block">暂无行业热度数据</div>
        </div>
      </article>

      <article class="panel xwide">
        <div class="panel-title coverage-title">
          <div>
            <h2>数据覆盖</h2>
            <span>最近 {{ dataCoverage.length }} 个交易日</span>
          </div>
          <form class="coverage-actions" @submit.prevent="submitBackfill">
            <label>
              <span>开始</span>
              <input v-model="backfillStart" type="date" />
            </label>
            <label>
              <span>结束</span>
              <input v-model="backfillEnd" type="date" />
            </label>
            <label class="checkbox-label">
              <input v-model="evaluateSignals" type="checkbox" />
              <span>评估信号</span>
            </label>
            <button class="primary-button" type="submit" :disabled="submittingIngestion">
              {{ submittingIngestion ? "提交中" : "拉取数据" }}
            </button>
          </form>
        </div>
        <div class="job-status-grid">
          <section class="job-current" :class="activeJob?.status.toLowerCase() || 'idle'">
            <div class="job-current-head">
              <span>当前任务</span>
              <strong>{{ activeJob ? statusLabel(activeJob.status) : "无运行任务" }}</strong>
            </div>
            <template v-if="activeJob">
              <div class="job-progress-track">
                <i :style="{ width: `${progressPct(activeJob)}%` }"></i>
              </div>
              <div class="job-progress-meta">
                <span>{{ formatNumber(progressPct(activeJob), 1) }}%</span>
                <span>{{ activeJob.step || "--" }}</span>
              </div>
              <p>{{ metadataText(activeJob) }}</p>
              <p v-if="activeJob.error_message" class="job-error">
                {{ activeJob.error_message }}
              </p>
              <small>已写入/处理行数：{{ activeJob.row_count }}</small>
            </template>
            <template v-else>
              <p>最近状态会每 5 秒自动刷新</p>
            </template>
          </section>
          <section class="job-list">
            <div v-for="job in latestJobs" :key="job.id" class="job-row">
              <span class="job-type">{{ job.job_type }}</span>
              <span class="job-status" :class="job.status.toLowerCase()">
                {{ statusLabel(job.status) }}
              </span>
              <span class="job-step">{{ job.step || "--" }}</span>
              <span class="job-date">{{ metadataText(job) }}</span>
              <span v-if="job.error_message" class="job-error-line">
                {{ job.error_message }}
              </span>
            </div>
            <div v-if="!latestJobs.length" class="empty-block compact-empty">暂无任务记录</div>
          </section>
        </div>
        <div class="table-wrap compact">
          <table>
            <thead>
              <tr>
                <th>日期</th>
                <th>日线</th>
                <th>指标</th>
                <th>复权</th>
                <th>指数</th>
                <th>因子</th>
                <th>市场</th>
                <th>行业</th>
                <th>状态</th>
                <th>信号</th>
                <th>后验</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in dataCoverage" :key="row.trade_date">
                <td>{{ row.trade_date }}</td>
                <td>{{ row.stock_daily_rows }}</td>
                <td>{{ row.daily_basic_rows }}</td>
                <td>{{ row.adj_factor_rows }}</td>
                <td>{{ row.index_daily_rows }}</td>
                <td>{{ row.factor_rows }}</td>
                <td>{{ row.market_rows }}</td>
                <td>{{ row.sector_factor_rows }}</td>
                <td>{{ row.state_rows }}</td>
                <td>{{ row.signal_rows }}</td>
                <td>{{ row.signal_eval_rows }}</td>
              </tr>
              <tr v-if="!dataCoverage.length">
                <td colspan="11" class="empty-cell">暂无已拉取交易日</td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>
    </section>
  </main>
</template>
