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
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    requests.push(url);
    let data: unknown = [];
    if (url.includes("/auth/me")) data = { username: "test-admin", must_change_password: false };
    else if (url.includes("/jobs?")) data = jobRequest ? await jobRequest() : currentJobs;
    else if (url.includes("/system/data-coverage")) data = coverageRequest ? await coverageRequest() : [];
    else if (url.includes("/dashboard/summary")) data = { sector_heat_top: [] };
    else if (url.includes("/system/status")) data = {};
    else if (url.includes("/system/runtime")) data = { services: {}, queued_count: 0, running_count: 1 };
    return { ok: true, status: 200, json: async () => ({ code: 0, data, meta: {} }) };
  }));
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
