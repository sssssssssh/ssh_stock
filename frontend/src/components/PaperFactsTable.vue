<script setup lang="ts">
import type { PaperFacts } from "../services/decisionPaper";
defineProps<{ rows: PaperFacts[]; columns: { key: string; title: string }[]; loading?: boolean; failed?: boolean }>();
function cell(row: PaperFacts, key: string) {
  const value = key.split(".").reduce<unknown>((parent, part) =>
    parent !== null && typeof parent === "object" ? (parent as Record<string, unknown>)[part] : null, row);
  return value === null || value === undefined ? "--" : typeof value === "object"
    ? JSON.stringify(value) : String(value);
}
</script>
<template>
  <table class="paper-facts-table"><thead><tr><th v-for="column in columns" :key="column.key">{{ column.title }}</th><th>证据</th></tr></thead>
    <tbody><tr v-for="row in rows" :key="row.id"><td v-for="column in columns" :key="column.key" :data-label="column.title">{{ cell(row, column.key) }}</td>
      <td data-label="证据"><details><summary>审计明细</summary><pre>{{ JSON.stringify(row, null, 2) }}</pre></details></td></tr>
      <tr v-if="!rows.length"><td :colspan="columns.length + 1" class="paper-empty">{{ loading ? '加载中' : failed ? '加载失败' : '暂无记录' }}</td></tr></tbody></table>
</template>
<style scoped>
table { border-collapse: collapse; width: 100%; table-layout: fixed; font-size: 12px; }
th, td { border-bottom: 1px solid #dce3e9; padding: 10px 8px; text-align: left; overflow-wrap: anywhere; vertical-align: top; }
th { color: #556172; font-weight: 600; background: #f7f9fa; }
pre { max-height: 280px; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; font-size: 11px; margin: 8px 0; }
summary { cursor: pointer; color: #087f72; }
.paper-empty { text-align: center; padding: 22px; color: #697481; }
@media (max-width: 650px) { thead { display: none; } table, tbody, tr { display: block; } tr { padding: 8px 0; border-bottom: 1px solid #dce3e9; }
td { display: grid; grid-template-columns: 82px minmax(0, 1fr); gap: 8px; border: 0; padding: 5px 8px; }
td::before { content: attr(data-label); color: #697481; } td.paper-empty { display: block; } }
</style>
