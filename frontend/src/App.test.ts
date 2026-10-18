import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import App from "./App.vue";
import type { JobRun } from "./types";

vi.mock("echarts/core", () => ({
  use: vi.fn(),
  init: () => ({ setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn() })
}));

let wrapper: VueWrapper | undefined;
let currentJobs: JobRun[];
let jobRequest: (() => Promise<JobRun[]>) | undefined;
let coverageRequest: (() => Promise<unknown>) | undefined;
let requests: string[];
let cancellation: (() => Promise<unknown>) | undefined;
const count = (path: string) => requests.filter((url) => url.includes(path)).length;

function job(status = "RUNNING", stale = false): JobRun {
  return {
    id: "recalculation-1", job_type: "recalculate", target_trade_date: null,
    started_at: "2026-10-18T00:00:00Z", finished_at: null, status,
    step: "80 calculate trade status", row_count: 0, error_message: null,
    metadata: { stage: "trade_status", progress_pct: 4 },
    ...{ heartbeat_stale: stale }
  };
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-10-18T00:01:00Z"));
  requests = [];
  currentJobs = [job()];
  jobRequest = undefined;
  coverageRequest = undefined;
  cancellation = undefined;
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    requests.push(url);
    let data: unknown = [];
    if (url.endsWith("/cancel")) return cancellation ? await cancellation() : {
      ok: false, status: 409, json: async () => ({ detail: { code: "JOB_ALREADY_TERMINAL" } })
    };
    if (url.includes("/auth/me")) data = { username: "test-admin", must_change_password: false };
    else if (url.includes("/jobs?")) data = jobRequest ? await jobRequest() : currentJobs;
    else if (url.includes("/jobs/queue")) data = { running: [], queued: [] };
    else if (url.includes("/system/data-coverage")) data = coverageRequest ? await coverageRequest() : [];
    else if (url.includes("/dashboard/summary")) data = { sector_heat_top: [] };
    else if (url.includes("/system/status")) data = {};
    else if (url.includes("/system/runtime")) data = { services: {}, queued_count: 0, running_count: 1 };
    return { ok: true, status: 200, json: async () => ({ code: 0, data, meta: {} }) };
  }));
});

it("confirms cancellation, prevents duplicate posts, and waits for server CANCELLED", async () => {
  currentJobs = [{ ...job(), can_cancel: true }];
  vi.spyOn(window, "confirm").mockReturnValue(true);
  let resolve!: (value: unknown) => void;
  cancellation = () => new Promise((done) => { resolve = done; });
  await start();
  await wrapper!.findAll(".nav-button").find((button) => button.text().includes("覆盖、拉取"))!.trigger("click");
  const center = wrapper!.findComponent({ name: "JobCenter" });
  center.vm.$emit("cancel", currentJobs[0].id);
  center.vm.$emit("cancel", currentJobs[0].id);
  await flushPromises();
  expect(count("/cancel")).toBe(1);
  currentJobs = [{ ...job(), can_cancel: false, cancel_requested: true }];
  resolve({ ok: true, status: 200, json: async () => ({ code: 0, data: currentJobs[0], meta: {} }) });
  await flushPromises();
  expect(wrapper!.text()).toContain("已请求取消，等待当前安全点");
  expect(wrapper!.find(".job-current").text()).toContain("取消中");
  expect(currentJobs[0].status).toBe("RUNNING");
});

it("shows the real cancellation error without fabricating a terminal state", async () => {
  vi.spyOn(window, "confirm").mockReturnValue(true);
  await start();
  await wrapper!.findAll(".nav-button").find((button) => button.text().includes("覆盖、拉取"))!.trigger("click");
  wrapper!.findComponent({ name: "JobCenter" }).vm.$emit("cancel", currentJobs[0].id);
  await flushPromises();
  expect(wrapper!.text()).toContain("JOB_ALREADY_TERMINAL");
  expect(currentJobs[0].status).toBe("RUNNING");
});

it("refreshes coverage when an old active task exits outside recent history", async () => {
  await start();
  currentJobs = [];
  await vi.advanceTimersByTimeAsync(5_000);
  await flushPromises();
  expect(count("/system/data-coverage")).toBe(2);
});

it("shows unknown rather than no running tasks if the initial jobs query fails", async () => {
  jobRequest = async () => { throw new Error("SYNTHETIC_QUEUE_UNAVAILABLE"); };
  await start();
  const center = wrapper!.findComponent({ name: "JobCenter" });
  expect(center.text()).toContain("任务状态待确认");
  expect(center.text()).toContain("队列状态未知，请重试");
  expect(center.text()).not.toContain("无运行任务");
});

afterEach(() => {
  wrapper?.unmount();
  wrapper = undefined;
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

async function start() {
  wrapper = mount(App, { global: { stubs: [
    "DashboardView", "ResearchSummary", "DataQuality", "StockPool", "SectorHeatPanel",
    "ThemeHeatTable", "OpportunityTable", "ResearchLab", "BacktestAnalyticsView",
    "AgentResearchWorkbench", "AgentResearchReports", "DecisionPaperWorkbench"
  ] } });
  await flushPromises();
}

it("polls jobs without repeatedly scanning unchanged historical coverage", async () => {
  await start();
  await vi.advanceTimersByTimeAsync(65_000);
  await flushPromises();
  expect(count("/jobs?")).toBeGreaterThanOrEqual(10);
  expect(count("/system/data-coverage")).toBe(1);
  expect(count("/system/data-calendar")).toBe(1);
});

it("does not overlap slow job polls", async () => {
  await start();
  let resolve!: (rows: JobRun[]) => void;
  jobRequest = () => new Promise((done) => { resolve = done; });
  await vi.advanceTimersByTimeAsync(20_000);
  expect(count("/jobs?")).toBe(2);
  jobRequest = undefined;
  resolve(currentJobs);
  await flushPromises();
});

it("keeps observing a stale task without repeatedly refreshing coverage", async () => {
  currentJobs = [job("RUNNING", true)];
  await start();
  await vi.advanceTimersByTimeAsync(20_000);
  expect(count("/jobs?")).toBeGreaterThan(2);
  expect(count("/system/data-coverage")).toBe(1);
});

it.each(["SUCCESS", "FAILED", "CANCELLED", "PARTIAL"])(
  "refreshes coverage once when a task becomes %s", async (status) => {
    await start();
    currentJobs = [job(status)];
    await vi.advanceTimersByTimeAsync(20_000);
    await flushPromises();
    expect(count("/system/data-coverage")).toBe(2);
    expect(count("/system/data-calendar")).toBe(2);
  }
);

it("throttles advancing coverage to once per minute", async () => {
  await start();
  currentJobs = [{ ...job(), row_count: 10 }];
  await vi.advanceTimersByTimeAsync(55_000);
  expect(count("/system/data-coverage")).toBe(1);
  await vi.advanceTimersByTimeAsync(5_000);
  expect(count("/system/data-coverage")).toBe(2);
  currentJobs = [{ ...job(), row_count: 20 }];
  await vi.advanceTimersByTimeAsync(60_000);
  expect(count("/system/data-coverage")).toBe(3);
});

it("keeps polling jobs while a single coverage query is slow", async () => {
  let resolve!: (rows: unknown[]) => void;
  coverageRequest = () => new Promise((done) => { resolve = done; });
  await start();
  await vi.advanceTimersByTimeAsync(20_000);
  expect(count("/jobs?")).toBeGreaterThan(2);
  expect(count("/system/data-coverage")).toBe(1);
  coverageRequest = undefined;
  resolve([]);
  await flushPromises();
});

it("serializes the initial job query with subsequent polling", async () => {
  let resolve!: (rows: JobRun[]) => void;
  jobRequest = () => new Promise((done) => { resolve = done; });
  await start();
  await vi.advanceTimersByTimeAsync(20_000);
  expect(count("/jobs?")).toBe(1);
  jobRequest = undefined;
  resolve(currentJobs);
  await flushPromises();
  await vi.advanceTimersByTimeAsync(5_000);
  expect(count("/jobs?")).toBe(2);
});

it("retries failed initial coverage without flooding requests", async () => {
  coverageRequest = async () => { throw new Error("coverage unavailable"); };
  await start();
  coverageRequest = undefined;
  await vi.advanceTimersByTimeAsync(55_000);
  expect(count("/system/data-coverage")).toBe(1);
  await vi.advanceTimersByTimeAsync(5_000);
  expect(count("/system/data-coverage")).toBe(2);
});

it("does not lose a terminal refresh when an earlier statistics request is pending", async () => {
  await start();
  let resolve!: (rows: unknown[]) => void;
  coverageRequest = () => new Promise((done) => { resolve = done; });
  currentJobs = [{ ...job(), row_count: 10 }];
  await vi.advanceTimersByTimeAsync(60_000);
  currentJobs = [job("SUCCESS")];
  await vi.advanceTimersByTimeAsync(5_000);
  expect(count("/system/data-coverage")).toBe(2);
  coverageRequest = undefined;
  resolve([]);
  await flushPromises();
  await vi.advanceTimersByTimeAsync(5_000);
  expect(count("/system/data-coverage")).toBe(3);
});

it("ignores a late job response after unmount", async () => {
  await start();
  let resolve!: (rows: JobRun[]) => void;
  jobRequest = () => new Promise((done) => { resolve = done; });
  await vi.advanceTimersByTimeAsync(5_000);
  wrapper!.unmount();
  wrapper = undefined;
  resolve([job("SUCCESS")]);
  await flushPromises();
  await vi.advanceTimersByTimeAsync(60_000);
  expect(count("/system/data-coverage")).toBe(1);
  expect(count("/jobs?")).toBe(2);
});
