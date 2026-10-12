<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue";

import { ApiError } from "../services/api";
import {
  archiveAgentChat,
  createAgentChat,
  fetchAgentChat,
  fetchAgentChats,
  fetchAgentStatus,
  sendAgentMessage,
  type AgentChatSummary,
  type AgentCitation,
  type AgentMessage,
  type AgentMessageMetadata,
  type ResearchContext
} from "../services/agent";

const props = defineProps<{ initialContext?: ResearchContext | null }>();
const emit = defineEmits<{
  navigate: [target: { view: "overview" | "long" | "analytics"; run_id?: string }];
}>();

const chats = ref<AgentChatSummary[]>([]);
const chatTotal = ref(0);
const chatOffset = ref(0);
const chatLimit = 20;
const activeChatId = ref("");
const messages = ref<AgentMessage[]>([]);
const messageTotal = ref(0);
const loadingChats = ref(true);
const loadingMessages = ref(false);
const sending = ref(false);
const error = ref("");
const draft = ref("");
const llmEnabled = ref(false);
const registryVersion = ref("");
const toolCount = ref(0);
const evidenceOpen = ref(false);
const selectedCitation = ref<AgentCitation | null>(null);
const streamRef = ref<HTMLElement | null>(null);
const context = ref<ResearchContext>({});
const scrollPositions = ref<Record<string, number>>({});
const failedDraft = ref(false);

const activeChat = computed(() => chats.value.find((item) => item.chat_id === activeChatId.value));
const hasMoreChats = computed(() => chats.value.length < chatTotal.value);
const contextEntries = computed(() =>
  Object.entries(context.value).filter((entry): entry is [string, string] => Boolean(entry[1]))
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

function metadata(message: AgentMessage): AgentMessageMetadata {
  return message.metadata || {};
}

function verifiedClaims(message: AgentMessage) {
  const value = metadata(message);
  return value.verified_claims || value.claims || [];
}

function requestId() {
  return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function errorText(value: unknown) {
  if (value instanceof ApiError) {
    const labels: Record<string, string> = {
      AGENT_LLM_DISABLED: "智能研究尚未启用，请先配置服务端 LLM 开关和密钥。",
      CHAT_NOT_FOUND: "会话不存在或已不可访问。",
      CHAT_CONFLICT: "当前会话已有任务执行中，请稍后重试。",
      IDEMPOTENCY_CONFLICT: "本次请求标识已用于其他内容，请重新发送。",
      TOTAL_DEADLINE_EXCEEDED: "研究请求超时，请缩小问题范围后重试。"
    };
    return labels[value.code] || value.code;
  }
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
    const first = chats.value.find((item) => item.status === "ACTIVE");
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
    chats.value.push(...page.data);
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
  activeChatId.value = chatId;
  loadingMessages.value = true;
  error.value = "";
  try {
    const page = await fetchAgentChat(chatId, 200, 0);
    if (activeChatId.value !== chatId) return;
    messages.value = page.data.messages;
    messageTotal.value = page.meta.total;
    await restorePosition(chatId);
  } catch (value) {
    error.value = errorText(value);
  } finally {
    if (activeChatId.value === chatId) loadingMessages.value = false;
  }
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
  if (!activeChatId.value) return;
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
  if (!draft.value.trim() || sending.value || !llmEnabled.value) return;
  if (!activeChatId.value) await newChat();
  if (!activeChatId.value) return;
  const chatId = activeChatId.value;
  const content = composedQuestion();
  const optimistic: AgentMessage = {
    message_id: `pending-${requestId()}`,
    role: "USER",
    content,
    status: "COMPLETED",
    sequence_no: messages.value.length + 1,
    metadata: {},
    created_at: new Date().toISOString()
  };
  messages.value.push(optimistic);
  draft.value = "";
  sending.value = true;
  failedDraft.value = false;
  error.value = "";
  await scrollToEnd();
  try {
    await sendAgentMessage(chatId, content, requestId());
    delete scrollPositions.value[chatId];
    await selectChat(chatId);
    const current = chats.value.find((item) => item.chat_id === chatId);
    if (current) current.updated_at = new Date().toISOString();
  } catch (value) {
    messages.value = messages.value.filter((item) => item.message_id !== optimistic.message_id);
    draft.value = content.split("\n").slice(-1)[0] || "";
    failedDraft.value = true;
    error.value = errorText(value);
  } finally {
    sending.value = false;
  }
}

function showEvidence(citation: AgentCitation) {
  selectedCitation.value = citation;
  evidenceOpen.value = true;
}

async function copyEvidenceId() {
  if (selectedCitation.value) await navigator.clipboard.writeText(selectedCitation.value.evidence_id);
}

function clearContext(key: string) {
  context.value = { ...context.value, [key]: undefined };
}

function openBusinessDetail() {
  if (!selectedCitation.value) return;
  const tool = selectedCitation.value.tool_name;
  if (["backtest.summary", "performance.summary"].includes(tool)) {
    emit("navigate", {
      view: "analytics",
      run_id: selectedCitation.value.calc_run_id || undefined
    });
  } else if (["sector.top", "opportunity.list"].includes(tool)) {
    emit("navigate", { view: "long" });
  } else {
    emit("navigate", { view: "overview" });
  }
}

async function scrollToEnd() {
  await nextTick();
  streamRef.value?.scrollTo({ top: streamRef.value.scrollHeight, behavior: "smooth" });
}

async function restorePosition(chatId: string) {
  await nextTick();
  if (!streamRef.value) return;
  const saved = scrollPositions.value[chatId];
  if (saved === undefined) {
    streamRef.value.scrollTop = streamRef.value.scrollHeight;
  } else {
    streamRef.value.scrollTop = saved;
  }
}

onMounted(initialize);
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
    <div v-if="error" class="agent-error" role="alert">
      {{ error }}
      <button v-if="failedDraft" type="button" @click="submit">重试发送</button>
      <button v-else type="button" @click="initialize">重试</button>
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
          <button v-if="activeChatId" type="button" class="agent-icon-button" title="归档当前会话" aria-label="归档当前会话" @click="archiveCurrentChat">×</button>
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

        <div ref="streamRef" class="agent-stream" aria-live="polite">
          <div v-if="loadingMessages" class="agent-empty">正在加载消息</div>
          <div v-else-if="!messages.length" class="agent-empty">选择或新建会话后开始研究</div>
          <article v-for="message in messages" :key="message.message_id" class="agent-message" :class="message.role.toLowerCase()">
            <div class="agent-message-meta">
              <strong>{{ message.role === "USER" ? "你" : "研究助手" }}</strong>
              <span v-if="message.role === 'ASSISTANT'" class="agent-status" :class="statusClass(metadata(message).answer_status)">{{ statusLabel(metadata(message).answer_status) }}</span>
              <time>{{ new Date(message.created_at).toLocaleString("zh-CN") }}</time>
            </div>
            <p class="agent-answer">{{ message.content }}</p>

            <template v-if="message.role === 'ASSISTANT'">
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
                  <code>{{ call.tool_name }}</code><span>{{ call.status }} · {{ call.duration_ms }}ms</span>
                </div>
                <p v-for="warning in metadata(message).warnings" :key="warning" class="agent-warning">{{ warning }}</p>
              </details>
            </template>
          </article>
          <div v-if="sending" class="agent-thinking">正在调用只读工具并校验证据...</div>
        </div>

        <form class="agent-composer" @submit.prevent="submit">
          <textarea v-model="draft" rows="3" :disabled="!llmEnabled || sending" placeholder="输入需要核验的研究问题" @keydown.ctrl.enter.prevent="submit"></textarea>
          <button type="submit" class="agent-primary" :disabled="!draft.trim() || !llmEnabled || sending">{{ sending ? "研究中" : "发送" }}</button>
        </form>
      </main>

      <aside class="agent-evidence-pane" :class="{ open: evidenceOpen }">
        <div class="agent-pane-title"><strong>证据详情</strong><button type="button" class="agent-icon-button" aria-label="关闭证据详情" @click="evidenceOpen = false">×</button></div>
        <div v-if="selectedCitation" class="agent-evidence-detail">
          <dl>
            <template v-for="(value, key) in selectedCitation" :key="key">
              <dt>{{ key }}</dt><dd>{{ value || "--" }}</dd>
            </template>
          </dl>
          <button type="button" class="agent-secondary" @click="copyEvidenceId">复制 Evidence ID</button>
          <button type="button" class="agent-secondary" @click="openBusinessDetail">打开业务详情</button>
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
.agent-notice, .agent-error { border: 1px solid; border-radius: 6px; padding: 10px 12px; }
.agent-notice { border-color: #facc15; background: #fefce8; color: #713f12; }
.agent-error { border-color: #fecaca; background: #fef2f2; color: #b91c1c; }
.agent-error button { float: right; border: 0; background: transparent; color: inherit; font-weight: 700; cursor: pointer; }
.agent-layout { display: grid; grid-template-columns: 220px minmax(0, 1fr) 300px; height: calc(100vh - 190px); min-height: 560px; border: 1px solid #d8e0e8; border-radius: 7px; overflow: hidden; background: #fff; }
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
.agent-chat-pane { display: grid; grid-template-rows: auto auto minmax(0, 1fr) auto; min-width: 0; }
.agent-chat-toolbar { min-height: 46px; padding: 0 14px; border-bottom: 1px solid #e2e8f0; }
.agent-chat-toolbar > div { display: grid; gap: 2px; }
.agent-icon-button { width: 30px; height: 30px; border: 1px solid #cbd5e1; border-radius: 5px; background: #fff; font-size: 18px; cursor: pointer; }
.agent-context { padding: 10px 14px; border-bottom: 1px solid #e2e8f0; background: #fbfdff; }
.agent-context-fields { display: grid; grid-template-columns: repeat(5, minmax(100px, 1fr)); gap: 8px; margin-top: 8px; }
.agent-context-fields label { display: grid; gap: 3px; color: #64748b; font-size: 11px; }
.agent-context-fields input { width: 100%; min-width: 0; height: 30px; box-sizing: border-box; border: 1px solid #cbd5e1; border-radius: 4px; padding: 0 7px; }
.agent-context-chips { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 8px; }
.agent-context-chips button { max-width: 100%; overflow: hidden; border: 1px solid #bfdbfe; border-radius: 999px; background: #eff6ff; padding: 3px 8px; color: #1d4ed8; text-overflow: ellipsis; white-space: nowrap; cursor: pointer; }
.agent-stream { min-height: 0; overflow-y: auto; padding: 14px; background: #f5f7fa; }
.agent-message { width: min(780px, 92%); margin-bottom: 12px; border: 1px solid #dbe3eb; border-radius: 7px; background: #fff; padding: 12px; }
.agent-message.user { margin-left: auto; border-color: #bfdbfe; background: #eff6ff; }
.agent-message-meta time { margin-left: auto; color: #94a3b8; font-size: 11px; }
.agent-answer { margin: 10px 0 0; white-space: pre-wrap; line-height: 1.55; }
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
.agent-composer { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; padding: 12px 14px; border-top: 1px solid #e2e8f0; }
.agent-composer textarea { resize: vertical; min-height: 58px; max-height: 150px; border: 1px solid #cbd5e1; border-radius: 5px; padding: 9px; font: inherit; }
.agent-evidence-detail { padding: 12px; }
.agent-evidence-detail dl { display: grid; grid-template-columns: 95px minmax(0, 1fr); gap: 8px; margin: 0 0 14px; }
.agent-evidence-detail dt { color: #64748b; font-size: 11px; }
.agent-evidence-detail dd { margin: 0; overflow-wrap: anywhere; font-family: ui-monospace, monospace; font-size: 11px; }
.agent-evidence-detail .agent-secondary + .agent-secondary { margin-left: 6px; }
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
  .agent-context-fields { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .agent-message { width: auto; }
  .agent-composer { grid-template-columns: 1fr; }
}
</style>
