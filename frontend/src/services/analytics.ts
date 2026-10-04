import { ApiError, request, requestPage, type ApiPage } from "./api";
import type {
  AnalyticsIdentity,
  AnalyticsPeriod,
  AnalyticsSeries,
  AnalyticsSeriesMeta,
  AnalyticsSummary,
  BacktestRun,
  TradeEpisodeMeta,
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

export function fetchAnalyticsSummary(
  runId: string,
  identity?: Pick<AnalyticsIdentity, "performance_id" | "risk_id" | "trade_id">
): Promise<AnalyticsSummary> {
  const params = new URLSearchParams();
  if (identity) {
    params.set("performance_id", identity.performance_id);
    params.set("risk_id", identity.risk_id);
    params.set("trade_id", identity.trade_id);
  }
  const query = params.size ? `?${params}` : "";
  return request<AnalyticsSummary>(`/portfolio/backtests/${runId}/analytics/summary${query}`);
}

export async function fetchAllAnalyticsSeries(
  runId: string,
  identity: AnalyticsIdentity
): Promise<AnalyticsSeries[]> {
  const rows: AnalyticsSeries[] = [];
  const dates = new Set<string>();
  let offset = 0;
  let total: number | null = null;
  while (total === null || offset < total) {
    const params = identityParams(identity);
    params.set("limit", "500");
    params.set("offset", String(offset));
    const page = await requestPage<AnalyticsSeries[], AnalyticsSeriesMeta>(
      `/portfolio/backtests/${runId}/analytics/series?${params}`
    );
    validateSeriesMeta(page.meta, identity, runId, offset, total);
    total ??= page.meta.total;
    if (!page.data.length && offset < total) {
      throw new ApiError("ANALYTICS_SERIES_DATE_MISMATCH", 409);
    }
    for (const row of page.data) {
      const previous = rows.length ? rows[rows.length - 1].trade_date : undefined;
      if (dates.has(row.trade_date) || (previous && row.trade_date <= previous)) {
        throw new ApiError("ANALYTICS_SERIES_DATE_MISMATCH", 409);
      }
      dates.add(row.trade_date);
      rows.push(row);
    }
    offset += page.data.length;
  }
  if (rows.length !== total) {
    throw new ApiError("ANALYTICS_SERIES_DATE_MISMATCH", 409);
  }
  return rows;
}

export function fetchPeriods(
  runId: string,
  periodType: "MONTH" | "YEAR",
  identity: AnalyticsIdentity
): Promise<AnalyticsPeriod[]> {
  const params = identityParams(identity);
  params.set("period_type", periodType);
  params.set("limit", "500");
  return request<AnalyticsPeriod[]>(
    `/portfolio/backtests/${runId}/performance/period?${params}`
  );
}

export function calculatePeriods(
  runId: string,
  identity: AnalyticsIdentity
): Promise<{ job_id: string; job_status: string }> {
  return request(`/portfolio/backtests/${runId}/performance/period/calculate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      performance_id: identity.performance_id,
      risk_id: identity.risk_id,
      trade_id: identity.trade_id
    })
  });
}

export function fetchTradeEpisodes(
  runId: string,
  identity: AnalyticsIdentity,
  options: {
    status?: string;
    classification?: string;
    tsCode?: string;
    limit?: number;
    offset?: number;
  }
): Promise<ApiPage<TradeEpisode[], TradeEpisodeMeta>> {
  const params = new URLSearchParams();
  params.set("performance_id", identity.performance_id);
  params.set("trade_id", identity.trade_id);
  if (options.status) params.set("status", options.status);
  if (options.classification) params.set("classification", options.classification);
  if (options.tsCode) params.set("ts_code", options.tsCode);
  params.set("limit", String(options.limit ?? 20));
  params.set("offset", String(options.offset ?? 0));
  return requestPage<TradeEpisode[], TradeEpisodeMeta>(
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

export function buildNavSeries(rows: AnalyticsSeries[]) {
  return {
    dates: rows.map((row) => row.trade_date),
    strategy: rows.map((row) => Number(row.strategy_nav)),
    benchmark: rows.map((row) => Number(row.benchmark_nav))
  };
}

export function buildDrawdownSeries(rows: AnalyticsSeries[]) {
  return rows.map((row) => [row.trade_date, Number(row.drawdown)] as const);
}

function identityParams(identity: AnalyticsIdentity): URLSearchParams {
  const params = new URLSearchParams({
    performance_id: identity.performance_id,
    risk_id: identity.risk_id,
    trade_id: identity.trade_id
  });
  if (identity.period_id) params.set("period_id", identity.period_id);
  return params;
}

function validateSeriesMeta(
  meta: AnalyticsSeriesMeta,
  identity: AnalyticsIdentity,
  runId: string,
  offset: number,
  expectedTotal: number | null
): void {
  if (
    meta.run_id !== runId ||
    meta.performance_id !== identity.performance_id ||
    meta.risk_id !== identity.risk_id ||
    meta.trade_id !== identity.trade_id ||
    meta.period_id !== identity.period_id ||
    meta.offset !== offset ||
    (expectedTotal !== null && meta.total !== expectedTotal)
  ) {
    throw new ApiError("ANALYTICS_ARTIFACT_BUNDLE_MISMATCH", 409);
  }
}
