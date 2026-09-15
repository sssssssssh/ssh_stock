<script setup lang="ts">
import type { JobRun } from "../types";

defineProps<{
  collapsed: boolean;
  submittingBasicInfo: boolean;
  submittingIngestion: boolean;
  backfillStart: string;
  backfillEnd: string;
  activeJob: JobRun | null | undefined;
  jobs: JobRun[];
  statusLabel: (status: string) => string;
  progressPct: (job: JobRun) => number;
  jobStepText: (job: JobRun) => string;
  metadataText: (job: JobRun) => string;
  formatJobElapsed: (job: JobRun) => string;
  rowCountHint: (job: JobRun) => string;
  jobTooltip: (job: JobRun) => string;
  jobTypeText: (type: string) => string;
}>();

const emit = defineEmits<{
  toggle: [];
  syncBasic: [];
  submitBackfill: [];
  "update:backfillStart": [value: string];
  "update:backfillEnd": [value: string];
}>();

function updateStart(event: Event) {
  emit("update:backfillStart", (event.target as HTMLInputElement).value);
}

function updateEnd(event: Event) {
  emit("update:backfillEnd", (event.target as HTMLInputElement).value);
}
</script>

<template>
  <article class="panel" :class="{ collapsed }">
    <div class="panel-title coverage-title">
      <div>
        <h2>
          <button class="panel-title-button" type="button" :aria-expanded="!collapsed" @click="$emit('toggle')">
            <span class="collapse-icon" aria-hidden="true"></span><span>拉取数据与任务</span>
          </button>
        </h2>
        <span>先同步基础信息，再按日期拉取原始行情；计算请用上方补算入口</span>
      </div>
      <div class="coverage-actions-group">
        <button class="secondary-button" type="button" :disabled="submittingBasicInfo" @click="$emit('syncBasic')">
          {{ submittingBasicInfo ? "提交中" : "同步基础信息" }}
        </button>
        <form class="coverage-actions" @submit.prevent="$emit('submitBackfill')">
          <label><span>开始</span><input :value="backfillStart" type="date" @input="updateStart" /></label>
          <label><span>结束</span><input :value="backfillEnd" type="date" @input="updateEnd" /></label>
          <button class="primary-button" type="submit" :disabled="submittingIngestion">
            {{ submittingIngestion ? "提交中" : "拉取原始数据" }}
          </button>
        </form>
      </div>
    </div>
    <div v-show="!collapsed" class="job-status-grid panel-collapsible">
      <section class="job-current" :class="activeJob?.status.toLowerCase() || 'idle'">
        <div class="job-current-head">
          <span>当前任务</span><strong>{{ activeJob ? statusLabel(activeJob.status) : "无运行任务" }}</strong>
        </div>
        <template v-if="activeJob">
          <div class="job-progress-track"><i :style="{ width: `${progressPct(activeJob)}%` }"></i></div>
          <div class="job-progress-meta">
            <span>{{ progressPct(activeJob).toFixed(1) }}%</span>
            <span :title="activeJob.step || '--'">{{ jobStepText(activeJob) }}</span>
          </div>
          <p>{{ metadataText(activeJob) }}</p>
          <div class="job-time-row"><span>已耗时</span><strong>{{ formatJobElapsed(activeJob) }}</strong></div>
          <p v-if="activeJob.error_message" class="job-error">{{ activeJob.error_message }}</p>
          <small>
            已写入/处理行数：{{ activeJob.row_count }}
            <template v-if="rowCountHint(activeJob)"> / {{ rowCountHint(activeJob) }}</template>
          </small>
        </template>
        <p v-else>最近状态会每 5 秒自动刷新</p>
      </section>
      <section class="job-list">
        <div class="job-list-head"><span>最近任务</span><strong>{{ jobs.length }} 条</strong></div>
        <div
          v-for="job in jobs"
          :key="job.id"
          class="job-row"
          :class="{ 'has-error': Boolean(job.error_message) }"
          :title="jobTooltip(job)"
        >
          <span class="job-type" :title="job.job_type">{{ jobTypeText(job.job_type) }}</span>
          <span class="job-status" :class="job.status.toLowerCase()" :title="statusLabel(job.status)">
            {{ statusLabel(job.status) }}
          </span>
          <span class="job-step" :title="job.step || '--'">{{ jobStepText(job) }}</span>
          <span class="job-date" :title="metadataText(job)">{{ metadataText(job) }}</span>
          <span class="job-duration" :title="formatJobElapsed(job)">{{ formatJobElapsed(job) }}</span>
          <span v-if="job.error_message" class="job-error-line" :title="job.error_message">{{ job.error_message }}</span>
        </div>
        <div v-if="!jobs.length" class="empty-block compact-empty">暂无任务记录</div>
      </section>
    </div>
  </article>
</template>
