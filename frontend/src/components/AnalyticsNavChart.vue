<script setup lang="ts">
import { LineChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { init, use, type EChartsType } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { AnalyticsSeries } from "../types";
import { buildNavSeries } from "../services/analytics";

const props = defineProps<{ rows: AnalyticsSeries[] }>();
const chartRef = ref<HTMLDivElement | null>(null);
let chart: EChartsType | null = null;
use([LineChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer]);

function render() {
  if (!chartRef.value || !props.rows.length) return;
  chart ||= init(chartRef.value);
  const series = buildNavSeries(props.rows);
  chart.setOption({
    animation: false,
    tooltip: { trigger: "axis" },
    legend: { data: ["Strategy NAV", "Benchmark NAV"] },
    grid: { left: 54, right: 22, top: 42, bottom: 34 },
    xAxis: { type: "category", data: series.dates, boundaryGap: false },
    yAxis: { type: "value", scale: true },
    series: [
      { name: "Strategy NAV", type: "line", symbol: "none", data: series.strategy },
      { name: "Benchmark NAV", type: "line", symbol: "none", data: series.benchmark }
    ]
  });
}

function resize() { chart?.resize(); }
onMounted(async () => { window.addEventListener("resize", resize); await nextTick(); render(); });
watch(() => props.rows, async () => { await nextTick(); render(); }, { deep: true });
onBeforeUnmount(() => { window.removeEventListener("resize", resize); chart?.dispose(); });
</script>

<template><div ref="chartRef" class="analytics-chart" aria-label="策略与基准净值图"></div></template>
