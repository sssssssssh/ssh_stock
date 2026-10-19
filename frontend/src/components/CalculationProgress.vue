<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";

const props = defineProps<{ value: unknown; running: boolean }>();
const now = ref(Date.now());
let timer: ReturnType<typeof setInterval> | undefined;
onMounted(() => { timer = setInterval(() => { now.value = Date.now(); }, 1000); });
onUnmounted(() => { if (timer) clearInterval(timer); });

type Detail = Record<string, unknown>;
const detail = computed<Detail | null>(() => {
  const v = props.value;
  return v && typeof v === "object" && !Array.isArray(v) ? v as Detail : null;
});
const phases: Record<string, string> = {
  started: "准备开始", query: "查询输入", fetch: "分批读取", frame: "整理输入数据",
  compute: "执行计算", prepare: "整理待写入结果", lookup_candidate: "查询已有候选",
  lookup_published: "核对已发布结果", store: "写入候选区", batch_complete: "本批暂存完成",
  complete: "本步骤完成", failed: "本步骤异常",
};
const kinds: Record<string, string> = {
  read: "读取输入", compute: "计算", reconcile: "核对结果范围", candidate: "暂存候选", validate: "校验", publish: "整体发布事务",
};
const tables: Record<string, string> = {
  stock_trade_status_daily: "交易状态", stock_daily: "个股行情", stock_basic: "股票基础信息",
  stock_limit_daily: "涨跌停", stock_suspend_daily: "停复牌", stock_st_daily: "ST状态",
  stock_factor_daily: "个股因子", market_daily: "市场", sector_factor_daily: "行业",
  theme_factor_daily: "题材", stock_state_daily: "趋势状态", stock_opportunity_daily: "机会池",
  strategy_signal: "策略信号", data_quality_daily: "数据质量", signal_forward_eval: "信号评价",
  trade_status: "交易状态", factors: "个股因子", market: "市场", sector: "行业",
  theme: "题材", trend: "趋势", opportunity: "机会池",
  "publication.verify": "候选发布校验", "publication.count": "发布范围统计",
  "publication.tables": "派生结果", "recalculation.raw_prerequisites": "原始数据预检",
  "recalculation.cross_table_quality": "跨表质量校验", "recalculation.signal_eval": "信号后验",
};
function label(value: unknown, mapping: Record<string, string>) {
  return typeof value === "string" ? mapping[value] || value : "--";
}
function name(value: unknown) {
  if (typeof value !== "string") return "--";
  return tables[value] || tables[value.split(".")[1]] || tables[value.split(".")[0]] || value;
}
function number(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value.toLocaleString("zh-CN") : "--";
}
function duration(seconds: number) {
  if (!Number.isFinite(seconds)) return "--";
  const n = Math.max(0, Math.floor(seconds));
  return n >= 3600 ? `${Math.floor(n / 3600)}小时${Math.floor(n % 3600 / 60)}分${n % 60}秒`
    : n >= 60 ? `${Math.floor(n / 60)}分${n % 60}秒` : `${n}秒`;
}
const operationElapsed = computed(() => {
  if (!detail.value) return "--";
  if (!props.running || ['complete', 'batch_complete', 'failed'].includes(String(detail.value.phase))) {
    return duration(Number(detail.value.operation_elapsed_seconds));
  }
  return duration((now.value - Date.parse(String(detail.value.operation_started_at))) / 1000);
});
const stepElapsed = computed(() => {
  if (!detail.value) return "--";
  const started = Date.parse(String(detail.value.started_at));
  const active = props.running && !['complete', 'failed'].includes(String(detail.value.phase));
  return duration(active && Number.isFinite(started) ? (now.value - started) / 1000
    : Number(detail.value.elapsed_seconds));
});
const events = computed(() => {
  const value = detail.value?.recent_events;
  return Array.isArray(value) ? value.filter((v): v is Detail => !!v && typeof v === "object").slice(-12).reverse() : [];
});
const fraction = computed(() => {
  const d = detail.value;
  if (!d || typeof d.total_rows !== "number" || d.total_rows <= 0 || typeof d.completed_rows !== "number") return null;
  return Math.min(100, Math.max(0, d.completed_rows / d.total_rows * 100));
});
</script>

<template>
  <section v-if="detail" class="calculation-detail" aria-label="阶段内进度">
    <div class="detail-heading"><strong>{{ name(detail.name) }} · {{ label(detail.kind, kinds) }}</strong>
      <span>{{ label(detail.phase, phases) }}</span></div>
    <dl>
      <div v-if="detail.batch_count !== null || detail.batch_index"><dt>当前批次</dt>
        <dd>{{ number(detail.batch_index) }} / {{ number(detail.batch_count) }}</dd></div>
      <div><dt>{{ detail.kind === "read" ? "本步骤已读取" : detail.kind === "candidate" ? "本步骤已暂存" : detail.kind === "publish" ? "发布事务已处理" : "本步骤已处理" }}</dt>
        <dd>{{ number(detail.completed_rows) }}<template v-if="detail.total_rows !== null"> / {{ number(detail.total_rows) }}</template> 行</dd></div>
      <div><dt>{{ running ? "当前操作持续" : "最后操作耗时" }}</dt><dd>{{ operationElapsed }}</dd></div>
      <div><dt>本步骤累计耗时</dt><dd>{{ stepElapsed }}</dd></div>
    </dl>
    <div v-if="fraction !== null" class="detail-fraction">本步骤 {{ fraction.toFixed(1) }}%</div>
    <p v-if="detail.kind === 'candidate'" class="candidate-note">候选暂存计数，尚未发布；当前事务回滚时可能撤销。</p>
    <p v-if="detail.kind === 'publish' && running">发布事务尚未提交，正式结果以最终发布状态为准。</p>
    <p v-if="running && !['complete', 'batch_complete', 'failed'].includes(String(detail.phase))">当前操作尚未返回；以上行数为已完成部分。</p>
    <details v-if="events.length"><summary>最近处理记录（{{ events.length }} 条）</summary>
      <ol><li v-for="(event, index) in events" :key="index">
        <time>{{ new Date(String(event.updated_at)).toLocaleTimeString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) }}</time>
        <span>{{ name(event.name) }} · {{ label(event.phase, phases) }}</span>
        <span v-if="event.batch_index">第 {{ number(event.batch_index) }} 批</span>
        <span>{{ number(event.completed_rows) }} 行</span>
      </li></ol>
    </details>
  </section>
</template>

<style scoped>
.calculation-detail { margin: 12px 0; padding: 12px 0; border-block: 1px solid var(--space-border, #dbe3ed); min-width: 0; }
.detail-heading { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; font-size: 13px; overflow-wrap: anywhere; }
dl { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px 16px; margin: 12px 0; }
dl > div { min-width: 0; }
dt { font-size: 12px; color: #667085; }
dd { margin: 4px 0 0; font-size: 13px; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
.detail-fraction { font-size: 12px; }
.calculation-detail p, summary { font-size: 12px; line-height: 1.5; overflow-wrap: anywhere; }
summary { cursor: pointer; padding: 8px 0; }
ol { list-style: none; padding: 0; margin: 0; max-height: 240px; overflow: auto; }
li { display: flex; flex-wrap: wrap; gap: 4px 10px; padding: 6px 0; border-bottom: 1px solid var(--space-border, #dbe3ed); font-size: 12px; overflow-wrap: anywhere; }
@media (max-width: 600px) { dl { grid-template-columns: minmax(0, 1fr); } }
</style>
