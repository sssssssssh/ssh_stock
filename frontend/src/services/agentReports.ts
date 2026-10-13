import { API_BASE_URL, ApiError, request, requestPage, type ApiPage } from "./api";
import type { AgentCitation, AgentClaim, AgentRejectedClaim, AnswerStatus } from "./agent";

export type ReportType =
  | "market_review"
  | "opportunity_review"
  | "strategy_review"
  | "oos_review";
export type ReportComparisonState = "COMPARABLE" | "CONTEXT_REQUIRED" | "INCOMPATIBLE";
export type ContractCheckState = "VERIFIED" | "UNVERIFIABLE" | "MISMATCH";
export type ResearchComparisonMode = "AUTO" | "STRICT_SAME_SAMPLE" | "DIFFERENT_ASSUMPTIONS" | "WINDOW_DEGRADATION";

export interface FrozenContractReference {
  contract_id: string;
  contract_kind: "M14_EXACT_BUNDLE" | "M15_WINDOW_LINEAGE" | "M15_STUDY_AGGREGATE";
  subject_id: string;
  role: "LIVE" | "TRAIN" | "OOS" | "STUDY";
  schema_version: string;
  contract_hash: string;
  status: ContractCheckState;
  reason_codes: string[];
  tool_result_archive_id: string;
}
export interface ContractVerification {
  contract_manifest_id?: string | null;
  contract_manifest_hash?: string | null;
  policy_version?: string | null;
  archive_integrity?: { status: ContractCheckState } | null;
  frozen_fact_recheck?: { status: ContractCheckState } | null;
  contract_integrity: { status: ContractCheckState; reason_codes?: string[] };
  contract_semantics: { status: ContractCheckState; reason_codes?: string[] };
  comparison_permission: { allowed: boolean; reason_codes: string[] };
  calculation_reproduced: false;
  results?: Array<Omit<FrozenContractReference, "tool_result_archive_id">>;
}
export interface ContractManifestReference {
  manifest_id: string;
  manifest_hash: string;
  policy_version: string;
  contract_count: number;
  contract_scope: string[];
  gap_codes: string[];
  reproduction_level: "FROZEN_CONTRACT_RECHECK";
}
export interface FrozenContractDetail extends FrozenContractReference {
  projection: Record<string, unknown> | null;
}

export interface ReportChart {
  chart_id: string;
  chart_type: "line" | "bar" | "table";
  title: string;
  unit: string;
  columns: string[];
  rows: string[][];
  metric_id?: string | null;
  trade_date?: string | null;
  sample_role?: string | null;
  entity_kind?: string | null;
}

export interface ReportSnapshot {
  schema_version: string;
  snapshot_level: "CLAIM_SNAPSHOT_ONLY" | "FROZEN_TOOL_EVIDENCE";
  archive_reference?: { manifest_id: string; manifest_hash: string; manifest_version: string;
    archive_status: "COMPLETE"; reproduction_level: "FROZEN_FACT_RECHECK" } | null;
  contract_reference?: ContractManifestReference | null;
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
    snapshot_level: "CLAIM_SNAPSHOT_ONLY" | "FROZEN_TOOL_EVIDENCE";
    report_version: string;
    comparison_policy_version: string;
    tool_names: string[];
    evidence_versions: string[];
    limitations: string[];
    archive_manifest_hash?: string | null;
    archive_policy_version?: string | null;
    verification_scope?: string[];
    frozen_fields?: string[];
    gap_codes?: string[];
    contract_manifest_id?: string | null;
    contract_manifest_hash?: string | null;
    contract_policy_version?: string | null;
    contract_scope?: string[];
    contract_refs?: FrozenContractReference[];
  };
  contract_check?: ContractVerification | null;
}

export interface ReportComparison {
  comparison_id: string;
  left_report_id: string;
  right_report_id: string;
  policy_version: string;
  state: ReportComparisonState;
  reason_codes: string[];
  result: {
    facts?: Array<{ metric_key: string; left: string; right: string; delta?: string;
      pair_status?: ReportComparisonState; decision_reason_codes?: string[];
      comparison_permission?: { allowed: boolean; reason_codes: string[] };
      formula?: string; delta_semantics?: string;
      left_fact?: { trade_date: string; metric_identity?: { sample_role: string; unit: string } };
      right_fact?: { trade_date: string; metric_identity?: { sample_role: string; unit: string } } }>;
    unmatched_facts?: Record<string, Array<{ value: string; trade_date: string;
      metric_identity: { metric_id: string; entity_id: string; unit: string; sample_role: string } }>>;
    context_facts?: ReportComparison["result"]["unmatched_facts"];
    side_by_side_facts?: ReportComparison["result"]["unmatched_facts"];
    delta_policy?: string;
    comparison_mode?: ResearchComparisonMode;
    comparison_permissions?: { allowed: boolean; reason_codes: string[] };
    contract_check?: Record<string, ContractVerification>;
    contract_refs?: Record<string, Array<Omit<FrozenContractReference, "tool_result_archive_id"> & { source_ids?: Record<string, string | number> | null }>>;
    sample_context?: Record<string, unknown>;
    explain_reasons?: Array<{ field: string; left: string; right: string }>;
  };
  display_result?: ReportComparison["result"] | null;
  display_safety?: { legacy_policy: boolean; delta_allowed: boolean; warnings: string[] } | null;
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
  reportType?: ReportType,
  signal?: AbortSignal
): Promise<ApiPage<ResearchReportSummary[], { total: number }>> {
  const query = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
    include_archived: String(includeArchived)
  });
  if (reportType) query.set("type", reportType);
  return requestPage<ResearchReportSummary[], { total: number }>(
    `/agent/reports?${query.toString()}`, signal ? { signal } : undefined
  );
}

export function fetchResearchReport(reportId: string, signal?: AbortSignal): Promise<ResearchReport> {
  return request<ResearchReport>(`/agent/reports/${encodeURIComponent(reportId)}`, signal ? { signal } : undefined);
}

export function fetchReportContracts(reportId: string, offset = 0, signal?: AbortSignal): Promise<ApiPage<FrozenContractReference[], { total: number; check: ContractVerification }>> {
  return requestPage(`/agent/reports/${encodeURIComponent(reportId)}/contracts?limit=20&offset=${offset}`, { signal });
}
export function fetchReportContract(reportId: string, contractId: string, signal?: AbortSignal): Promise<FrozenContractDetail> {
  return request(`/agent/reports/${encodeURIComponent(reportId)}/contracts/${encodeURIComponent(contractId)}`, { signal });
}
export function verifyReportContracts(reportId: string, signal?: AbortSignal): Promise<ContractVerification> {
  return request(`/agent/reports/${encodeURIComponent(reportId)}/verify-contracts`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: "{}", signal
  });
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
  comparison_intent?: "AUTO" | "SAME_ENTITY_OVER_TIME" | "CROSS_ENTITY_SAME_DATE"
    | "INDEPENDENT_BACKTESTS" | "TRAIN_VS_OOS";
  comparison_mode?: Exclude<ResearchComparisonMode, "AUTO">;
}, signal?: AbortSignal): Promise<ReportComparison> {
  return request<ReportComparison>("/agent/report-comparisons", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload), signal
  });
}

export async function downloadReportComparison(comparisonId: string, format: "markdown" | "html"): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/agent/report-comparisons/${encodeURIComponent(comparisonId)}/export?format=${format}`, { credentials: "include" });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(body?.detail?.code || `HTTP ${response.status}`, response.status, body?.detail || null);
  }
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = `research-comparison-${comparisonId}.${format === "html" ? "html" : "md"}`;
  link.click();
  URL.revokeObjectURL(url);
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
