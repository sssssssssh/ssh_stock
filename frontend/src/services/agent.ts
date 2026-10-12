import { request, requestPage, type ApiPage } from "./api";

export type AnswerStatus = "COMPLETED" | "PARTIAL_VERIFIED" | "INSUFFICIENT_EVIDENCE";

export interface AgentStatus {
  agent_mode: "tools_only" | "llm_chat";
  registry_version: string;
  tool_count: number;
  llm_enabled: boolean;
  read_only: boolean;
  statement_timeout_ms: number;
}

export interface AgentChatSummary {
  chat_id: string;
  title: string;
  status: "ACTIVE" | "ARCHIVED";
  created_at: string;
  updated_at: string;
}

export interface AgentFact {
  path: string;
  value: string | number;
  unit: string;
  trade_date: string;
  entity: string;
  sample_role: string;
}

export interface AgentClaim {
  claim_id: string;
  claim_type: "FACT" | "INFERENCE" | "COMPARISON";
  text: string;
  evidence_ids: string[];
  structured_facts: AgentFact[];
  quality_status: string;
  comparison_state?: string | null;
  reason_codes: string[];
  policy_version?: string | null;
}

export interface AgentRejectedClaim {
  claim_id: string;
  claim_type: "FACT" | "INFERENCE" | "COMPARISON";
  reason_codes: string[];
  comparison_state?: string | null;
  policy_version?: string | null;
}

export interface AgentCitation {
  marker: string;
  evidence_id: string;
  evidence_version: "v1" | "v2";
  tool_name: string;
  entity_id: string;
  as_of_date?: string | null;
  report_id?: string | null;
  calc_run_id?: string | null;
  calc_version?: string | null;
  config_hash?: string | null;
  source_hash?: string | null;
  content_hash?: string | null;
  observed_at?: string | null;
}

export interface AgentToolCall {
  tool_call_id: string;
  tool_name: string;
  status: string;
  duration_ms: number;
  error_code?: string | null;
  cache_reused: boolean;
}

export interface AgentMessageMetadata {
  answer_status?: AnswerStatus;
  status?: AnswerStatus;
  verified_claims?: AgentClaim[];
  claims?: AgentClaim[];
  rejected_claims?: AgentRejectedClaim[];
  citations?: AgentCitation[];
  warnings?: string[];
  tool_calls?: AgentToolCall[];
  needs_clarification?: boolean;
  trace_id?: string | null;
}

export interface AgentMessage {
  message_id: string;
  role: "USER" | "ASSISTANT";
  content: string;
  status: "COMPLETED" | "FAILED";
  sequence_no: number;
  metadata: AgentMessageMetadata;
  created_at: string;
}

export interface AgentChatDetail extends AgentChatSummary {
  messages: AgentMessage[];
}

export interface AgentAnswer {
  chat_id: string;
  message_id: string;
  status: AnswerStatus;
  answer_status: AnswerStatus;
  answer: string;
  claims: AgentClaim[];
  verified_claims: AgentClaim[];
  rejected_claims: AgentRejectedClaim[];
  needs_clarification: boolean;
  citations: AgentCitation[];
  warnings: string[];
  tool_calls: AgentToolCall[];
  trace_id: string;
}

export interface ResearchContext {
  ts_code?: string;
  trade_date?: string;
  sector_id?: string;
  run_id?: string;
  study_id?: string;
  validation_id?: string;
}

export function fetchAgentStatus(): Promise<AgentStatus> {
  return request<AgentStatus>("/agent/status");
}

export function fetchAgentChats(limit = 20, offset = 0): Promise<ApiPage<AgentChatSummary[], { total: number }>> {
  return requestPage<AgentChatSummary[], { total: number }>(`/agent/chats?limit=${limit}&offset=${offset}`);
}

export function createAgentChat(title?: string): Promise<AgentChatSummary> {
  return request<AgentChatSummary>("/agent/chats", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: title || undefined })
  });
}

export function fetchAgentChat(chatId: string, limit = 100, offset = 0): Promise<ApiPage<AgentChatDetail, { total: number }>> {
  return requestPage<AgentChatDetail, { total: number }>(
    `/agent/chats/${encodeURIComponent(chatId)}?limit=${limit}&offset=${offset}`
  );
}

export function archiveAgentChat(chatId: string): Promise<AgentChatSummary> {
  return request<AgentChatSummary>(`/agent/chats/${encodeURIComponent(chatId)}`, {
    method: "DELETE"
  });
}

export function sendAgentMessage(chatId: string, content: string, requestId: string): Promise<AgentAnswer> {
  return request<AgentAnswer>(`/agent/chats/${encodeURIComponent(chatId)}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content, request_id: requestId })
  });
}
