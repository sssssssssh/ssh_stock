import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";

import { ApiError } from "../services/api";
import AgentResearchWorkbench from "./AgentResearchWorkbench.vue";

const mocks = vi.hoisted(() => ({
  send: vi.fn(),
  create: vi.fn(),
  archive: vi.fn()
}));

beforeEach(() => {
  mocks.send.mockReset().mockResolvedValue({});
  mocks.create.mockReset();
  mocks.archive.mockReset();
});

vi.mock("../services/agent", () => ({
  fetchAgentStatus: vi.fn().mockResolvedValue({
    agent_mode: "llm_chat",
    registry_version: "m16.3-v1",
    tool_count: 9,
    llm_enabled: true,
    read_only: true,
    statement_timeout_ms: 5000
  }),
  fetchAgentChats: vi.fn().mockResolvedValue({
    data: [{
      chat_id: "chat-1", title: "窗口研究", status: "ACTIVE",
      created_at: "2026-10-12T01:00:00Z", updated_at: "2026-10-12T01:00:00Z"
    }],
    meta: { total: 1 }
  }),
  fetchAgentChat: vi.fn().mockResolvedValue({
    data: {
      chat_id: "chat-1", title: "窗口研究", status: "ACTIVE",
      created_at: "2026-10-12T01:00:00Z", updated_at: "2026-10-12T01:00:00Z",
      messages: [{
        message_id: "message-1", role: "ASSISTANT", content: "仅保留通过校验的结论。",
        status: "COMPLETED", sequence_no: 1, created_at: "2026-10-12T01:00:00Z",
        metadata: {
          answer_status: "PARTIAL_VERIFIED",
          verified_claims: [{
            claim_id: "verified", claim_type: "FACT", text: "已验证事实",
            evidence_ids: ["evidence-1"], structured_facts: [], quality_status: "PASS",
            reason_codes: []
          }],
          rejected_claims: [{
            claim_id: "rejected", claim_type: "FACT", reason_codes: ["VALUE_MISMATCH"]
          }],
          citations: [{
            marker: "E1", evidence_id: "evidence-1", evidence_version: "v2",
            tool_name: "walk_forward.window_lineage", entity_id: "study:window:1"
          }],
          warnings: [], tool_calls: []
        }
      }]
    },
    meta: { total: 1 }
  }),
  sendAgentMessage: mocks.send.mockResolvedValue({}),
  createAgentChat: mocks.create,
  archiveAgentChat: mocks.archive
}));

it("renders tri-state evidence and sends explicit context with an idempotency key", async () => {
  const wrapper = mount(AgentResearchWorkbench, {
    props: { initialContext: { run_id: "run-123" } }
  });
  await flushPromises();

  expect(wrapper.text()).toContain("部分已验证");
  expect(wrapper.text()).toContain("已验证事实");
  expect(wrapper.text()).toContain("VALUE_MISMATCH");
  expect(wrapper.text()).toContain("run_id: run-123");
  expect(wrapper.text()).not.toContain("unverified value");

  const evidenceButton = wrapper.findAll("button").find((item) => item.text().includes("E1"));
  await evidenceButton?.trigger("click");
  expect(wrapper.text()).toContain("evidence-1");
  const businessButton = wrapper.findAll("button").find((item) => item.text() === "打开业务详情");
  await businessButton?.trigger("click");
  expect(wrapper.emitted("navigate")?.[0]).toEqual([{ view: "overview" }]);

  await wrapper.find("textarea").setValue("比较训练期和样本外表现");
  await wrapper.find("form.agent-composer").trigger("submit");
  await flushPromises();

  expect(mocks.send).toHaveBeenCalledOnce();
  expect(mocks.send.mock.calls[0][0]).toBe("chat-1");
  expect(mocks.send.mock.calls[0][1]).toContain("run_id=run-123");
  expect(mocks.send.mock.calls[0][2]).toEqual(expect.any(String));
});

it.each([
  ["CHAT_NOT_FOUND", 404, "会话不存在或已不可访问"],
  ["CHAT_CONFLICT", 409, "当前会话已有任务执行中"],
  ["TOTAL_DEADLINE_EXCEEDED", 504, "研究请求超时"]
])("shows a controlled error for %s", async (code, status, expected) => {
  mocks.send.mockRejectedValueOnce(new ApiError(code, status));
  const wrapper = mount(AgentResearchWorkbench);
  await flushPromises();

  await wrapper.find("textarea").setValue("需要校验的问题");
  await wrapper.find("form.agent-composer").trigger("submit");
  await flushPromises();

  expect(wrapper.text()).toContain(expected);
  expect(wrapper.text()).toContain("重试发送");
});
