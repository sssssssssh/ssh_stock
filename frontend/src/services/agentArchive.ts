import { request, requestPage } from "./api";

export type ArchiveStatus = "COMPLETE" | "PARTIAL" | "UNAVAILABLE";
export type CheckStatus = "VERIFIED" | "MISMATCH" | "UNVERIFIABLE";
export interface ArchiveSummary {
  archive_status: ArchiveStatus;
  manifest_id?: string | null;
  manifest_version?: string | null;
  manifest_hash?: string | null;
  source_turn_id?: string | null;
  reproduction_level: "SNAPSHOT_ONLY" | "FROZEN_FACT_RECHECK" | "FROZEN_CONTRACT_RECHECK";
  required_evidence_count: number;
  archived_evidence_count: number;
  integrity: { status: CheckStatus; policy_version: string };
  calculation_reproduced: false;
  warnings: string[];
  limitations: string[];
}
export interface ArchiveEvidence {
  evidence_id: string;
  tool_call_id: string;
  tool_name: string;
  tool_version: string;
  as_of_date?: string | null;
  created_at: string;
  record_path: string;
  entity_id?: string | null;
  calc_version?: string | null;
  algo_version?: string | null;
  config_hash?: string | null;
  source_hash?: string | null;
  content_hash?: string | null;
}
export interface ArchiveDetail extends ArchiveSummary, Partial<ArchiveEvidence> {
  evidence_id: string;
  projection_version?: string | null;
  arguments_summary: Record<string, string | number | null>;
  arguments_hash?: string | null;
  registry_schema_hash?: string | null;
  frozen_facts: Array<{ claim_id: string; path: string; value: string | number;
    unit: string; entity: string; trade_date: string; sample_role: string }>;
}
export interface ArchiveVerification extends ArchiveSummary {
  verification_level: string;
  claim_recheck_summary?: { status: CheckStatus; verified_count: number;
    mismatch_count: number; unverifiable_count: number };
  fact_recheck: { status: CheckStatus; checked_claim_count: number; policy_version: string;
    results: Array<{ claim_id: string; status: CheckStatus; reason_codes: string[];
      facts_status?: CheckStatus; facts_applicable?: boolean;
      check_kind?: "DIRECT_FACT" | "COMPARISON_CONTEXT" | "INFERENCE_SUPPORT";
      support_status?: CheckStatus | null;
      comparison_state?: "COMPARABLE" | "CONTEXT_REQUIRED" | "INCOMPATIBLE" | null;
      verified_fact_refs: string[]; failed_fields: Array<{ path: string; code: string }> }> };
}
export const unavailableArchive: ArchiveSummary = {
  archive_status: "UNAVAILABLE", reproduction_level: "SNAPSHOT_ONLY",
  required_evidence_count: 0, archived_evidence_count: 0,
  integrity: { status: "UNVERIFIABLE", policy_version: "m16.5-integrity-v1" },
  calculation_reproduced: false, warnings: ["ARCHIVE_UNAVAILABLE", "REPLAY_UNAVAILABLE"],
  limitations: ["历史报告仅含 Claim 快照，无法恢复当次工具原始响应"]
};
export function fetchTurnArchive(chatId: string, requestId: string, signal?: AbortSignal) {
  return request<ArchiveSummary & { evidence: ArchiveEvidence[] }>(
    `/agent/chats/${encodeURIComponent(chatId)}/turn-archives/${encodeURIComponent(requestId)}`, { signal });
}
export function fetchReportEvidence(reportId: string, offset = 0, signal?: AbortSignal) {
  return requestPage<ArchiveEvidence[], ArchiveSummary & { total: number }>(
    `/agent/reports/${encodeURIComponent(reportId)}/evidence?limit=20&offset=${offset}`, { signal });
}
export function fetchEvidenceDetail(reportId: string, evidenceId: string, signal?: AbortSignal) {
  return request<ArchiveDetail>(`/agent/reports/${encodeURIComponent(reportId)}/evidence/${encodeURIComponent(evidenceId)}`, { signal });
}
export function verifyFrozenReport(reportId: string, signal?: AbortSignal) {
  return request<ArchiveVerification>(`/agent/reports/${encodeURIComponent(reportId)}/verify`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: "{}", signal
  });
}
