<script setup lang="ts">
import type { SectorHeat } from "../types";
import type { ResearchContext } from "../services/agent";

defineProps<{
  title: string;
  subtitle: string;
  rows: SectorHeat[];
  highlightSectorId?: string;
  highlightTradeDate?: string;
  momentum?: boolean;
  formatNumber: (value: number | null | undefined, digits?: number) => string;
}>();

defineEmits<{ research: [context: ResearchContext] }>();
</script>

<template>
  <article class="panel wide">
    <div class="panel-title"><h2>{{ title }}</h2><span>{{ subtitle }}</span></div>
    <div class="sector-list">
      <div v-for="row in rows" :key="row.sector_id" class="sector-row" :class="{ 'research-highlight': String(row.sector_id) === highlightSectorId && (!highlightTradeDate || row.trade_date === highlightTradeDate) }">
        <span class="sector-rank">{{ row.heat_rank ?? "--" }}</span>
        <button class="sector-name stock-code-button" type="button" title="带入智能研究" @click="$emit('research', { view: 'long', sector_id: String(row.sector_id), trade_date: row.trade_date, source_tool: 'ui.sector_heat' })">{{ row.name || row.sector_name || row.sector_id }}</button>
        <div class="heat-track">
          <i :style="{ width: `${Math.max(0, Math.min(row.heat_score ?? 0, 100))}%` }"></i>
        </div>
        <strong>{{ formatNumber(momentum ? row.heat_momentum3 : row.heat_score, 1) }}</strong>
        <small>{{ row.lifecycle || "--" }}</small>
      </div>
      <div v-if="!rows.length" class="empty-block">暂无行业数据</div>
    </div>
  </article>
</template>

<style scoped>
.research-highlight { background: #fff7d6; box-shadow: inset 3px 0 #d97706; }
</style>
