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

import DashboardView from "./components/DashboardView.vue";
import DataQuality from "./components/DataQuality.vue";
import JobCenter from "./components/JobCenter.vue";
import OpportunityTable from "./components/OpportunityTable.vue";
import ResearchSummary from "./components/ResearchSummary.vue";
import ResearchLab from "./components/ResearchLab.vue";
import SectorHeatPanel from "./components/SectorHeat.vue";
import StockPool from "./components/StockPool.vue";
import ThemeDetail from "./components/ThemeDetail.vue";
import ThemeHeatTable from "./components/ThemeHeatTable.vue";
import LoginView from "./components/LoginView.vue";
import ChangePasswordView from "./components/ChangePasswordView.vue";
import UserMenu from "./components/UserMenu.vue";
import { fetchCurrentUser, logout } from "./services/auth";
import {
  enqueueBackfillJob,
  enqueueRecalculateJob,
  enqueueSyncBasicJob,
  fetchDashboardSummary,
  fetchDataCalendar,
  fetchDataCoverage,
  fetchDecayPool,
  fetchJobs,
  fetchLeftReversal,
  fetchOpportunityRightSide,
  fetchOpportunityTrends,
  fetchRealtimeKline,
  fetchResearchStats,
  fetchRightSidePool,
  fetchSectorHeat,
  fetchSystemStatus,
  fetchSystemRuntime,
  fetchThemeHeat,
  fetchThemeOverview,
  fetchTrendPool
} from "./services/api";
import type {
  DashboardSummary,
  DataCalendarRow,
  DataCoverageRow,
  JobRun,
  OpportunityItem,
  RealtimeKlineResponse,
  RealtimeKlineRow,
  ResearchStats,
  SectorHeat,
  StockPoolItem,
  SystemStatus,
  SystemRuntime,
  ThemeHeat,
  ThemeOverview,
  AuthUser
} from "./types";
import { businessDaysAgoIso, businessTodayIso } from "./utils/businessTime";

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
const authLoading = ref(true);
const authUser = ref<AuthUser | null>(null);
const showChangePassword = ref(false);
const submittingBasicInfo = ref(false);
const submittingIngestion = ref(false);
const submittingRecalculation = ref(false);
const errorMessage = ref("");
const jobMessage = ref("");
const activeView = ref<ViewKey>("overview");
const overviewMode = ref<"market" | "research">("market");
const activePool = ref<PoolTab>("right");
const collapsedDataPanels = ref<Record<DataPanelKey, boolean>>({
  recalc: false,
  tasks: false,
  coverage: false
});
const backfillStart = ref(businessDaysAgoIso(30));
const backfillEnd = ref(businessTodayIso());
const recalcStart = ref(businessDaysAgoIso(180));
const recalcEnd = ref(businessTodayIso());
const recalcEvaluateSignals = ref(true);
const calendarMonth = ref(businessTodayIso().slice(0, 7));
const selectedCalendarDate = ref("");
const coveragePage = ref(1);
const coveragePageSize = ref(20);
const selectedKlineStock = ref<StockPoolItem | null>(null);
const selectedKlineDays = ref(180);
const klineData = ref<RealtimeKlineResponse | null>(null);
const klineLoading = ref(false);
const klineError = ref("");
const nowMs = ref(Date.now());
const status = ref<SystemStatus | null>(null);
const runtime = ref<SystemRuntime | null>(null);
const summary = ref<DashboardSummary | null>(null);
const sectorHeat = ref<SectorHeat[]>([]);
const dataCoverage = ref<DataCoverageRow[]>([]);
const dataCalendar = ref<DataCalendarRow[]>([]);
const jobs = ref<JobRun[]>([]);
const rightSidePool = ref<StockPoolItem[]>([]);
const trendPool = ref<StockPoolItem[]>([]);
const decayPool = ref<StockPoolItem[]>([]);
const researchStats = ref<ResearchStats | null>(null);
const themeHeat = ref<ThemeHeat[]>([]);
const leftOpportunities = ref<OpportunityItem[]>([]);
const rightOpportunities = ref<OpportunityItem[]>([]);
const trendOpportunities = ref<OpportunityItem[]>([]);
const selectedTheme = ref<ThemeHeat | null>(null);
const themeOverview = ref<ThemeOverview | null>(null);
const themeDetailLoading = ref(false);
const marketChartRef = ref<HTMLDivElement | null>(null);
const sectorChartRef = ref<HTMLDivElement | null>(null);
const klineChartRef = ref<HTMLDivElement | null>(null);
let marketChart: EChartsType | null = null;
let sectorChart: EChartsType | null = null;
let klineChart: EChartsType | null = null;
let jobPollTimer: number | undefined;
let elapsedTimer: number | undefined;

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

const latestJobs = computed(() => jobs.value);

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
    complete: openRows.filter((row) =>
      ["CORE_COMPLETE", "OPPORTUNITY_COMPLETE"].includes(row.coverage_status)
    ).length
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
      nextRuntime,
      nextSummary,
      nextDataCoverage,
      nextDataCalendar,
      nextJobs,
      nextRightSide,
      nextTrend,
      nextDecay,
      nextSectorHeat,
      nextResearchStats,
      nextThemeHeat,
      nextLeftOpportunities,
      nextRightOpportunities,
      nextTrendOpportunities
    ] = await Promise.all([
      fetchSystemStatus(),
      fetchSystemRuntime(),
      fetchDashboardSummary(),
      fetchDataCoverage(),
      fetchDataCalendar(monthStartIso(calendarMonth.value), monthEndIso(calendarMonth.value)),
      fetchJobs(),
      fetchRightSidePool(),
      fetchTrendPool(),
      fetchDecayPool(),
      fetchSectorHeat(),
      fetchResearchStats(),
      fetchThemeHeat(),
      fetchLeftReversal(),
      fetchOpportunityRightSide(),
      fetchOpportunityTrends()
    ]);
    status.value = nextStatus;
    runtime.value = nextRuntime;
    summary.value = nextSummary;
    dataCoverage.value = nextDataCoverage;
    dataCalendar.value = nextDataCalendar;
    jobs.value = nextJobs;
    rightSidePool.value = nextRightSide;
    trendPool.value = nextTrend;
    decayPool.value = nextDecay;
    sectorHeat.value = nextSectorHeat.length ? nextSectorHeat : nextSummary.sector_heat_top;
    researchStats.value = nextResearchStats;
    themeHeat.value = nextThemeHeat;
    leftOpportunities.value = nextLeftOpportunities;
    rightOpportunities.value = nextRightOpportunities;
    trendOpportunities.value = nextTrendOpportunities;
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

async function openThemeDetail(theme: ThemeHeat) {
  selectedTheme.value = theme;
  themeOverview.value = null;
  themeDetailLoading.value = true;
  try {
    themeOverview.value = await fetchThemeOverview(theme.theme_code);
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "题材详情加载失败";
  } finally {
    themeDetailLoading.value = false;
  }
}

function closeThemeDetail() {
  selectedTheme.value = null;
  themeOverview.value = null;
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
      end: backfillEnd.value
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

async function submitBasicInfo() {
  errorMessage.value = "";
  jobMessage.value = "";
  submittingBasicInfo.value = true;
  try {
    const job = await enqueueSyncBasicJob();
    jobMessage.value = jobMessageText(job);
    await refreshJobStatus();
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "基础信息同步任务提交失败";
  } finally {
    submittingBasicInfo.value = false;
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

function startWorkspace() {
  if (jobPollTimer) return;
  void loadData();
  jobPollTimer = window.setInterval(() => {
    void refreshJobStatus();
  }, 5000);
  elapsedTimer = window.setInterval(() => {
    nowMs.value = Date.now();
  }, 1000);
}

function stopWorkspace() {
  if (jobPollTimer) window.clearInterval(jobPollTimer);
  if (elapsedTimer) window.clearInterval(elapsedTimer);
  jobPollTimer = undefined;
  elapsedTimer = undefined;
}

function handleAuthenticated(user: AuthUser) {
  authUser.value = user;
  showChangePassword.value = user.must_change_password;
  if (!user.must_change_password) startWorkspace();
}

async function handleLogout() {
  try {
    await logout();
  } finally {
    stopWorkspace();
    authUser.value = null;
    showChangePassword.value = false;
  }
}

function handlePasswordChanged() {
  stopWorkspace();
  authUser.value = null;
  showChangePassword.value = false;
}

function handleAuthRequired() {
  stopWorkspace();
  authUser.value = null;
  showChangePassword.value = false;
}

function handlePasswordRequired() {
  showChangePassword.value = true;
}

onMounted(async () => {
  window.addEventListener("auth-required", handleAuthRequired);
  window.addEventListener("password-change-required", handlePasswordRequired);
  try {
    handleAuthenticated(await fetchCurrentUser());
  } catch {
    authUser.value = null;
  } finally {
    authLoading.value = false;
  }
});

onUnmounted(() => {
  window.removeEventListener("resize", handleResize);
  window.removeEventListener("auth-required", handleAuthRequired);
  window.removeEventListener("password-change-required", handlePasswordRequired);
  if (jobPollTimer) {
    window.clearInterval(jobPollTimer);
  }
  if (elapsedTimer) {
    window.clearInterval(elapsedTimer);
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

function formatJobElapsed(job: JobRun | null | undefined) {
  if (!job?.started_at) return "--";
  const startedAt = Date.parse(job.started_at);
  if (Number.isNaN(startedAt)) return "--";
  const finishedAt = job.finished_at ? Date.parse(job.finished_at) : nowMs.value;
  if (Number.isNaN(finishedAt) || finishedAt < startedAt) return "--";
  return formatDuration(finishedAt - startedAt);
}

function formatDuration(durationMs: number) {
  const totalSeconds = Math.max(0, Math.floor(durationMs / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) {
    return `${hours}小时${String(minutes).padStart(2, "0")}分${String(seconds).padStart(2, "0")}秒`;
  }
  if (minutes > 0) {
    return `${minutes}分${String(seconds).padStart(2, "0")}秒`;
  }
  return `${seconds}秒`;
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
    CORE_COMPLETE: "核",
    OPPORTUNITY_COMPLETE: "全",
    DEGRADED: "差"
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
  const stage = typeof job.metadata.stage === "string" ? job.metadata.stage : null;
  const current =
    typeof job.metadata.current_trade_date === "string" ? job.metadata.current_trade_date : null;
  const deferredDate =
    typeof job.metadata.deferred_trade_date === "string"
      ? job.metadata.deferred_trade_date
      : null;
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
  const themeChunkIndex =
    typeof job.metadata.theme_chunk_index === "number" ? job.metadata.theme_chunk_index : null;
  const themeChunkCount =
    typeof job.metadata.theme_chunk_count === "number" ? job.metadata.theme_chunk_count : null;
  const themeChunkStart =
    typeof job.metadata.theme_chunk_start === "string" ? job.metadata.theme_chunk_start : null;
  const themeChunkEnd =
    typeof job.metadata.theme_chunk_end === "string" ? job.metadata.theme_chunk_end : null;
  const opportunityChunkIndex =
    typeof job.metadata.opportunity_chunk_index === "number"
      ? job.metadata.opportunity_chunk_index
      : null;
  const opportunityChunkCount =
    typeof job.metadata.opportunity_chunk_count === "number"
      ? job.metadata.opportunity_chunk_count
      : null;
  const opportunityChunkStart =
    typeof job.metadata.opportunity_chunk_start === "string"
      ? job.metadata.opportunity_chunk_start
      : null;
  const opportunityChunkEnd =
    typeof job.metadata.opportunity_chunk_end === "string"
      ? job.metadata.opportunity_chunk_end
      : null;
  const skippedRawDays =
    typeof job.metadata.skipped_raw_days === "number" ? job.metadata.skipped_raw_days : 0;
  const isDailyStage =
    stage === "daily" ||
    stage === "eod_deferred" ||
    Boolean(job.step?.startsWith("30 sync daily"));
  const datePart = start && end ? `${start} 到 ${end}` : job.target_trade_date || "--";
  const stagePart = stage && stage !== "daily" ? ` / ${jobStageText(job)}` : "";
  const chunkPart = factorChunkIndex !== null && factorChunkCount !== null
    ? ` / 因子分块 ${factorChunkIndex}/${factorChunkCount}`
    : themeChunkIndex !== null && themeChunkCount !== null
      ? ` / 题材分块 ${themeChunkIndex}/${themeChunkCount}`
      : opportunityChunkIndex !== null && opportunityChunkCount !== null
        ? ` / 机会池分块 ${opportunityChunkIndex}/${opportunityChunkCount}`
        : "";
  const chunkStart = factorChunkStart || themeChunkStart || opportunityChunkStart;
  const chunkEnd = factorChunkEnd || themeChunkEnd || opportunityChunkEnd;
  const chunkDatePart = chunkStart && chunkEnd ? `：${chunkStart} 到 ${chunkEnd}` : "";
  const progressPart = isDailyStage && currentIndex !== null && total !== null
    ? ` / 第 ${currentIndex}/${total} 个交易日`
    : isDailyStage && completed !== null && total !== null
      ? ` / 已完成 ${completed}/${total} 个交易日`
      : "";
  const skippedPart = isDailyStage && skippedRawDays > 0
    ? ` / 已跳过 ${skippedRawDays} 个已完整交易日`
    : "";
  const totalPart = !isDailyStage && total !== null ? ` / 覆盖 ${total} 个交易日` : "";
  const currentPart = isDailyStage && current ? ` / 当前 ${current}` : "";
  const deferredPart = stage === "eod_deferred" && deferredDate
    ? ` / 待更新 ${deferredDate}`
    : "";
  return `${datePart}${stagePart}${chunkPart}${chunkDatePart}${progressPart}${skippedPart}${totalPart}${currentPart}${deferredPart}`;
}

function jobStageText(job: JobRun) {
  const stage = typeof job.metadata.stage === "string" ? job.metadata.stage : "";
  const map: Record<string, string> = {
    starting: "准备任务",
    calendar: "同步交易日历",
    metadata: "同步基础资料",
    stock_basic: "同步股票基础信息",
    sector_metadata: "同步行业分类",
    sector_members: "同步行业成分",
    daily: "拉取交易日数据",
    validate_data: "校验存量数据",
    factors: "计算个股因子",
    market: "计算市场温度",
    sectors: "计算行业热度",
    themes: "计算题材热度",
    states: "计算趋势状态与策略信号",
    opportunities: "计算机会池",
    cross_table_quality: "校验跨表质量",
    signal_eval: "评估信号后验",
    eod_deferred: "历史数据已完成，今日 EOD 数据待更新",
    success: "任务完成"
  };
  return map[stage] || jobStepText(job);
}

function jobStepText(job: JobRun) {
  const step = job.step || "--";
  if (step.startsWith("00 start sync basic info")) return "00 准备同步基础信息";
  if (step.startsWith("00 start backfill")) return "00 准备拉取任务";
  if (step.startsWith("00 start validate data")) return "00 准备校验存量数据";
  if (step.startsWith("10 sync trade_calendar")) return "10 同步交易日历";
  if (step.startsWith("20 sync stock_basic")) return "20 同步股票基础信息";
  if (step.startsWith("25 sync sector metadata")) return "25 同步行业分类";
  if (step.startsWith("26 sync sector members")) return "26 同步行业成分";
  if (step.startsWith("30 skip existing raw")) {
    return `30 跳过已完整交易日 ${step.replace("30 skip existing raw", "").trim()}`;
  }
  if (step.startsWith("30 sync daily")) return `30 拉取交易日数据 ${step.replace("30 sync daily", "").trim()}`;
  if (step.startsWith("70 validate raw data")) {
    return `70 校验存量原始数据 ${step.replace("70 validate raw data", "").trim()}`;
  }
  if (step.startsWith("90 factors done")) return "90 个股因子分块完成";
  if (step.startsWith("90 factors")) return "90 计算个股因子分块";
  if (step.startsWith("90 calculate stock factors")) return "90 计算个股因子";
  if (step.startsWith("100 calculate market score")) return "100 计算市场温度";
  if (step.startsWith("110 calculate sector heat")) return "110 计算行业热度";
  if (step.startsWith("115 theme heat")) return "115 计算题材热度分块";
  if (step.startsWith("120 calculate trend states")) return "120 计算趋势状态与策略信号";
  if (step.startsWith("130 opportunities")) return "130 计算机会池分块";
  if (step.startsWith("180 validate cross table quality")) return "180 校验跨表质量";
  if (step.startsWith("175 raw sync complete; current EOD deferred")) {
    return "175 历史数据已完成，今日 EOD 数据待更新";
  }
  if (step.startsWith("180 sync basic info complete")) return "180 基础信息同步完成";
  if (step.startsWith("180 raw sync complete")) return "180 原始数据拉取完成";
  if (step.startsWith("180 mark SUCCESS")) return "180 任务完成";
  if (step.startsWith("190 evaluate signals")) return "190 评估信号后验";
  if (step.startsWith("200 signal eval complete")) return "200 信号后验完成";
  if (step.startsWith("200 recalculation complete")) return "200 重算完成";
  if (step.startsWith("200 validate data complete")) return "200 存量数据校验完成";
  return step;
}

function jobTooltip(job: JobRun) {
  const parts = [
    `类型：${jobTypeText(job.job_type)}`,
    `状态：${statusLabel(job.status)}`,
    `步骤：${jobStepText(job)}`,
    `原始步骤：${job.step || "--"}`,
    `范围：${metadataText(job)}`,
    `耗时：${formatJobElapsed(job)}`
  ];
  if (job.error_message) {
    parts.push(`错误：${job.error_message}`);
  }
  return parts.join("\n");
}

function jobTypeText(jobType: string) {
  const map: Record<string, string> = {
    sync_basic: "基础信息",
    backfill: "原始数据",
    recalculate: "补算",
    validate_data: "校验",
    daily: "日更"
  };
  return map[jobType] || jobType;
}

function rowCountHint(job: JobRun) {
  const stage = typeof job.metadata.stage === "string" ? job.metadata.stage : "";
  if (stage === "factors" && typeof job.metadata.factor_chunk_index === "number") {
    return "当前因子分块完成后更新行数";
  }
  if (stage === "themes" && typeof job.metadata.theme_chunk_index === "number") {
    return "当前题材分块完成后更新行数";
  }
  if (
    stage === "opportunities" &&
    typeof job.metadata.opportunity_chunk_index === "number"
  ) {
    return "当前机会池分块完成后更新行数";
  }
  if (stage === "daily" && job.metadata.current_day_action === "skip") {
    return "该交易日原始数据已完整，已跳过重复拉取";
  }
  if (
    [
      "factors",
      "market",
      "sectors",
      "themes",
      "states",
      "opportunities",
      "cross_table_quality",
      "signal_eval"
    ].includes(stage)
  ) {
    return "当前计算阶段完成后更新行数";
  }
  return "";
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
  <main v-if="authLoading" class="auth-shell"><div class="auth-loading">正在确认登录状态</div></main>
  <LoginView v-else-if="!authUser" @authenticated="handleAuthenticated" />
  <ChangePasswordView
    v-else-if="showChangePassword"
    :username="authUser.username"
    :required="authUser.must_change_password"
    @changed="handlePasswordChanged"
    @cancel="showChangePassword = false"
  />
  <main v-else class="workspace-shell">
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
        <div class="topbar-actions">
          <button class="refresh-button" :disabled="loading" @click="loadData">
            {{ loading ? "刷新中" : "刷新" }}
          </button>
          <UserMenu
            :username="authUser.username"
            @change-password="showChangePassword = true"
            @logout="handleLogout"
          />
        </div>
      </header>

      <div v-if="errorMessage" class="error-strip">{{ errorMessage }}</div>
      <div v-if="jobMessage" class="success-strip">{{ jobMessage }}</div>

      <section v-show="activeView === 'overview'" class="view-stack">
        <div class="overview-mode-switch" role="tablist" aria-label="总览视图">
          <button type="button" role="tab" :aria-selected="overviewMode === 'market'"
            :class="{ selected: overviewMode === 'market' }" @click="overviewMode = 'market'">市场</button>
          <button type="button" role="tab" :aria-selected="overviewMode === 'research'"
            :class="{ selected: overviewMode === 'research' }" @click="overviewMode = 'research'">研究</button>
        </div>
        <template v-if="overviewMode === 'market'">
        <DashboardView
          :metrics="metrics"
          :market-regime="summary?.market?.regime || 'NO_DATA'"
          :sector-count="sectorHeat.length"
        >
          <template #market>
            <div ref="marketChartRef" class="chart"></div>
          </template>
          <template #sector>
            <div v-if="sectorHeat.length" ref="sectorChartRef" class="chart"></div>
            <div v-else class="empty-chart">暂无行业热度数据</div>
          </template>
          <template #research>
            <ResearchSummary :stats="researchStats" :format-percent="formatPercent" />
          </template>
        </DashboardView>
        <section class="discovery-grid">
          <SectorHeatPanel
            title="热门行业"
            subtitle="申万一级行业"
            :rows="sectorHeat.slice(0, 15)"
            :format-number="formatNumber"
          />
          <ThemeHeatTable
            :rows="themeHeat"
            :format-number="formatNumber"
            @select="openThemeDetail"
          />
        </section>
        <section class="discovery-grid">
          <OpportunityTable
            title="左侧反转"
            kind="left"
            :rows="leftOpportunities"
            :format-number="formatNumber"
          />
          <OpportunityTable
            title="新右侧确认"
            kind="right"
            :rows="rightOpportunities"
            :format-number="formatNumber"
          />
        </section>
        <OpportunityTable
          title="趋势强股"
          kind="trend"
          :rows="trendOpportunities"
          :format-number="formatNumber"
        />
        </template>
        <ResearchLab v-else />
      </section>

      <section v-show="activeView === 'data'" class="view-stack">
        <section class="runtime-strip" aria-label="运行状态">
          <div><span>Backend / 数据库</span><strong>{{ runtime?.services?.backend?.status || "--" }} / {{ runtime?.services?.database?.status || "--" }}</strong></div>
          <div><span>Worker / Scheduler</span><strong>{{ runtime?.services?.worker?.status || "--" }} / {{ runtime?.services?.scheduler?.status || "--" }}</strong></div>
          <div><span>当前任务</span><strong>{{ runtime?.active_job?.step || "无" }}</strong></div>
          <div><span>排队 / 运行</span><strong>{{ runtime?.queued_count ?? 0 }} / {{ runtime?.running_count ?? 0 }}</strong></div>
          <div><span>Raw / 分析 / 机会</span><strong>{{ runtime?.latest_raw_date || "--" }} / {{ runtime?.latest_analysis_date || "--" }} / {{ runtime?.latest_opportunity_date || "--" }}</strong></div>
        </section>
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

        <JobCenter
          v-model:backfill-start="backfillStart"
          v-model:backfill-end="backfillEnd"
          :collapsed="collapsedDataPanels.tasks"
          :submitting-basic-info="submittingBasicInfo"
          :submitting-ingestion="submittingIngestion"
          :active-job="activeJob"
          :jobs="latestJobs"
          :status-label="statusLabel"
          :progress-pct="progressPct"
          :job-step-text="jobStepText"
          :metadata-text="metadataText"
          :format-job-elapsed="formatJobElapsed"
          :row-count-hint="rowCountHint"
          :job-tooltip="jobTooltip"
          :job-type-text="jobTypeText"
          @toggle="toggleDataPanel('tasks')"
          @sync-basic="submitBasicInfo"
          @submit-backfill="submitBackfill"
        />

        <DataQuality
          v-model:page-size="coveragePageSize"
          :collapsed="collapsedDataPanels.coverage"
          :summary="calendarSummary"
          :month-title="calendarMonthTitle"
          :cells="calendarCells"
          :selected-date="selectedCalendarDate"
          :selected-row="selectedCalendarRow"
          :page-rows="pagedDataCoverage"
          :total-rows="dataCoverage.length"
          :page="coveragePage"
          :page-sizes="coveragePageSizeOptions"
          :total-pages="coverageTotalPages"
          :page-start="coveragePageStart"
          :page-end="coveragePageEnd"
          :status-label="calendarStatusLabel"
          @toggle="toggleDataPanel('coverage')"
          @previous-month="shiftCalendarMonth(-1)"
          @next-month="shiftCalendarMonth(1)"
          @select-date="selectCalendarDay"
          @set-page="setCoveragePage"
        />
      </section>

      <section v-show="activeView === 'long'" class="view-stack">
        <StockPool
          title="长线股票池"
          :rows="currentPool"
          empty-text="暂无符合条件的股票"
          :format-number="formatNumber"
          :reason-text="reasonText"
          @select="openRealtimeKline"
        >
          <template #actions>
            <div class="segmented">
              <button :class="{ active: activePool === 'right' }" @click="activePool = 'right'">
                右侧
              </button>
              <button :class="{ active: activePool === 'trend' }" @click="activePool = 'trend'">
                趋势
              </button>
            </div>
          </template>
        </StockPool>
        <SectorHeatPanel
          title="长线行业"
          subtitle="按热度排序"
          :rows="sectorHeat.slice(0, 20)"
          :format-number="formatNumber"
        />
      </section>

      <section v-show="activeView === 'short'" class="view-stack">
        <section class="dashboard-grid short-grid">
          <StockPool
            title="短线风险池"
            subtitle="衰退 / 破位观察"
            :rows="decayPool"
            warning
            empty-text="暂无短线风险股票"
            :format-number="formatNumber"
            :reason-text="reasonText"
            @select="openRealtimeKline"
          />

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

          <SectorHeatPanel
            title="短线行业动量"
            subtitle="按 Heat Momentum 3 排序"
            :rows="shortSectorRows"
            momentum
            :format-number="formatNumber"
          />
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
    <ThemeDetail
      v-if="selectedTheme"
      :data="themeOverview"
      :loading="themeDetailLoading"
      @close="closeThemeDetail"
    />
  </main>
</template>
