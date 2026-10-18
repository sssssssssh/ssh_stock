import { mount } from "@vue/test-utils";
import { expect, it } from "vitest";

import JobCenter from "./JobCenter.vue";
import type { JobRun } from "../types";

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
  expect(wrapper.get(".job-status").text()).toContain("心跳超时");
  expect(wrapper.get('[role="status"]').text()).toContain("不会自动续算");
  expect(job.status).toBe("RUNNING");
  await wrapper.get(".secondary-button").trigger("click");
  expect(wrapper.emitted("syncBasic")).toHaveLength(1);
  await wrapper.setProps({ activeJob: { ...job, heartbeat_stale: false }, jobs: [] });
  expect(wrapper.get(".job-current-head").text()).toContain("运行中");
  expect(wrapper.find('[role="status"]').exists()).toBe(false);
  wrapper.unmount();
});
