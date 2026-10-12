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
  navigation?: ResearchNavigationContext | null;
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
  active_turn?: AgentTurnStatus | null;
}

export interface AgentMessagePageMeta {
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
  next_cursor: number | null;
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

export interface ResearchNavigationContext {
  view: "overview" | "long" | "analytics" | "walk_forward";
  ts_code?: string;
  trade_date?: string;
  sector_id?: string;
  run_id?: string;
  study_id?: string;
  validation_id?: string;
  window_no?: number;
  source_tool: string;
}

export type ResearchContext = Partial<ResearchNavigationContext>;

export type PendingSendState =
  | "IDLE"
  | "SENDING"
  | "UNKNOWN_RESULT"
  | "RUNNING"
  | "COMPLETED"
  | "FAILED";

export interface PendingSend {
  chatId: string;
  requestId: string;
  normalizedContent: string;
  state: PendingSendState;
  createdAt: string;
}

export interface AgentTurnStatus {
  chat_id: string;
  request_id: string;
  status: "RUNNING" | "COMPLETED" | "FAILED";
  error_code?: string | null;
  content: string;
  user_message_id: string;
  assistant_message_id?: string | null;
  started_at: string;
  finished_at?: string | null;
  answer?: AgentAnswer | null;
}

export type WalkForwardDetail = Record<string, unknown>;

export function normalizeAgentRequestContent(content: string): string {
  return content.normalize("NFKC").replace(/\r\n?/g, "\n").trim()
    .split("\n").map((line) => line.trimEnd()).join("\n");
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

export function fetchLatestAgentChat(
  chatId: string,
  limit = 50
): Promise<ApiPage<AgentChatDetail, AgentMessagePageMeta>> {
  return requestPage<AgentChatDetail, AgentMessagePageMeta>(
    `/agent/chats/${encodeURIComponent(chatId)}?limit=${limit}&latest=true`
  );
}

export function fetchEarlierAgentMessages(
  chatId: string,
  beforeSequence: number,
  limit = 50
): Promise<ApiPage<AgentChatDetail, AgentMessagePageMeta>> {
  return requestPage<AgentChatDetail, AgentMessagePageMeta>(
    `/agent/chats/${encodeURIComponent(chatId)}?limit=${limit}&before_sequence=${beforeSequence}`
  );
}

export function fetchAgentTurnStatus(chatId: string, requestId: string): Promise<AgentTurnStatus> {
  return request<AgentTurnStatus>(
    `/agent/chats/${encodeURIComponent(chatId)}/turns/${encodeURIComponent(requestId)}`
  );
}

export function archiveAgentChat(chatId: string): Promise<AgentChatSummary> {
  return request<AgentChatSummary>(`/agent/chats/${encodeURIComponent(chatId)}`, {
    method: "DELETE"
  });
}

export async function sendAgentMessage(chatId: string, content: string, requestId: string): Promise<AgentAnswer> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 180000);
  try {
    return await request<AgentAnswer>(`/agent/chats/${encodeURIComponent(chatId)}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content, request_id: requestId }),
      signal: controller.signal
    });
  } finally {
    window.clearTimeout(timeout);
  }
}

export function fetchWalkForwardStudy(studyId: string): Promise<WalkForwardDetail> {
  return request<WalkForwardDetail>(`/portfolio/walk-forwards/${encodeURIComponent(studyId)}`);
}

export function fetchWalkForwardValidation(
  studyId: string,
  validationId: string
): Promise<WalkForwardDetail> {
  return request<WalkForwardDetail>(
    `/portfolio/walk-forwards/${encodeURIComponent(studyId)}/validations/${encodeURIComponent(validationId)}`
  );
}

export function fetchWalkForwardValidationWindow(
  studyId: string, validationId: string, windowNo: number
): Promise<ApiPage<WalkForwardDetail[], { total: number }>> {
  return requestPage<WalkForwardDetail[], { total: number }>(
    `/portfolio/walk-forwards/${encodeURIComponent(studyId)}/validations/${encodeURIComponent(validationId)}/windows?limit=1&window_no=${windowNo}`
  );
}
