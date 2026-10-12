<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";

import { ApiError } from "../services/api";
import {
  archiveAgentChat,
  createAgentChat,
  fetchAgentChats,
  fetchAgentStatus,
  fetchAgentTurnStatus,
  fetchEarlierAgentMessages,
  fetchLatestAgentChat,
  normalizeAgentRequestContent,
  sendAgentMessage,
  type AgentChatSummary,
  type AgentCitation,
  type AgentMessage,
  type AgentMessageMetadata,
  type AgentMessagePageMeta,
  type AgentTurnStatus,
  type PendingSend,
  type ResearchContext,
  type ResearchNavigationContext
} from "../services/agent";

const MESSAGE_PAGE_SIZE = 50;
const MAX_POLL_ATTEMPTS = 12;
const PENDING_STORAGE_PREFIX = "ssh-stock.agent.pending.v2.";
const PENDING_MAX_AGE = 24 * 60 * 60 * 1000;

const props = withDefaults(defineProps<{
  initialContext?: ResearchContext | null;
  ownerId?: string;
  visible?: boolean;
}>(), { visible: true });
const emit = defineEmits<{ navigate: [target: ResearchNavigationContext] }>();

const chats = ref<AgentChatSummary[]>([]);
const chatTotal = ref(0);
const chatOffset = ref(0);
const chatLimit = 20;
const activeChatId = ref("");
const messages = ref<AgentMessage[]>([]);
const messageTotal = ref(0);
const messageHasMore = ref(false);
const messageCursor = ref<number | null>(null);
const loadingChats = ref(true);
const loadingMessages = ref(false);
const loadingEarlier = ref(false);
const error = ref("");
const draft = ref("");
const llmEnabled = ref(false);
const registryVersion = ref("");
const toolCount = ref(0);
const evidenceOpen = ref(false);
const selectedCitation = ref<AgentCitation | null>(null);
const citationEntries = computed(() => {
  const citation = selectedCitation.value;
  if (!citation) return [];
  const keys: Array<keyof AgentCitation> = ["marker", "evidence_id", "evidence_version", "tool_name", "entity_id", "as_of_date", "report_id", "calc_run_id", "calc_version", "config_hash", "source_hash", "content_hash", "observed_at"];
  return keys.map((key) => [key, citation[key]]);
});
const navigationError = ref("");
const streamRef = ref<HTMLElement | null>(null);
const context = ref<ResearchContext>({});
const scrollPositions = ref<Record<string, number>>({});
const pendingByChat = ref<Record<string, PendingSend>>({});
const persistedPending = ref(loadPersistedPending());
const pollAttempts = new Map<string, number>();
const pollTimers = new Map<string, number>();
const draftByChat = new Map<string, string>();
const pageByChat = new Map<string, { messages: AgentMessage[]; meta: AgentMessagePageMeta }>();
const sendErrors = ref<Record<string, string>>({});
const blockedReplay = ref(new Set<string>());
const online = ref(navigator.onLine);
let selectionGeneration = 0;
let disposed = false;
let submitting = false;

const activeChat = computed(() => chats.value.find((item) => item.chat_id === activeChatId.value));
const activePending = computed(() => pendingByChat.value[activeChatId.value]);
const visibleError = computed(() => sendErrors.value[activeChatId.value] || error.value);
const sending = computed(() => ["SENDING", "RUNNING"].includes(activePending.value?.state || ""));
const hasMoreChats = computed(() => chats.value.length < chatTotal.value);
const contextEntries = computed(() =>
  Object.entries(context.value).filter(
    (entry): entry is [string, string | number] =>
      !["view", "source_tool"].includes(entry[0]) && entry[1] !== undefined && entry[1] !== ""
  )
);

watch(
  () => props.initialContext,
  (value) => {
    if (value) context.value = { ...context.value, ...value };
  },
  { deep: true, immediate: true }
);

function statusLabel(value?: string) {
  return {
    COMPLETED: "已验证",
    PARTIAL_VERIFIED: "部分已验证",
    INSUFFICIENT_EVIDENCE: "证据不足"
  }[value || ""] || value || "--";
}

function statusClass(value?: string) {
  if (value === "COMPLETED") return "complete";
  if (value === "PARTIAL_VERIFIED") return "partial";
  return "insufficient";
}

function pendingLabel(value?: string) {
  return {
    SENDING: "正在发送",
    UNKNOWN_RESULT: "结果待确认",
    RUNNING: "服务端处理中",
    COMPLETED: "已完成",
    FAILED: "执行失败"
  }[value || ""] || "";
}

function metadata(message: AgentMessage): AgentMessageMetadata {
  return message.metadata || {};
}

function verifiedClaims(message: AgentMessage) {
  const value = metadata(message);
  return value.verified_claims || value.claims || [];
}

function newRequestId() {
  return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function errorText(value: unknown) {
  if (value instanceof ApiError) {
    const labels: Record<string, string> = {
      AGENT_LLM_DISABLED: "智能研究尚未启用，请先配置服务端 LLM 开关和密钥。",
      LLM_DISABLED: "智能研究尚未启用，请先配置服务端 LLM 开关和密钥。",
      LLM_NOT_CONFIGURED: "智能研究模型凭据尚未配置。",
      CHAT_NOT_FOUND: "会话不存在或已不可访问。",
      CHAT_CONFLICT: "当前会话已有任务执行中。",
      IDEMPOTENCY_CONFLICT: "本次请求标识已用于其他内容，不能自动重放。",
      TOTAL_DEADLINE_EXCEEDED: "研究请求已超过服务端总时限。",
      TOOL_TIMEOUT: "只读工具执行超时。",
      LLM_TIMEOUT: "模型请求超时。",
      TURN_NOT_FOUND: "服务端尚未发现该请求。",
      UNAUTHORIZED: "登录已失效，请重新登录。"
    };
    return labels[value.code] || value.code;
  }
  if (value instanceof TypeError) return "网络连接中断，结果尚不能确认。";
  return value instanceof Error ? value.message : "智能研究请求失败";
}

async function initialize() {
  loadingChats.value = true;
  error.value = "";
  try {
    const [status, page] = await Promise.all([fetchAgentStatus(), fetchAgentChats(chatLimit, 0)]);
    llmEnabled.value = status.llm_enabled;
    registryVersion.value = status.registry_version;
    toolCount.value = status.tool_count;
    chats.value = page.data;
    chatTotal.value = page.meta.total;
    chatOffset.value = page.data.length;
    const recoverable = persistedPending.value.find((item) =>
      chats.value.some((chat) => chat.chat_id === item.chatId && chat.status === "ACTIVE")
    );
    const first = recoverable
      ? chats.value.find((item) => item.chat_id === recoverable.chatId)
      : chats.value.find((item) => item.status === "ACTIVE");
    if (first) await selectChat(first.chat_id);
  } catch (value) {
    error.value = errorText(value);
  } finally {
    loadingChats.value = false;
  }
}

async function loadMoreChats() {
  if (!hasMoreChats.value || loadingChats.value) return;
  loadingChats.value = true;
  try {
    const page = await fetchAgentChats(chatLimit, chatOffset.value);
    const known = new Set(chats.value.map((item) => item.chat_id));
    chats.value.push(...page.data.filter((item) => !known.has(item.chat_id)));
    chatOffset.value += page.data.length;
    chatTotal.value = page.meta.total;
  } catch (value) {
    error.value = errorText(value);
  } finally {
    loadingChats.value = false;
  }
}

async function selectChat(chatId: string) {
  if (activeChatId.value && streamRef.value) {
    scrollPositions.value[activeChatId.value] = streamRef.value.scrollTop;
  }
  draftByChat.set(activeChatId.value, draft.value);
  const generation = ++selectionGeneration;
  activeChatId.value = chatId;
  const selectedPage = pageByChat.get(chatId);
  messages.value = selectedPage?.messages || [];
  messageTotal.value = selectedPage?.meta.total || 0;
  messageHasMore.value = selectedPage?.meta.has_more || false;
  messageCursor.value = selectedPage?.meta.next_cursor || null;
  draft.value = draftByChat.get(chatId) || "";
  selectedCitation.value = null;
  evidenceOpen.value = false;
  loadingMessages.value = true;
  loadingEarlier.value = false;
  error.value = "";
  try {
    const page = await fetchLatestAgentChat(chatId, MESSAGE_PAGE_SIZE);
    if (disposed || generation !== selectionGeneration || activeChatId.value !== chatId) return;
    const cached = pageByChat.get(chatId);
    messages.value = uniqueMessages([...(cached?.messages || []), ...page.data.messages]);
    messageTotal.value = page.meta.total;
    const overlaps = cached?.messages.some((row) => page.data.messages.some((fresh) => fresh.sequence_no === row.sequence_no));
    updatePageCursor(page.meta, overlaps ? cached?.meta.next_cursor : undefined);
    await restorePosition(chatId);
    await recoverPending(chatId, page.data.active_turn);
  } catch (value) {
    if (activeChatId.value === chatId) error.value = errorText(value);
  } finally {
    if (generation === selectionGeneration && activeChatId.value === chatId) {
      loadingMessages.value = false;
    }
  }
}

async function loadEarlierMessages() {
  const chatId = activeChatId.value;
  const generation = selectionGeneration;
  const before = messageCursor.value;
  const stream = streamRef.value;
  if (!chatId || !before || loadingEarlier.value) return;
  loadingEarlier.value = true;
  const previousHeight = stream?.scrollHeight || 0;
  const previousTop = stream?.scrollTop || 0;
  try {
    const page = await fetchEarlierAgentMessages(chatId, before, MESSAGE_PAGE_SIZE);
    if (disposed || generation !== selectionGeneration || activeChatId.value !== chatId) return;
    messages.value = uniqueMessages([...page.data.messages, ...messages.value]);
    messageTotal.value = page.meta.total;
    messageHasMore.value = page.meta.has_more;
    messageCursor.value = page.meta.next_cursor;
    cacheCurrentPage();
    await nextTick();
    if (streamRef.value) {
      streamRef.value.scrollTop = streamRef.value.scrollHeight - previousHeight + previousTop;
    }
  } catch (value) {
    if (activeChatId.value === chatId) error.value = errorText(value);
  } finally {
    if (generation === selectionGeneration) loadingEarlier.value = false;
  }
}

async function refreshCurrentMessages(chatId: string, forceEnd = false) {
  const atBottom = isAtBottom();
  const page = await fetchLatestAgentChat(chatId, MESSAGE_PAGE_SIZE);
  if (disposed) return;
  const shouldFollow = forceEnd || (atBottom && isAtBottom());
  const cached = pageByChat.get(chatId);
  const base = activeChatId.value === chatId ? messages.value : cached?.messages || [];
  const merged = uniqueMessages([
    ...base.filter((row) => !row.message_id.startsWith("pending-")),
    ...page.data.messages
  ]);
  const overlaps = base.some((row) => page.data.messages.some((fresh) => fresh.sequence_no === row.sequence_no));
  const previousCursor = activeChatId.value === chatId ? messageCursor.value : cached?.meta.next_cursor;
  const hasMore = merged.length < page.meta.total;
  const cursor = hasMore ? (overlaps && previousCursor ? previousCursor : page.meta.next_cursor) : null;
  pageByChat.set(chatId, { messages: merged, meta: { ...page.meta, has_more: hasMore, next_cursor: cursor } });
  if (activeChatId.value !== chatId) return;
  messages.value = merged;
  messageTotal.value = page.meta.total;
  messageHasMore.value = hasMore;
  messageCursor.value = cursor;
  if (shouldFollow && props.visible) await scrollToEnd();
}

function updatePageCursor(meta: AgentMessagePageMeta, preservedCursor?: number | null) {
  messageHasMore.value = messages.value.length < meta.total;
  messageCursor.value = messageHasMore.value ? preservedCursor || meta.next_cursor : null;
  cacheCurrentPage();
}

function cacheCurrentPage() {
  if (!activeChatId.value) return;
  pageByChat.set(activeChatId.value, {
    messages: [...messages.value],
    meta: { total: messageTotal.value, has_more: messageHasMore.value, next_cursor: messageCursor.value, limit: MESSAGE_PAGE_SIZE, offset: 0 }
  });
}

async function newChat() {
  error.value = "";
  try {
    const chat = await createAgentChat();
    chats.value.unshift(chat);
    chatTotal.value += 1;
    await selectChat(chat.chat_id);
  } catch (value) {
    error.value = errorText(value);
  }
}

async function archiveCurrentChat() {
  if (!activeChatId.value || activePending.value) return;
  const chatId = activeChatId.value;
  try {
    await archiveAgentChat(chatId);
    chats.value = chats.value.filter((item) => item.chat_id !== chatId);
    chatTotal.value = Math.max(0, chatTotal.value - 1);
    activeChatId.value = "";
    messages.value = [];
    const next = chats.value.find((item) => item.status === "ACTIVE");
    if (next) await selectChat(next.chat_id);
  } catch (value) {
    error.value = errorText(value);
  }
}

function composedQuestion() {
  const selectors = contextEntries.value.map(([key, value]) => `${key}=${value}`).join(", ");
  return selectors
    ? `[显式上下文选择器，仅用于定位，不构成证据: ${selectors}]\n${draft.value.trim()}`
    : draft.value.trim();
}

async function submit() {
  if (submitting || !draft.value.trim() || activePending.value || !llmEnabled.value || !online.value || activeChat.value?.status === "ARCHIVED") return;
  submitting = true;
  if (!activeChatId.value) await newChat();
  if (!activeChatId.value) { submitting = false; return; }
  const pending: PendingSend = {
    chatId: activeChatId.value,
    requestId: newRequestId(),
    normalizedContent: normalizeAgentRequestContent(composedQuestion()),
    state: "SENDING",
    createdAt: new Date().toISOString()
  };
  setPending(pending);
  messages.value.push({
    message_id: `pending-${pending.requestId}`,
    role: "USER",
    content: pending.normalizedContent,
    status: "COMPLETED",
    sequence_no: (messages.value[messages.value.length - 1]?.sequence_no || 0) + 1,
    metadata: {},
    created_at: pending.createdAt
  });
  draft.value = "";
  draftByChat.set(pending.chatId, "");
  error.value = "";
  submitting = false;
  await scrollToEnd();
  await performSend(pending);
}

async function performSend(pending: PendingSend) {
  updatePending(pending.chatId, { state: "SENDING" });
  try {
    await sendAgentMessage(pending.chatId, pending.normalizedContent, pending.requestId);
    if (disposed) return;
    await completePending(pending.chatId, pending.requestId);
  } catch (value) {
    if (disposed) return;
    await handleSendFailure(pending, value);
  }
}

async function handleSendFailure(pending: PendingSend, value: unknown) {
  if (!isCurrentPending(pending)) return;
  if (isUnknownResult(value)) {
    updatePending(pending.chatId, { state: "UNKNOWN_RESULT" });
    sendErrors.value[pending.chatId] = errorText(value);
    await reconcilePending(pending, true);
    return;
  }
  if (value instanceof ApiError && value.code === "CHAT_CONFLICT") {
    await reconcilePending(pending, true, value);
    return;
  }
  updatePending(pending.chatId, { state: "FAILED" });
  removePersistedPending(pending.chatId);
  sendErrors.value[pending.chatId] = errorText(value);
}

function isUnknownResult(value: unknown) {
  if (value instanceof TypeError) return true;
  if (value instanceof DOMException && value.name === "AbortError") return true;
  return value instanceof ApiError && value.status >= 500 && /^HTTP \d+$/.test(value.code);
}

async function recoverPending(chatId: string, activeTurn?: AgentTurnStatus | null) {
  if (disposed || pendingByChat.value[chatId]) return;
  if (activeTurn) {
    const pending: PendingSend = {
      chatId, requestId: activeTurn.request_id, normalizedContent: activeTurn.content,
      state: "RUNNING", createdAt: activeTurn.started_at
    };
    setPending(pending);
    await applyTurnStatus(pending, activeTurn, true);
    return;
  }
  const saved = persistedPending.value.find((item) => item.chatId === chatId);
  if (!saved) return;
  setPending({ ...saved, normalizedContent: "", state: "UNKNOWN_RESULT" });
  blockedReplay.value.add(chatId);
  try {
    const status = await fetchAgentTurnStatus(chatId, saved.requestId);
    if (disposed) return;
    const pending: PendingSend = {
      chatId,
      requestId: saved.requestId,
      normalizedContent: status.content,
      state: status.status === "RUNNING" ? "RUNNING" : status.status,
      createdAt: saved.createdAt
    };
    setPending(pending);
    await applyTurnStatus(pending, status, true);
  } catch (value) {
    if (value instanceof ApiError && value.code === "TURN_NOT_FOUND") {
      sendErrors.value[chatId] = "服务端尚未确认这条请求，请先刷新状态。原问题正文未保存在浏览器。";
      return;
    }
    sendErrors.value[chatId] = errorText(value);
  }
}

async function reconcilePending(
  pending: PendingSend,
  startPolling: boolean,
  fallbackError?: unknown
) {
  try {
    const status = await fetchAgentTurnStatus(pending.chatId, pending.requestId);
    if (disposed || !isCurrentPending(pending)) return;
    await applyTurnStatus(pending, status, startPolling);
  } catch (value) {
    if (disposed || !isCurrentPending(pending)) return;
    if (value instanceof ApiError && value.code === "TURN_NOT_FOUND") {
      updatePending(pending.chatId, { state: fallbackError ? "FAILED" : "UNKNOWN_RESULT" });
      if (fallbackError) removePersistedPending(pending.chatId);
      sendErrors.value[pending.chatId] = fallbackError ? errorText(fallbackError) : "服务端尚未发现该请求，可使用原请求标识重试。";
      return;
    }
    updatePending(pending.chatId, { state: "UNKNOWN_RESULT" });
    if (fallbackError) blockedReplay.value.add(pending.chatId);
    sendErrors.value[pending.chatId] = errorText(fallbackError || value);
  }
}

async function applyTurnStatus(pending: PendingSend, status: AgentTurnStatus, startPolling: boolean) {
  if (!isCurrentPending(pending)) return;
  const sameContent = !pending.normalizedContent || normalizeAgentRequestContent(pending.normalizedContent) === normalizeAgentRequestContent(status.content);
  if (status.chat_id !== pending.chatId || status.request_id !== pending.requestId || !sameContent) {
    updatePending(pending.chatId, { state: "FAILED" });
    removePersistedPending(pending.chatId);
    clearPoll(pending.chatId);
    sendErrors.value[pending.chatId] = errorText(new ApiError("IDEMPOTENCY_CONFLICT", 409));
    return;
  }
  if (!pending.normalizedContent) updatePending(pending.chatId, { normalizedContent: status.content });
  if (status.status === "COMPLETED") {
    await completePending(pending.chatId, pending.requestId);
    return;
  }
  if (status.status === "FAILED") {
    updatePending(pending.chatId, { state: "FAILED" });
    removePersistedPending(pending.chatId);
    clearPoll(pending.chatId);
    sendErrors.value[pending.chatId] = errorText(new ApiError(status.error_code || "INTERNAL_ERROR", 500));
    return;
  }
  updatePending(pending.chatId, { state: "RUNNING" });
  delete sendErrors.value[pending.chatId];
  if (startPolling) schedulePoll(pending.chatId);
}

function isCurrentPending(pending: PendingSend) {
  return pendingByChat.value[pending.chatId]?.requestId === pending.requestId;
}

async function completePending(chatId: string, requestId: string) {
  if (pendingByChat.value[chatId]?.requestId !== requestId) return;
  updatePending(chatId, { state: "COMPLETED" });
  removePersistedPending(chatId);
  clearPoll(chatId);
  pollAttempts.delete(chatId);
  delete sendErrors.value[chatId];
  blockedReplay.value.delete(chatId);
  try { await refreshCurrentMessages(chatId); }
  catch (value) { sendErrors.value[chatId] = errorText(value); return; }
  const current = chats.value.find((item) => item.chat_id === chatId);
  if (current) current.updated_at = new Date().toISOString();
  if (pendingByChat.value[chatId]?.requestId === requestId) delete pendingByChat.value[chatId];
}

function schedulePoll(chatId: string) {
  clearPoll(chatId);
  const attempts = pollAttempts.get(chatId) || 0;
  if (disposed || attempts >= MAX_POLL_ATTEMPTS || document.visibilityState === "hidden" || !props.visible) return;
  pollAttempts.set(chatId, attempts + 1);
  const delay = 2000;
  pollTimers.set(chatId, window.setTimeout(async () => {
    const pending = pendingByChat.value[chatId];
    if (!pending || pending.state !== "RUNNING") return;
    await reconcilePending(pending, true);
  }, delay));
}

function clearPoll(chatId: string) {
  const timer = pollTimers.get(chatId);
  if (timer !== undefined) window.clearTimeout(timer);
  pollTimers.delete(chatId);
}

async function retryUnknown() {
  const pending = activePending.value;
  if (!pending || !pending.normalizedContent || pending.state !== "UNKNOWN_RESULT" || blockedReplay.value.has(pending.chatId)) return;
  // A lost HTTP reply may already have committed a turn; check before replay.
  updatePending(pending.chatId, { state: "SENDING" });
  try {
    const status = await fetchAgentTurnStatus(pending.chatId, pending.requestId);
    if (!disposed) await applyTurnStatus(pending, status, true);
  } catch (value) {
    if (disposed || !isCurrentPending(pending)) return;
    if (value instanceof ApiError && value.code === "TURN_NOT_FOUND") await performSend(pending);
    else {
      updatePending(pending.chatId, { state: "UNKNOWN_RESULT" });
      sendErrors.value[pending.chatId] = errorText(value);
    }
  }
}

async function refreshPendingStatus() {
  const pending = activePending.value;
  if (!pending) return;
  await reconcilePending(pending, pending.state === "RUNNING");
}

function retryAsNewRequest() {
  const pending = activePending.value;
  if (!pending || pending.state !== "FAILED") return;
  const lines = pending.normalizedContent.split("\n");
  draft.value = lines[0]?.startsWith("[显式上下文选择器") ? lines.slice(1).join("\n") : pending.normalizedContent;
  messages.value = messages.value.filter((row) => row.message_id !== `pending-${pending.requestId}`);
  delete pendingByChat.value[pending.chatId];
  error.value = "";
  delete sendErrors.value[pending.chatId];
  blockedReplay.value.delete(pending.chatId);
}

function setPending(pending: PendingSend) {
  pendingByChat.value[pending.chatId] = pending;
  const safe = {
    chatId: pending.chatId,
    requestId: pending.requestId,
    state: pending.state,
    createdAt: pending.createdAt
  };
  persistedPending.value = [
    ...persistedPending.value.filter((item) => item.chatId !== pending.chatId),
    safe
  ];
  savePersistedPending();
}

function updatePending(chatId: string, patch: Partial<PendingSend>) {
  const current = pendingByChat.value[chatId];
  if (!current) return;
  setPending({ ...current, ...patch });
}

function removePersistedPending(chatId: string) {
  persistedPending.value = persistedPending.value.filter((item) => item.chatId !== chatId);
  savePersistedPending();
}

function loadPersistedPending(): Array<Omit<PendingSend, "normalizedContent">> {
  if (!props.ownerId) return [];
  try {
    const raw = sessionStorage.getItem(`${PENDING_STORAGE_PREFIX}${encodeURIComponent(props.ownerId)}`);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((item) =>
      typeof item?.chatId === "string" && typeof item?.requestId === "string"
      && Number.isFinite(Date.parse(item.createdAt))
      && Date.now() - Date.parse(item.createdAt) < PENDING_MAX_AGE
    ).map((item) => ({ chatId: item.chatId, requestId: item.requestId, state: item.state, createdAt: item.createdAt })) : [];
  } catch {
    return [];
  }
}

function savePersistedPending() {
  if (!props.ownerId || disposed) return;
  try {
    sessionStorage.setItem(`${PENDING_STORAGE_PREFIX}${encodeURIComponent(props.ownerId)}`, JSON.stringify(persistedPending.value));
  } catch { /* Server status remains the recovery authority when storage is unavailable. */ }
}

function showEvidence(citation: AgentCitation) {
  selectedCitation.value = citation;
  navigationError.value = "";
  evidenceOpen.value = true;
}

async function copyEvidenceId() {
  if (selectedCitation.value) await navigator.clipboard.writeText(selectedCitation.value.evidence_id);
}

function clearContext(key: string) {
  context.value = { ...context.value, [key]: undefined };
}

function openBusinessDetail() {
  const target = selectedCitation.value?.navigation;
  navigationError.value = "";
  if (!target || !hasRequiredNavigationIdentity(target)) {
    navigationError.value = "该证据暂不支持精准定位。";
    return;
  }
  evidenceOpen.value = false;
  emit("navigate", target);
}

function hasRequiredNavigationIdentity(target: ResearchNavigationContext) {
  if (target.view === "analytics") return Boolean(target.run_id);
  if (target.view === "long") return Boolean((target.ts_code || target.sector_id) && target.trade_date);
  if (target.view === "walk_forward") {
    return Boolean(target.study_id && target.validation_id && target.window_no);
  }
  return true;
}

function uniqueMessages(rows: AgentMessage[]) {
  const bySequence = new Map<number, AgentMessage>();
  for (const row of rows) bySequence.set(row.sequence_no, row);
  return [...bySequence.values()].sort((left, right) => left.sequence_no - right.sequence_no);
}

async function scrollToEnd() {
  await nextTick();
  if (streamRef.value) streamRef.value.scrollTop = streamRef.value.scrollHeight;
}

async function restorePosition(chatId: string) {
  await nextTick();
  if (!streamRef.value) return;
  const saved = scrollPositions.value[chatId];
  streamRef.value.scrollTop = saved === undefined ? streamRef.value.scrollHeight : saved;
}

function isAtBottom() {
  const stream = streamRef.value;
  return !stream || stream.scrollHeight - stream.scrollTop - stream.clientHeight <= 60;
}

function resumeVisiblePolling() {
  if (document.visibilityState === "hidden" || !props.visible) {
    for (const chatId of pollTimers.keys()) clearPoll(chatId);
    return;
  }
  for (const pending of Object.values(pendingByChat.value)) {
    if (pending.state === "RUNNING") schedulePoll(pending.chatId);
  }
}

function updateOnline() { online.value = navigator.onLine; }
watch(() => props.visible, (visible) => {
  if (!visible && activeChatId.value && streamRef.value) {
    scrollPositions.value[activeChatId.value] = streamRef.value.scrollTop;
  }
  if (visible && scrollPositions.value[activeChatId.value] !== undefined) {
    void restorePosition(activeChatId.value);
  }
  resumeVisiblePolling();
});

onMounted(() => {
  document.addEventListener("visibilitychange", resumeVisiblePolling);
  window.addEventListener("online", updateOnline);
  window.addEventListener("offline", updateOnline);
  void initialize();
});
onBeforeUnmount(() => {
  disposed = true;
  document.removeEventListener("visibilitychange", resumeVisiblePolling);
  window.removeEventListener("online", updateOnline);
  window.removeEventListener("offline", updateOnline);
  for (const chatId of pollTimers.keys()) clearPoll(chatId);
});
</script>

<template>
  <section class="agent-workbench">
    <header class="agent-header">
      <div><h2>智能研究</h2><p>只读证据工作台 · {{ registryVersion || "--" }} · {{ toolCount }} 个工具</p></div>
      <div class="agent-header-actions">
        <span class="readonly-badge">只读</span>
        <button type="button" class="agent-primary" @click="newChat">新建会话</button>
      </div>
    </header>

    <div v-if="!llmEnabled && !loadingChats" class="agent-notice">
      智能研究当前未启用。历史会话仍可查看，启用服务端 LLM 配置后才能发送问题。
    </div>
    <div v-if="!online" class="agent-notice" role="status">网络离线，待处理请求将保留原请求标识。</div>
    <div v-if="visibleError" class="agent-error" role="alert">
      {{ visibleError }}
      <button v-if="!activePending" type="button" @click="initialize">重试</button>
    </div>

    <div class="agent-layout">
      <aside class="agent-conversations" aria-label="研究会话">
        <div class="agent-pane-title"><strong>会话</strong><span>{{ chatTotal }}</span></div>
        <button
          v-for="chat in chats"
          :key="chat.chat_id"
          type="button"
          class="agent-chat-item"
          :class="{ active: chat.chat_id === activeChatId }"
          @click="selectChat(chat.chat_id)"
        >
          <strong>{{ chat.title }}</strong>
          <span>{{ new Date(chat.updated_at).toLocaleString("zh-CN") }}</span>
        </button>
        <div v-if="loadingChats" class="agent-empty">正在加载会话</div>
        <button v-if="hasMoreChats" type="button" class="agent-load-more" @click="loadMoreChats">加载更多</button>
      </aside>

      <main class="agent-chat-pane">
        <div class="agent-chat-toolbar">
          <div><strong>{{ activeChat?.title || "新研究会话" }}</strong><span v-if="messageTotal">{{ messageTotal }} 条消息</span></div>
          <button v-if="activeChatId" type="button" class="agent-icon-button" title="归档当前会话" aria-label="归档当前会话" :disabled="Boolean(activePending)" @click="archiveCurrentChat">×</button>
        </div>

        <div class="agent-context">
          <div class="agent-context-heading"><strong>上下文选择器</strong><span>仅用于定位，不作为证据</span></div>
          <div class="agent-context-fields">
            <label>股票代码<input v-model.trim="context.ts_code" placeholder="000001.SZ" /></label>
            <label>交易日<input v-model="context.trade_date" type="date" /></label>
            <label>回测 Run<input v-model.trim="context.run_id" placeholder="UUID" /></label>
            <label>Study<input v-model.trim="context.study_id" placeholder="UUID" /></label>
            <label>Validation<input v-model.trim="context.validation_id" placeholder="UUID" /></label>
          </div>
          <div v-if="contextEntries.length" class="agent-context-chips">
            <button v-for="[key, value] in contextEntries" :key="key" type="button" :title="`移除 ${key}`" @click="clearContext(key)">{{ key }}: {{ value }} ×</button>
          </div>
        </div>

        <div ref="streamRef" class="agent-stream" aria-live="polite" :aria-busy="loadingMessages || sending">
          <div v-if="loadingMessages" class="agent-empty">正在加载消息</div>
          <div v-else-if="!messages.length" class="agent-empty">选择或新建会话后开始研究</div>
          <button v-if="!loadingMessages && messageHasMore" type="button" class="agent-load-earlier" :disabled="loadingEarlier" @click="loadEarlierMessages">
            {{ loadingEarlier ? "正在加载" : "加载更早消息" }}
          </button>
          <article v-for="message in messages" :key="message.message_id" class="agent-message" :class="message.role.toLowerCase()">
            <div class="agent-message-meta">
              <strong>{{ message.role === "USER" ? "你" : "研究助手" }}</strong>
              <span v-if="message.role === 'ASSISTANT'" class="agent-status" :class="message.status === 'FAILED' ? 'insufficient' : statusClass(metadata(message).answer_status)">{{ message.status === 'FAILED' ? '执行失败' : statusLabel(metadata(message).answer_status) }}</span>
              <time>{{ new Date(message.created_at).toLocaleString("zh-CN") }}</time>
            </div>
            <p class="agent-answer">{{ message.content }}</p>

            <template v-if="message.role === 'ASSISTANT' && message.status !== 'FAILED'">
              <div v-if="verifiedClaims(message).length" class="agent-claims">
                <strong>已验证结论</strong>
                <div v-for="claim in verifiedClaims(message)" :key="claim.claim_id" class="agent-claim">
                  <span>{{ claim.claim_type }}</span><p>{{ claim.text }}</p>
                  <small v-if="claim.comparison_state">比较状态：{{ claim.comparison_state }}<template v-if="claim.reason_codes.length"> · {{ claim.reason_codes.join(" / ") }}</template></small>
                  <div v-if="claim.structured_facts.length" class="agent-facts">
                    <div v-for="fact in claim.structured_facts" :key="`${claim.claim_id}-${fact.path}-${fact.entity}`">
                      <code>{{ fact.path }}</code><strong>{{ fact.value }} {{ fact.unit }}</strong><span>{{ fact.trade_date }} · {{ fact.sample_role }}</span>
                    </div>
                  </div>
                </div>
              </div>
              <div v-if="metadata(message).rejected_claims?.length" class="agent-rejected">
                <strong>未通过校验</strong>
                <div v-for="claim in metadata(message).rejected_claims" :key="claim.claim_id">
                  <span>{{ claim.claim_id }}</span><code>{{ claim.reason_codes.join(" / ") }}</code>
                </div>
              </div>
              <div v-if="metadata(message).citations?.length" class="agent-citations">
                <button v-for="citation in metadata(message).citations" :key="citation.evidence_id" type="button" @click="showEvidence(citation)">
                  {{ citation.marker }} · {{ citation.tool_name }}
                </button>
              </div>
              <details v-if="metadata(message).tool_calls?.length || metadata(message).warnings?.length">
                <summary>执行详情</summary>
                <div v-for="call in metadata(message).tool_calls" :key="call.tool_call_id" class="agent-tool-call">
                  <code>{{ call.tool_name }}</code><span>{{ call.status }} · {{ call.duration_ms }}ms<template v-if="call.error_code"> · {{ call.error_code }}</template></span>
                </div>
                <p v-for="warning in metadata(message).warnings" :key="warning" class="agent-warning">{{ warning }}</p>
              </details>
            </template>
          </article>
          <div v-if="activePending" class="agent-pending" role="status">
            <strong>{{ pendingLabel(activePending.state) }}</strong>
            <span>{{ activePending.requestId }}</span>
            <button v-if="activePending.state === 'UNKNOWN_RESULT' && activePending.normalizedContent && !blockedReplay.has(activePending.chatId)" type="button" @click="retryUnknown">沿用原请求重试</button>
            <button v-if="['UNKNOWN_RESULT', 'RUNNING', 'COMPLETED'].includes(activePending.state)" type="button" @click="refreshPendingStatus">刷新状态</button>
            <button v-if="activePending.state === 'FAILED'" type="button" @click="retryAsNewRequest">作为新消息重试</button>
          </div>
          <div v-if="sending" class="agent-thinking">正在调用只读工具并校验证据...</div>
        </div>

        <form class="agent-composer" @submit.prevent="submit">
          <textarea v-model="draft" aria-label="研究问题" rows="3" :disabled="!llmEnabled || Boolean(activePending) || activeChat?.status === 'ARCHIVED'" placeholder="输入需要核验的研究问题" @keydown.ctrl.enter.prevent="submit"></textarea>
          <button type="submit" class="agent-primary" :disabled="!draft.trim() || !llmEnabled || Boolean(activePending) || activeChat?.status === 'ARCHIVED' || !online">{{ sending ? "研究中" : "发送" }}</button>
        </form>
      </main>

      <aside class="agent-evidence-pane" :class="{ open: evidenceOpen }">
        <div class="agent-pane-title"><strong>证据详情</strong><button type="button" class="agent-icon-button" aria-label="关闭证据详情" @click="evidenceOpen = false">×</button></div>
        <div v-if="selectedCitation" class="agent-evidence-detail">
          <dl>
            <template v-for="[key, value] in citationEntries" :key="String(key)">
              <dt>{{ key }}</dt><dd>{{ value || "--" }}</dd>
            </template>
          </dl>
          <button type="button" class="agent-secondary" @click="copyEvidenceId">复制 Evidence ID</button>
          <button type="button" class="agent-secondary" @click="openBusinessDetail">打开业务详情</button>
          <p v-if="navigationError" class="agent-navigation-error" role="alert">{{ navigationError }}</p>
        </div>
        <div v-else class="agent-empty">点击回答中的证据标记查看来源身份</div>
      </aside>
    </div>
    <button v-if="evidenceOpen" type="button" class="agent-evidence-backdrop" aria-label="关闭证据详情" @click="evidenceOpen = false"></button>
  </section>
</template>

<style scoped>
.agent-workbench { display: grid; gap: 12px; min-width: 0; }
.agent-header, .agent-chat-toolbar, .agent-pane-title, .agent-message-meta, .agent-context-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.agent-header h2, .agent-header p, .agent-chat-toolbar strong, .agent-chat-toolbar span { margin: 0; }
.agent-header p, .agent-chat-toolbar span, .agent-context-heading span { color: #64748b; font-size: 12px; }
.agent-header-actions { display: flex; align-items: center; gap: 8px; }
.readonly-badge, .agent-status { border-radius: 999px; padding: 3px 8px; font-size: 12px; font-weight: 700; }
.readonly-badge { background: #e2e8f0; color: #334155; }
.agent-primary, .agent-secondary, .agent-load-more { min-height: 34px; border-radius: 5px; padding: 0 12px; cursor: pointer; }
.agent-primary { border: 1px solid #111827; background: #111827; color: #fff; }
.agent-secondary, .agent-load-more { border: 1px solid #cbd5e1; background: #fff; color: #1e293b; }
.agent-primary:disabled { cursor: not-allowed; opacity: .5; }
.agent-icon-button:disabled { cursor: not-allowed; opacity: .45; }
.agent-notice, .agent-error { border: 1px solid; border-radius: 6px; padding: 10px 12px; }
.agent-notice { border-color: #facc15; background: #fefce8; color: #713f12; }
.agent-error { border-color: #fecaca; background: #fef2f2; color: #b91c1c; }
.agent-error button { float: right; border: 0; background: transparent; color: inherit; font-weight: 700; cursor: pointer; }
.agent-layout { display: grid; grid-template-columns: 220px minmax(0, 1fr) 300px; grid-template-rows: minmax(0, 1fr); height: calc(100vh - 190px); min-height: 560px; border: 1px solid #d8e0e8; border-radius: 7px; overflow: hidden; background: #fff; }
.agent-conversations, .agent-evidence-pane { min-width: 0; background: #f8fafc; }
.agent-conversations { border-right: 1px solid #e2e8f0; overflow-y: auto; }
.agent-evidence-pane { border-left: 1px solid #e2e8f0; overflow-y: auto; }
.agent-pane-title { position: sticky; top: 0; z-index: 1; min-height: 46px; padding: 0 12px; border-bottom: 1px solid #e2e8f0; background: #f8fafc; }
.agent-pane-title span { color: #64748b; font-size: 12px; }
.agent-chat-item { display: grid; width: 100%; gap: 4px; border: 0; border-bottom: 1px solid #e2e8f0; background: transparent; padding: 11px 12px; text-align: left; cursor: pointer; }
.agent-chat-item.active { background: #e8f0fb; box-shadow: inset 3px 0 #2563eb; }
.agent-chat-item strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #172033; }
.agent-chat-item span { color: #64748b; font-size: 11px; }
.agent-load-more { display: block; margin: 10px auto; }
.agent-chat-pane { display: grid; grid-template-rows: auto auto minmax(0, 1fr) auto; min-width: 0; min-height: 0; height: 100%; overflow: hidden; }
.agent-chat-toolbar { min-height: 46px; padding: 0 14px; border-bottom: 1px solid #e2e8f0; }
.agent-chat-toolbar > div { display: grid; gap: 2px; }
.agent-icon-button { width: 30px; height: 30px; border: 1px solid #cbd5e1; border-radius: 5px; background: #fff; font-size: 18px; cursor: pointer; }
.agent-context { padding: 10px 14px; border-bottom: 1px solid #e2e8f0; background: #fbfdff; }
.agent-context-fields { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 8px; margin-top: 8px; }
.agent-context-fields label { display: grid; gap: 3px; color: #64748b; font-size: 11px; }
.agent-context-fields input { width: 100%; min-width: 0; height: 30px; box-sizing: border-box; border: 1px solid #cbd5e1; border-radius: 4px; padding: 0 7px; }
.agent-context-chips { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 8px; }
.agent-context-chips button { max-width: 100%; overflow: hidden; border: 1px solid #bfdbfe; border-radius: 999px; background: #eff6ff; padding: 3px 8px; color: #1d4ed8; text-overflow: ellipsis; white-space: nowrap; cursor: pointer; }
.agent-stream { min-height: 0; overflow-y: auto; padding: 14px; background: #f5f7fa; }
.agent-load-earlier { display: block; margin: 0 auto 12px; border: 1px solid #cbd5e1; border-radius: 4px; background: #fff; padding: 5px 10px; color: #334155; cursor: pointer; }
.agent-message { width: min(780px, 92%); margin-bottom: 12px; border: 1px solid #dbe3eb; border-radius: 7px; background: #fff; padding: 12px; }
.agent-message.user { margin-left: auto; border-color: #bfdbfe; background: #eff6ff; }
.agent-message-meta time { margin-left: auto; color: #94a3b8; font-size: 11px; }
.agent-answer { margin: 10px 0 0; white-space: pre-wrap; line-height: 1.55; overflow-wrap: anywhere; }
.agent-message-meta { flex-wrap: wrap; }
.agent-status.complete { background: #dcfce7; color: #166534; }
.agent-status.partial { background: #fef3c7; color: #92400e; }
.agent-status.insufficient { background: #fee2e2; color: #991b1b; }
.agent-claims, .agent-rejected { display: grid; gap: 7px; margin-top: 12px; padding-top: 10px; border-top: 1px solid #e2e8f0; }
.agent-claim { display: grid; grid-template-columns: auto 1fr; gap: 7px; }
.agent-claim span { color: #475569; font-size: 11px; font-weight: 700; }
.agent-claim p { margin: 0; }
.agent-claim small { grid-column: 2; color: #64748b; }
.agent-facts { grid-column: 1 / -1; display: grid; gap: 4px; overflow-x: auto; }
.agent-facts > div { display: grid; grid-template-columns: minmax(180px, 1fr) auto auto; gap: 8px; border-top: 1px solid #eef2f6; padding-top: 5px; font-size: 11px; }
.agent-facts span { color: #64748b; font-weight: 400; }
.agent-rejected > div { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 6px; color: #991b1b; }
.agent-rejected code { overflow-wrap: anywhere; }
.agent-citations { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.agent-citations button { border: 1px solid #a7c7ed; border-radius: 4px; background: #f0f7ff; padding: 4px 7px; color: #1d4ed8; cursor: pointer; }
.agent-message details { margin-top: 10px; }
.agent-tool-call { display: flex; justify-content: space-between; gap: 8px; margin-top: 6px; color: #475569; }
.agent-warning { margin: 5px 0; color: #b45309; font-size: 12px; overflow-wrap: anywhere; }
.agent-thinking, .agent-empty { padding: 18px 12px; color: #64748b; text-align: center; }
.agent-pending { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; border: 1px solid #bfdbfe; border-radius: 5px; background: #eff6ff; padding: 9px 10px; color: #1e3a8a; }
.agent-pending span { min-width: 0; overflow: hidden; color: #64748b; font-family: ui-monospace, monospace; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.agent-pending button { border: 1px solid #93c5fd; border-radius: 4px; background: #fff; padding: 4px 7px; color: #1d4ed8; cursor: pointer; }
.agent-composer { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; padding: 12px 14px; border-top: 1px solid #e2e8f0; }
.agent-composer textarea { resize: vertical; min-height: 58px; max-height: 150px; border: 1px solid #cbd5e1; border-radius: 5px; padding: 9px; font: inherit; }
.agent-evidence-detail { padding: 12px; }
.agent-evidence-detail dl { display: grid; grid-template-columns: 95px minmax(0, 1fr); gap: 8px; margin: 0 0 14px; }
.agent-evidence-detail dt { color: #64748b; font-size: 11px; }
.agent-evidence-detail dd { margin: 0; overflow-wrap: anywhere; font-family: ui-monospace, monospace; font-size: 11px; }
.agent-evidence-detail .agent-secondary + .agent-secondary { margin-left: 6px; }
.agent-navigation-error { color: #b91c1c; font-size: 12px; }
.agent-evidence-backdrop { display: none; }
@media (max-width: 1100px) {
  .agent-layout { grid-template-columns: 190px minmax(0, 1fr); }
  .agent-evidence-pane { position: fixed; inset: 0 0 0 auto; z-index: 30; width: min(360px, 90vw); transform: translateX(100%); transition: transform .18s ease; box-shadow: -8px 0 24px rgba(15, 23, 42, .16); }
  .agent-evidence-pane.open { transform: translateX(0); }
  .agent-evidence-backdrop { display: block; position: fixed; inset: 0; z-index: 29; border: 0; background: rgba(15, 23, 42, .28); }
  .agent-context-fields { grid-template-columns: repeat(3, minmax(100px, 1fr)); }
}
@media (max-width: 720px) {
  .agent-layout { grid-template-columns: 1fr; height: auto; min-height: 620px; }
  .agent-conversations { max-height: 180px; border-right: 0; border-bottom: 1px solid #e2e8f0; }
  .agent-chat-pane { min-height: 600px; }
  .agent-stream { max-height: 460px; }
  .agent-context-fields { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .agent-message { width: auto; }
  .agent-composer { grid-template-columns: 1fr; }
}
</style>
