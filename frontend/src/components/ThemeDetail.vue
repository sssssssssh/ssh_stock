<script setup lang="ts">
import type { ThemeOverview } from "../types";

defineProps<{ data: ThemeOverview | null; loading: boolean }>();
defineEmits<{ close: [] }>();
</script>

<template>
  <div class="modal-backdrop" @click.self="$emit('close')">
    <section class="theme-drawer" role="dialog" aria-modal="true">
      <header class="kline-header"><div><span>题材详情</span><h2>{{ data?.theme?.name || "加载中" }}</h2></div><button class="icon-button" aria-label="关闭" @click="$emit('close')">×</button></header>
      <div v-if="loading" class="empty-block">加载中</div>
      <template v-else-if="data">
        <div
          v-if="data.member_snapshot.member_snapshot_mode === 'PARTIAL'"
          class="snapshot-warning"
          role="status"
        >
          <strong>成员快照部分覆盖</strong>
          <span>
            {{ data.member_snapshot.member_snapshot_date || "--" }} ·
            {{ data.member_snapshot.member_snapshot_coverage == null ? "--" : `${(data.member_snapshot.member_snapshot_coverage * 100).toFixed(1)}%` }}
          </span>
        </div>
        <div class="theme-metrics"><div><span>Heat</span><strong>{{ data.factor?.heat_score?.toFixed(1) || "--" }}</strong></div><div><span>阶段</span><strong>{{ data.factor?.lifecycle || "--" }}</strong></div><div><span>成员覆盖</span><strong>{{ data.factor?.eligible_member_count ?? "--" }}/{{ data.factor?.member_count ?? "--" }}</strong></div><div><span>数据覆盖</span><strong>{{ data.factor?.data_coverage == null ? "--" : `${(data.factor.data_coverage * 100).toFixed(0)}%` }}</strong></div></div>
        <h3>成员状态</h3><div class="signal-list"><div v-for="row in data.member_distribution" :key="row.stage"><span>{{ row.stage }}</span><strong>{{ row.count }}</strong></div></div>
        <h3>趋势成员</h3><div class="drawer-member" v-for="row in data.top_members.trend || []" :key="row.ts_code"><span>{{ row.name || row.ts_code }}</span><b>{{ row.state }} · {{ row.trend_rank_score?.toFixed(1) || "--" }}</b></div>
      </template>
    </section>
  </div>
</template>
