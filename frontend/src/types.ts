export type ApiEnvelope<T> = {
  code: number;
  message: string;
  data: T;
  meta: Record<string, unknown>;
};

export type AuthUser = {
  username: string;
  must_change_password: boolean;
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
  latest_theme_daily_date: string | null;
  latest_theme_factor_date: string | null;
  latest_opportunity_date: string | null;
  latest_theme_member_snapshot: string | null;
};

export type SystemRuntime = {
  latest_job_heartbeat: string | null;
  worker_heartbeat: string | null;
  active_job: { id: string; job_type: string; step: string | null; started_at: string | null } | null;
  queued_count: number;
  running_count: number;
  services: Record<"backend" | "worker" | "scheduler" | "database", {
    status: "UP" | "STALE" | "DOWN";
    heartbeat_at: string | null;
    instance_id?: string | null;
  }>;
  scheduler_cron: { daily: string; basic_info: string; research: string };
  latest_raw_date: string | null;
  latest_analysis_date: string | null;
  latest_opportunity_date: string | null;
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
  theme_daily_rows: number;
  theme_factor_rows: number;
  opportunity_rows: number;
  quality_status?: string | null;
};

export type DataCalendarRow = {
  date: string;
  is_open: boolean | null;
  coverage_status:
    | "CLOSED"
    | "MISSING"
    | "RAW_ONLY"
    | "ANALYZED"
    | "CORE_COMPLETE"
    | "OPPORTUNITY_COMPLETE"
    | "DEGRADED";
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
  theme_daily_rows: number;
  theme_factor_rows: number;
  opportunity_rows: number;
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
  industry_heat_top: SectorHeat[];
  theme_heat_top: ThemeHeat[];
  left_reversal_top: OpportunityItem[];
  right_side_new: OpportunityItem[];
  trend_leaders: OpportunityItem[];
};

export type ThemeHeat = {
  trade_date: string;
  theme_code: string;
  name: string;
  heat_score: number | null;
  heat_rank: number | null;
  heat_momentum3: number | null;
  rank_change: number | null;
  lifecycle: string | null;
  return1: number | null;
  return5: number | null;
  moneyflow_score: number | null;
  net_amount: number | null;
  limit_up_count: number | null;
  continuous_limit_count: number | null;
  breadth20: number | null;
  rps60_median: number | null;
  data_coverage: number | null;
  member_count?: number | null;
  eligible_member_count?: number | null;
};

export type OpportunityItem = {
  trade_date: string;
  ts_code: string;
  name: string | null;
  state: string;
  previous_state: string | null;
  left_reversal_score: number | null;
  left_reversal_new: boolean;
  right_side_score: number | null;
  trend_score: number | null;
  trend_rank_score: number | null;
  position_score: number | null;
  extension_risk: string | null;
  market_score: number | null;
  industry_name: string | null;
  industry_heat: number | null;
  primary_theme_code: string | null;
  primary_theme_name: string | null;
  primary_theme_heat: number | null;
  context_score: number | null;
  opportunity_stage: string;
  opportunity_score: number | null;
  rps20?: number | null;
  rps60?: number | null;
  rps120?: number | null;
  rps20_delta5?: number | null;
  ma20_slope5?: number | null;
  higher_low?: boolean | null;
  reason_codes: Record<string, unknown> | null;
};

export type ThemeOverview = {
  theme: Record<string, unknown>;
  factor: ThemeHeat | null;
  history: ThemeHeat[];
  member_distribution: Array<{ stage: string; count: number }>;
  top_members: Record<string, OpportunityItem[]>;
  member_context: {
    member_context_available: boolean;
    member_context_mode: "INTERVAL" | "SNAPSHOT" | "INTERVAL_SNAPSHOT" | "UNAVAILABLE";
    member_context_coverage: number | null;
    source_snapshot_date: string | null;
  };
  member_snapshot: {
    member_snapshot_date: string | null;
    member_snapshot_status: string | null;
    member_snapshot_coverage: number | null;
    member_snapshot_mode: "FULL" | "PARTIAL" | null;
  };
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

export type ResearchStatus = {
  research_version: string;
  research_config_hash: string;
  benchmark_code: string;
  latest_opportunity_eval_base_date: string | null;
  latest_theme_eval_base_date: string | null;
  latest_transition_eval_base_date: string | null;
  latest_evaluated_market_date: string | null;
  opportunity_eval_rows: number;
  theme_eval_rows: number;
  transition_eval_rows: number;
  mature5_rows: number;
  mature20_rows: number;
  mature60_rows: number;
};

export type ResearchHorizonStats = {
  horizon: number;
  event_count: number;
  mature_count: number;
  entry_executable_count: number;
  exit_executable_count: number;
  return_sample_count: number;
  excess_sample_count: number;
  avg_return: number | null;
  median_return: number | null;
  p25_return: number | null;
  p75_return: number | null;
  win_rate: number | null;
  avg_benchmark_return: number | null;
  avg_excess_return: number | null;
  median_excess_return: number | null;
  excess_win_rate: number | null;
  avg_mark_return: number | null;
  median_mark_return: number | null;
  mark_win_rate: number | null;
  avg_delayed_exit_return: number | null;
  median_delayed_exit_return: number | null;
  delayed_exit_win_rate: number | null;
  avg_net_return: number | null;
  avg_net_delayed_exit_return: number | null;
  avg_exit_delay_days: number | null;
  non_executable_rate: number | null;
  avg_mfe20: number | null;
  avg_mae20: number | null;
  sample_warning: boolean;
};

export type ResearchBucketRow = {
  group: string;
  event_count: number;
  horizons: ResearchHorizonStats[];
};

export type LeftThresholdRow = ResearchBucketRow & {
  reached_s3_20: number | null;
  reached_s4plus_20: number | null;
  reached_s5_20: number | null;
  avg_days_to_s3: number | null;
  avg_days_to_s4plus: number | null;
  avg_days_to_s5: number | null;
  hit_s0_20: number | null;
  hit_s6_20: number | null;
};

export type RightTransitionStats = LeftThresholdRow & {
  fell_below_s3_20: number | null;
};

export type TrendTopNRow = ResearchBucketRow;
export type PositionStatsRow = ResearchBucketRow;
export type ThemeTopNRow = ResearchBucketRow;
export type ThemeLifecycleRow = ResearchBucketRow;
