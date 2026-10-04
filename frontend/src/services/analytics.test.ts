import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import AnalyticsSummaryCards from "../components/AnalyticsSummaryCards.vue";
import type { AnalyticsSummary } from "../types";
import {
  buildDrawdownSeries,
  buildNavSeries,
  compareAnalytics,
  fetchAllAnalyticsSeries,
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
    const identity = summary("run-a").identity;
    identity.period_id = "x";
    await fetchPeriods("run-a", "MONTH", identity);
    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toContain("performance_id=p");
    expect(url).toContain("risk_id=r");
    expect(url).toContain("trade_id=t");
    expect(url).toContain("period_id=x");
    expect(url).toContain("period_type=MONTH");
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
    await fetchTradeEpisodes("run-a", summary("run-a").identity, {
      status: "CLOSED",
      tsCode: "000001.SZ",
      limit: 20,
      offset: 40
    });
    expect(fetchMock.mock.calls[0][0]).toContain(
      "performance_id=p&trade_id=t&status=CLOSED&ts_code=000001.SZ&limit=20&offset=40"
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
        [{
          trade_date: "2026-01-02",
          strategy_nav: "1.234",
          strategy_daily_return: "0.01",
          strategy_cumulative_return: "0.234",
          drawdown: "-0.01",
          benchmark_nav: "1.111",
          benchmark_daily_return: "0.005",
          active_return: "0.005"
        }]
      )
    ).toEqual({ dates: ["2026-01-02"], strategy: [1.234], benchmark: [1.111] });
  });

  it("uses persisted API drawdown", () => {
    expect(
      buildDrawdownSeries([{
        trade_date: "2026-01-02",
        strategy_nav: "1.2",
        strategy_daily_return: "0",
        strategy_cumulative_return: "0.2",
        drawdown: "-0.123",
        benchmark_nav: "1.1",
        benchmark_daily_return: "0",
        active_return: "0"
      }])
    ).toEqual([["2026-01-02", -0.123]]);
  });

  it("loads all 1200 bundle-pinned series rows in three ordered pages", async () => {
    const identity = summary("run-a").identity;
    identity.period_id = "x";
    const allRows = Array.from({ length: 1200 }, (_, index) => ({
      trade_date: new Date(Date.UTC(2020, 0, index + 1)).toISOString().slice(0, 10),
      strategy_nav: String(1 + index / 10000),
      strategy_daily_return: "0.0001",
      strategy_cumulative_return: String(index / 10000),
      drawdown: String(-index / 100000),
      benchmark_nav: String(1 + index / 20000),
      benchmark_daily_return: "0.00005",
      active_return: "0.00005"
    }));
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const offset = Number(new URL(String(input), "http://local").searchParams.get("offset"));
      const data = allRows.slice(offset, offset + 500);
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({
          code: 0,
          message: "ok",
          data,
          meta: { ...identity, limit: 500, offset, total: 1200 }
        })
      } as Response);
    });
    const rows = await fetchAllAnalyticsSeries("run-a", identity);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(rows).toHaveLength(1200);
    expect(rows[0].trade_date).toBe(allRows[0].trade_date);
    expect(rows[1199].trade_date).toBe(allRows[1199].trade_date);
    expect(buildNavSeries(rows).dates).toHaveLength(1200);
    expect(buildDrawdownSeries(rows)).toHaveLength(1200);
  });

  it("fails closed when a later series page changes bundle identity", async () => {
    const identity = summary("run-a").identity;
    const rows = Array.from({ length: 501 }, (_, index) => ({
      trade_date: new Date(Date.UTC(2020, 0, index + 1)).toISOString().slice(0, 10),
      strategy_nav: "1",
      strategy_daily_return: "0",
      strategy_cumulative_return: "0",
      drawdown: "0",
      benchmark_nav: "1",
      benchmark_daily_return: "0",
      active_return: "0"
    }));
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const offset = Number(new URL(String(input), "http://local").searchParams.get("offset"));
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({
          code: 0,
          message: "ok",
          data: rows.slice(offset, offset + 500),
          meta: {
            ...identity,
            risk_id: offset === 0 ? identity.risk_id : "r2",
            limit: 500,
            offset,
            total: 501
          }
        })
      } as Response);
    });
    await expect(fetchAllAnalyticsSeries("run-a", identity)).rejects.toThrow(
      "ANALYTICS_ARTIFACT_BUNDLE_MISMATCH"
    );
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
