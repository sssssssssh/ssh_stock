import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import CalculationProgress from "./CalculationProgress.vue";

describe("candidate terminal details", () => {
  it("distinguishes cancellation from failure without claiming publication", () => {
    const wrapper = mount(CalculationProgress, { props: { running: false, value: {
      name: "stock_trade_status_daily", kind: "candidate", phase: "cancelled",
      batch_index: 1, batch_count: 2, completed_rows: 500, total_rows: 1000,
      elapsed_seconds: 12, operation_elapsed_seconds: 3, recent_events: [],
    } } });
    expect(wrapper.text()).toContain("本步骤已取消");
    expect(wrapper.text()).not.toContain("本步骤异常");
    expect(wrapper.text()).toContain("尚未发布");
    wrapper.unmount();
  });

  it("does not interpret reconciled scope as completed candidate writes", () => {
    const wrapper = mount(CalculationProgress, { props: { running: true, value: {
      name: "stock_trade_status_daily", kind: "reconcile", phase: "complete",
      total_rows: 1000, completed_rows: 0, elapsed_seconds: 12,
      operation_elapsed_seconds: 3, recent_events: [], batch_count: null,
    } } });
    expect(wrapper.text()).toContain("候选写入及正式发布尚未完成");
    expect(wrapper.text()).not.toContain("本步骤已暂存");
    wrapper.unmount();
  });
});
