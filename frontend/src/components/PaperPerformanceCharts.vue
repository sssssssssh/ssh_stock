<script setup lang="ts">
import { LineChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { init, use, type EChartsType } from "echarts/core";
import { SVGRenderer } from "echarts/renderers";
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { PaperPerformance } from "../services/decisionPaper";
import { paperChartData } from "../services/paperCharts";
const props = defineProps<{ performance: PaperPerformance }>();
const host = ref<HTMLDivElement | null>(null), error = ref("");
const mode = ref<"nav" | "balance" | "drawdown" | "cost">("nav");
const page = ref(0);
const tableRows = computed(() => props.performance.series.slice(page.value * 20, (page.value + 1) * 20));
let instance: EChartsType | null = null, observer: ResizeObserver | null = null, alive = true;
use([LineChart, GridComponent, LegendComponent, TooltipComponent, SVGRenderer]);
const keys = computed(() => mode.value === "nav" ? ["nav", "benchmark_nav"] as const
  : mode.value === "balance" ? ["cash", "market_value"] as const
  : mode.value === "drawdown" ? ["drawdown"] as const : ["cumulative_cost"] as const);
const names: Record<string, string> = { nav: "模拟净值", benchmark_nav: "基准", cash: "现金", market_value: "持仓市值", drawdown: "回撤", cumulative_cost: "累计模拟成本" };
async function render() {
  await nextTick();
  if (!alive || !host.value) return;
  instance?.dispose(); instance = null; error.value = "";
  const series = keys.value.map(key => ({ key, ...paperChartData(props.performance.series, key) }));
  error.value = series.find(row => row.warning)?.warning || "";
  if (error.value || !series[0]?.dates.length) return;
  try {
    instance = init(host.value, undefined, { renderer: "svg" });
    instance.setOption({ animation: false, tooltip: { trigger: "axis", renderMode: "richText" },
      legend: { bottom: 0 }, grid: { left: 16, right: 16, top: 20, bottom: 50, containLabel: true },
      xAxis: { type: "category", data: series[0].dates, boundaryGap: false, axisLabel: { formatter: (value: string) => value.slice(5) } }, yAxis: { type: "value", scale: true },
      color: ["#087f72", "#ca8a04"], series: series.map(row => ({ name: names[row.key], type: "line", data: row.values,
        connectNulls: false, showSymbol: true, symbolSize: 4, smooth: false })) });
  } catch { instance?.dispose(); instance = null; error.value = "CHART_RENDER_FAILED"; }
}
function resize() { instance?.resize(); }
onMounted(() => { window.addEventListener("resize", resize); if (typeof ResizeObserver !== "undefined" && host.value) {
  observer = new ResizeObserver(resize); observer.observe(host.value); } void render(); });
watch(() => [props.performance, mode.value], render, { deep: true });
onBeforeUnmount(() => { alive = false; observer?.disconnect(); window.removeEventListener("resize", resize); instance?.dispose(); });
</script>
<template>
  <section class="paper-performance">
    <div class="paper-chart-modes" role="tablist" aria-label="模拟表现图表"><button v-for="item in [{ key: 'nav', title: '净值' }, { key: 'balance', title: '现金与持仓' }, { key: 'drawdown', title: '回撤' }, { key: 'cost', title: '成本' }]" :key="item.key" role="tab" :aria-selected="mode === item.key" @click="mode = item.key as typeof mode">{{ item.title }}</button></div>
    <p v-if="!performance.continuous" role="status">净值序列不连续或需复核，连续收益与回撤不可用。</p>
    <p v-if="performance.benchmark_status !== 'READY'" role="status">基准数据不完整</p>
    <p v-if="error" role="alert">{{ error }}</p>
    <div ref="host" class="paper-chart" role="img" aria-label="冻结模拟组合表现" />
    <details><summary>冻结数值</summary><div class="paper-values"><table><thead><tr><th>交易日</th><th>净值</th><th>基准</th><th>现金</th><th>持仓市值</th></tr></thead><tbody><tr v-for="row in tableRows" :key="row.trade_date"><td>{{ row.trade_date }}</td><td>{{ row.nav ?? '--' }}</td><td>{{ row.benchmark_nav ?? '--' }}</td><td>{{ row.cash ?? '--' }}</td><td>{{ row.market_value ?? '--' }}</td></tr></tbody></table></div><div><button :disabled="page === 0" @click="page--">上一页数值</button><button :disabled="(page + 1) * 20 >= performance.series.length" @click="page++">下一页数值</button></div></details>
  </section>
</template>
<style scoped>
.paper-performance { min-width: 0; } .paper-chart { width: 100%; height: 280px; min-width: 0; }
.paper-chart-modes { display: flex; flex-wrap: wrap; gap: 4px; } button { border: 0; border-bottom: 2px solid transparent; background: transparent; padding: 8px 12px; color: #546170; cursor: pointer; } button[aria-selected="true"] { color: #087f72; border-color: #087f72; }
p { font-size: 12px; color: #9a6515; overflow-wrap: anywhere; } summary { font-size: 12px; cursor: pointer; color: #087f72; } .paper-values { max-height: 300px; overflow: auto; } table { border-collapse: collapse; width: 100%; font-size: 11px; } td, th { padding: 8px 5px; text-align: left; border-bottom: 1px solid #dce3e9; overflow-wrap: anywhere; }
</style>
