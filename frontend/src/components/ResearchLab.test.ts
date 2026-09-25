import { flushPromises, mount } from "@vue/test-utils";
import { expect, it, vi } from "vitest";

import ResearchLab from "./ResearchLab.vue";

vi.mock("../services/research", () => {
  const makeHorizon = (days: number, avgReturn: number) => ({
    horizon: days, event_count: 1, mature_count: 1, entry_executable_count: 1,
    exit_executable_count: 1, return_sample_count: 1, mark_sample_count: 1,
    delayed_exit_sample_count: 1, net_return_sample_count: 1,
    net_delayed_exit_sample_count: 1, excess_sample_count: 1,
    avg_return: avgReturn, median_return: avgReturn, p25_return: avgReturn,
    p75_return: avgReturn, win_rate: 1, avg_benchmark_return: 0,
    avg_excess_return: avgReturn, median_excess_return: avgReturn, excess_win_rate: 1,
    avg_mark_return: avgReturn, median_mark_return: avgReturn, mark_win_rate: 1,
    avg_delayed_exit_return: avgReturn, median_delayed_exit_return: avgReturn,
    delayed_exit_win_rate: 1, avg_net_return: avgReturn,
    avg_net_delayed_exit_return: avgReturn, avg_exit_delay_days: 0,
    delayed_exit_count: 0, delayed_exit_rate: 0, avg_positive_exit_delay_days: null,
    final_exit_success_count: 1, final_exit_success_rate: 1, final_exit_completed_count: 1,
    final_exit_unresolved_count: 0, unresolved_exit_rate: 0,
    final_exit_pending_count: 0, pending_exit_rate: 0,
    final_exit_data_incomplete_count: 0, data_incomplete_exit_rate: 0,
    non_executable_rate: 0, avg_mfe20: null, avg_mae20: null, sample_warning: false,
    return_sample_warning: false, mark_sample_warning: false,
    delayed_exit_sample_warning: false
  });
  const rows = [{
    group: "ALL", event_count: 1,
    horizons: [makeHorizon(20, 0.1), makeHorizon(60, 0.2)]
  }];
  return {
    fetchResearchStatus: vi.fn().mockResolvedValue({
      benchmark_code: "000300.SH",
      research_version: "research_v1",
      opportunity_eval_rows: 1,
      theme_eval_rows: 1,
      transition_eval_rows: 1,
      mature20_rows: 1,
      latest_evaluated_market_date: "2026-09-25"
    }),
    fetchThemeStats: vi.fn().mockResolvedValue(rows),
    fetchThemeBuckets: vi.fn().mockResolvedValue([]),
    fetchThemeTopN: vi.fn().mockResolvedValue([]),
    fetchThemeLifecycle: vi.fn().mockResolvedValue([]),
    fetchLeftThresholds: vi.fn().mockResolvedValue([]),
    fetchRightTransitions: vi.fn().mockResolvedValue([]),
    fetchTrendTopN: vi.fn().mockResolvedValue([]),
    fetchOpportunityBuckets: vi.fn().mockResolvedValue([]),
    fetchPositionStats: vi.fn().mockResolvedValue([]),
    fetchContext: vi.fn().mockResolvedValue([]),
    queueResearchEvaluation: vi.fn().mockResolvedValue({ id: "job-1", status: "QUEUED" })
  };
});

it("switches horizon metrics and uses final-exit terminology", async () => {
  const wrapper = mount(ResearchLab);
  await flushPromises();
  expect(wrapper.text()).toContain("最终可退出收益");
  expect(wrapper.text()).toContain("10.0%");

  const sixty = wrapper.findAll("button").find((button) => button.text() === "60日");
  await sixty?.trigger("click");
  expect(wrapper.text()).toContain("20.0%");
});
