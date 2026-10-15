import { request, requestPage, type ApiPage } from "./api";

export type PaperFacts = {
  id: string; mode: "PAPER"; record_hash: string; schema_version: string;
  created_at: string; account_id?: string; request_id?: string;
  state?: string; status?: string; ts_code?: string; trade_date?: string;
  signal_date?: string; scheduled_date?: string; stage?: string; action?: string;
  target_weight?: string; note?: string; data: Record<string, unknown>;
  [key: string]: unknown;
};
export type PaperRisk = { max_positions: number; max_single_position_weight: string;
  min_cash_ratio: string; max_new_positions_per_day: number; max_sector_weight: string;
  max_theme_weight: string; max_daily_turnover: string };
export type PaperAccount = PaperFacts & { name: string; state: "ACTIVE" | "PAUSED" | "CLOSED";
  initial_cash: string; benchmark_code: string; first_trade_date: string;
  next_trade_date?: string | null; latest_trade_date?: string | null;
  config_snapshot_json: { paper: { risk: PaperRisk }; [key: string]: unknown } };
export type PaperStatus = { enabled: boolean; schema_ready: boolean; auto_advance: boolean;
  auto_approve: false; business_date: string; latest_raw_date: string | null; default_risk: PaperRisk };
export type PaperCandidate = { ts_code: string; name: string; opportunity_stage: string;
  opportunity_score: string; close: string | null; industry_sector_id: number | null;
  primary_theme_code: string | null; reason_codes: unknown; risk_codes: string[];
  rule_status: string; [key: string]: unknown };
export type PaperJob = { id: string; status: string; job_type: string; trade_date: string;
  started_at: string; finished_at: string | null; error_code: string | null; step: string;
  progress_pct: number; account_id: string; stage?: string; cancel_requested?: boolean };
export type PaperSeries = { trade_date: string; nav: string | null; benchmark_nav: string | null;
  cash: string | null; market_value: string | null; daily_return: string | null; drawdown: string | null;
  cumulative_cost: string | null; valid: boolean };
export type PaperPerformance = { continuous: boolean; series: PaperSeries[];
  latest: PaperFacts | null; cumulative_return: string | null; maximum_drawdown: string | null;
  cumulative_cost: string; cumulative_turnover: string; realized_pnl: string; unrealized_pnl: string;
  benchmark_status: string; financial_source_hash: string; reason_codes: string[];
  decision_metrics?: { approval_rate: string | null; denominator: { legal_proposals: number }; counts: Record<string, number> };
  stage_attribution?: { groups: Record<string, { realized_pnl: string; unrealized_pnl: string; trading_cost: string; gross_amount: string }> };
  observation_metrics?: { windows: Record<string, { reviewed: number; valid_marks: number; positive_marks: number; hit_rate: string | null }> };
  execution: { reached_orders: number; filled_orders: number; hypothetical_fill_rate: string | null;
    blocked_reasons: Record<string, number>; stages: Record<string, { orders: number; filled: number }> } };

export type PaperPage<T> = ApiPage<T[], { total: number; offset: number; limit: number }>;
export function paperStatus(signal?: AbortSignal) { return request<PaperStatus>("/paper/status", { signal }); }
export function paperAccounts(offset = 0, signal?: AbortSignal) {
  return requestPage<PaperAccount[], { total: number; offset: number; limit: number }>(
    `/paper/accounts?limit=20&offset=${offset}`, { signal });
}
export function paperAccount(id: string, signal?: AbortSignal) {
  return request<PaperAccount>(`/paper/accounts/${encodeURIComponent(id)}`, { signal });
}
export function paperPerformance(id: string, signal?: AbortSignal) {
  return request<PaperPerformance>(`/paper/accounts/${encodeURIComponent(id)}/performance`, { signal });
}
export function paperPage(kind: string, accountId: string, filters: Record<string, string | number> = {},
                          signal?: AbortSignal): Promise<PaperPage<PaperFacts>> {
  const query = new URLSearchParams({ limit: "20", offset: "0" });
  for (const [key, value] of Object.entries(filters)) if (value !== "") query.set(key, String(value));
  const path = ["observations", "proposals"].includes(kind)
    ? `/decisions/${kind}` : `/paper/accounts/${encodeURIComponent(accountId)}/${kind}`;
  if (["observations", "proposals"].includes(kind)) query.set("account_id", accountId);
  return requestPage<PaperFacts[], { total: number; offset: number; limit: number }>(`${path}?${query}`, { signal });
}
export function paperJobs(accountId: string, signal?: AbortSignal, offset = 0) {
  return requestPage<PaperJob[], { total: number; offset: number; limit: number; active_count?: number }>(
    `/paper/accounts/${encodeURIComponent(accountId)}/jobs?limit=20&offset=${offset}`, { signal });
}
export function paperWrite<T = PaperFacts>(path: string, payload: Record<string, unknown>) {
  return request<T>(path, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload) });
}

const pending = new Map<string, string>();
export function paperRequestId(owner: string, operation: string, subject: string): string {
  const key = `space.paper.request.${encodeURIComponent(owner)}.${operation}.${encodeURIComponent(subject)}`;
  let value = pending.get(key);
  try { value ||= sessionStorage.getItem(key) || undefined; } catch { /* Restricted storage. */ }
  if (!value) {
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    value = Array.from(bytes, byte => byte.toString(16).padStart(2, "0")).join("");
    pending.set(key, value);
    try { sessionStorage.setItem(key, value); } catch { /* In-memory retry remains stable. */ }
  }
  return value;
}
export function clearPaperRequest(owner: string, operation: string, subject: string) {
  const key = `space.paper.request.${encodeURIComponent(owner)}.${operation}.${encodeURIComponent(subject)}`;
  pending.delete(key);
  try { sessionStorage.removeItem(key); } catch { /* Restricted storage. */ }
}
