import { request } from "./api";
import type {
  LeftThresholdRow,
  PositionStatsRow,
  ResearchBucketRow,
  ResearchStatus,
  RightTransitionStats,
  ThemeLifecycleRow,
  ThemeTopNRow,
  TrendTopNRow
} from "../types";

export type ResearchWindow = { start: string; end: string };
export type ResearchType = "ALL" | "LEFT" | "RIGHT" | "TREND" | "POSITION";

function query(window: ResearchWindow, extra: Record<string, string> = {}): string {
  return new URLSearchParams({ ...window, ...extra }).toString();
}

export function fetchResearchStatus(): Promise<ResearchStatus> {
  return request<ResearchStatus>("/research/status");
}

export function fetchThemeStats(window: ResearchWindow): Promise<ResearchBucketRow[]> {
  return request(`/research/themes/stats?${query(window)}`);
}

export function fetchThemeBuckets(window: ResearchWindow, field: string): Promise<ResearchBucketRow[]> {
  return request(`/research/themes/buckets?${query(window, { field })}`);
}

export function fetchThemeTopN(window: ResearchWindow): Promise<ThemeTopNRow[]> {
  return request(`/research/themes/topn?${query(window)}`);
}

export function fetchThemeLifecycle(window: ResearchWindow): Promise<ThemeLifecycleRow[]> {
  return request(`/research/themes/lifecycle?${query(window)}`);
}

export function fetchLeftThresholds(window: ResearchWindow): Promise<LeftThresholdRow[]> {
  return request(`/research/left/thresholds?${query(window)}`);
}

export function fetchRightTransitions(window: ResearchWindow): Promise<RightTransitionStats[]> {
  return request(`/research/right/transitions?${query(window)}`);
}

export function fetchTrendTopN(window: ResearchWindow): Promise<TrendTopNRow[]> {
  return request(`/research/trends/topn?${query(window)}`);
}

export function fetchOpportunityBuckets(window: ResearchWindow, field: string, researchType: ResearchType = "ALL"): Promise<ResearchBucketRow[]> {
  return request(`/research/opportunities/buckets?${query(window, { field, research_type: researchType })}`);
}

export function fetchPositionStats(window: ResearchWindow): Promise<PositionStatsRow[]> {
  return request(`/research/positions/stats?${query(window)}`);
}

export function fetchContext(window: ResearchWindow, groupBy: string, researchType: ResearchType = "ALL"): Promise<ResearchBucketRow[]> {
  return request(`/research/context?${query(window, { group_by: groupBy, research_type: researchType })}`);
}

export function queueResearchEvaluation(window: ResearchWindow): Promise<{ id: string; status: string }> {
  return request("/research/evaluate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(window)
  });
}
