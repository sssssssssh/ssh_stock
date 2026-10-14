import { expect, it } from "vitest";
import { paperChartData } from "./paperCharts";
import type { PaperSeries } from "./decisionPaper";

const row = (date: string, nav: string | null, valid = true): PaperSeries => ({ trade_date: date,
  nav, benchmark_nav: null, cash: "1000", market_value: "0", daily_return: null, drawdown: null,
  cumulative_cost: "0", valid });
it("keeps unavailable and review-required dates as gaps", () => {
  expect(paperChartData([row("2026-10-14", "1"), row("2026-10-15", null, false), row("2026-10-16", "1.1")], "nav").values).toEqual([1, null, 1.1]);
  expect(paperChartData([row("2026-10-14", "1")], "benchmark_nav").values).toEqual([null]);
});
it.each(["NaN", "Infinity", "1e99", "<img src=x onerror=alert(1)>", "99999999999999999999999"])("rejects unsafe chart input %s", value => {
  expect(paperChartData([row("2026-10-14", value)], "nav").warning).toBe("CHART_VALUE_INVALID");
});
it("rejects bad dates, duplicate order, and excessive capacity", () => {
  expect(paperChartData([row("<img>", "1")], "nav").warning).toBe("CHART_SEQUENCE_INVALID");
  expect(paperChartData([row("2026-10-14", "1"), row("2026-10-14", "2")], "nav").warning).toBe("CHART_SEQUENCE_INVALID");
  expect(paperChartData(Array(2001).fill(row("2026-10-14", "1")), "nav").warning).toBe("CHART_CAPACITY_EXCEEDED");
});
