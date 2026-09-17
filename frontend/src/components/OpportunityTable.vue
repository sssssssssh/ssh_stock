<script setup lang="ts">
import type { OpportunityItem } from "../types";

defineProps<{
  title: string;
  kind: "left" | "right" | "trend";
  rows: OpportunityItem[];
  formatNumber: (value: number | null, digits?: number) => string;
}>();
</script>

<template>
  <article class="panel opportunity-panel">
    <div class="panel-title"><h2>{{ title }}</h2><span>{{ rows.length }} 只</span></div>
    <div class="table-scroll">
      <table class="opportunity-table">
        <thead><tr><th>代码</th><th>名称</th><th>阶段</th><th v-if="kind === 'left'">Left</th><th v-if="kind === 'right'">Right</th><th v-if="kind === 'trend'">Trend / Rank</th><th v-if="kind === 'trend'">位置 / 风险</th><th>RPS60</th><th>行业</th><th>题材 / Heat</th><th>市场</th></tr></thead>
        <tbody>
          <tr v-for="row in rows" :key="row.ts_code">
            <td>{{ row.ts_code }}</td><td class="stock-name">{{ row.name || "--" }}</td><td><span class="stage-tag">{{ row.opportunity_stage }}</span><b v-if="row.left_reversal_new" class="new-mark">NEW</b></td><td v-if="kind === 'left'">{{ formatNumber(row.left_reversal_score, 1) }}</td><td v-if="kind === 'right'">{{ formatNumber(row.right_side_score, 1) }}</td><td v-if="kind === 'trend'">{{ formatNumber(row.trend_score, 1) }} / {{ formatNumber(row.trend_rank_score, 1) }}</td><td v-if="kind === 'trend'">{{ formatNumber(row.position_score, 1) }} / {{ row.extension_risk || "--" }}</td><td>{{ formatNumber(row.rps60 ?? null, 1) }}</td><td>{{ row.industry_name || "--" }} <small>{{ formatNumber(row.industry_heat, 0) }}</small></td><td>{{ row.primary_theme_name || "--" }} <small>{{ formatNumber(row.primary_theme_heat, 0) }}</small></td><td>{{ formatNumber(row.market_score, 0) }}</td>
          </tr>
          <tr v-if="!rows.length"><td :colspan="kind === 'trend' ? 11 : 9" class="table-empty">暂无符合条件的数据</td></tr>
        </tbody>
      </table>
    </div>
  </article>
</template>
