import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import AnalyticsSummaryCards from "../components/AnalyticsSummaryCards.vue";
import type { AnalyticsSummary } from "../types";
import {
  buildDrawdownSeries,
  buildNavSeries,
  compareAnalytics,
  fetchPeriods,
  fetchTradeEpisodes,
  formatAnalyticsPercent,
  formatCny,
  formatMetric,
  sortedCompareItems
} from "./analytics";

const response = (data: unknown) =>
  Promise.resolve({
    ok: true,
    status: 200,
    json: () => Promise.resolve({ code: 0, message: "ok", data, meta: {} })
  } as Response);

function summary(runId: string, annualized = "0.1"): AnalyticsSummary {
  return {
    schema_version: "analytics_read_v1",
    identity: {
      run_id: runId,
      performance_id: "p",
      risk_id: "r",
      trade_id: "t",
      period_id: null
    },
    backtest: {
      name: runId,
      status: "SUCCESS",
      start_date: "2026-01-01",
      end_date: "2026-01-31",
      initial_cash: "100000",
      benchmark_code: "000300.SH"
    },
    performance: {
      cumulative_return: "0.1",
      annualized_return: annualized,
      max_drawdown: "-0.03",
      max_drawdown_peak_date: null,
      max_drawdown_trough_date: null,
      max_drawdown_recovery_date: null,
      trade_days: 20
    },
    risk: {
      benchmark_code: "000300.SH",
      benchmark_cumulative_return: "0.05",
      benchmark_annualized_return: "0.05",
      excess_cumulative_return: "0.047",
      strategy_annualized_volatility: null,
      sharpe_ratio: null,
      sortino_ratio: null,
      calmar_ratio: null,
      tracking_error: null,
      information_ratio: null,
      alpha_annualized: null,
      beta: null,
      correlation: null
    },
    trade: {
      total_turnover: "0.8",
      annualized_turnover: "10",
      traded_gross_amount: "20000",
      cash_fee_total: "30",
      slippage_cost_total: "20",
      total_execution_cost: "50",
      total_cost_to_initial_capital: "0.0005",
      closed_episode_count: 2,
      open_episode_count: 0,
      win_rate: null,
      profit_factor: null,
      payoff_ratio: null,
      average_holding_trade_days: null,
      median_holding_trade_days: null,
      closed_realized_pnl: "100"
    },
    warnings: [],
    source_versions: {}
  };
}

afterEach(() => vi.restoreAllMocks());

describe("analytics service and presentation contract", () => {
  it("builds period endpoint parameters", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(() => response([]));
    await fetchPeriods("run-a", "MONTH");
    expect(fetchMock.mock.calls[0][0]).toContain(
      "/portfolio/backtests/run-a/performance/period?period_type=MONTH&limit=500"
    );
  });

  it("sends compare items in request order", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(() =>
      response({ schema_version: "analytics_read_v1", items: [] })
    );
    await compareAnalytics([{ run_id: "b" }, { run_id: "a" }]);
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(init.body)).items.map((row: { run_id: string }) => row.run_id)).toEqual([
      "b",
      "a"
    ]);
  });

  it("builds episode filters and pagination", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(() => response([]));
    await fetchTradeEpisodes("run-a", {
      status: "CLOSED",
      tsCode: "000001.SZ",
      limit: 20,
      offset: 40
    });
    expect(fetchMock.mock.calls[0][0]).toContain(
      "status=CLOSED&ts_code=000001.SZ&limit=20&offset=40"
    );
  });

  it("formats null metrics as double dash", () => {
    expect(formatMetric(null)).toBe("--");
    expect(formatAnalyticsPercent(null)).toBe("--");
    expect(formatCny(null)).toBe("--");
  });

  it("formats percent amount and ratio", () => {
    expect(formatAnalyticsPercent("0.125")).toBe("12.50%");
    expect(formatMetric("1.23456", 3)).toBe("1.235");
    expect(formatCny("12")).toContain("12.00");
  });

  it("uses persisted NAV and benchmark NAV without recalculation", () => {
    expect(
      buildNavSeries(
        [{ trade_date: "2026-01-02", nav: "1.234", drawdown: "-0.01" }],
        [{ trade_date: "2026-01-02", benchmark_nav: "1.111" }]
      )
    ).toEqual({ dates: ["2026-01-02"], strategy: [1.234], benchmark: [1.111] });
  });

  it("uses persisted API drawdown", () => {
    expect(
      buildDrawdownSeries([{ trade_date: "2026-01-02", nav: "1.2", drawdown: "-0.123" }])
    ).toEqual([["2026-01-02", -0.123]]);
  });

  it("client sorting leaves source array identity and order unchanged", () => {
    const original = [summary("a", "0.1"), summary("b", "0.2")];
    const sorted = sortedCompareItems(original, "annualized_return");
    expect(sorted.map((row) => row.identity.run_id)).toEqual(["b", "a"]);
    expect(original.map((row) => row.identity.run_id)).toEqual(["a", "b"]);
    expect(sorted).not.toBe(original);
  });

  it("summary cards render nulls as double dash", () => {
    const wrapper = mount(AnalyticsSummaryCards, { props: { summary: summary("a") } });
    expect(wrapper.text()).toContain("Sharpe--");
    expect(wrapper.text()).toContain("胜率--");
  });
});
