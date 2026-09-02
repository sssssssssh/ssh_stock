import type {
  ApiEnvelope,
  DataCalendarRow,
  DataCoverageRow,
  DashboardSummary,
  JobRun,
  RealtimeKlineResponse,
  ResearchStats,
  SectorHeat,
  StockPoolItem,
  SystemStatus
} from "../types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api/v1";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init);
  const body = (await response.json().catch(() => null)) as ApiEnvelope<T> | { detail?: string } | null;
  if (!response.ok) {
    const detail = body && "detail" in body ? body.detail : null;
    throw new Error(detail || `HTTP ${response.status}`);
  }
  if (!body || !("code" in body) || body.code !== 0) {
    throw new Error((body && "message" in body && body.message) || "API_ERROR");
  }
  return body.data;
}

export function fetchSystemStatus(): Promise<SystemStatus> {
  return request<SystemStatus>("/system/status");
}

export function fetchDashboardSummary(): Promise<DashboardSummary> {
  return request<DashboardSummary>("/dashboard/summary");
}

export function fetchDataCoverage(): Promise<DataCoverageRow[]> {
  return request<DataCoverageRow[]>("/system/data-coverage");
}

export function fetchDataCalendar(start: string, end: string): Promise<DataCalendarRow[]> {
  return request<DataCalendarRow[]>(`/system/data-calendar?start=${start}&end=${end}`);
}

export function fetchJobs(): Promise<JobRun[]> {
  return request<JobRun[]>("/jobs?limit=30");
}

export function fetchRightSidePool(): Promise<StockPoolItem[]> {
  return request<StockPoolItem[]>("/stocks/right-side?limit=80");
}

export function fetchTrendPool(): Promise<StockPoolItem[]> {
  return request<StockPoolItem[]>("/stocks/trends?states=S4,S5&limit=80");
}

export function fetchDecayPool(): Promise<StockPoolItem[]> {
  return request<StockPoolItem[]>("/stocks/decay?limit=80");
}

export function fetchSectorHeat(): Promise<SectorHeat[]> {
  return request<SectorHeat[]>("/sectors/heat?limit=50");
}

export function fetchRealtimeKline(tsCode: string, days = 180): Promise<RealtimeKlineResponse> {
  return request<RealtimeKlineResponse>(
    `/stocks/${encodeURIComponent(tsCode)}/realtime-kline?days=${days}`
  );
}

export function fetchResearchStats(): Promise<ResearchStats> {
  return request<ResearchStats>("/research/signals/stats?signal_type=RIGHT_SIDE_NEW");
}

export function enqueueBackfillJob(payload: {
  start: string;
  end: string;
  evaluate_signals?: boolean;
}): Promise<JobRun> {
  return request<JobRun>("/jobs/backfill", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
}

export function enqueueSyncBasicJob(): Promise<JobRun> {
  return request<JobRun>("/jobs/sync-basic", {
    method: "POST",
    headers: { "Content-Type": "application/json" }
  });
}

export function enqueueRecalculateJob(payload: {
  start: string;
  end: string;
  evaluate_signals?: boolean;
}): Promise<JobRun> {
  return request<JobRun>("/jobs/recalculate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
}

export function enqueueDailyJob(payload: { trade_date: string }): Promise<JobRun> {
  return request<JobRun>("/jobs/daily", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
}
