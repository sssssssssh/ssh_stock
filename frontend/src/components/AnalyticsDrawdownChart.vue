<script setup lang="ts">
import { LineChart } from "echarts/charts";
import { GridComponent, MarkLineComponent, TooltipComponent } from "echarts/components";
import { init, use, type EChartsType } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { AnalyticsSeries, AnalyticsSummary } from "../types";
import { buildDrawdownSeries } from "../services/analytics";

const props = defineProps<{ rows: AnalyticsSeries[]; summary: AnalyticsSummary }>();
const chartRef = ref<HTMLDivElement | null>(null);
let chart: EChartsType | null = null;
use([LineChart, GridComponent, MarkLineComponent, TooltipComponent, CanvasRenderer]);

function render() {
  if (!chartRef.value || !props.rows.length) return;
  chart ||= init(chartRef.value);
  const markers = [
    props.summary.performance.max_drawdown_peak_date,
    props.summary.performance.max_drawdown_trough_date,
    props.summary.performance.max_drawdown_recovery_date
  ].filter((value): value is string => Boolean(value));
  chart.setOption({
    animation: false,
    tooltip: { trigger: "axis", valueFormatter: (value: unknown) => `${(Number(value) * 100).toFixed(2)}%` },
    grid: { left: 58, right: 22, top: 26, bottom: 34 },
    xAxis: { type: "time" },
    yAxis: { type: "value", axisLabel: { formatter: (value: number) => `${(value * 100).toFixed(0)}%` } },
    series: [{
      name: "Drawdown",
      type: "line",
      symbol: "none",
      areaStyle: { opacity: 0.16 },
      data: buildDrawdownSeries(props.rows),
      markLine: { symbol: "none", data: markers.map((value) => ({ xAxis: value })) }
    }]
  });
}

function resize() { chart?.resize(); }
onMounted(async () => { window.addEventListener("resize", resize); await nextTick(); render(); });
watch(() => [props.rows, props.summary], async () => { await nextTick(); render(); }, { deep: true });
onBeforeUnmount(() => { window.removeEventListener("resize", resize); chart?.dispose(); });
</script>

<template><div ref="chartRef" class="analytics-chart" aria-label="回撤图"></div></template>
