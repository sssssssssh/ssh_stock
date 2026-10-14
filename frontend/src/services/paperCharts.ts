import type { PaperSeries } from "./decisionPaper";
export function paperChartData(rows: PaperSeries[], key: "nav" | "benchmark_nav" | "cash" | "market_value" | "drawdown" | "cumulative_cost") {
  if (rows.length > 2000) return { dates: [], values: [], warning: "CHART_CAPACITY_EXCEEDED" };
  const dates: string[] = [], values: (number | null)[] = [];
  for (const row of rows) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(row.trade_date) || (dates.length && row.trade_date <= dates[dates.length - 1]))
      return { dates: [], values: [], warning: "CHART_SEQUENCE_INVALID" };
    const raw = row[key];
    if (!row.valid || raw === null) { dates.push(row.trade_date); values.push(null); continue; }
    if (typeof raw !== "string" || !/^-?\d+(\.\d+)?$/.test(raw)) return { dates: [], values: [], warning: "CHART_VALUE_INVALID" };
    const value = Number(raw);
    if (!Number.isFinite(value) || Math.abs(value) > 1e20) return { dates: [], values: [], warning: "CHART_VALUE_INVALID" };
    dates.push(row.trade_date); values.push(value);
  }
  return { dates, values, warning: "" };
}
