import { request } from "./api";
import type {
  AnalyticsPeriod,
  AnalyticsSummary,
  BacktestRun,
  PerformanceDaily,
  RiskDaily,
  TradeEpisode
} from "../types";

export type CompareRequestItem = {
  run_id: string;
  performance_id?: string | null;
  risk_id?: string | null;
  trade_id?: string | null;
};

export function fetchBacktests(): Promise<BacktestRun[]> {
  return request<BacktestRun[]>("/portfolio/backtests?limit=200");
}

export function fetchAnalyticsSummary(runId: string): Promise<AnalyticsSummary> {
  return request<AnalyticsSummary>(`/portfolio/backtests/${runId}/analytics/summary`);
}

export function fetchPerformanceDaily(runId: string): Promise<PerformanceDaily[]> {
  return request<PerformanceDaily[]>(
    `/portfolio/backtests/${runId}/performance/daily?limit=500`
  );
}

export function fetchRiskDaily(
  runId: string,
  performanceId: string
): Promise<RiskDaily[]> {
  return request<RiskDaily[]>(
    `/portfolio/backtests/${runId}/performance/risk/daily?performance_id=${performanceId}&limit=500`
  );
}

export function fetchPeriods(
  runId: string,
  periodType: "MONTH" | "YEAR"
): Promise<AnalyticsPeriod[]> {
  return request<AnalyticsPeriod[]>(
    `/portfolio/backtests/${runId}/performance/period?period_type=${periodType}&limit=500`
  );
}

export function calculatePeriods(runId: string): Promise<{ job_id: string; job_status: string }> {
  return request(`/portfolio/backtests/${runId}/performance/period/calculate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({})
  });
}

export function fetchTradeEpisodes(
  runId: string,
  options: {
    status?: string;
    classification?: string;
    tsCode?: string;
    limit?: number;
    offset?: number;
  }
): Promise<TradeEpisode[]> {
  const params = new URLSearchParams();
  if (options.status) params.set("status", options.status);
  if (options.classification) params.set("classification", options.classification);
  if (options.tsCode) params.set("ts_code", options.tsCode);
  params.set("limit", String(options.limit ?? 20));
  params.set("offset", String(options.offset ?? 0));
  return request<TradeEpisode[]>(
    `/portfolio/backtests/${runId}/performance/trade/episodes?${params}`
  );
}

export function compareAnalytics(
  items: CompareRequestItem[]
): Promise<{ schema_version: string; items: AnalyticsSummary[] }> {
  return request("/portfolio/analytics/compare", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ items })
  });
}

export function formatMetric(value: string | null | undefined, digits = 2): string {
  if (value === null || value === undefined || value === "") return "--";
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed.toFixed(digits) : "--";
}

export function formatAnalyticsPercent(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "--";
  const parsed = Number(value);
  return Number.isFinite(parsed) ? `${(parsed * 100).toFixed(2)}%` : "--";
}

export function formatCny(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "--";
  const parsed = Number(value);
  return Number.isFinite(parsed)
    ? new Intl.NumberFormat("zh-CN", { style: "currency", currency: "CNY" }).format(parsed)
    : "--";
}

export function sortedCompareItems(
  items: AnalyticsSummary[],
  metric: "annualized_return" | "max_drawdown" | "sharpe_ratio"
): AnalyticsSummary[] {
  const copy = [...items];
  return copy.sort((left, right) => {
    const leftValue =
      metric === "sharpe_ratio" ? left.risk.sharpe_ratio : left.performance[metric];
    const rightValue =
      metric === "sharpe_ratio" ? right.risk.sharpe_ratio : right.performance[metric];
    return Number(rightValue ?? Number.NEGATIVE_INFINITY) - Number(leftValue ?? Number.NEGATIVE_INFINITY);
  });
}

export function buildNavSeries(performance: PerformanceDaily[], risk: RiskDaily[]) {
  const riskByDate = new Map(risk.map((row) => [row.trade_date, row.benchmark_nav]));
  return {
    dates: performance.map((row) => row.trade_date),
    strategy: performance.map((row) => Number(row.nav)),
    benchmark: performance.map((row) => Number(riskByDate.get(row.trade_date) ?? NaN))
  };
}

export function buildDrawdownSeries(rows: PerformanceDaily[]) {
  return rows.map((row) => [row.trade_date, Number(row.drawdown)] as const);
}
