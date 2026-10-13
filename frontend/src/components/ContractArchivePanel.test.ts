import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";
import ContractArchivePanel from "./ContractArchivePanel.vue";

const mocks = vi.hoisted(() => ({ fetchReportContracts: vi.fn(), fetchReportContract: vi.fn(), verifyReportContracts: vi.fn() }));
vi.mock("../services/agentReports", () => mocks);
const reference = { manifest_id: "child", manifest_hash: "a".repeat(64), policy_version: "m16.6-contract-manifest-v1",
  contract_ids_hash: "b".repeat(64), contract_refs_hash: "c".repeat(64), contract_count: 21, contract_scope: ["M14_EXACT_BUNDLE"], gap_codes: [], reproduction_level: "FROZEN_CONTRACT_RECHECK" as const };
const check = { archive_integrity: { status: "VERIFIED" }, frozen_fact_recheck: { status: "VERIFIED" },
  contract_integrity: { status: "VERIFIED" }, contract_semantics: { status: "VERIFIED", reason_codes: [] },
  comparison_permission: { allowed: false }, calculation_reproduced: false, results: [] };
const row = { contract_id: "contract", contract_kind: "M14_EXACT_BUNDLE", subject_id: "run", role: "LIVE",
  schema_version: "m16.6-m14-bundle-v1", contract_hash: "e".repeat(64), tool_result_archive_id: "tool", status: "VERIFIED", reason_codes: [] };
beforeEach(() => {
  vi.resetAllMocks();
  mocks.fetchReportContracts.mockResolvedValue({ data: [row], meta: { total: 1, check } });
  mocks.fetchReportContract.mockResolvedValue({ ...row, projection: { run_id: "run", note: '<img src=x onerror="alert(1)">' } });
  mocks.verifyReportContracts.mockResolvedValue(check);
});
it("never backfills a historical report or offers a repair action", async () => {
  const wrapper = mount(ContractArchivePanel, { props: { reportId: "old" } });
  await flushPromises();
  expect(wrapper.text()).toContain("无合同归档");
  expect(wrapper.findAll("button")).toHaveLength(0);
  expect(mocks.fetchReportContracts).not.toHaveBeenCalled();
  wrapper.unmount();
});
it("renders distinct levels, safe details and keyboard-accessible pagination", async () => {
  mocks.fetchReportContracts.mockResolvedValueOnce({ data: Array.from({ length: 20 }, (_, i) => ({ ...row, contract_id: `${i}` })), meta: { total: 21, check } });
  const wrapper = mount(ContractArchivePanel, { props: { reportId: "new", reference } });
  await flushPromises();
  expect(wrapper.text()).toContain("算法未重跑");
  expect(wrapper.text()).toContain("待场景校验");
  expect(wrapper.find('button[aria-label="上一页"]').attributes("disabled")).toBeDefined();
  await wrapper.find('button[aria-label="下一页"]').trigger("click");
  await flushPromises();
  expect(mocks.fetchReportContracts).toHaveBeenLastCalledWith("new", 20, expect.any(AbortSignal));
  await wrapper.find("tbody button").trigger("click");
  await flushPromises();
  expect(wrapper.text()).toContain("onerror");
  expect(wrapper.find("img").exists()).toBe(false);
  wrapper.unmount();
});
it("cancels obsolete report requests and never displays stale results", async () => {
  let resolve!: (value: unknown) => void;
  mocks.fetchReportContracts.mockReturnValueOnce(new Promise(r => { resolve = r; }));
  const wrapper = mount(ContractArchivePanel, { props: { reportId: "first", reference } });
  const signal = mocks.fetchReportContracts.mock.calls[0][2];
  await wrapper.setProps({ reportId: "second" });
  await flushPromises();
  expect(signal.aborted).toBe(true);
  resolve({ data: [{ ...row, subject_id: "stale-run" }], meta: { total: 1, check } });
  await flushPromises();
  expect(wrapper.text()).not.toContain("stale-run");
  wrapper.unmount();
});
it("clears current verification on an error and recovers by reload", async () => {
  mocks.verifyReportContracts.mockRejectedValueOnce(new Error("CONTRACT_HASH_MISMATCH"));
  const wrapper = mount(ContractArchivePanel, { props: { reportId: "new", reference } });
  await flushPromises();
  await wrapper.findAll("button").find(b => b.text() === "复核合同")!.trigger("click");
  await flushPromises();
  expect(wrapper.get('[role="alert"]').text()).toContain("CONTRACT_HASH_MISMATCH");
  expect(wrapper.get(".contract-statuses").text()).toContain("待核验");
  await wrapper.get('[role="alert"] button').trigger("click");
  await flushPromises();
  expect(wrapper.find('[role="alert"]').exists()).toBe(false);
  expect(wrapper.get(".contract-statuses").text()).toContain("通过");
  wrapper.unmount();
});
