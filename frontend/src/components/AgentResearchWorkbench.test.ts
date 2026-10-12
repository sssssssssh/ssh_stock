import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { ApiError } from "../services/api";
import type { AgentCitation, AgentMessage, AgentTurnStatus } from "../services/agent";
import AgentResearchWorkbench from "./AgentResearchWorkbench.vue";

const mocks = vi.hoisted(() => ({
  sendAgentMessage: vi.fn(), createAgentChat: vi.fn(), archiveAgentChat: vi.fn(),
  fetchAgentStatus: vi.fn(), fetchAgentChats: vi.fn(), fetchLatestAgentChat: vi.fn(),
  fetchEarlierAgentMessages: vi.fn(), fetchAgentTurnStatus: vi.fn()
}));
vi.mock("../services/agent", async (original) => ({
  ...(await original<typeof import("../services/agent")>()), ...mocks
}));

const wrappers: VueWrapper[] = [];
const chat = (id: string) => ({ chat_id: id, title: id, status: "ACTIVE", created_at: "2026-10-12T01:00:00Z", updated_at: "2026-10-12T01:00:00Z" });
const message = (sequence: number, content = `message-${sequence}`): AgentMessage => ({
  message_id: `message-${sequence}`, role: "USER", content, status: "COMPLETED", sequence_no: sequence,
  metadata: {}, created_at: "2026-10-12T01:00:00Z"
});
function page(id = "chat-a", rows: AgentMessage[] = [], total = rows.length, activeTurn: AgentTurnStatus | null = null) {
  return { data: { ...chat(id), messages: rows, active_turn: activeTurn }, meta: {
    total, limit: 50, offset: 0, has_more: (rows[0]?.sequence_no || 1) > 1,
    next_cursor: (rows[0]?.sequence_no || 1) > 1 ? rows[0].sequence_no : null
  } };
}
function turn(status: AgentTurnStatus["status"]): AgentTurnStatus {
  return { chat_id: "chat-a", request_id: "saved-request", status, content: "saved question", user_message_id: "user-1", started_at: new Date().toISOString() };
}
async function workbench(props = {}) {
  const wrapper = mount(AgentResearchWorkbench, { props: { ownerId: "owner-a", ...props } });
  wrappers.push(wrapper);
  await flushPromises();
  return wrapper;
}
function button(wrapper: VueWrapper, text: string) {
  const match = wrapper.findAll("button").find((item) => item.text() === text || (item.find("strong").exists() && item.find("strong").text() === text));
  if (!match) throw new Error(`Missing button: ${text}`);
  return match;
}
async function send(wrapper: VueWrapper, content = "question") {
  await wrapper.get("textarea").setValue(content);
  await wrapper.get("form.agent-composer").trigger("submit");
  await flushPromises();
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (value: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

beforeEach(() => {
  vi.resetAllMocks();
  sessionStorage.clear();
  Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" });
  mocks.fetchAgentStatus.mockResolvedValue({ registry_version: "m16.3-v1", tool_count: 9, llm_enabled: true });
  mocks.fetchAgentChats.mockResolvedValue({ data: [chat("chat-a"), chat("chat-b")], meta: { total: 2 } });
  mocks.fetchLatestAgentChat.mockImplementation((id: string) => Promise.resolve(page(id)));
  mocks.sendAgentMessage.mockResolvedValue({});
  mocks.fetchAgentTurnStatus.mockRejectedValue(new ApiError("TURN_NOT_FOUND", 404));
});
afterEach(() => {
  for (const wrapper of wrappers.splice(0)) wrapper.unmount();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

it("queries before replay and reuses the original requestId and full content", async () => {
  mocks.sendAgentMessage.mockRejectedValueOnce(new TypeError("offline"));
  const wrapper = await workbench({ initialContext: { run_id: "run-1" } });
  await send(wrapper, "line one\nline two");
  const first = mocks.sendAgentMessage.mock.calls[0];
  expect(first[1]).toContain("run_id=run-1");
  expect(first[1]).toContain("line one\nline two");
  expect(wrapper.text()).toContain("结果待确认");
  await button(wrapper, "沿用原请求重试").trigger("click");
  await flushPromises();
  expect(mocks.fetchAgentTurnStatus).toHaveBeenCalledTimes(2);
  expect(mocks.sendAgentMessage.mock.calls[1]).toEqual(first);
});

it("recovers a committed answer after a lost response without another POST", async () => {
  const reply: AgentMessage = { ...message(2, "verified answer"), role: "ASSISTANT", metadata: { answer_status: "COMPLETED" } };
  mocks.sendAgentMessage.mockRejectedValueOnce(new TypeError("response lost"));
  mocks.fetchAgentTurnStatus.mockImplementation((chatId: string, requestId: string) => Promise.resolve({ ...turn("COMPLETED"), chat_id: chatId, request_id: requestId, content: "question" }));
  mocks.fetchLatestAgentChat.mockResolvedValueOnce(page()).mockResolvedValue(page("chat-a", [message(1, "question"), reply]));
  const wrapper = await workbench();
  await send(wrapper);
  expect(mocks.sendAgentMessage).toHaveBeenCalledOnce();
  expect(wrapper.findAll(".agent-message")).toHaveLength(2);
  expect(wrapper.text()).toContain("verified answer");
  expect(wrapper.text()).not.toContain("结果待确认");
});

it("a double submit only sends one request", async () => {
  const delayed = deferred<object>();
  mocks.sendAgentMessage.mockReturnValue(delayed.promise);
  const wrapper = await workbench();
  await send(wrapper);
  await wrapper.get("form").trigger("submit");
  expect(mocks.sendAgentMessage).toHaveBeenCalledOnce();
  delayed.resolve({});
  await flushPromises();
});

it("does not accept a completed lookup that is bound to different request content", async () => {
  mocks.sendAgentMessage.mockRejectedValue(new TypeError("lost reply"));
  mocks.fetchAgentTurnStatus.mockImplementation((chatId: string, requestId: string) => Promise.resolve({ ...turn("COMPLETED"), chat_id: chatId, request_id: requestId, content: "different content" }));
  const wrapper = await workbench();
  await send(wrapper, "original content");
  expect(wrapper.text()).toContain("不能自动重放");
  expect(wrapper.text()).not.toContain("沿用原请求重试");
  expect(mocks.sendAgentMessage).toHaveBeenCalledOnce();
});

it.each(["resolve", "reject"])("a late %s stays in its originating chat", async (finish) => {
  const delayed = deferred<object>();
  mocks.sendAgentMessage.mockReturnValue(delayed.promise);
  const wrapper = await workbench();
  await send(wrapper, "only belongs to a");
  await button(wrapper, "chat-b").trigger("click");
  await flushPromises();
  await wrapper.get("textarea").setValue("draft b");
  if (finish === "resolve") delayed.resolve({});
  else delayed.reject(new ApiError("TOOL_TIMEOUT", 504));
  await flushPromises();
  expect(wrapper.get(".agent-chat-toolbar").text()).toContain("chat-b");
  expect((wrapper.get("textarea").element as HTMLTextAreaElement).value).toBe("draft b");
  expect(wrapper.text()).not.toContain("only belongs to a");
  expect(wrapper.text()).not.toContain("只读工具执行超时");
});

it("keeps each chat draft across switches", async () => {
  const wrapper = await workbench();
  await wrapper.get("textarea").setValue("draft a\nsecond line");
  await button(wrapper, "chat-b").trigger("click");
  await flushPromises();
  await wrapper.get("textarea").setValue("draft b");
  await button(wrapper, "chat-a").trigger("click");
  await flushPromises();
  expect((wrapper.get("textarea").element as HTMLTextAreaElement).value).toBe("draft a\nsecond line");
});

it("does not show another chat's messages while its history is still loading", async () => {
  const delayed = deferred<ReturnType<typeof page>>();
  mocks.fetchLatestAgentChat.mockImplementation((id: string) => id === "chat-a" ? Promise.resolve(page(id, [message(1, "a only")])) : delayed.promise);
  const wrapper = await workbench();
  await button(wrapper, "chat-b").trigger("click");
  expect(wrapper.text()).not.toContain("a only");
  delayed.resolve(page("chat-b", [message(1, "b only")]));
  await flushPromises();
  expect(wrapper.text()).toContain("b only");
});

it("opens the latest 50 of 201 and loads every earlier message once", async () => {
  const rows = Array.from({ length: 201 }, (_, index) => message(index + 1));
  mocks.fetchLatestAgentChat.mockResolvedValue(page("chat-a", rows.slice(-50), 201));
  mocks.fetchEarlierAgentMessages.mockImplementation((_id, before: number) => {
    const earlier = rows.filter((row) => row.sequence_no < before).slice(-50);
    return Promise.resolve(page("chat-a", earlier, 201));
  });
  const wrapper = await workbench();
  expect(wrapper.findAll(".agent-message")).toHaveLength(50);
  expect(wrapper.text()).toContain("message-201");
  for (let attempt = 0; attempt < 4; attempt += 1) {
    await button(wrapper, "加载更早消息").trigger("click");
    await flushPromises();
  }
  expect(wrapper.findAll(".agent-message")).toHaveLength(201);
  expect(wrapper.findAll(".agent-answer").map((item) => item.text())).toEqual(rows.map((item) => item.content));
  expect(wrapper.text()).not.toContain("加载更早消息");
});

it("deduplicates overlap and keeps the viewport anchor while prepending", async () => {
  mocks.fetchLatestAgentChat.mockResolvedValue(page("chat-a", [message(3), message(4)], 4));
  mocks.fetchEarlierAgentMessages.mockResolvedValue(page("chat-a", [message(1), message(2), message(3)], 4));
  const wrapper = await workbench();
  const stream = wrapper.get(".agent-stream").element as HTMLElement;
  Object.defineProperty(stream, "scrollHeight", { configurable: true, get: () => wrapper.findAll(".agent-message").length * 100 });
  stream.scrollTop = 35;
  await button(wrapper, "加载更早消息").trigger("click");
  await flushPromises();
  expect(wrapper.findAll(".agent-message")).toHaveLength(4);
  expect(stream.scrollTop).toBe(235);
});

it("fills history gaps when new replies arrive between session visits", async () => {
  const rows = Array.from({ length: 10 }, (_, index) => message(index + 1));
  let visits = 0;
  mocks.fetchLatestAgentChat.mockImplementation((id: string) => Promise.resolve(
    id === "chat-b" ? page(id) : ++visits === 1 ? page(id, rows.slice(2, 4), 4) : page(id, rows.slice(8), 10)
  ));
  mocks.fetchEarlierAgentMessages.mockImplementation((_id, before: number) => Promise.resolve(page("chat-a", rows.filter((row) => row.sequence_no < before).slice(-2), 10)));
  const wrapper = await workbench();
  await button(wrapper, "chat-b").trigger("click");
  await flushPromises();
  await button(wrapper, "chat-a").trigger("click");
  await flushPromises();
  for (let attempt = 0; attempt < 4; attempt += 1) {
    await button(wrapper, "加载更早消息").trigger("click");
    await flushPromises();
  }
  expect(mocks.fetchEarlierAgentMessages.mock.calls[0][1]).toBe(9);
  expect(wrapper.findAll(".agent-answer").map((item) => item.text())).toEqual(rows.map((item) => item.content));
});

it("does not force scroll to the bottom when the reader moved upward", async () => {
  const delayed = deferred<object>();
  mocks.sendAgentMessage.mockReturnValue(delayed.promise);
  mocks.fetchLatestAgentChat.mockResolvedValue(page("chat-a", [message(1)], 1));
  const wrapper = await workbench();
  await send(wrapper);
  const stream = wrapper.get(".agent-stream").element as HTMLElement;
  Object.defineProperty(stream, "scrollHeight", { configurable: true, value: 2000 });
  Object.defineProperty(stream, "clientHeight", { configurable: true, value: 400 });
  stream.scrollTop = 100;
  delayed.resolve({});
  await flushPromises();
  expect(stream.scrollTop).toBe(100);
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(stream.scrollTop).toBe(100);
});

it.each([
  ["LLM_DISABLED", 503, "智能研究尚未启用"],
  ["CHAT_NOT_FOUND", 404, "会话不存在"],
  ["CHAT_CONFLICT", 409, "当前会话已有任务"],
  ["IDEMPOTENCY_CONFLICT", 409, "不能自动重放"],
  ["TOTAL_DEADLINE_EXCEEDED", 504, "超过服务端总时限"],
  ["TOOL_TIMEOUT", 504, "只读工具执行超时"],
  ["UNAUTHORIZED", 401, "登录已失效"]
])("handles explicit %s without automatically resending", async (code, status, expected) => {
  mocks.sendAgentMessage.mockRejectedValue(new ApiError(code, status));
  const wrapper = await workbench();
  await send(wrapper, "first\nsecond");
  expect(wrapper.text()).toContain(expected);
  expect(wrapper.text()).not.toContain("沿用原请求重试");
  expect(mocks.sendAgentMessage).toHaveBeenCalledOnce();
  await button(wrapper, "作为新消息重试").trigger("click");
  expect((wrapper.get("textarea").element as HTMLTextAreaElement).value).toBe("first\nsecond");
});

it("recovers RUNNING from the server without browser storage or another POST", async () => {
  mocks.fetchLatestAgentChat.mockResolvedValue(page("chat-a", [message(1)], 1, turn("RUNNING")));
  const wrapper = await workbench();
  expect(wrapper.text()).toContain("服务端处理中");
  expect(wrapper.get("textarea").attributes("disabled")).toBeDefined();
  expect(mocks.sendAgentMessage).not.toHaveBeenCalled();
});

it("a 409 followed by an unavailable status only offers status refresh", async () => {
  mocks.sendAgentMessage.mockRejectedValue(new ApiError("CHAT_CONFLICT", 409));
  mocks.fetchAgentTurnStatus.mockRejectedValue(new TypeError("status offline"));
  const wrapper = await workbench();
  await send(wrapper);
  expect(wrapper.text()).toContain("结果待确认");
  expect(wrapper.text()).toContain("刷新状态");
  expect(wrapper.text()).not.toContain("沿用原请求重试");
  expect(mocks.sendAgentMessage).toHaveBeenCalledOnce();
});

it("shows FAILED turn evidence after recovering an unknown response", async () => {
  mocks.sendAgentMessage.mockRejectedValue(new TypeError("lost reply"));
  mocks.fetchAgentTurnStatus.mockImplementation((chatId: string, requestId: string) => Promise.resolve({ ...turn("FAILED"), chat_id: chatId, request_id: requestId, content: "question", error_code: "TOOL_TIMEOUT" }));
  const wrapper = await workbench();
  await send(wrapper);
  expect(wrapper.text()).toContain("执行失败");
  expect(wrapper.text()).toContain("只读工具执行超时");
  expect(wrapper.text()).not.toContain("沿用原请求重试");
});

it("does not allow archiving an unresolved send", async () => {
  const delayed = deferred<object>();
  mocks.sendAgentMessage.mockReturnValue(delayed.promise);
  const wrapper = await workbench();
  await send(wrapper);
  expect(wrapper.get('[aria-label="归档当前会话"]').attributes("disabled")).toBeDefined();
  expect(mocks.archiveAgentChat).not.toHaveBeenCalled();
  delayed.resolve({});
  await flushPromises();
});

it("persists only request identity under the current owner's tab storage", async () => {
  mocks.sendAgentMessage.mockRejectedValue(new TypeError("offline"));
  const wrapper = await workbench();
  await send(wrapper, "private question");
  const raw = sessionStorage.getItem("ssh-stock.agent.pending.v2.owner-a")!;
  expect(raw).toContain(mocks.sendAgentMessage.mock.calls[0][2]);
  expect(raw).not.toContain("private question");
  expect(raw).not.toContain("normalizedContent");
  wrapper.unmount();
  mocks.fetchAgentTurnStatus.mockClear();
  await workbench({ ownerId: "owner-b" });
  expect(mocks.fetchAgentTurnStatus).not.toHaveBeenCalled();
});

it("reconciles a saved request on refresh using the authenticated server result", async () => {
  sessionStorage.setItem("ssh-stock.agent.pending.v2.owner-a", JSON.stringify([{ chatId: "chat-a", requestId: "saved-request", state: "UNKNOWN_RESULT", createdAt: new Date().toISOString() }]));
  mocks.fetchAgentTurnStatus.mockResolvedValue(turn("RUNNING"));
  const wrapper = await workbench();
  expect(mocks.fetchAgentTurnStatus).toHaveBeenCalledWith("chat-a", "saved-request");
  expect(wrapper.text()).toContain("服务端处理中");
  expect(mocks.sendAgentMessage).not.toHaveBeenCalled();
});

it.each(["missing", "offline"])("retains a saved unknown identity when refresh is %s", async (failure) => {
  sessionStorage.setItem("ssh-stock.agent.pending.v2.owner-a", JSON.stringify([{ chatId: "chat-a", requestId: "saved-request", state: "UNKNOWN_RESULT", createdAt: new Date().toISOString() }]));
  if (failure === "offline") mocks.fetchAgentTurnStatus.mockRejectedValue(new TypeError("offline"));
  const wrapper = await workbench();
  expect(wrapper.text()).toContain("结果待确认");
  expect(wrapper.text()).not.toContain("沿用原请求重试");
  expect(wrapper.get("textarea").attributes("disabled")).toBeDefined();
  expect(sessionStorage.getItem("ssh-stock.agent.pending.v2.owner-a")).toContain("saved-request");
  expect(mocks.sendAgentMessage).not.toHaveBeenCalled();
});

it("bounds polling and stops after unmount", async () => {
  vi.useFakeTimers();
  mocks.fetchLatestAgentChat.mockResolvedValue(page("chat-a", [], 0, turn("RUNNING")));
  mocks.fetchAgentTurnStatus.mockResolvedValue(turn("RUNNING"));
  const wrapper = await workbench();
  for (let attempt = 0; attempt < 15; attempt += 1) {
    await vi.advanceTimersByTimeAsync(5000);
    await flushPromises();
  }
  expect(mocks.fetchAgentTurnStatus).toHaveBeenCalledTimes(12);
  wrapper.unmount();
  await vi.advanceTimersByTimeAsync(10000);
  expect(mocks.fetchAgentTurnStatus).toHaveBeenCalledTimes(12);
});

it.each(["COMPLETED", "PARTIAL_VERIFIED", "INSUFFICIENT_EVIDENCE"] as const)("retains the %s answer state", async (status) => {
  const reply: AgentMessage = { ...message(1, "safe answer"), role: "ASSISTANT", metadata: { answer_status: status } };
  mocks.fetchLatestAgentChat.mockResolvedValue(page("chat-a", [reply]));
  const wrapper = await workbench();
  expect(wrapper.get(".agent-status").text()).toBe({ COMPLETED: "已验证", PARTIAL_VERIFIED: "部分已验证", INSUFFICIENT_EVIDENCE: "证据不足" }[status]);
});

it("a FAILED assistant is not rendered as a verified success", async () => {
  const reply: AgentMessage = { ...message(1), role: "ASSISTANT", status: "FAILED", metadata: { answer_status: "COMPLETED" } };
  mocks.fetchLatestAgentChat.mockResolvedValue(page("chat-a", [reply]));
  const wrapper = await workbench();
  expect(wrapper.get(".agent-status").text()).toBe("执行失败");
});

it.each([
  { view: "analytics", run_id: "run-a", source_tool: "performance.summary" },
  { view: "walk_forward", study_id: "study-a", validation_id: "validation-a", window_no: 301, source_tool: "walk_forward.window_lineage" },
  { view: "long", ts_code: "000001.SZ", trade_date: "2026-01-02", source_tool: "opportunity.list" }
])("navigates using structured citation identity: $source_tool", async (navigation) => {
  const citation = { marker: "E1", evidence_id: "evidence-1", tool_name: navigation.source_tool, entity_id: "entity", evidence_version: "v2", navigation } as AgentCitation;
  mocks.fetchLatestAgentChat.mockResolvedValue(page("chat-a", [{ ...message(1), role: "ASSISTANT", metadata: { citations: [citation] } }]));
  const wrapper = await workbench();
  await wrapper.get(".agent-citations button").trigger("click");
  await button(wrapper, "打开业务详情").trigger("click");
  expect(wrapper.emitted("navigate")?.[0]).toEqual([navigation]);
});

it("an old citation with missing identities gives an explicit downgrade", async () => {
  const citation: AgentCitation = { marker: "E1", evidence_id: "evidence-1", tool_name: "walk_forward.window_lineage", entity_id: "model free text", evidence_version: "v2" };
  mocks.fetchLatestAgentChat.mockResolvedValue(page("chat-a", [{ ...message(1), role: "ASSISTANT", metadata: { citations: [citation] } }]));
  const wrapper = await workbench();
  await wrapper.get(".agent-citations button").trigger("click");
  await button(wrapper, "打开业务详情").trigger("click");
  expect(wrapper.text()).toContain("该证据暂不支持精准定位");
  expect(wrapper.emitted("navigate")).toBeUndefined();
});
