<script setup lang="ts">
import type { JobRun } from "../types";
import { computed } from "vue";
import CalculationProgress from "./CalculationProgress.vue";

const props = defineProps<{
  collapsed: boolean;
  submittingBasicInfo: boolean;
  submittingIngestion: boolean;
  backfillStart: string;
  backfillEnd: string;
  activeJob: JobRun | null | undefined;
  jobs: JobRun[];
  cancellingJobs?: string[];
  loading?: boolean;
  loadError?: string;
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
  cancel: [jobId: string];
  "update:backfillStart": [value: string];
  "update:backfillEnd": [value: string];
}>();

const dataTypes = new Set(["daily", "backfill", "recalculate", "sync_basic", "validate_data", "catchup"]);
const queued = computed(() => props.jobs.filter((job) => job.status === "QUEUED" &&
  dataTypes.has(job.job_type) && !job.parent_job_id).sort((a, b) =>
  (a.started_at || "").localeCompare(b.started_at || "") || a.id.localeCompare(b.id)));
const history = computed(() => props.jobs.filter((job) => !queued.value.includes(job) &&
  job.id !== props.activeJob?.id));
function canCancel(job: JobRun) {
  if (job.execution_unconfirmed) return false;
  if (!["QUEUED", "RUNNING"].includes(job.status)) return false;
  return !job.cancel_requested && !props.cancellingJobs?.includes(job.id) &&
    (job.can_cancel ?? (job.status === "QUEUED" || job.status === "RUNNING" &&
      ["backfill", "recalculate", "RESEARCH_EVAL", "portfolio_backtest"].includes(job.job_type)));
}

function label(job: JobRun) {
  if (job.status === "RUNNING" && job.execution_unconfirmed) return "执行结果待确认";
  if (job.status === "RUNNING" && job.cancel_requested) return "取消中 · 等待安全点";
  return job.heartbeat_stale ? "心跳超时，状态待确认" : props.statusLabel(job.status);
}

function publicationText(job: JobRun) {
  const raw = job.publication || job.metadata.publication;
  if (!raw || typeof raw !== "object") return "";
  const publication = raw as Record<string, unknown>;
  if (publication.state === "PUBLISHED") return `已发布 · ${publication.published_at || "--"} · ${publication.identity}`;
  if (publication.state === "ABORTED") return "未发布：本次候选未替换已发布结果";
  if (publication.state === "NO_CHANGES") return "本次无派生结果发布";
  if (publication.parent_owned && job.status === "SUCCESS") return "候选已完成，等待父任务整体发布";
  return "候选计算中，尚未发布";
}

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
      <p v-if="loading" role="status">任务状态读取中</p>
      <p v-if="loadError" class="job-error" role="alert">任务状态查询失败：{{ loadError }}；已有内容仅为上次成功查询结果。</p>
      <section class="job-current" :class="activeJob?.status.toLowerCase() || 'idle'">
        <div class="job-current-head">
          <span>当前执行</span><strong>{{ loading ? "任务状态待加载" : activeJob ? label(activeJob) : loadError ? "任务状态待确认" : "无运行任务" }}</strong>
        </div>
        <template v-if="activeJob">
          <p v-if="activeJob.execution_unconfirmed" class="job-error" role="status">执行身份或数据库结果无法确认，无法证明旧 SQL 已停止；执行槽位保持阻塞，需人工确认执行者与写事务停止后对账。不会把取消请求伪报为已停止。</p>
          <p v-if="activeJob.heartbeat_stale" class="job-error" role="status">任务心跳已超时，Worker 可能已退出；当前进度不代表仍在执行。执行槽位保持阻塞，须确认旧执行者已停止后人工对账，不会自动续算。</p>
          <p v-if="activeJob.progress_stalled" class="job-error">业务进度长时间未变化，疑似卡住；心跳正常不代表计算仍有进展。</p>
          <p v-if="activeJob.cancel_requested" role="status">已请求取消，等待当前安全点</p>
          <p v-if="activeJob.cancel_delayed" class="job-error">取消耗时较长，当前调用尚未安全退出，不会放行下一数据任务。</p>
          <div class="job-progress-track"><i :style="{ width: `${progressPct(activeJob)}%` }"></i></div>
          <div class="job-progress-meta">
            <span>{{ progressPct(activeJob).toFixed(1) }}%</span>
            <span :title="activeJob.step || '--'">{{ jobStepText(activeJob) }}</span>
          </div>
          <p>{{ metadataText(activeJob) }}</p>
          <div class="job-time-row"><span>已耗时</span><strong>{{ formatJobElapsed(activeJob) }}</strong></div>
          <p>Worker：{{ activeJob.worker_id || "--" }}</p>
          <p>最近心跳：{{ activeJob.heartbeat_at || "--" }}</p>
          <p>最近进度：{{ activeJob.last_progress_at || "--" }}</p>
          <CalculationProgress :value="activeJob.metadata.calculation_progress" :running="activeJob.status === 'RUNNING'" />
          <p v-if="activeJob.job_type === 'recalculate' && !activeJob.metadata.calculation_progress">当前执行尚未上报阶段内明细。</p>
          <p v-if="activeJob.metadata.last_completed_end">最近确认完成：{{ activeJob.metadata.last_completed_stage }} / {{ activeJob.metadata.last_completed_start }} ~ {{ activeJob.metadata.last_completed_end }}</p>
          <p v-if="publicationText(activeJob)" class="job-publication" role="status">{{ publicationText(activeJob) }}</p>
          <button v-if="activeJob.can_cancel || canCancel(activeJob) || activeJob.cancel_requested" class="secondary-button" type="button"
            :disabled="!canCancel(activeJob)" @click="$emit('cancel', activeJob.id)">
            {{ activeJob.cancel_requested ? "取消中" : cancellingJobs?.includes(activeJob.id) ? "提交中" : "请求取消" }}
          </button>
          <p v-if="activeJob.error_message" class="job-error">{{ activeJob.error_message }}</p>
          <small>
            已写入/处理行数：{{ activeJob.row_count }}
            <template v-if="rowCountHint(activeJob)"> / {{ rowCountHint(activeJob) }}</template>
          </small>
          <p><small>处理行数不代表发布行数。计算检查点保存在候选区；整体发布前仍读取旧成功结果。</small></p>
        </template>
        <p v-else>最近状态会每 5 秒自动刷新</p>
      </section>
      <section class="job-list">
        <div class="job-list-head"><span>等待队列</span><strong>{{ queued.length }} 条</strong></div>
        <div v-for="(job, index) in queued" :key="job.id" class="queue-entry" :title="jobTooltip(job)">
          <div><strong>#{{ job.queue_position || index + 1 }} {{ jobTypeText(job.job_type) }}</strong>
            <span>排队中 · 等待 {{ formatJobElapsed(job) }}</span></div>
          <p>{{ metadataText(job) }}</p>
          <small>提交时间：{{ job.started_at }}</small>
          <p v-if="job.depends_on_job_id">前置任务：{{ job.depends_on_job_id }} / {{ job.dependency_status || "等待确认" }}</p>
          <button class="secondary-button" type="button" :disabled="!canCancel(job)" @click="$emit('cancel', job.id)">
            {{ cancellingJobs?.includes(job.id) ? "提交中" : "取消排队" }}
          </button>
        </div>
        <div v-if="!queued.length" class="empty-block compact-empty">{{ loading ? "正在读取等待队列" : loadError ? "队列状态未知，请重试" : "暂无等待任务" }}</div>
        <div class="job-list-head"><span>最近任务与其他通道</span><strong>{{ history.length }} 条</strong></div>
        <div
          v-for="job in history"
          :key="job.id"
          class="job-row"
          :class="{ 'has-error': Boolean(job.error_message) }"
          :title="jobTooltip(job)"
        >
          <span class="job-type" :title="job.job_type">{{ jobTypeText(job.job_type) }}</span>
          <span class="job-status" :class="job.status.toLowerCase()" :title="job.heartbeat_stale ? '心跳超时，状态待确认' : statusLabel(job.status)">
            {{ label(job) }}
          </span>
          <span class="job-step" :title="job.step || '--'">{{ jobStepText(job) }}</span>
          <span class="job-date" :title="metadataText(job)">{{ metadataText(job) }}</span>
          <span class="job-duration" :title="formatJobElapsed(job)">{{ formatJobElapsed(job) }}</span>
          <button v-if="canCancel(job)" class="secondary-button" type="button" @click="$emit('cancel', job.id)">请求取消</button>
          <span v-if="job.error_message" class="job-error-line" :title="job.error_message">{{ job.error_message }}</span>
          <span v-if="job.metadata.last_completed_end" class="job-completed-line">最近确认完成：{{ job.metadata.last_completed_start }} ~ {{ job.metadata.last_completed_end }}</span>
          <span v-if="publicationText(job)" class="job-completed-line job-publication">{{ publicationText(job) }}</span>
          <details v-if="job.metadata.calculation_progress" class="job-completed-line job-history-progress">
            <summary>阶段内明细</summary>
            <CalculationProgress :value="job.metadata.calculation_progress" :running="job.status === 'RUNNING'" />
          </details>
        </div>
        <div v-if="!history.length" class="empty-block compact-empty">暂无任务记录</div>
      </section>
    </div>
  </article>
</template>

<style scoped>
.queue-entry { padding: 12px; border-bottom: 1px solid var(--border-color, #dce3ec); overflow-wrap: anywhere; }
.queue-entry > div { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px; }
.queue-entry p, .job-current p { overflow-wrap: anywhere; }
.queue-entry button { margin-top: 8px; }
.job-current-head { flex-wrap: wrap; }
.job-completed-line { grid-column: 1 / -1; font-size: 12px; overflow-wrap: anywhere; }
.job-status-grid > p { grid-column: 1 / -1; margin: 0; }
.job-history-progress > summary { cursor: pointer; padding-top: 8px; }
</style>
