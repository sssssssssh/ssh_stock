import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import DecisionPaperWorkbench from "./DecisionPaperWorkbench.vue";
import { ApiError } from "../services/api";

vi.mock("./PaperPerformanceCharts.vue", () => ({ default: { template: '<div>冻结模拟图表</div>' } }));
const mocks = vi.hoisted(() => ({ paperStatus: vi.fn(), paperAccounts: vi.fn(), paperAccount: vi.fn(),
  paperPerformance: vi.fn(), paperJobs: vi.fn(), paperPage: vi.fn(), paperWrite: vi.fn(), fetchResearchReports: vi.fn() }));
vi.mock("../services/decisionPaper", async original => ({ ...(await original<typeof import("../services/decisionPaper")>()), ...mocks }));
vi.mock("../services/agentReports", () => ({ fetchResearchReports: mocks.fetchResearchReports }));
const risk = { max_positions: 10, max_single_position_weight: "0.1", min_cash_ratio: "0.02",
  max_new_positions_per_day: 2, max_sector_weight: "0.3", max_theme_weight: "0.3", max_daily_turnover: "0.5" };
const account = { id: "account", name: "模拟账户", state: "ACTIVE", initial_cash: "1000000", benchmark_code: "000300.SH",
  first_trade_date: "2026-10-15", next_trade_date: "2026-10-15", latest_trade_date: null, config_snapshot_json: { paper: { risk } } };
const proposal = { id: "proposal", account_id: "account", ts_code: "000001.SZ", action: "PROPOSE_BUY", target_weight: "0.08",
  stage: "RIGHT_SIDE_NEW", state: "PENDING_REVIEW", expires_at: "2026-10-15T01:30:00Z", data: {} };
const snapshot = { id: "snapshot", signal_date: "2026-10-14", data: { candidates: [{ ts_code: "000001.SZ",
  name: '<img src=x onerror="window.__xss=true">', opportunity_stage: "RIGHT_SIDE_NEW", opportunity_score: "82",
  industry_sector_id: 1, primary_theme_code: null, risk_codes: [], reason_codes: ["SYNTHETIC"] }] } };
const wrappers: ReturnType<typeof mount>[] = [];
beforeEach(() => {
  vi.resetAllMocks(); sessionStorage.clear();
  mocks.paperStatus.mockResolvedValue({ enabled: true, schema_ready: true, default_risk: risk,
    business_date: "2026-10-14", latest_raw_date: "2026-10-14" });
  mocks.paperAccounts.mockResolvedValue({ data: [account], meta: { total: 1 } });
  mocks.paperAccount.mockResolvedValue(account);
  mocks.paperPerformance.mockResolvedValue({ latest: null, continuous: true, series: [], cumulative_cost: "0",
    realized_pnl: "0", unrealized_pnl: "0", cumulative_return: null, maximum_drawdown: null,
    execution: { filled_orders: 0, reached_orders: 0, hypothetical_fill_rate: null, blocked_reasons: {}, stages: {} } });
  mocks.paperJobs.mockResolvedValue({ data: [], meta: { total: 0 } });
  mocks.paperPage.mockImplementation(async kind => ({ data: kind === "observations" ? [snapshot] : kind === "proposals" ? [proposal] : [], meta: { total: 1 } }));
  mocks.fetchResearchReports.mockResolvedValue({ data: [], meta: { total: 0 } });
  mocks.paperWrite.mockResolvedValue({ id: "approved" });
});
afterEach(() => { for (const wrapper of wrappers.splice(0)) wrapper.unmount(); });
async function open() { const wrapper = mount(DecisionPaperWorkbench, { props: { ownerId: "owner-a" } }); wrappers.push(wrapper); await flushPromises(); return wrapper; }
function button(wrapper: ReturnType<typeof mount>, text: string) { return wrapper.findAll("button").find(row => row.text() === text || row.attributes("aria-label") === text)!; }

it("load and approval modal are read-only until a separate manual confirmation", async () => {
  const wrapper = await open();
  expect(mocks.paperWrite).not.toHaveBeenCalled();
  expect(wrapper.findAll("img")).toHaveLength(0);
  await button(wrapper, "人工审批").trigger("click"); await flushPromises();
  expect(mocks.paperWrite).not.toHaveBeenCalled();
  expect(button(wrapper, "确认模拟委托").attributes("disabled")).toBeDefined();
  await wrapper.find('.paper-checkbox input').setValue(true);
  await wrapper.find('.paper-modal form').trigger("submit"); await flushPromises();
  expect(mocks.paperWrite).toHaveBeenCalledWith("/decisions/proposals/proposal/approve", expect.objectContaining({ confirmed: true, target_weight: "0.08" }));
});

it("double submit has one POST and failure retains the retry identity", async () => {
  const wrapper = await open(); await button(wrapper, "人工审批").trigger("click");
  await wrapper.find('.paper-checkbox input').setValue(true);
  let reject: (error: unknown) => void = () => {};
  mocks.paperWrite.mockReturnValueOnce(new Promise((_, fail) => { reject = fail; }));
  await wrapper.find('.paper-modal form').trigger("submit");
  await wrapper.find('.paper-modal form').trigger("submit");
  expect(mocks.paperWrite).toHaveBeenCalledTimes(1);
  const request = mocks.paperWrite.mock.calls[0][1].request_id;
  reject(new TypeError("network interrupted")); await flushPromises();
  expect(wrapper.text()).toContain("NETWORK_OR_REQUEST_FAILED");
  await wrapper.find('.paper-modal form').trigger("submit"); await flushPromises();
  expect(mocks.paperWrite.mock.calls[1][1].request_id).toBe(request);
});

it("feature disabled cannot approve", async () => {
  mocks.paperStatus.mockResolvedValue({ enabled: false, schema_ready: true, default_risk: risk, business_date: "2026-10-14" });
  const wrapper = await open();
  expect(wrapper.text()).toContain("历史记录只读");
  expect(button(wrapper, "人工审批").attributes("disabled")).toBeDefined();
  expect(mocks.paperWrite).not.toHaveBeenCalled();
});

it("paused account permits history but cannot approve or advance", async () => {
  mocks.paperAccount.mockResolvedValue({ ...account, state: "PAUSED" });
  const wrapper = await open();
  expect(button(wrapper, "人工审批").attributes("disabled")).toBeDefined();
  expect(button(wrapper, "结算下一交易日").attributes("disabled")).toBeDefined();
  expect(mocks.paperWrite).not.toHaveBeenCalled();
});

it("changing account removes old decision rows before asynchronous reads return", async () => {
  mocks.paperAccounts.mockResolvedValue({ data: [account, { ...account, id: "account-other", name: "另一个账户" }], meta: { total: 2 } });
  const wrapper = await open();
  await button(wrapper, "人工审批").trigger("click");
  mocks.paperAccount.mockReturnValueOnce(new Promise(() => {}));
  await wrapper.find('.paper-account-picker select').setValue("account-other");
  expect(wrapper.find('[role=dialog]').exists()).toBe(false);
  expect(wrapper.findAll('.paper-proposal')).toHaveLength(0);
  expect(mocks.paperWrite).not.toHaveBeenCalled();
});

it("unmigrated schema does not query nonexistent tables", async () => {
  mocks.paperStatus.mockResolvedValue({ enabled: false, schema_ready: false, default_risk: risk, business_date: "2026-10-14" });
  const wrapper = await open();
  expect(wrapper.text()).toContain("0053"); expect(mocks.paperAccounts).not.toHaveBeenCalled();
});

it("WATCH cannot approve, rejection requires a reason and creates no approval call", async () => {
  mocks.paperPage.mockImplementation(async kind => ({ data: kind === "observations" ? [snapshot] : [{ ...proposal, action: "WATCH", target_weight: "0" }], meta: { total: 1 } }));
  const wrapper = await open();
  expect(button(wrapper, "人工审批").attributes("disabled")).toBeDefined();
  await button(wrapper, "驳回").trigger("click");
  await wrapper.find('.paper-modal textarea').setValue("仅观察");
  await wrapper.find('.paper-modal form').trigger("submit"); await flushPromises();
  expect(mocks.paperWrite).toHaveBeenCalledWith("/decisions/proposals/proposal/reject", expect.objectContaining({ reason: "仅观察" }));
});

it("pagination and error recovery do not trigger trading POSTs", async () => {
  mocks.paperPage.mockImplementation(async kind => ({ data: kind === "observations" ? [snapshot] : [proposal], meta: { total: 24 } }));
  const wrapper = await open();
  await button(wrapper, "下一页").trigger("click"); await flushPromises();
  expect(mocks.paperPage).toHaveBeenCalledWith("proposals", "account", expect.objectContaining({ offset: 20 }), expect.anything());
  mocks.paperStatus.mockRejectedValueOnce(new ApiError("SOURCE_NOT_READY", 409));
  await button(wrapper, "刷新").trigger("click"); await flushPromises();
  expect(wrapper.text()).toContain("SOURCE_NOT_READY");
  await button(wrapper, "刷新").trigger("click"); await flushPromises();
  expect(mocks.paperWrite).not.toHaveBeenCalled();
});

it("job pagination retains account-wide active state and cancellation is explicit", async () => {
  const job = { id: "job", job_type: "PAPER_DAILY", status: "RUNNING", trade_date: "2026-10-15",
    started_at: "2026-10-15T10:00:00Z", finished_at: null, progress_pct: 40, step: "paper execution" };
  mocks.paperJobs.mockResolvedValue({ data: [job], meta: { total: 25, active_count: 1 } });
  const wrapper = await open();
  expect(button(wrapper, "结算下一交易日").attributes("disabled")).toBeDefined();
  expect(mocks.paperWrite).not.toHaveBeenCalled();
  await button(wrapper, "任务下一页").trigger("click"); await flushPromises();
  expect(mocks.paperJobs).toHaveBeenCalledWith("account", expect.anything(), 20);
  await button(wrapper, "取消任务").trigger("click"); await flushPromises();
  expect(mocks.paperWrite).toHaveBeenCalledWith("/paper/accounts/account/jobs/job/cancel",
    expect.objectContaining({ request_id: expect.any(String) }));
});
