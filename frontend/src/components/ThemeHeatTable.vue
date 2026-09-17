<script setup lang="ts">
import type { ThemeHeat } from "../types";

defineProps<{ rows: ThemeHeat[]; formatNumber: (value: number | null, digits?: number) => string }>();
defineEmits<{ select: [row: ThemeHeat] }>();
</script>

<template>
  <article class="panel opportunity-panel">
    <div class="panel-title"><h2>热门题材</h2><span>{{ rows.length }} 个</span></div>
    <div class="table-scroll">
      <table class="opportunity-table">
        <thead><tr><th>排名</th><th>题材</th><th>Heat</th><th>阶段</th><th>3日变化</th><th>排名变化</th><th>涨跌</th><th>净流入</th><th>涨停/连板</th><th>Breadth20</th><th>RPS60</th></tr></thead>
        <tbody>
          <tr v-for="row in rows" :key="row.theme_code" class="clickable-row" @click="$emit('select', row)">
            <td>{{ row.heat_rank ?? "--" }}</td><td class="stock-name">{{ row.name }}</td><td>{{ formatNumber(row.heat_score, 1) }}</td><td><span class="stage-tag">{{ row.lifecycle || "--" }}</span></td><td>{{ formatNumber(row.heat_momentum3, 1) }}</td><td>{{ formatNumber(row.rank_change, 0) }}</td><td>{{ formatNumber(row.return1 == null ? null : row.return1 * 100, 2) }}%</td><td>{{ formatNumber(row.net_amount, 0) }}</td><td>{{ row.limit_up_count ?? "--" }}/{{ row.continuous_limit_count ?? "--" }}</td><td>{{ formatNumber(row.breadth20 == null ? null : row.breadth20 * 100, 1) }}%</td><td>{{ formatNumber(row.rps60_median, 1) }}</td>
          </tr>
          <tr v-if="!rows.length"><td colspan="11" class="table-empty">暂无题材热度数据</td></tr>
        </tbody>
      </table>
    </div>
  </article>
</template>
