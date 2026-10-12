import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";

import AgentResearchReports from "./AgentResearchReports.vue";

const mocks = vi.hoisted(() => ({
  fetchResearchReports: vi.fn(),
  fetchResearchReport: vi.fn(),
  createResearchReport: vi.fn(),
  archiveResearchReport: vi.fn(),
  createReportComparison: vi.fn(),
  downloadResearchReport: vi.fn()
}));

vi.mock("../services/agentReports", async (original) => ({
  ...(await original<typeof import("../services/agentReports")>()),
  ...mocks
}));

const summary = {
  report_id: "report-1",
  report_type: "strategy_review",
  report_version: "m16.4-v1",
  title: "策略复盘",
  source_chat_id: "chat-1",
  source_message_id: "message-1",
  as_of_date: "2026-10-10",
  source_answer_status: "COMPLETED",
  snapshot_hash: "a".repeat(64),
  archived_at: null,
  created_at: "2026-10-12T00:00:00Z"
};

const detail = {
  ...summary,
  source_chat_id: "chat-1",
  source_message_id: "message-1",
  source_turn_id: "turn-1",
  parent_report_id: null,
  source_contract: {
    snapshot_level: "CLAIM_SNAPSHOT_ONLY",
    report_version: "m16.4-v1",
    comparison_policy_version: "m16.2.2-comparison-v1",
    tool_names: ["market.snapshot"],
    evidence_versions: ["v2"],
    evidence_identities: [],
    limitations: ["SOURCE_PAYLOAD_NOT_ARCHIVED"]
  },
  snapshot: {
    schema_version: "m16.4-v1",
    snapshot_level: "CLAIM_SNAPSHOT_ONLY",
    report_type: "strategy_review",
    title: "策略复盘",
    as_of_date: "2026-10-10",
    source_answer_status: "COMPLETED",
    source_chat_id: "chat-1",
    source_message_id: "message-1",
    source_turn_id: "turn-1",
    claims: [{ claim_id: "claim-1", claim_type: "FACT", text: "收益可核验", evidence_ids: ["ev-1"], structured_facts: [], quality_status: "PASS", reason_codes: [] }],
    rejected_claims: [],
    citations: [{ marker: "[1]", evidence_id: "ev-1", evidence_version: "v2", tool_name: "market.snapshot", entity_id: "run-1" }],
    sections: [{ section_id: "facts", title: "已验证事实", claim_ids: ["claim-1"] }],
    charts: [],
    warnings: ["SERIES_NOT_AVAILABLE"]
  }
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.fetchResearchReports.mockResolvedValue({ data: [summary], meta: { total: 1 } });
  mocks.fetchResearchReport.mockResolvedValue(detail);
  mocks.createResearchReport.mockResolvedValue(detail);
});

it("accepts a source message, creates a report and renders evidence", async () => {
  const wrapper = mount(AgentResearchReports, {
    props: { initialSource: { chatId: "chat-1", messageId: "message-1" } }
  });
  await flushPromises();
  await wrapper.findAll("button").find((button) => button.text() === "生成报告")?.trigger("click");
  await flushPromises();
  expect(mocks.createResearchReport).toHaveBeenCalledWith(expect.objectContaining({
    source_chat_id: "chat-1",
    source_message_id: "message-1"
  }));
  expect(wrapper.text()).toContain("收益可核验");
  expect(wrapper.text()).toContain("ev-1");
  expect(wrapper.text()).toContain("CLAIM_SNAPSHOT_ONLY");
});

it("shows only side-by-side facts when comparison requires context", async () => {
  mocks.createReportComparison.mockResolvedValue({
    comparison_id: "comparison-1",
    left_report_id: "report-1",
    right_report_id: "report-2",
    policy_version: "m16.2.2-comparison-v1",
    state: "CONTEXT_REQUIRED",
    reason_codes: ["AS_OF_DATE_MISMATCH"],
    result: { facts: [{ metric_key: "return|ratio", left: "0.1", right: "0.2" }], delta_policy: "DISABLED" },
    left_snapshot_hash: "a".repeat(64),
    right_snapshot_hash: "b".repeat(64),
    comparison_hash: "c".repeat(64),
    created_at: "2026-10-12T00:00:00Z"
  });
  mocks.fetchResearchReports.mockResolvedValue({ data: [summary, { ...summary, report_id: "report-2", title: "另一报告" }], meta: { total: 2 } });
  const wrapper = mount(AgentResearchReports);
  await flushPromises();
  const selects = wrapper.findAll(".report-compare select");
  await selects[0].setValue("report-1");
  await selects[1].setValue("report-2");
  await wrapper.findAll("button").find((button) => button.text() === "比较")?.trigger("click");
  await flushPromises();
  expect(wrapper.text()).toContain("CONTEXT_REQUIRED");
  expect(wrapper.text()).toContain("AS_OF_DATE_MISMATCH");
  expect(wrapper.findAll("th").some((cell) => cell.text() === "delta")).toBe(false);
});

it.each(["legacy", "pair-rejected"])("hides unsafe delta for %s comparisons", async (kind) => {
  mocks.createReportComparison.mockResolvedValue({
    policy_version: kind === "legacy" ? "m16.2.2-comparison-v1" : "m16.4.1-report-comparison-v2",
    state: "COMPARABLE", reason_codes: [],
    display_safety: { legacy_policy: kind === "legacy", delta_allowed: kind !== "legacy", warnings: [] },
    result: { facts: [{ metric_key: "score", left: "10", right: "12", delta: "999",
      pair_status: "INCOMPATIBLE" }] }
  });
  mocks.fetchResearchReports.mockResolvedValue({ data: [summary, { ...summary, report_id: "report-2" }], meta: { total: 2 } });
  const wrapper = mount(AgentResearchReports);
  await flushPromises();
  const selects = wrapper.findAll(".report-compare select");
  await selects[0].setValue("report-1");
  await selects[1].setValue("report-2");
  await wrapper.findAll("button").find((button) => button.text() === "比较")?.trigger("click");
  await flushPromises();
  expect(wrapper.text()).not.toContain("999");
  if (kind === "legacy") expect(wrapper.text()).toContain("旧版比较策略");
  wrapper.unmount();
});
