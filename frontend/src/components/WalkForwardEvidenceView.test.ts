import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";
import WalkForwardEvidenceView from "./WalkForwardEvidenceView.vue";

const mocks = vi.hoisted(() => ({ fetchWalkForwardStudy: vi.fn(), fetchWalkForwardValidation: vi.fn(), fetchWalkForwardValidationWindow: vi.fn() }));
vi.mock("../services/agent", async (original) => ({ ...(await original<typeof import("../services/agent")>()), ...mocks }));
beforeEach(() => {
  vi.resetAllMocks();
  mocks.fetchWalkForwardStudy.mockResolvedValue({ status: "SUCCESS" });
  mocks.fetchWalkForwardValidation.mockResolvedValue({ status: "SUCCESS", window_count: 1001 });
  mocks.fetchWalkForwardValidationWindow.mockResolvedValue({ data: [{ window_no: 301, selected_train_run_id: "train-301", oos_run_id: "oos-301" }], meta: { total: 1 } });
});
it("directly locates a window beyond the first page and preserves back navigation", async () => {
  const wrapper = mount(WalkForwardEvidenceView, { props: { navigation: { view: "walk_forward", study_id: "study-a", validation_id: "validation-a", window_no: 301, source_tool: "walk_forward.window_lineage" } } });
  await flushPromises();
  expect(mocks.fetchWalkForwardValidationWindow).toHaveBeenCalledOnce();
  expect(mocks.fetchWalkForwardValidationWindow).toHaveBeenCalledWith("study-a", "validation-a", 301);
  expect(wrapper.text()).toContain("oos-301");
  expect(wrapper.text()).toContain("train-301");
  await wrapper.get("button").trigger("click");
  expect(wrapper.emitted("back")).toHaveLength(1);
  wrapper.unmount();
});
it("fails explicitly when the frozen validation does not contain that window", async () => {
  mocks.fetchWalkForwardValidationWindow.mockResolvedValue({ data: [], meta: { total: 0 } });
  const wrapper = mount(WalkForwardEvidenceView, { props: { navigation: { view: "walk_forward", study_id: "study-a", validation_id: "validation-a", window_no: 301, source_tool: "walk_forward.window_lineage" } } });
  await flushPromises();
  expect(wrapper.text()).toContain("未找到 Window 301");
  wrapper.unmount();
});
