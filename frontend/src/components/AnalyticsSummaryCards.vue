<script setup lang="ts">
import type { AnalyticsSummary } from "../types";
import { formatAnalyticsPercent, formatMetric } from "../services/analytics";

defineProps<{ summary: AnalyticsSummary }>();
</script>

<template>
  <section class="analytics-cards" aria-label="回测核心指标">
    <div><span>累计收益</span><strong>{{ formatAnalyticsPercent(summary.performance.cumulative_return) }}</strong></div>
    <div><span>年化收益</span><strong>{{ formatAnalyticsPercent(summary.performance.annualized_return) }}</strong></div>
    <div><span>最大回撤</span><strong>{{ formatAnalyticsPercent(summary.performance.max_drawdown) }}</strong></div>
    <div><span>Sharpe</span><strong>{{ formatMetric(summary.risk.sharpe_ratio, 3) }}</strong></div>
    <div><span>Sortino</span><strong>{{ formatMetric(summary.risk.sortino_ratio, 3) }}</strong></div>
    <div><span>Calmar</span><strong>{{ formatMetric(summary.risk.calmar_ratio, 3) }}</strong></div>
    <div><span>相对超额</span><strong>{{ formatAnalyticsPercent(summary.risk.excess_cumulative_return) }}</strong></div>
    <div><span>总换手</span><strong>{{ formatAnalyticsPercent(summary.trade.total_turnover) }}</strong></div>
    <div><span>胜率</span><strong>{{ formatAnalyticsPercent(summary.trade.win_rate) }}</strong></div>
    <div><span>Profit Factor</span><strong>{{ formatMetric(summary.trade.profit_factor, 3) }}</strong></div>
    <div><span>成本率</span><strong>{{ formatAnalyticsPercent(summary.trade.total_cost_to_initial_capital) }}</strong></div>
  </section>
</template>
