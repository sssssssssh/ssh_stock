<script setup lang="ts">
import { BarChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { init, use, type EChartsType } from "echarts/core";
import { SVGRenderer } from "echarts/renderers";
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { ReportChart, ReportSnapshot } from "../services/agentReports";
import { snapshotBarData } from "../services/reportSnapshotChart";

const props = defineProps<{ chart: ReportChart; snapshot: ReportSnapshot }>();
const element = ref<HTMLDivElement | null>(null);
const failure = ref("");
const data = computed(() => snapshotBarData(props.chart, props.snapshot));
let instance: EChartsType | null = null;
let observer: ResizeObserver | null = null;
let alive = true;
use([BarChart, GridComponent, TooltipComponent, SVGRenderer]);

function resize() { instance?.resize(); }
async function render() {
  await nextTick();
  if (!alive) return;
  instance?.dispose();
  instance = null;
  failure.value = "";
  if (data.value.warning || !data.value.values.length || !element.value) return;
  try {
    instance = init(element.value, undefined, { renderer: "svg" });
    instance.setOption({
      animation: false,
      tooltip: { trigger: "axis", renderMode: "richText", formatter: (params: unknown) => {
        const point = (Array.isArray(params) ? params[0] : params) as { dataIndex?: number };
        const index = point?.dataIndex;
        return typeof index === "number"
          ? `${data.value.labels[index]}\n${data.value.raw[index]} ${props.chart.unit}` : "";
      } },
      grid: { left: 60, right: 20, top: 24, bottom: 60, containLabel: true },
      xAxis: { type: "category", data: data.value.labels, axisLabel: { rotate: 25 } },
      yAxis: { type: "value", name: props.chart.unit },
      series: [{ type: "bar", name: props.chart.metric_id, data: data.value.values,
        itemStyle: { color: "#64748b" } }]
    });
  } catch {
    instance?.dispose();
    instance = null;
    failure.value = "CHART_RENDER_FAILED";
  }
}
onMounted(() => {
  window.addEventListener("resize", resize);
  if (typeof ResizeObserver !== "undefined" && element.value) {
    observer = new ResizeObserver(resize);
    observer.observe(element.value);
  }
  void render();
});
watch(() => [props.chart, props.snapshot], render, { deep: true });
onBeforeUnmount(() => {
  alive = false;
  observer?.disconnect();
  window.removeEventListener("resize", resize);
  instance?.dispose();
});
</script>

<template>
  <section class="snapshot-chart">
    <strong>{{ chart.title }}</strong>
    <p v-if="data.warning || failure" role="status">{{ data.warning || failure }} · 仅展示冻结事实表</p>
    <div ref="element" v-show="data.values.length && !failure" class="bar-chart" role="img"
      :aria-label="`${chart.title}，单位 ${chart.unit}`"></div>
    <div class="table-scroll" tabindex="0" :aria-label="`${chart.title} 冻结数值`">
      <table><caption>冻结数值 · {{ chart.unit }}</caption><thead><tr><th v-for="column in chart.columns" :key="column">{{ column }}</th></tr></thead>
        <tbody><tr v-for="(row, index) in chart.rows" :key="index"><td v-for="(cell, cellIndex) in row" :key="cellIndex">{{ cell }}</td></tr></tbody></table>
    </div>
  </section>
</template>

<style scoped>
.snapshot-chart { margin-top: 10px; min-width: 0; }
.bar-chart { width: 100%; height: 300px; min-width: 0; }
.table-scroll { overflow-x: auto; max-width: 100%; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th, td { border-bottom: 1px solid #e2e8f0; padding: 7px; text-align: left; }
caption { text-align: left; color: #64748b; padding: 7px 0; }
p { color: #64748b; overflow-wrap: anywhere; }
</style>
