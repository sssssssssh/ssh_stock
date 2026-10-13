import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";
import EvidenceArchivePanel from "./EvidenceArchivePanel.vue";
import { unavailableArchive } from "../services/agentArchive";

const mocks = vi.hoisted(() => ({ fetchReportEvidence: vi.fn(), fetchTurnArchive: vi.fn(),
  fetchEvidenceDetail: vi.fn(), verifyFrozenReport: vi.fn() }));
vi.mock("../services/agentArchive", async (original) => ({
  ...await original<typeof import("../services/agentArchive")>(), ...mocks
}));
const summary = { ...unavailableArchive, archive_status: "COMPLETE", reproduction_level: "FROZEN_FACT_RECHECK",
  integrity: { status: "VERIFIED", policy_version: "m16.5-integrity-v1" },
  manifest_id: "manifest", manifest_hash: "a".repeat(64), manifest_version: "m16.5-archive-v1",
  source_turn_id: "turn", archived_evidence_count: 1, required_evidence_count: 1, total: 1 };
const row = { evidence_id: "e1", tool_call_id: "tool", tool_name: "market.snapshot", tool_version: "1.0",
  entity_id: "market", as_of_date: "2026-01-02", record_path: "records.0", created_at: "2026-01-02" };
beforeEach(() => {
  vi.clearAllMocks();
  mocks.fetchReportEvidence.mockResolvedValue({ data: [row], meta: summary });
  mocks.fetchTurnArchive.mockResolvedValue({ ...summary, evidence: [row] });
});
async function click(wrapper: ReturnType<typeof mount>, text: string) {
  await wrapper.findAll("button").find((button) => button.text() === text)!.trigger("click");
  await flushPromises();
}
it("separates complete capture, integrity, unexecuted recheck and never claims algorithm reproduction", async () => {
  const wrapper = mount(EvidenceArchivePanel, { props: { reportId: "report" } });
  await flushPromises();
  expect(wrapper.text()).toContain("归档：COMPLETE");
  expect(wrapper.text()).toContain("完整性：VERIFIED");
  expect(wrapper.text()).toContain("冻结事实字段：尚未执行");
  expect(wrapper.text()).toContain("不是行情重拉");
  mocks.verifyFrozenReport.mockResolvedValue({ ...summary, verification_level: "MISMATCH",
    fact_recheck: { status: "MISMATCH", checked_claim_count: 1, results: [{ claim_id: "c1",
      status: "MISMATCH", reason_codes: ["VALUE_MISMATCH"], failed_fields: [{ path: "records.0.market_score", code: "VALUE_MISMATCH" }] }] } });
  await click(wrapper, "从冻结证据复核");
  expect(wrapper.text()).toContain("冻结事实字段：MISMATCH");
  expect(wrapper.text()).toContain("VALUE_MISMATCH");
  wrapper.unmount();
});
it("shows white-projected fact details, supports closing and bounded pagination", async () => {
  mocks.fetchReportEvidence.mockResolvedValueOnce({ data: [row], meta: { ...summary, total: 2 } });
  mocks.fetchEvidenceDetail.mockResolvedValue({ ...summary, ...row, arguments_summary: { trade_date: "2026-01-02" }, frozen_facts: [{ claim_id: "c1", path: "records.0.market_score", value: "60", unit: "score", entity: "market", trade_date: "2026-01-02", sample_role: "LIVE" }] });
  const wrapper = mount(EvidenceArchivePanel, { props: { reportId: "report" } });
  await flushPromises();
  await click(wrapper, "查看冻结事实");
  expect(wrapper.text()).toContain("60 score");
  await click(wrapper, "关闭详情");
  expect(wrapper.text()).not.toContain("60 score");
  await click(wrapper, "更多证据");
  expect(mocks.fetchReportEvidence).toHaveBeenLastCalledWith("report", 1, expect.any(AbortSignal));
  wrapper.unmount();
});
it("shows legacy unavailable without upstream reconstruction or verify button", async () => {
  mocks.fetchReportEvidence.mockResolvedValue({ data: [], meta: { ...unavailableArchive, total: 0 } });
  const wrapper = mount(EvidenceArchivePanel, { props: { reportId: "legacy" } });
  await flushPromises();
  expect(wrapper.text()).toContain("历史报告仅含 Claim 快照，无法恢复当次工具原始响应");
  expect(wrapper.findAll("button")[0].attributes("disabled")).toBeDefined();
  expect(mocks.verifyFrozenReport).not.toHaveBeenCalled();
  wrapper.unmount();
});
it("network failure clears recheck success and offers retry, never marks new request verified", async () => {
  mocks.verifyFrozenReport.mockRejectedValue(new Error("ARCHIVE_INTEGRITY_MISMATCH"));
  const wrapper = mount(EvidenceArchivePanel, { props: { reportId: "report" } });
  await flushPromises();
  await click(wrapper, "从冻结证据复核");
  expect(wrapper.find('[role="alert"]').text()).toContain("不能标记为已验证");
  expect(wrapper.text()).toContain("冻结事实字段：尚未执行");
  await click(wrapper, "重试读取");
  expect(wrapper.find('[role="alert"]').exists()).toBe(false);
  wrapper.unmount();
});
it("cancels stale report response and unloads pending read", async () => {
  let resolve!: (value: unknown) => void;
  mocks.fetchReportEvidence.mockReturnValueOnce(new Promise((done) => { resolve = done; }));
  const wrapper = mount(EvidenceArchivePanel, { props: { reportId: "old" } });
  const signal = mocks.fetchReportEvidence.mock.calls[0][2];
  await wrapper.setProps({ reportId: "new" });
  await flushPromises();
  resolve({ data: [{ ...row, evidence_id: "stale" }], meta: summary });
  await flushPromises();
  expect(signal.aborted).toBe(true);
  expect(wrapper.text()).not.toContain("stale");
  wrapper.unmount();
  expect(mocks.fetchReportEvidence.mock.calls[1][2].aborted).toBe(true);
});
it("chat uses exact request identity; missing historical identity remains unavailable", async () => {
  const wrapper = mount(EvidenceArchivePanel, { props: { chatId: "chat", requestId: "request" } });
  await flushPromises();
  expect(mocks.fetchTurnArchive).toHaveBeenCalledWith("chat", "request", expect.any(AbortSignal));
  await wrapper.setProps({ requestId: null });
  await flushPromises();
  expect(wrapper.text()).toContain("归档：UNAVAILABLE");
  wrapper.unmount();
});

it("separates direct facts, comparison context and bounded inference support", async () => {
  mocks.verifyFrozenReport.mockResolvedValue({ ...summary, verification_level: "UNVERIFIABLE",
    claim_recheck_summary: { status: "UNVERIFIABLE", verified_count: 2, mismatch_count: 0, unverifiable_count: 1 },
    fact_recheck: { status: "VERIFIED", checked_claim_count: 3, results: [
      { claim_id: "F1", status: "VERIFIED", facts_status: "VERIFIED", check_kind: "DIRECT_FACT",
        facts_applicable: true, reason_codes: [], failed_fields: [] },
      { claim_id: "C1", status: "UNVERIFIABLE", facts_status: "VERIFIED", check_kind: "COMPARISON_CONTEXT",
        facts_applicable: true, comparison_state: "INCOMPATIBLE", reason_codes: ["EXACT_M14_BUNDLE_NOT_ARCHIVED"], failed_fields: [] },
      { claim_id: "I1", status: "VERIFIED", facts_status: "UNVERIFIABLE", check_kind: "INFERENCE_SUPPORT",
        facts_applicable: false, support_status: "VERIFIED", reason_codes: ["INFERENCE_NOT_CAUSAL_PROOF"], failed_fields: [] }
    ] } });
  const wrapper = mount(EvidenceArchivePanel, { props: { reportId: "report" } });
  await flushPromises();
  await click(wrapper, "从冻结证据复核");
  expect(wrapper.text()).toContain("冻结事实字段：VERIFIED");
  expect(wrapper.text()).toContain("结论支持：UNVERIFIABLE");
  expect(wrapper.text()).toContain("支持关系：VERIFIED（不代表因果被证实）");
  expect(wrapper.text()).toContain("比较许可：INCOMPATIBLE（不代表收益差值已获授权）");
  expect(wrapper.text()).not.toContain("因果已验证");
  wrapper.unmount();
});
