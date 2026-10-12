import { API_BASE_URL, ApiError, request, requestPage, type ApiPage } from "./api";
import type { AgentCitation, AgentClaim, AgentRejectedClaim, AnswerStatus } from "./agent";

export type ReportType =
  | "market_review"
  | "opportunity_review"
  | "strategy_review"
  | "oos_review";
export type ReportComparisonState = "COMPARABLE" | "CONTEXT_REQUIRED" | "INCOMPATIBLE";

export interface ReportChart {
  chart_id: string;
  chart_type: "line" | "bar" | "table";
  title: string;
  unit: string;
  columns: string[];
  rows: string[][];
}

export interface ReportSnapshot {
  schema_version: string;
  snapshot_level: "CLAIM_SNAPSHOT_ONLY";
  report_type: ReportType;
  title: string;
  as_of_date?: string | null;
  source_answer_status: Exclude<AnswerStatus, "INSUFFICIENT_EVIDENCE">;
  source_chat_id: string;
  source_message_id: string;
  source_turn_id?: string | null;
  claims: AgentClaim[];
  rejected_claims: AgentRejectedClaim[];
  citations: AgentCitation[];
  sections: Array<{ section_id: string; title: string; claim_ids: string[]; items?: string[] }>;
  charts: ReportChart[];
  warnings: string[];
}

export interface ResearchReportSummary {
  report_id: string;
  report_type: ReportType;
  report_version: string;
  title: string;
  source_chat_id: string;
  source_message_id: string;
  as_of_date?: string | null;
  source_answer_status: Exclude<AnswerStatus, "INSUFFICIENT_EVIDENCE">;
  snapshot_hash: string;
  archived_at?: string | null;
  created_at: string;
}

export interface ResearchReport extends ResearchReportSummary {
  source_chat_id: string;
  source_message_id: string;
  source_turn_id?: string | null;
  parent_report_id?: string | null;
  snapshot: ReportSnapshot;
  source_contract: {
    snapshot_level: "CLAIM_SNAPSHOT_ONLY";
    report_version: string;
    comparison_policy_version: string;
    tool_names: string[];
    evidence_versions: string[];
    limitations: string[];
  };
}

export interface ReportComparison {
  comparison_id: string;
  left_report_id: string;
  right_report_id: string;
  policy_version: string;
  state: ReportComparisonState;
  reason_codes: string[];
  result: {
    facts?: Array<{ metric_key: string; left: string; right: string; delta?: string }>;
    delta_policy?: string;
  };
  left_snapshot_hash: string;
  right_snapshot_hash: string;
  comparison_hash: string;
  created_at: string;
}

export interface ReportSourceSelection {
  chatId: string;
  messageId: string;
}

export function fetchResearchReports(
  limit = 20,
  offset = 0,
  includeArchived = false,
  reportType?: ReportType
): Promise<ApiPage<ResearchReportSummary[], { total: number }>> {
  const query = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
    include_archived: String(includeArchived)
  });
  if (reportType) query.set("type", reportType);
  return requestPage<ResearchReportSummary[], { total: number }>(
    `/agent/reports?${query.toString()}`
  );
}

export function fetchResearchReport(reportId: string): Promise<ResearchReport> {
  return request<ResearchReport>(`/agent/reports/${encodeURIComponent(reportId)}`);
}

export function createResearchReport(payload: {
  source_chat_id: string;
  source_message_id: string;
  report_type: ReportType;
  request_id: string;
  title?: string;
}): Promise<ResearchReport> {
  return request<ResearchReport>("/agent/reports", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
}

export function archiveResearchReport(reportId: string): Promise<ResearchReport> {
  return request<ResearchReport>(`/agent/reports/${encodeURIComponent(reportId)}/archive`, {
    method: "POST"
  });
}

export function createReportComparison(payload: {
  left_report_id: string;
  right_report_id: string;
  request_id: string;
}): Promise<ReportComparison> {
  return request<ReportComparison>("/agent/report-comparisons", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
}

export async function downloadResearchReport(
  reportId: string,
  format: "markdown" | "html"
): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/agent/reports/${encodeURIComponent(reportId)}/export?format=${format}`,
    { credentials: "include" }
  );
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const code = body?.detail?.code || `HTTP ${response.status}`;
    throw new ApiError(code, response.status, body?.detail || null);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `research-report-${reportId}.${format === "markdown" ? "md" : "html"}`;
  link.click();
  URL.revokeObjectURL(url);
}
