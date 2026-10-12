import type { ReportChart, ReportSnapshot } from "./agentReports";

const numeric = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/;
function decimalIdentity(value: string): string | null {
  if (!numeric.test(value) || value.length > 128) return null;
  const [mantissa, exp = "0"] = value.toLowerCase().split("e");
  const exponent = Number(exp);
  if (!Number.isInteger(exponent) || Math.abs(exponent) > 128) return null;
  const negative = mantissa.startsWith("-");
  const [whole, fraction = ""] = mantissa.replace(/^[+-]/, "").split(".");
  let digits = `${whole}${fraction}`.replace(/^0+/, "");
  let scale = fraction.length - exponent;
  while (digits.endsWith("0")) { digits = digits.slice(0, -1); scale--; }
  return digits ? `${negative ? "-" : ""}${digits}:${scale}` : "0";
}
const kinds: Record<string, string> = {
  "market.snapshot": "market", "sector.top": "sector", "theme.top": "theme",
  "opportunity.list": "stock", "performance.summary": "backtest_run",
  "backtest.summary": "backtest_run", "walk_forward.summary": "study",
  "walk_forward.window_lineage": "window"
};

export function snapshotBarData(chart: ReportChart, snapshot: ReportSnapshot): {
  warning: string; labels: string[]; values: number[]; raw: string[];
} {
  const fail = (warning: string) => ({ warning, labels: [], values: [], raw: [] });
  if (chart.chart_type === "line") return fail("SERIES_NOT_AVAILABLE");
  if (chart.chart_type !== "bar") return fail("");
  if (!chart.metric_id || !chart.trade_date || !chart.sample_role || !chart.entity_kind
      || chart.columns.join("|") !== "entity|value") return fail("CHART_SEMANTICS_INCOMPLETE");
  if (chart.unit === "mixed" || !chart.unit || chart.rows.length < 2) return fail("CHART_UNIT_OR_DATA_INVALID");
  if (chart.rows.length > 300) return fail("CHART_POINT_LIMIT_EXCEEDED");
  const entities = new Set<string>();
  for (const row of chart.rows) {
    if (row.length !== 2 || entities.has(row[0]) || !numeric.test(row[1])
        || row[1].length > 128 || !Number.isFinite(Number(row[1]))) return fail("CHART_VALUE_INVALID");
    entities.add(row[0]);
    const facts = snapshot.claims.flatMap((claim) => claim.structured_facts.filter((fact) => {
      if (fact.entity !== row[0] || fact.trade_date !== chart.trade_date || fact.unit !== chart.unit
          || fact.sample_role !== chart.sample_role) return false;
      const refs = snapshot.citations.filter((ref) => claim.evidence_ids.includes(ref.evidence_id)
        && ref.entity_id === fact.entity && ref.as_of_date === fact.trade_date
        && `${ref.tool_name}:${fact.path.split(".").slice(2).join(".")}` === chart.metric_id
        && kinds[ref.tool_name] === chart.entity_kind);
      return refs.length === 1;
    }));
    // Numeric conversion is only for plotting; the frozen decimal text remains visible.
    if (decimalIdentity(row[1]) === null || !facts.length
        || facts.some((fact) => decimalIdentity(String(fact.value)) !== decimalIdentity(row[1]))) {
      return fail("CHART_FACT_BINDING_INVALID");
    }
  }
  const rows = [...chart.rows].sort((a, b) => a[0].localeCompare(b[0]));
  return { warning: "", labels: rows.map((row) => row[0]),
    values: rows.map((row) => Number(row[1])), raw: rows.map((row) => row[1]) };
}
