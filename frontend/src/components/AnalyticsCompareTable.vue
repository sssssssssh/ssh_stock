<script setup lang="ts">
import { computed, ref } from "vue";
import type { AnalyticsSummary } from "../types";
import { formatAnalyticsPercent, formatMetric, sortedCompareItems } from "../services/analytics";

const props = defineProps<{ items: AnalyticsSummary[] }>();
const sortKey = ref<"annualized_return" | "max_drawdown" | "sharpe_ratio" | null>(null);
const rows = computed(() => sortKey.value ? sortedCompareItems(props.items, sortKey.value) : props.items);
</script>

<template>
  <div class="analytics-table-wrap">
    <table class="analytics-table">
      <thead><tr>
        <th>Run</th>
        <th><button @click="sortKey = 'annualized_return'">Annualized Return</button></th>
        <th><button @click="sortKey = 'max_drawdown'">Max Drawdown</button></th>
        <th><button @click="sortKey = 'sharpe_ratio'">Sharpe</button></th>
        <th>Excess</th><th>Win Rate</th><th>Profit Factor</th><th>Turnover</th><th>Cost Ratio</th>
      </tr></thead>
      <tbody><tr v-for="row in rows" :key="row.identity.run_id">
        <td>{{ row.backtest.name || row.identity.run_id.slice(0, 8) }}</td>
        <td>{{ formatAnalyticsPercent(row.performance.annualized_return) }}</td>
        <td>{{ formatAnalyticsPercent(row.performance.max_drawdown) }}</td>
        <td>{{ formatMetric(row.risk.sharpe_ratio, 3) }}</td>
        <td>{{ formatAnalyticsPercent(row.risk.excess_cumulative_return) }}</td>
        <td>{{ formatAnalyticsPercent(row.trade.win_rate) }}</td>
        <td>{{ formatMetric(row.trade.profit_factor, 3) }}</td>
        <td>{{ formatAnalyticsPercent(row.trade.total_turnover) }}</td>
        <td>{{ formatAnalyticsPercent(row.trade.total_cost_to_initial_capital) }}</td>
      </tr></tbody>
    </table>
  </div>
</template>
