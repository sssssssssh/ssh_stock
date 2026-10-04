<script setup lang="ts">
import type { AnalyticsPeriod } from "../types";
import { formatAnalyticsPercent, formatCny } from "../services/analytics";

defineProps<{ rows: AnalyticsPeriod[] }>();
</script>

<template>
  <div class="analytics-table-wrap">
    <table class="analytics-table">
      <thead><tr><th>Period</th><th>Strategy</th><th>Benchmark</th><th>Relative</th><th>Turnover</th><th>Total Cost</th><th>Closed</th><th>Win Rate</th></tr></thead>
      <tbody>
        <tr v-for="row in rows" :key="`${row.period_type}-${row.period_key}`">
          <td>{{ row.period_key }}</td>
          <td>{{ formatAnalyticsPercent(row.strategy_return) }}</td>
          <td>{{ formatAnalyticsPercent(row.benchmark_return) }}</td>
          <td>{{ formatAnalyticsPercent(row.relative_return) }}</td>
          <td>{{ formatAnalyticsPercent(row.period_turnover) }}</td>
          <td>{{ formatCny(row.total_execution_cost) }}</td>
          <td>{{ row.closed_episode_count }}</td>
          <td>{{ formatAnalyticsPercent(row.win_rate) }}</td>
        </tr>
        <tr v-if="!rows.length"><td colspan="8" class="analytics-empty">暂无周期数据</td></tr>
      </tbody>
    </table>
  </div>
</template>
