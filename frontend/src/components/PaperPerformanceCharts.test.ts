import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import PaperPerformanceCharts from "./PaperPerformanceCharts.vue";
import type { PaperPerformance } from "../services/decisionPaper";
const mocks = vi.hoisted(() => ({ init: vi.fn(), setOption: vi.fn(), dispose: vi.fn(), resize: vi.fn(), disconnect: vi.fn(), observe: vi.fn() }));
vi.mock("echarts/core", () => ({ init: mocks.init, use: vi.fn() }));
function fixture() { return { continuous: true, benchmark_status: "BENCHMARK_UNAVAILABLE", series: [
  { trade_date: "2026-10-14", nav: "1", benchmark_nav: null, cash: "1000", market_value: "0", cumulative_cost: "5", valid: true, drawdown: "0" },
  { trade_date: "2026-10-15", nav: null, benchmark_nav: null, cash: null, market_value: null, cumulative_cost: null, valid: false, drawdown: null },
] } as PaperPerformance; }
beforeEach(() => { vi.resetAllMocks(); mocks.init.mockReturnValue({ setOption: mocks.setOption, dispose: mocks.dispose, resize: mocks.resize });
  vi.stubGlobal("ResizeObserver", class { observe = mocks.observe; disconnect = mocks.disconnect; }); });
afterEach(() => vi.unstubAllGlobals());
it("uses safe SVG, richText tooltips and no interpolation", async () => {
  const wrapper = mount(PaperPerformanceCharts, { props: { performance: fixture() } }); await flushPromises();
  expect(mocks.init).toHaveBeenCalledWith(expect.anything(), undefined, { renderer: "svg" });
  const options = mocks.setOption.mock.calls[0][0];
  expect(options.tooltip.renderMode).toBe("richText");
  expect(options.series[0]).toEqual(expect.objectContaining({ connectNulls: false, smooth: false, data: [1, null] }));
  expect(wrapper.text()).toContain("基准数据不完整");
  wrapper.unmount(); expect(mocks.dispose).toHaveBeenCalled(); expect(mocks.disconnect).toHaveBeenCalledOnce();
});
it("unsafe values do not reach ECharts and remain escaped fact table text", async () => {
  const performance = fixture(); performance.series[0].nav = '<img src=x onerror="bad()">';
  const wrapper = mount(PaperPerformanceCharts, { props: { performance } }); await flushPromises();
  expect(mocks.init).not.toHaveBeenCalled(); expect(wrapper.text()).toContain("CHART_VALUE_INVALID");
  expect(wrapper.findAll("img")).toHaveLength(0); wrapper.unmount();
});
it("mode changes dispose old charts and large numeric tables paginate", async () => {
  const performance = fixture(); performance.series = Array.from({ length: 24 }, (_, i) => ({ ...performance.series[0], trade_date: `2026-10-${String(i + 1).padStart(2, "0")}` }));
  const wrapper = mount(PaperPerformanceCharts, { props: { performance } }); await flushPromises();
  await wrapper.findAll('[role=tab]').find(row => row.text() === "现金与持仓")!.trigger("click"); await flushPromises();
  expect(mocks.dispose).toHaveBeenCalled(); expect(wrapper.findAll("tbody tr")).toHaveLength(20);
  await wrapper.findAll("button").find(row => row.text() === "下一页数值")!.trigger("click");
  expect(wrapper.findAll("tbody tr")).toHaveLength(4); wrapper.unmount();
});
