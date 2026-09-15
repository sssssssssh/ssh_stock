<script setup lang="ts">
type Metric = { label: string; value: string | number; sub?: string; tone?: string };

defineProps<{
  metrics: Metric[];
  marketRegime: string;
  sectorCount: number;
}>();
</script>

<template>
  <section class="metric-grid">
    <article v-for="metric in metrics" :key="metric.label" class="metric-card" :class="metric.tone">
      <span>{{ metric.label }}</span>
      <strong>{{ metric.value }}</strong>
      <small>{{ metric.sub || "" }}</small>
    </article>
  </section>
  <section class="dashboard-grid overview-grid">
    <article class="panel">
      <div class="panel-title">
        <h2>市场分布</h2>
        <span>{{ marketRegime }}</span>
      </div>
      <slot name="market" />
    </article>
    <article class="panel">
      <div class="panel-title">
        <h2>行业热度</h2>
        <span>{{ sectorCount }} 个行业</span>
      </div>
      <slot name="sector" />
    </article>
    <slot name="research" />
  </section>
</template>
