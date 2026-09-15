<script setup lang="ts">
import type { ResearchStats } from "../types";

defineProps<{
  stats: ResearchStats | null;
  formatPercent: (value: number | null | undefined) => string;
}>();
</script>

<template>
  <article class="panel">
    <div class="panel-title">
      <h2>信号后验</h2>
      <span>{{ stats?.latest_evaluated_until_date || "--" }}</span>
    </div>
    <div class="stats-stack">
      <div><span>5日均值</span><strong>{{ formatPercent(stats?.avg_ret5) }}</strong></div>
      <div><span>20日均值</span><strong>{{ formatPercent(stats?.avg_ret20) }}</strong></div>
      <div><span>20日胜率</span><strong>{{ formatPercent(stats?.win_rate20) }}</strong></div>
      <div>
        <span>MFE20 / MAE20</span>
        <strong>{{ formatPercent(stats?.avg_mfe20) }} / {{ formatPercent(stats?.avg_mae20) }}</strong>
      </div>
    </div>
  </article>
</template>
