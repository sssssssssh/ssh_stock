import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import type { AnalyticsSummary } from "../types";

const mocks = vi.hoisted(() => ({
  calculatePeriods: vi.fn(),
  compareAnalytics: vi.fn(),
  fetchAllAnalyticsSeries: vi.fn(),
  fetchAnalyticsSummary: vi.fn(),
  fetchBacktests: vi.fn(),
  fetchPeriods: vi.fn(),
  fetchTradeEpisodes: vi.fn()
}));

vi.mock("../services/analytics", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../services/analytics")>()),
  ...mocks
}));

import BacktestAnalyticsView from "./BacktestAnalyticsView.vue";

const summary: AnalyticsSummary = {
  schema_version: "analytics_read_v1",
  identity: {
    run_id: "run-a",
    performance_id: "p1",
    risk_id: "r1",
    trade_id: "t1",
    period_id: "x1"
  },
  backtest: {
    name: "demo",
    status: "SUCCESS",
    start_date: "2020-01-01",
    end_date: "2024-12-31",
    initial_cash: "1000000",
    benchmark_code: "000300.SH"
  },
  performance: {
    cumulative_return: "0.2",
    annualized_return: "0.04",
    max_drawdown: "-0.1",
    max_drawdown_peak_date: null,
    max_drawdown_trough_date: null,
    max_drawdown_recovery_date: null,
    trade_days: 1200
  },
  risk: {
    benchmark_code: "000300.SH",
    benchmark_cumulative_return: "0.1",
    benchmark_annualized_return: "0.02",
    excess_cumulative_return: "0.09",
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
    total_turnover: "1",
    annualized_turnover: "0.2",
    traded_gross_amount: "1",
    cash_fee_total: "1",
    slippage_cost_total: "1",
    total_execution_cost: "2",
    total_cost_to_initial_capital: "0.000002",
    closed_episode_count: 0,
    open_episode_count: 0,
    win_rate: null,
    profit_factor: null,
    payoff_ratio: null,
    average_holding_trade_days: null,
    median_holding_trade_days: null,
    closed_realized_pnl: "0"
  },
  warnings: [],
  source_versions: {}
};

beforeEach(() => {
  vi.clearAllMocks();
  mocks.fetchBacktests.mockResolvedValue([
    {
      id: "run-a",
      name: "demo",
      account_mode: "BACKTEST",
      status: "SUCCESS",
      start_date: "2020-01-01",
      end_date: "2024-12-31",
      initial_cash: "1000000",
      benchmark_code: "000300.SH",
      created_at: "2026-01-01T00:00:00Z"
    }
  ]);
  mocks.fetchAnalyticsSummary.mockResolvedValue(summary);
  mocks.fetchAllAnalyticsSeries.mockResolvedValue([]);
  mocks.fetchPeriods.mockResolvedValue([]);
  mocks.fetchTradeEpisodes.mockResolvedValue({
    data: [],
    meta: {
      performance_id: "p1",
      trade_id: "t1",
      limit: 20,
      offset: 0,
      total: 0
    }
  });
});

describe("BacktestAnalyticsView bundle pinning", () => {
  it("loads the initial run once and pins every child read to summary identity", async () => {
    const wrapper = mount(BacktestAnalyticsView, {
      global: {
        stubs: {
          AnalyticsSummaryCards: true,
          AnalyticsNavChart: true,
          AnalyticsDrawdownChart: true,
          AnalyticsPeriodTable: true,
          AnalyticsCompareTable: true
        }
      }
    });
    await flushPromises();
    await flushPromises();

    expect(mocks.fetchAnalyticsSummary).toHaveBeenCalledTimes(1);
    expect(mocks.fetchAllAnalyticsSeries).toHaveBeenCalledWith("run-a", summary.identity);
    expect(mocks.fetchTradeEpisodes).toHaveBeenCalledWith(
      "run-a",
      summary.identity,
      expect.objectContaining({ limit: 20, offset: 0 })
    );
    expect(mocks.fetchPeriods).toHaveBeenCalledTimes(2);
    expect(mocks.fetchPeriods).toHaveBeenNthCalledWith(1, "run-a", "MONTH", summary.identity);
    expect(mocks.fetchPeriods).toHaveBeenNthCalledWith(2, "run-a", "YEAR", summary.identity);
    const next = wrapper.findAll("button").find((button) => button.text() === "下一页");
    expect(next?.attributes("disabled")).toBeDefined();
  });

  it("discards a slow response from a previously selected run", async () => {
    let resolveSlow: ((value: AnalyticsSummary) => void) | undefined;
    const slow = new Promise<AnalyticsSummary>((resolve) => { resolveSlow = resolve; });
    const runB = { ...summary, identity: { ...summary.identity, run_id: "run-b" } };
    mocks.fetchBacktests.mockResolvedValue([
      {
        id: "run-a",
        name: "A",
        account_mode: "BACKTEST",
        status: "SUCCESS",
        start_date: "2020-01-01",
        end_date: "2024-12-31",
        initial_cash: "1000000",
        benchmark_code: "000300.SH",
        created_at: "2026-01-01T00:00:00Z"
      },
      {
        id: "run-b",
        name: "B",
        account_mode: "BACKTEST",
        status: "SUCCESS",
        start_date: "2020-01-01",
        end_date: "2024-12-31",
        initial_cash: "1000000",
        benchmark_code: "000300.SH",
        created_at: "2026-01-01T00:00:00Z"
      }
    ]);
    mocks.fetchAnalyticsSummary
      .mockResolvedValueOnce(summary)
      .mockReturnValueOnce(slow)
      .mockResolvedValueOnce(summary);
    const wrapper = mount(BacktestAnalyticsView, {
      global: {
        stubs: {
          AnalyticsSummaryCards: {
            props: ["summary"],
            template: '<div data-test="summary-run">{{ summary.identity.run_id }}</div>'
          },
          AnalyticsNavChart: true,
          AnalyticsDrawdownChart: true,
          AnalyticsPeriodTable: true,
          AnalyticsCompareTable: true
        }
      }
    });
    await flushPromises();
    const select = wrapper.find("select");
    await select.setValue("run-b");
    await nextTick();
    await Promise.resolve();
    expect(mocks.fetchAnalyticsSummary).toHaveBeenCalledWith("run-b");
    (select.element as HTMLSelectElement).disabled = false;
    await select.setValue("run-a");
    await flushPromises();
    expect(mocks.fetchAnalyticsSummary).toHaveBeenCalledTimes(3);
    expect(wrapper.get('[data-test="summary-run"]').text()).toBe("run-a");
    resolveSlow?.(runB);
    await flushPromises();
    expect(wrapper.get('[data-test="summary-run"]').text()).toBe("run-a");
  });
});
