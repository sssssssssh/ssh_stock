import { mount } from "@vue/test-utils";
import { expect, it } from "vitest";

import JobCenter from "./JobCenter.vue";
import type { JobRun } from "../types";

const baseJob: JobRun = { id: "a", job_type: "backfill", status: "QUEUED",
  started_at: "2026-10-18T00:00:00Z", finished_at: null, target_trade_date: null,
  step: null, row_count: 0, error_message: null, metadata: {}, can_cancel: true };
function mountJobs(jobs: JobRun[], activeJob: JobRun | null = null) {
  return mount(JobCenter, { props: {
    collapsed: false, submittingBasicInfo: false, submittingIngestion: false,
    backfillStart: "2026-01-01", backfillEnd: "2026-01-31", activeJob, jobs,
    statusLabel: (status) => status, progressPct: () => 4, jobStepText: () => "步骤",
    metadataText: () => "日期", formatJobElapsed: () => "1小时", rowCountHint: () => "",
    jobTooltip: () => "任务", jobTypeText: () => "拉取"
  } });
}

it("shows in-flight batches separately from committed stage counts and publication", async () => {
  const active: JobRun = { ...baseJob, status: "RUNNING", job_type: "recalculate", metadata: {
    calculation_progress: { name: "stock_trade_status_daily", kind: "candidate",
      phase: "lookup_published", batch_index: 157, batch_count: 2880,
      completed_rows: 78000, total_rows: 1439327, elapsed_seconds: 7200,
      operation_started_at: "2026-10-19T03:00:00Z", updated_at: "2026-10-19T05:00:00Z",
      recent_events: [{ name: "stock_trade_status_daily", phase: "batch_complete",
        batch_index: 156, completed_rows: 78000, updated_at: "2026-10-19T05:00:00Z" }] }
  } };
  const wrapper = mountJobs([active], active);
  const detail = wrapper.get('[aria-label="阶段内进度"]');
  expect(detail.text()).toContain("157 / 2,880");
  expect(detail.text()).toContain("78,000 / 1,439,327 行");
  expect(detail.text()).toContain("核对已发布结果");
  expect(detail.text()).toContain("尚未发布");
  expect(detail.text()).toContain("当前操作尚未返回");
  expect(wrapper.text()).toContain("已写入/处理行数：0");
  expect(wrapper.text()).not.toContain("已发布 78,000");
  await detail.get("summary").trigger("click");
  expect(detail.get("ol").text()).toContain("第 156 批");
  wrapper.unmount();
});

it("does not invent a batch total for input reads or add empty diagnostics to legacy jobs", () => {
  const legacy = { ...baseJob, status: "RUNNING", job_type: "recalculate" };
  const empty = mountJobs([legacy], legacy);
  expect(empty.find('[aria-label="阶段内进度"]').exists()).toBe(false);
  expect(empty.text()).toContain("当前执行尚未上报阶段内明细");
  empty.unmount();
  const active = { ...legacy, metadata: { calculation_progress: {
    name: "trade_status.stock_daily", kind: "read", phase: "fetch", batch_index: 12,
    batch_count: null, total_rows: null, completed_rows: 60000, elapsed_seconds: 30,
    operation_started_at: "2026-10-19T03:00:00Z", recent_events: []
  } } };
  const wrapper = mountJobs([active], active);
  const text = wrapper.get('[aria-label="阶段内进度"]').text();
  expect(text).toContain("12 / --");
  expect(text).toContain("60,000 行");
  expect(text).not.toContain("NaN");
  expect(text).not.toContain("undefined");
  expect(text).not.toContain("100.0%");
  wrapper.unmount();
});

it("keeps historical batch details collapsed so recent task rows stay compact", async () => {
  const job = { ...baseJob, status: "FAILED", metadata: { calculation_progress: {
    name: "stock_trade_status_daily", kind: "candidate", phase: "failed",
    batch_index: 157, batch_count: 2880, completed_rows: 78000, total_rows: 1439327,
    elapsed_seconds: 7200, operation_elapsed_seconds: 120, recent_events: []
  } } };
  const wrapper = mountJobs([job]);
  const history = wrapper.get(".job-history-progress");
  expect(history.attributes("open")).toBeUndefined();
  expect(history.get("summary").text()).toBe("阶段内明细");
  expect(history.get('[aria-label="阶段内进度"]').text()).toContain("78,000");
  wrapper.unmount();
});

it.each([
  ["PREPARING", "RUNNING", false, "候选计算中，尚未发布"],
  ["PREPARING", "SUCCESS", true, "等待父任务整体发布"],
  ["ABORTED", "CANCELLED", false, "本次候选未替换已发布结果"],
  ["PUBLISHED", "SUCCESS", false, "已发布 · 2026-10-18T01:00:00Z · published-identity"],
  ["NO_CHANGES", "SUCCESS", false, "本次无派生结果发布"]
])("shows truthful %s publication independently of processed row count", (state, status, parentOwned, expected) => {
  const job = { ...baseJob, status, row_count: 9999, publication: {
    state, identity: "published-identity", parent_owned: parentOwned,
    published_at: "2026-10-18T01:00:00Z"
  } };
  const wrapper = mountJobs([job], status === "RUNNING" ? job : null);
  expect(wrapper.text()).toContain(expected);
  expect(wrapper.text()).not.toContain("已对外发布 9999");
  wrapper.unmount();
});

it("sorts all queued jobs oldest first and emits cancellation without network calls", async () => {
  const wrapper = mountJobs([{ ...baseJob, id: "b", started_at: "2026-10-18T00:01:00Z" }, baseJob]);
  const entries = wrapper.findAll(".queue-entry");
  expect(entries).toHaveLength(2);
  expect(entries[0].text()).toContain("#1");
  await entries[0].get("button").trigger("click");
  expect(wrapper.emitted("cancel")).toEqual([["a"]]);
  await wrapper.setProps({ cancellingJobs: ["a"] });
  expect(wrapper.findAll(".queue-entry")[0].get("button").attributes("disabled")).toBeDefined();
  wrapper.unmount();
});

it("keeps requesting cancellation RUNNING until the server reports terminal", () => {
  const active = { ...baseJob, status: "RUNNING", cancel_requested: true,
    progress_stalled: true, cancel_delayed: true };
  const wrapper = mountJobs([active], active);
  expect(wrapper.get(".job-current").text()).toContain("取消中 · 等待安全点");
  expect(wrapper.get(".job-current").text()).toContain("疑似卡住");
  expect(wrapper.get(".job-current").text()).toContain("取消耗时较长");
  expect(wrapper.get(".job-current button").attributes("disabled")).toBeDefined();
  expect(active.status).toBe("RUNNING");
  wrapper.unmount();
});

it.each(["SUCCESS", "PARTIAL", "FAILED", "CANCELLED", "BLOCKED"])("never offers cancel for %s", (status) => {
  const wrapper = mountJobs([{ ...baseJob, status }]);
  expect(wrapper.findAll(".job-row button")).toHaveLength(0);
  expect(wrapper.get(".job-status").text()).toBe(status);
  wrapper.unmount();
});

it("never treats an unavailable queue as an empty or stopped queue", async () => {
  const wrapper = mountJobs([]);
  await wrapper.setProps({ loading: true });
  expect(wrapper.text()).toContain("任务状态待加载");
  expect(wrapper.text()).not.toContain("无运行任务");
  await wrapper.setProps({ loading: false, loadError: "HTTP 503" });
  expect(wrapper.get('[role="alert"]').text()).toContain("HTTP 503");
  expect(wrapper.text()).toContain("队列状态未知，请重试");
  expect(wrapper.text()).not.toContain("无运行任务");
  wrapper.unmount();
});

it("keeps an unconfirmed executor blocked and never offers an effective cancel", () => {
  const active = { ...baseJob, status: "RUNNING", execution_unconfirmed: true };
  const wrapper = mountJobs([active], active);
  expect(wrapper.get(".job-current-head").text()).toContain("执行结果待确认");
  expect(wrapper.get(".job-current button").attributes("disabled")).toBeDefined();
  expect(wrapper.get('.job-error[role="status"]').text()).toContain("无法证明旧 SQL 已停止");
  wrapper.unmount();
});

it("shows stale execution explicitly without changing persisted status or controls", async () => {
  const job: JobRun = {
    id: "stale-job", job_type: "recalculate", target_trade_date: null,
    started_at: "2026-10-18T00:00:00Z", finished_at: null, status: "RUNNING",
    heartbeat_stale: true, step: "80 calculate trade status", row_count: 0,
    error_message: null, metadata: {}
  };
  const wrapper = mount(JobCenter, { props: {
    collapsed: false, submittingBasicInfo: false, submittingIngestion: false,
    backfillStart: "2026-01-01", backfillEnd: "2026-01-31", activeJob: job, jobs: [job],
    statusLabel: () => "运行中", progressPct: () => 4, jobStepText: () => "计算交易状态",
    metadataText: () => "2026-01", formatJobElapsed: () => "1小时", rowCountHint: () => "",
    jobTooltip: () => "任务", jobTypeText: () => "补算"
  } });
  expect(wrapper.get(".job-current-head").text()).toContain("心跳超时，状态待确认");
  expect(wrapper.get(".job-current").classes()).toContain("running");
  expect(wrapper.get('[role="status"]').text()).toContain("不会自动续算");
  expect(job.status).toBe("RUNNING");
  await wrapper.get(".secondary-button").trigger("click");
  expect(wrapper.emitted("syncBasic")).toHaveLength(1);
  await wrapper.setProps({ activeJob: { ...job, heartbeat_stale: false }, jobs: [] });
  expect(wrapper.get(".job-current-head").text()).toContain("运行中");
  expect(wrapper.find('[role="status"]').exists()).toBe(false);
  wrapper.unmount();
});
