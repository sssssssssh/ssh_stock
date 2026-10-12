import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { ReportChart, ReportSnapshot } from "../services/agentReports";
import { snapshotBarData } from "../services/reportSnapshotChart";
import ReportSnapshotChart from "./ReportSnapshotChart.vue";

const mocks = vi.hoisted(() => ({ init: vi.fn(), setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn(),
  observe: vi.fn(), disconnect: vi.fn() }));
vi.mock("echarts/core", () => ({ init: mocks.init, use: vi.fn() }));

function fixture(): { chart: ReportChart; snapshot: ReportSnapshot } {
  const chart: ReportChart = { chart_id: "bar", chart_type: "bar", title: "分数", unit: "score",
    metric_id: "opportunity.list:score", entity_kind: "stock", sample_role: "LIVE",
    trade_date: "2026-10-10", columns: ["entity", "value"], rows: [["B", "12"], ["A", "10"]] };
  const snapshot: ReportSnapshot = { schema_version: "m16.4.1-report-snapshot-v2",
    snapshot_level: "CLAIM_SNAPSHOT_ONLY", report_type: "market_review", title: "test",
    source_answer_status: "COMPLETED", source_chat_id: "chat", source_message_id: "message",
    claims: chart.rows.map(([entity, value], index) => ({ claim_id: `c-${index}`, claim_type: "FACT",
      text: "verified", evidence_ids: [`ev-${entity}`], quality_status: "PASS", reason_codes: [],
      structured_facts: [{ path: `records.${index}.score`, value, unit: "score", entity,
        trade_date: "2026-10-10", sample_role: "LIVE" }] })),
    citations: chart.rows.map(([entity]) => ({ marker: "E", evidence_id: `ev-${entity}`,
      evidence_version: "v2", tool_name: "opportunity.list", entity_id: entity, as_of_date: "2026-10-10" })),
    rejected_claims: [], sections: [], charts: [chart], warnings: ["SERIES_NOT_AVAILABLE"] };
  return { chart, snapshot };
}

beforeEach(() => {
  vi.resetAllMocks();
  mocks.init.mockReturnValue({ setOption: mocks.setOption, resize: mocks.resize, dispose: mocks.dispose });
  vi.stubGlobal("ResizeObserver", class { observe = mocks.observe; disconnect = mocks.disconnect; });
});
afterEach(() => vi.unstubAllGlobals());

it("plots only bound frozen values, keeps raw numbers and units, and sorts consistently", async () => {
  const props = fixture();
  const data = snapshotBarData(props.chart, props.snapshot);
  expect(data).toEqual({ warning: "", labels: ["A", "B"], values: [10, 12], raw: ["10", "12"] });
  const wrapper = mount(ReportSnapshotChart, { props });
  await flushPromises();
  expect(mocks.setOption).toHaveBeenCalledWith(expect.objectContaining({
    xAxis: expect.objectContaining({ data: ["A", "B"] }),
    series: [expect.objectContaining({ type: "bar", data: [10, 12] })]
  }));
  const options = mocks.setOption.mock.calls[0][0];
  expect(options.tooltip.formatter([{ dataIndex: 1 }])).toBe("B\n12 score");
  expect(wrapper.text()).toContain("冻结数值 · score");
  expect(wrapper.find(".table-scroll").attributes("tabindex")).toBe("0");
  wrapper.unmount();
});

it.each(["mixed", "empty", "invalid", "over-limit", "unbound", "precise-mismatch", "legacy", "line"])(
  "falls back to a fact table for %s without creating a chart", async (fault) => {
    const props = fixture();
    if (fault === "mixed") props.chart.unit = "mixed";
    if (fault === "empty") props.chart.rows = [];
    if (fault === "invalid") props.chart.rows[0][1] = "NaN";
    if (fault === "over-limit") props.chart.rows = Array.from({ length: 301 }, (_, i) => [String(i), "1"]);
    if (fault === "unbound") props.chart.rows[0][1] = "99";
    if (fault === "precise-mismatch") {
      props.chart.rows[0][1] = "0.100000000000000001";
      props.snapshot.claims[0].structured_facts[0].value = "0.100000000000000002";
    }
    if (fault === "legacy") delete props.chart.metric_id;
    if (fault === "line") props.chart.chart_type = "line";
    const wrapper = mount(ReportSnapshotChart, { props });
    await flushPromises();
    expect(mocks.init).not.toHaveBeenCalled();
    expect(wrapper.find("table").exists()).toBe(true);
    expect(wrapper.text()).toContain("仅展示冻结事实表");
    if (fault === "line") expect(wrapper.text()).toContain("SERIES_NOT_AVAILABLE");
    wrapper.unmount();
  }
);

it("disposes charts across report switches and cleans observers and event handlers", async () => {
  const remove = vi.spyOn(window, "removeEventListener");
  const props = fixture();
  const wrapper = mount(ReportSnapshotChart, { props });
  await flushPromises();
  window.dispatchEvent(new Event("resize"));
  expect(mocks.resize).toHaveBeenCalled();
  await wrapper.setProps({ chart: { ...props.chart, title: "second" } });
  await flushPromises();
  expect(mocks.dispose).toHaveBeenCalledTimes(1);
  wrapper.unmount();
  expect(mocks.dispose).toHaveBeenCalledTimes(2);
  expect(mocks.disconnect).toHaveBeenCalledOnce();
  expect(remove).toHaveBeenCalledWith("resize", expect.any(Function));
});

it("reports renderer failure and retains the frozen table", async () => {
  mocks.init.mockImplementation(() => { throw new Error("renderer unavailable"); });
  const wrapper = mount(ReportSnapshotChart, { props: fixture() });
  await flushPromises();
  expect(wrapper.text()).toContain("CHART_RENDER_FAILED");
  expect(wrapper.find("table").exists()).toBe(true);
  wrapper.unmount();
});
