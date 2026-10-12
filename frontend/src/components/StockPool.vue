<script setup lang="ts">
import type { StockPoolItem } from "../types";
import type { ResearchContext } from "../services/agent";

defineProps<{
  title: string;
  subtitle?: string;
  rows: StockPoolItem[];
  highlightTsCode?: string;
  highlightTradeDate?: string;
  warning?: boolean;
  emptyText: string;
  formatNumber: (value: number | null | undefined, digits?: number) => string;
  reasonText: (value: StockPoolItem["reason_codes"]) => string;
}>();

defineEmits<{
  select: [row: StockPoolItem];
  research: [context: ResearchContext];
}>();
</script>

<template>
  <article class="panel wide">
    <div class="panel-title">
      <h2>{{ title }}</h2>
      <span v-if="subtitle">{{ subtitle }}</span>
      <slot name="actions" />
    </div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>代码</th><th>名称</th><th>状态</th><th>机会</th>
            <th>右侧</th><th>趋势</th><th>行业</th><th>原因</th><th>研究</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="`${row.ts_code}-${row.trade_date}`" :class="{ 'research-highlight': row.ts_code === highlightTsCode && (!highlightTradeDate || row.trade_date === highlightTradeDate) }">
            <td>
              <button class="stock-code-button" type="button" @click="$emit('select', row)">
                {{ row.ts_code }}
              </button>
            </td>
            <td>{{ row.name || "--" }}</td>
            <td><span class="state-pill" :class="{ warning }">{{ row.state }}</span></td>
            <td>{{ formatNumber(row.opportunity_score, 1) }}</td>
            <td>{{ formatNumber(row.right_side_score, 1) }}</td>
            <td>{{ formatNumber(row.trend_score, 1) }}</td>
            <td>{{ row.sector_name || row.industry || "--" }}</td>
            <td class="reason-cell">{{ reasonText(row.reason_codes) }}</td>
            <td><button class="stock-code-button" type="button" title="带入智能研究" @click="$emit('research', { view: 'long', ts_code: row.ts_code, trade_date: row.trade_date, source_tool: 'ui.stock_pool' })">↗</button></td>
          </tr>
          <tr v-if="!rows.length"><td colspan="9" class="empty-cell">{{ emptyText }}</td></tr>
        </tbody>
      </table>
    </div>
  </article>
</template>

<style scoped>
.research-highlight { background: #fff7d6; box-shadow: inset 3px 0 #d97706; }
</style>
