export type ApiEnvelope<T> = {
  code: number;
  message: string;
  data: T;
  meta: Record<string, unknown>;
};

export type SystemStatus = {
  latest_trade_date: string | null;
  latest_raw_date: string | null;
  latest_factor_date: string | null;
  latest_market_date: string | null;
  latest_sector_factor_date: string | null;
  latest_state_date: string | null;
  latest_signal_date: string | null;
  latest_signal_eval_date: string | null;
};

export type DataCoverageRow = {
  trade_date: string;
  stock_daily_rows: number;
  daily_basic_rows: number;
  adj_factor_rows: number;
  index_daily_rows: number;
  factor_rows: number;
  market_rows: number;
  sector_factor_rows: number;
  state_rows: number;
  signal_rows: number;
  signal_eval_rows: number;
  quality_status?: string | null;
};

export type DataCalendarRow = {
  date: string;
  is_open: boolean | null;
  coverage_status: "CLOSED" | "MISSING" | "RAW_ONLY" | "ANALYZED" | "COMPLETE" | "DEGRADED";
  stock_daily_rows: number;
  daily_basic_rows: number;
  adj_factor_rows: number;
  index_daily_rows: number;
  factor_rows: number;
  market_rows: number;
  sector_factor_rows: number;
  state_rows: number;
  signal_rows: number;
  signal_eval_rows: number;
  quality_status?: string | null;
};

export type JobRun = {
  id: string;
  job_type: string;
  target_trade_date: string | null;
  started_at: string | null;
  finished_at: string | null;
  status: string;
  step: string | null;
  row_count: number;
  error_message: string | null;
  metadata: Record<string, unknown>;
};

export type MarketSummary = {
  trade_date: string;
  market_score: number | null;
  regime: string | null;
  breadth20: number | null;
  breadth60: number | null;
  up_count: number | null;
  down_count: number | null;
  flat_count: number | null;
  up_rate: number | null;
  new_high20_count: number | null;
  new_low20_count: number | null;
  total_amount: number | null;
  amount_ratio20: number | null;
};

export type StateCount = {
  state: string;
  count: number;
};

export type SignalCount = {
  signal_type: string;
  count: number;
};

export type SectorHeat = {
  trade_date: string;
  sector_id: number;
  name?: string;
  sector_name?: string;
  level: string | null;
  heat_score: number | null;
  heat_rank: number | null;
  rank_change: number | null;
  lifecycle: string | null;
  member_count: number | null;
  eligible_member_count: number | null;
  return5?: number | null;
  return20?: number | null;
  up_rate?: number | null;
  heat_momentum1?: number | null;
  heat_momentum3?: number | null;
};

export type StockPoolItem = {
  trade_date: string;
  ts_code: string;
  name: string | null;
  industry: string | null;
  state: string;
  previous_state: string | null;
  state_day_count: number | null;
  is_new_state: boolean;
  right_side_score: number | null;
  trend_score: number | null;
  opportunity_score: number | null;
  primary_sector_id: number | null;
  sector_name: string | null;
  sector_heat: number | null;
  market_score: number | null;
  fast_transition: boolean;
  reason_codes: string[] | Record<string, unknown> | null;
};

export type RealtimeKlineRow = {
  ts_code: string;
  trade_date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  pre_close: number | null;
  change: number | null;
  pct_chg: number | null;
  vol: number | null;
  amount: number | null;
};

export type RealtimeKlineResponse = {
  stock: {
    ts_code: string;
    name?: string | null;
  } & Record<string, unknown>;
  source: string;
  stored: boolean;
  days: number;
  start: string;
  end: string;
  rows: RealtimeKlineRow[];
};

export type DashboardSummary = {
  trade_date: string | null;
  market: MarketSummary | null;
  state_counts: StateCount[];
  signal_counts: SignalCount[];
  sector_heat_top: SectorHeat[];
  right_side_new: StockPoolItem[];
  trend_leaders: StockPoolItem[];
};

export type ResearchStats = {
  signal_type: string;
  algo_version: string;
  count: number;
  avg_ret5: number | null;
  avg_ret10: number | null;
  avg_ret20: number | null;
  avg_ret60: number | null;
  win_rate5: number | null;
  win_rate10: number | null;
  win_rate20: number | null;
  win_rate60: number | null;
  avg_mfe20: number | null;
  avg_mae20: number | null;
  latest_evaluated_until_date: string | null;
};
