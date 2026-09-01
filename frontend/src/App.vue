<script setup lang="ts">
import { BarChart, CandlestickChart, LineChart, PieChart } from "echarts/charts";
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  TooltipComponent
} from "echarts/components";
import { init, use, type EChartsType } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";

import {
  enqueueBackfillJob,
  enqueueRecalculateJob,
  fetchDashboardSummary,
  fetchDataCalendar,
  fetchDataCoverage,
  fetchDecayPool,
  fetchJobs,
  fetchRealtimeKline,
  fetchResearchStats,
  fetchRightSidePool,
  fetchSectorHeat,
  fetchSystemStatus,
  fetchTrendPool
} from "./services/api";
import type {
  DashboardSummary,
  DataCalendarRow,
  DataCoverageRow,
  JobRun,
  RealtimeKlineResponse,
  RealtimeKlineRow,
  ResearchStats,
  SectorHeat,
  StockPoolItem,
  SystemStatus
} from "./types";

type ViewKey = "overview" | "data" | "long" | "short";
type PoolTab = "right" | "trend";
type DataPanelKey = "recalc" | "tasks" | "coverage";

use([
  BarChart,
  CandlestickChart,
  LineChart,
  PieChart,
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  CanvasRenderer
]);

const loading = ref(true);
const submittingIngestion = ref(false);
const submittingRecalculation = ref(false);
const errorMessage = ref("");
const jobMessage = ref("");
const activeView = ref<ViewKey>("overview");
const activePool = ref<PoolTab>("right");
const collapsedDataPanels = ref<Record<DataPanelKey, boolean>>({
  recalc: false,
  tasks: false,
  coverage: false
});
const backfillStart = ref(daysAgoIso(30));
const backfillEnd = ref(todayIso());
const recalcStart = ref(daysAgoIso(180));
const recalcEnd = ref(todayIso());
const evaluateSignals = ref(false);
const recalcEvaluateSignals = ref(true);
const calendarMonth = ref(todayIso().slice(0, 7));
const selectedCalendarDate = ref("");
const coveragePage = ref(1);
const coveragePageSize = ref(20);
const selectedKlineStock = ref<StockPoolItem | null>(null);
const selectedKlineDays = ref(180);
const klineData = ref<RealtimeKlineResponse | null>(null);
const klineLoading = ref(false);
const klineError = ref("");
const status = ref<SystemStatus | null>(null);
const summary = ref<DashboardSummary | null>(null);
const sectorHeat = ref<SectorHeat[]>([]);
const dataCoverage = ref<DataCoverageRow[]>([]);
const dataCalendar = ref<DataCalendarRow[]>([]);
const jobs = ref<JobRun[]>([]);
const rightSidePool = ref<StockPoolItem[]>([]);
const trendPool = ref<StockPoolItem[]>([]);
const decayPool = ref<StockPoolItem[]>([]);
const researchStats = ref<ResearchStats | null>(null);
const marketChartRef = ref<HTMLDivElement | null>(null);
const sectorChartRef = ref<HTMLDivElement | null>(null);
const klineChartRef = ref<HTMLDivElement | null>(null);
let marketChart: EChartsType | null = null;
let sectorChart: EChartsType | null = null;
let klineChart: EChartsType | null = null;
let jobPollTimer: number | undefined;

const navItems: Array<{ key: ViewKey; label: string; description: string }> = [
  { key: "overview", label: "总览", description: "市场状态与后验表现" },
  { key: "data", label: "数据", description: "覆盖、拉取和任务进度" },
  { key: "long", label: "长线", description: "右侧池、趋势池、行业热度" },
  { key: "short", label: "短线", description: "风险池、信号和短期动量" }
];

const activeNav = computed(() => navItems.find((item) => item.key === activeView.value));

const currentPool = computed(() => {
  if (activePool.value === "trend") return trendPool.value;
  return rightSidePool.value;
});

const shortSectorRows = computed(() =>
  [...sectorHeat.value]
    .sort((left, right) => (right.heat_momentum3 ?? -999) - (left.heat_momentum3 ?? -999))
    .slice(0, 12)
);

const activeJob = computed(() =>
  jobs.value.find((job) => ["QUEUED", "RUNNING"].includes(job.status))
);

const latestJobs = computed(() => jobs.value.slice(0, 5));

const coveragePageSizeOptions = [10, 20, 50, 100];
const klineDayOptions = [90, 180, 365];

const coverageTotalPages = computed(() =>
  Math.max(1, Math.ceil(dataCoverage.value.length / coveragePageSize.value))
);

const pagedDataCoverage = computed(() => {
  const start = (coveragePage.value - 1) * coveragePageSize.value;
  return dataCoverage.value.slice(start, start + coveragePageSize.value);
});

const coveragePageStart = computed(() =>
  dataCoverage.value.length ? (coveragePage.value - 1) * coveragePageSize.value + 1 : 0
);

const coveragePageEnd = computed(() =>
  Math.min(dataCoverage.value.length, coveragePage.value * coveragePageSize.value)
);

const klineTitle = computed(() => {
  const stock = selectedKlineStock.value;
  if (!stock) return "实时 K 线";
  return `${stock.name || stock.ts_code} ${stock.ts_code}`;
});

const calendarRowsByDate = computed(() => {
  const rows = new Map<string, DataCalendarRow>();
  for (const row of dataCalendar.value) rows.set(row.date, row);
  return rows;
});

const calendarCells = computed(() => buildCalendarCells(calendarMonth.value, calendarRowsByDate.value));

const calendarMonthTitle = computed(() => {
  const [year, month] = calendarMonth.value.split("-");
  return `${year} 年 ${Number(month)} 月`;
});

const selectedCalendarRow = computed(() =>
  selectedCalendarDate.value ? calendarRowsByDate.value.get(selectedCalendarDate.value) : null
);

const calendarSummary = computed(() => {
  const openRows = dataCalendar.value.filter((row) => row.is_open !== false);
  return {
    open: openRows.length,
    pulled: openRows.filter((row) => row.stock_daily_rows > 0).length,
    analyzed: openRows.filter((row) => row.factor_rows > 0 && row.state_rows > 0).length,
    complete: openRows.filter((row) => row.coverage_status === "COMPLETE").length
  };
});

watch([dataCoverage, coveragePageSize], clampCoveragePage);

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
      nextDataCalendar,
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
      fetchDataCalendar(monthStartIso(calendarMonth.value), monthEndIso(calendarMonth.value)),
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
    dataCalendar.value = nextDataCalendar;
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
      await loadCoverageCalendar();
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "任务状态刷新失败";
  }
}

async function loadCoverageCalendar() {
  dataCalendar.value = await fetchDataCalendar(
    monthStartIso(calendarMonth.value),
    monthEndIso(calendarMonth.value)
  );
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
    await loadCoverageCalendar();
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "任务提交失败";
  } finally {
    submittingIngestion.value = false;
  }
}

async function submitRecalculation() {
  errorMessage.value = "";
  jobMessage.value = "";
  if (!recalcStart.value || !recalcEnd.value) {
    errorMessage.value = "请选择补算开始日期和结束日期";
    return;
  }
  if (recalcEnd.value < recalcStart.value) {
    errorMessage.value = "补算结束日期不能早于开始日期";
    return;
  }

  submittingRecalculation.value = true;
  try {
    const job = await enqueueRecalculateJob({
      start: recalcStart.value,
      end: recalcEnd.value,
      evaluate_signals: recalcEvaluateSignals.value
    });
    jobMessage.value = jobMessageText(job);
    await refreshJobStatus();
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "补算任务提交失败";
  } finally {
    submittingRecalculation.value = false;
  }
}

async function openRealtimeKline(row: StockPoolItem) {
  selectedKlineStock.value = row;
  await loadRealtimeKline();
}

async function loadRealtimeKline() {
  const stock = selectedKlineStock.value;
  if (!stock) return;
  klineLoading.value = true;
  klineError.value = "";
  klineData.value = null;
  try {
    klineData.value = await fetchRealtimeKline(stock.ts_code, selectedKlineDays.value);
    klineLoading.value = false;
    await nextTick();
    renderKlineChart();
  } catch (error) {
    klineError.value = error instanceof Error ? error.message : "K 线加载失败";
    klineLoading.value = false;
  }
}

async function setKlineDays(days: number) {
  selectedKlineDays.value = days;
  if (selectedKlineStock.value) {
    await loadRealtimeKline();
  }
}

function closeRealtimeKline() {
  selectedKlineStock.value = null;
  klineData.value = null;
  klineError.value = "";
  klineChart?.dispose();
  klineChart = null;
}

function renderCharts() {
  renderMarketChart();
  renderSectorChart();
  renderKlineChart();
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
        label: { show: false },
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

function renderKlineChart() {
  if (!klineChartRef.value || !klineData.value?.rows.length) return;
  klineChart ||= init(klineChartRef.value);
  const rows = klineData.value.rows.filter(
    (row) =>
      row.open !== null && row.close !== null && row.low !== null && row.high !== null
  );
  const dates = rows.map((row) => row.trade_date);
  const candles = rows.map((row) => [row.open, row.close, row.low, row.high]);
  const closes = rows.map((row) => row.close);
  klineChart.setOption({
    color: ["#2563eb", "#16a34a", "#f97316"],
    animation: false,
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "cross" },
      valueFormatter: (value: unknown) =>
        typeof value === "number" ? value.toFixed(2) : `${value ?? "--"}`
    },
    legend: {
      top: 0,
      data: ["K线", "MA5", "MA20", "MA60"],
      textStyle: { color: "#64748b" }
    },
    grid: { left: 56, right: 20, top: 34, bottom: 54 },
    xAxis: {
      type: "category",
      data: dates,
      boundaryGap: true,
      axisLabel: { color: "#64748b" },
      axisLine: { lineStyle: { color: "#cbd5e1" } }
    },
    yAxis: {
      type: "value",
      scale: true,
      axisLabel: { color: "#64748b" },
      splitLine: { lineStyle: { color: "#e2e8f0" } }
    },
    dataZoom: [
      { type: "inside", start: 45, end: 100 },
      { type: "slider", height: 22, bottom: 16, start: 45, end: 100 }
    ],
    series: [
      {
        name: "K线",
        type: "candlestick",
        data: candles,
        itemStyle: {
          color: "#dc2626",
          color0: "#16a34a",
          borderColor: "#dc2626",
          borderColor0: "#16a34a"
        }
      },
      lineSeries("MA5", movingAverage(closes, 5)),
      lineSeries("MA20", movingAverage(closes, 20)),
      lineSeries("MA60", movingAverage(closes, 60))
    ]
  });
}

function handleResize() {
  marketChart?.resize();
  sectorChart?.resize();
  klineChart?.resize();
}

async function setActiveView(view: ViewKey) {
  activeView.value = view;
  await nextTick();
  renderCharts();
}

async function shiftCalendarMonth(delta: number) {
  calendarMonth.value = shiftMonth(calendarMonth.value, delta);
  selectedCalendarDate.value = "";
  await loadCoverageCalendar();
}

function selectCalendarDay(row: DataCalendarRow | null) {
  selectedCalendarDate.value = row?.date || "";
}

function movingAverage(values: Array<RealtimeKlineRow["close"]>, windowSize: number) {
  return values.map((_, index) => {
    if (index < windowSize - 1) return null;
    const windowValues = values.slice(index + 1 - windowSize, index + 1);
    if (windowValues.some((value) => value === null)) return null;
    const numericValues = windowValues as number[];
    const sum = numericValues.reduce((total, value) => total + value, 0);
    return Number((sum / windowSize).toFixed(2));
  });
}

function lineSeries(name: string, data: Array<number | null>) {
  return {
    name,
    type: "line",
    data,
    smooth: true,
    symbol: "none",
    lineStyle: { width: 1.4 }
  };
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

function monthStartIso(month: string) {
  return `${month}-01`;
}

function monthEndIso(month: string) {
  const [year, monthNumber] = month.split("-").map(Number);
  const date = new Date(year, monthNumber, 0);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(
    date.getDate()
  ).padStart(2, "0")}`;
}

function shiftMonth(month: string, delta: number) {
  const [year, monthNumber] = month.split("-").map(Number);
  const date = new Date(year, monthNumber - 1 + delta, 1);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
}

function buildCalendarCells(month: string, rowsByDate: Map<string, DataCalendarRow>) {
  const [year, monthNumber] = month.split("-").map(Number);
  const first = new Date(year, monthNumber - 1, 1);
  const last = new Date(year, monthNumber, 0);
  const leading = (first.getDay() + 6) % 7;
  const cells: Array<{ key: string; day: number | null; row: DataCalendarRow | null }> = [];
  for (let index = 0; index < leading; index += 1) {
    cells.push({ key: `blank-start-${index}`, day: null, row: null });
  }
  for (let day = 1; day <= last.getDate(); day += 1) {
    const key = `${month}-${String(day).padStart(2, "0")}`;
    cells.push({ key, day, row: rowsByDate.get(key) || null });
  }
  while (cells.length % 7 !== 0) {
    cells.push({ key: `blank-end-${cells.length}`, day: null, row: null });
  }
  return cells;
}

function calendarStatusLabel(status: DataCalendarRow["coverage_status"] | undefined) {
  const map: Record<DataCalendarRow["coverage_status"], string> = {
    CLOSED: "休",
    MISSING: "缺",
    RAW_ONLY: "原",
    ANALYZED: "算",
    COMPLETE: "全"
  };
  return status ? map[status] : "--";
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
  const factorChunkIndex =
    typeof job.metadata.factor_chunk_index === "number" ? job.metadata.factor_chunk_index : null;
  const factorChunkCount =
    typeof job.metadata.factor_chunk_count === "number" ? job.metadata.factor_chunk_count : null;
  const factorChunkStart =
    typeof job.metadata.factor_chunk_start === "string" ? job.metadata.factor_chunk_start : null;
  const factorChunkEnd =
    typeof job.metadata.factor_chunk_end === "string" ? job.metadata.factor_chunk_end : null;
  const datePart = start && end ? `${start} 到 ${end}` : job.target_trade_date || "--";
  const chunkPart = factorChunkIndex !== null && factorChunkCount !== null
    ? ` / 因子分块 ${factorChunkIndex}/${factorChunkCount}`
    : "";
  const chunkDatePart = factorChunkStart && factorChunkEnd
    ? `：${factorChunkStart} 到 ${factorChunkEnd}`
    : "";
  const progressPart = currentIndex !== null && total !== null
    ? ` / 第 ${currentIndex}/${total} 个交易日`
    : completed !== null && total !== null
      ? ` / 已完成 ${completed}/${total} 个交易日`
      : "";
  const currentPart = current ? ` / 当前 ${current}` : "";
  return `${datePart}${chunkPart}${chunkDatePart}${progressPart}${currentPart}`;
}

function rowCountHint(job: JobRun) {
  const isFactorRecalculate =
    job.job_type === "recalculate" &&
    typeof job.metadata.factor_chunk_index === "number" &&
    job.step?.startsWith("90 factors ");
  return isFactorRecalculate ? "当前因子分块完成后更新行数" : "";
}

function clampCoveragePage() {
  coveragePage.value = Math.min(Math.max(coveragePage.value, 1), coverageTotalPages.value);
}

function setCoveragePage(page: number) {
  coveragePage.value = Math.min(Math.max(page, 1), coverageTotalPages.value);
}

function toggleDataPanel(panel: DataPanelKey) {
  collapsedDataPanels.value[panel] = !collapsedDataPanels.value[panel];
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
  <main class="workspace-shell">
    <aside class="side-nav">
      <div class="brand-block">
        <div class="brand-logo">空</div>
        <div>
          <h1>空间</h1>
          <p>A 股机会研究工作台</p>
        </div>
      </div>
      <div class="data-badges">
        <span>raw {{ status?.latest_raw_date || "--" }}</span>
        <span>factor {{ status?.latest_factor_date || "--" }}</span>
      </div>
      <nav class="nav-menu" aria-label="功能目录">
        <button
          v-for="item in navItems"
          :key="item.key"
          class="nav-button"
          :class="{ active: activeView === item.key }"
          type="button"
          @click="setActiveView(item.key)"
        >
          <span>{{ item.label }}</span>
          <small>{{ item.description }}</small>
        </button>
      </nav>
      <div class="nav-footer">
        <span>状态日期</span>
        <strong>{{ status?.latest_state_date || "--" }}</strong>
      </div>
    </aside>

    <section class="content-shell">
      <header class="topbar">
        <div class="page-heading">
          <span>当前页面</span>
          <h2>{{ activeNav?.label || "总览" }}</h2>
          <p>{{ activeNav?.description || "市场状态与后验表现" }}</p>
        </div>
        <button class="refresh-button" :disabled="loading" @click="loadData">
          {{ loading ? "刷新中" : "刷新" }}
        </button>
      </header>

      <div v-if="errorMessage" class="error-strip">{{ errorMessage }}</div>
      <div v-if="jobMessage" class="success-strip">{{ jobMessage }}</div>

      <section v-show="activeView === 'overview'" class="view-stack">
        <section class="metric-grid">
          <article
            v-for="metric in metrics"
            :key="metric.label"
            class="metric-card"
            :class="metric.tone"
          >
            <span>{{ metric.label }}</span>
            <strong>{{ metric.value }}</strong>
            <small>{{ metric.sub || "" }}</small>
          </article>
        </section>

        <section class="dashboard-grid overview-grid">
          <article class="panel">
            <div class="panel-title">
              <h2>市场分布</h2>
              <span>{{ summary?.market?.regime || "NO_DATA" }}</span>
            </div>
            <div ref="marketChartRef" class="chart"></div>
          </article>

          <article class="panel">
            <div class="panel-title">
              <h2>行业热度</h2>
              <span>{{ sectorHeat.length }} 个行业</span>
            </div>
            <div v-if="sectorHeat.length" ref="sectorChartRef" class="chart"></div>
            <div v-else class="empty-chart">暂无行业热度数据</div>
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
        </section>
      </section>

      <section v-show="activeView === 'data'" class="view-stack">
        <article class="panel action-panel" :class="{ collapsed: collapsedDataPanels.recalc }">
          <div class="panel-title coverage-title">
            <div>
              <h2>
                <button
                  class="panel-title-button"
                  type="button"
                  :aria-expanded="!collapsedDataPanels.recalc"
                  @click="toggleDataPanel('recalc')"
                >
                  <span class="collapse-icon" aria-hidden="true"></span>
                  <span>补算因子与股票池</span>
                </button>
              </h2>
              <span>原始行情补充后，用这里重新计算分析结果</span>
            </div>
            <form class="coverage-actions" @submit.prevent="submitRecalculation">
              <label>
                <span>开始</span>
                <input v-model="recalcStart" type="date" />
              </label>
              <label>
                <span>结束</span>
                <input v-model="recalcEnd" type="date" />
              </label>
              <label class="checkbox-label">
                <input v-model="recalcEvaluateSignals" type="checkbox" />
                <span>评估信号</span>
              </label>
              <button class="primary-button" type="submit" :disabled="submittingRecalculation">
                {{ submittingRecalculation ? "提交中" : "开始补算" }}
              </button>
            </form>
          </div>
          <div v-show="!collapsedDataPanels.recalc" class="panel-collapsible">
            <div class="recalc-flow">
              <span>因子</span>
              <span>市场</span>
              <span>行业</span>
              <span>状态</span>
              <span>信号</span>
            </div>
          </div>
        </article>

        <article class="panel" :class="{ collapsed: collapsedDataPanels.tasks }">
          <div class="panel-title coverage-title">
            <div>
              <h2>
                <button
                  class="panel-title-button"
                  type="button"
                  :aria-expanded="!collapsedDataPanels.tasks"
                  @click="toggleDataPanel('tasks')"
                >
                  <span class="collapse-icon" aria-hidden="true"></span>
                  <span>拉取数据与任务</span>
                </button>
              </h2>
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
          <div v-show="!collapsedDataPanels.tasks" class="job-status-grid panel-collapsible">
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
                <small>
                  已写入/处理行数：{{ activeJob.row_count }}
                  <template v-if="rowCountHint(activeJob)"> / {{ rowCountHint(activeJob) }}</template>
                </small>
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
        </article>

        <article class="panel" :class="{ collapsed: collapsedDataPanels.coverage }">
          <div class="panel-title coverage-title">
            <div>
              <h2>
                <button
                  class="panel-title-button"
                  type="button"
                  :aria-expanded="!collapsedDataPanels.coverage"
                  @click="toggleDataPanel('coverage')"
                >
                  <span class="collapse-icon" aria-hidden="true"></span>
                  <span>数据覆盖日历</span>
                </button>
              </h2>
              <span>
                已拉 {{ calendarSummary.pulled }} / 开市 {{ calendarSummary.open }}，
                已算 {{ calendarSummary.analyzed }}
              </span>
            </div>
            <div class="calendar-controls">
              <button type="button" @click="shiftCalendarMonth(-1)">上月</button>
              <strong>{{ calendarMonthTitle }}</strong>
              <button type="button" @click="shiftCalendarMonth(1)">下月</button>
            </div>
          </div>
          <div v-show="!collapsedDataPanels.coverage" class="panel-collapsible">
            <div class="calendar-legend">
              <span class="analyzed">算 已算基础</span>
              <span class="complete">全 行业完成</span>
              <span class="raw-only">原 已拉未算</span>
              <span class="missing">缺 未拉取</span>
              <span class="closed">休 休市</span>
            </div>
            <div class="coverage-calendar-layout">
              <section class="coverage-calendar">
                <div class="calendar-week">一</div>
                <div class="calendar-week">二</div>
                <div class="calendar-week">三</div>
                <div class="calendar-week">四</div>
                <div class="calendar-week">五</div>
                <div class="calendar-week">六</div>
                <div class="calendar-week">日</div>
                <button
                  v-for="cell in calendarCells"
                  :key="cell.key"
                  class="calendar-day"
                  :class="[
                    cell.row?.coverage_status.toLowerCase(),
                    { blank: !cell.row, selected: selectedCalendarDate === cell.row?.date }
                  ]"
                  type="button"
                  :disabled="!cell.row"
                  :title="cell.row ? `${cell.row.date} ${calendarStatusLabel(cell.row.coverage_status)}` : ''"
                  @click="selectCalendarDay(cell.row)"
                >
                  <span>{{ cell.day || "" }}</span>
                  <strong v-if="cell.row">{{ calendarStatusLabel(cell.row.coverage_status) }}</strong>
                </button>
              </section>
              <aside class="calendar-detail">
                <template v-if="selectedCalendarRow">
                  <span>{{ selectedCalendarRow.date }}</span>
                  <strong>{{ calendarStatusLabel(selectedCalendarRow.coverage_status) }}</strong>
                  <dl>
                    <div>
                      <dt>日线</dt>
                      <dd>{{ selectedCalendarRow.stock_daily_rows }}</dd>
                    </div>
                    <div>
                      <dt>因子</dt>
                      <dd>{{ selectedCalendarRow.factor_rows }}</dd>
                    </div>
                    <div>
                      <dt>行业</dt>
                      <dd>{{ selectedCalendarRow.sector_factor_rows }}</dd>
                    </div>
                    <div>
                      <dt>状态</dt>
                      <dd>{{ selectedCalendarRow.state_rows }}</dd>
                    </div>
                    <div>
                      <dt>信号</dt>
                      <dd>{{ selectedCalendarRow.signal_rows }}</dd>
                    </div>
                    <div>
                      <dt>后验</dt>
                      <dd>{{ selectedCalendarRow.signal_eval_rows }}</dd>
                    </div>
                  </dl>
                </template>
                <template v-else>
                  <span>日期明细</span>
                  <strong>点击日历查看</strong>
                </template>
              </aside>
            </div>
            <div class="coverage-table-toolbar">
              <span>
                覆盖明细 {{ coveragePageStart }}-{{ coveragePageEnd }} / {{ dataCoverage.length }}
              </span>
              <div class="pagination-controls">
                <label>
                  <span>每页</span>
                  <select v-model.number="coveragePageSize" aria-label="覆盖明细每页条数">
                    <option v-for="size in coveragePageSizeOptions" :key="size" :value="size">
                      {{ size }}
                    </option>
                  </select>
                </label>
                <button
                  type="button"
                  :disabled="coveragePage <= 1"
                  @click="setCoveragePage(coveragePage - 1)"
                >
                  上一页
                </button>
                <strong>{{ coveragePage }} / {{ coverageTotalPages }}</strong>
                <button
                  type="button"
                  :disabled="coveragePage >= coverageTotalPages"
                  @click="setCoveragePage(coveragePage + 1)"
                >
                  下一页
                </button>
              </div>
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
                  <tr v-for="row in pagedDataCoverage" :key="row.trade_date">
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
          </div>
        </article>
      </section>

      <section v-show="activeView === 'long'" class="view-stack">
        <article class="panel">
          <div class="panel-title">
            <h2>长线股票池</h2>
            <div class="segmented">
              <button :class="{ active: activePool === 'right' }" @click="activePool = 'right'">
                右侧
              </button>
              <button :class="{ active: activePool === 'trend' }" @click="activePool = 'trend'">
                趋势
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
                  <td>
                    <button class="stock-code-button" type="button" @click="openRealtimeKline(row)">
                      {{ row.ts_code }}
                    </button>
                  </td>
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
            <h2>长线行业</h2>
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
      </section>

      <section v-show="activeView === 'short'" class="view-stack">
        <section class="dashboard-grid short-grid">
          <article class="panel wide">
            <div class="panel-title">
              <h2>短线风险池</h2>
              <span>衰退 / 破位观察</span>
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
                  <tr v-for="row in decayPool" :key="`${row.ts_code}-${row.trade_date}`">
                    <td>
                      <button class="stock-code-button" type="button" @click="openRealtimeKline(row)">
                        {{ row.ts_code }}
                      </button>
                    </td>
                    <td>{{ row.name || "--" }}</td>
                    <td><span class="state-pill warning">{{ row.state }}</span></td>
                    <td>{{ formatNumber(row.opportunity_score, 1) }}</td>
                    <td>{{ formatNumber(row.right_side_score, 1) }}</td>
                    <td>{{ formatNumber(row.trend_score, 1) }}</td>
                    <td>{{ row.sector_name || row.industry || "--" }}</td>
                    <td class="reason-cell">{{ reasonText(row.reason_codes) }}</td>
                  </tr>
                  <tr v-if="!decayPool.length">
                    <td colspan="8" class="empty-cell">暂无短线风险股票</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </article>

          <article class="panel">
            <div class="panel-title">
              <h2>信号计数</h2>
              <span>{{ summary?.trade_date || "--" }}</span>
            </div>
            <div class="signal-list">
              <div v-for="row in summary?.signal_counts || []" :key="row.signal_type">
                <span>{{ row.signal_type }}</span>
                <strong>{{ row.count }}</strong>
              </div>
              <div v-if="!(summary?.signal_counts || []).length" class="empty-block compact-empty">
                暂无策略信号
              </div>
            </div>
          </article>

          <article class="panel wide">
            <div class="panel-title">
              <h2>短线行业动量</h2>
              <span>按 Heat Momentum 3 排序</span>
            </div>
            <div class="sector-list">
              <div v-for="row in shortSectorRows" :key="row.sector_id" class="sector-row">
                <span class="sector-rank">{{ row.heat_rank ?? "--" }}</span>
                <span class="sector-name">{{ row.name || row.sector_name || row.sector_id }}</span>
                <div class="heat-track">
                  <i :style="{ width: `${Math.max(0, Math.min(row.heat_score ?? 0, 100))}%` }"></i>
                </div>
                <strong>{{ formatNumber(row.heat_momentum3, 1) }}</strong>
                <small>{{ row.lifecycle || "--" }}</small>
              </div>
              <div v-if="!shortSectorRows.length" class="empty-block">暂无行业动量数据</div>
            </div>
          </article>
        </section>
      </section>
    </section>

    <div v-if="selectedKlineStock" class="modal-backdrop" @click.self="closeRealtimeKline">
      <section class="kline-modal" role="dialog" aria-modal="true" :aria-label="klineTitle">
        <header class="kline-header">
          <div>
            <span>实时 K 线</span>
            <h2>{{ klineTitle }}</h2>
          </div>
          <div class="kline-actions">
            <div class="segmented">
              <button
                v-for="days in klineDayOptions"
                :key="days"
                type="button"
                :class="{ active: selectedKlineDays === days }"
                @click="setKlineDays(days)"
              >
                {{ days }}日
              </button>
            </div>
            <button class="ghost-button" type="button" :disabled="klineLoading" @click="loadRealtimeKline">
              {{ klineLoading ? "加载中" : "刷新" }}
            </button>
            <button class="icon-button" type="button" aria-label="关闭" @click="closeRealtimeKline">
              ×
            </button>
          </div>
        </header>
        <div class="kline-meta">
          <span>{{ klineData?.start || "--" }} 到 {{ klineData?.end || "--" }}</span>
          <span>{{ klineData?.rows.length || 0 }} 个交易日</span>
          <span>{{ klineData?.source || "tushare" }} / 不入库</span>
        </div>
        <div v-if="klineError" class="empty-block kline-error">{{ klineError }}</div>
        <div v-else-if="klineLoading" class="empty-block">加载中</div>
        <div v-else-if="klineData?.rows.length" ref="klineChartRef" class="kline-chart"></div>
        <div v-else class="empty-block">暂无 K 线数据</div>
      </section>
    </div>
  </main>
</template>
