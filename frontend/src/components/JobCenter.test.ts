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
