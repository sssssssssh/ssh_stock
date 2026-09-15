<script setup lang="ts">
import type { SectorHeat } from "../types";

defineProps<{
  title: string;
  subtitle: string;
  rows: SectorHeat[];
  momentum?: boolean;
  formatNumber: (value: number | null | undefined, digits?: number) => string;
}>();
</script>

<template>
  <article class="panel wide">
    <div class="panel-title"><h2>{{ title }}</h2><span>{{ subtitle }}</span></div>
    <div class="sector-list">
      <div v-for="row in rows" :key="row.sector_id" class="sector-row">
        <span class="sector-rank">{{ row.heat_rank ?? "--" }}</span>
        <span class="sector-name">{{ row.name || row.sector_name || row.sector_id }}</span>
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
