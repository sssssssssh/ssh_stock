<script setup lang="ts">
import type { DataCalendarRow, DataCoverageRow } from "../types";

type CalendarCell = { key: string; day: number | null; row: DataCalendarRow | null };

defineProps<{
  collapsed: boolean;
  summary: { open: number; pulled: number; analyzed: number };
  monthTitle: string;
  cells: CalendarCell[];
  selectedDate: string;
  selectedRow: DataCalendarRow | null | undefined;
  pageRows: DataCoverageRow[];
  totalRows: number;
  page: number;
  pageSize: number;
  pageSizes: number[];
  totalPages: number;
  pageStart: number;
  pageEnd: number;
  statusLabel: (status: DataCalendarRow["coverage_status"] | undefined) => string;
}>();

const emit = defineEmits<{
  toggle: [];
  previousMonth: [];
  nextMonth: [];
  selectDate: [row: DataCalendarRow | null];
  setPage: [page: number];
  "update:pageSize": [value: number];
}>();

function updatePageSize(event: Event) {
  emit("update:pageSize", Number((event.target as HTMLSelectElement).value));
}
</script>

<template>
  <article class="panel" :class="{ collapsed }">
    <div class="panel-title coverage-title">
      <div>
        <h2>
          <button class="panel-title-button" type="button" :aria-expanded="!collapsed" @click="$emit('toggle')">
            <span class="collapse-icon" aria-hidden="true"></span><span>数据覆盖日历</span>
          </button>
        </h2>
        <span>已拉 {{ summary.pulled }} / 开市 {{ summary.open }}，已算 {{ summary.analyzed }}</span>
      </div>
      <div class="calendar-controls">
        <button type="button" @click="$emit('previousMonth')">上月</button>
        <strong>{{ monthTitle }}</strong>
        <button type="button" @click="$emit('nextMonth')">下月</button>
      </div>
    </div>
    <div v-show="!collapsed" class="panel-collapsible">
      <div class="calendar-legend">
        <span class="analyzed">算 已算基础</span><span class="complete">全 行业完成</span>
        <span class="raw-only">原 已拉未算</span><span class="degraded">差 质量异常</span>
        <span class="missing">缺 未拉取</span><span class="closed">休 休市</span>
      </div>
      <div class="coverage-calendar-layout">
        <section class="coverage-calendar">
          <div v-for="weekday in ['一', '二', '三', '四', '五', '六', '日']" :key="weekday" class="calendar-week">{{ weekday }}</div>
          <button
            v-for="cell in cells"
            :key="cell.key"
            class="calendar-day"
            :class="[cell.row?.coverage_status.toLowerCase(), { blank: !cell.row, selected: selectedDate === cell.row?.date }]"
            type="button"
            :disabled="!cell.row"
            :title="cell.row ? `${cell.row.date} ${statusLabel(cell.row.coverage_status)}` : ''"
            @click="$emit('selectDate', cell.row)"
          >
            <span>{{ cell.day || "" }}</span><strong v-if="cell.row">{{ statusLabel(cell.row.coverage_status) }}</strong>
          </button>
        </section>
        <aside class="calendar-detail">
          <template v-if="selectedRow">
            <span>{{ selectedRow.date }}</span><strong>{{ statusLabel(selectedRow.coverage_status) }}</strong>
            <dl>
              <div><dt>日线</dt><dd>{{ selectedRow.stock_daily_rows }}</dd></div>
              <div><dt>因子</dt><dd>{{ selectedRow.factor_rows }}</dd></div>
              <div><dt>行业</dt><dd>{{ selectedRow.sector_factor_rows }}</dd></div>
              <div><dt>状态</dt><dd>{{ selectedRow.state_rows }}</dd></div>
              <div><dt>信号</dt><dd>{{ selectedRow.signal_rows }}</dd></div>
              <div><dt>后验</dt><dd>{{ selectedRow.signal_eval_rows }}</dd></div>
            </dl>
          </template>
          <template v-else><span>日期明细</span><strong>点击日历查看</strong></template>
        </aside>
      </div>
      <div class="coverage-table-toolbar">
        <span>覆盖明细 {{ pageStart }}-{{ pageEnd }} / {{ totalRows }}</span>
        <div class="pagination-controls">
          <label>
            <span>每页</span>
            <select :value="pageSize" aria-label="覆盖明细每页条数" @change="updatePageSize">
              <option v-for="size in pageSizes" :key="size" :value="size">{{ size }}</option>
            </select>
          </label>
          <button type="button" :disabled="page <= 1" @click="$emit('setPage', page - 1)">上一页</button>
          <strong>{{ page }} / {{ totalPages }}</strong>
          <button type="button" :disabled="page >= totalPages" @click="$emit('setPage', page + 1)">下一页</button>
        </div>
      </div>
      <div class="table-wrap compact">
        <table>
          <thead><tr><th>日期</th><th>日线</th><th>指标</th><th>复权</th><th>指数</th><th>因子</th><th>市场</th><th>行业</th><th>状态</th><th>信号</th><th>后验</th></tr></thead>
          <tbody>
            <tr v-for="row in pageRows" :key="row.trade_date">
              <td>{{ row.trade_date }}</td><td>{{ row.stock_daily_rows }}</td><td>{{ row.daily_basic_rows }}</td>
              <td>{{ row.adj_factor_rows }}</td><td>{{ row.index_daily_rows }}</td><td>{{ row.factor_rows }}</td>
              <td>{{ row.market_rows }}</td><td>{{ row.sector_factor_rows }}</td><td>{{ row.state_rows }}</td>
              <td>{{ row.signal_rows }}</td><td>{{ row.signal_eval_rows }}</td>
            </tr>
            <tr v-if="!totalRows"><td colspan="11" class="empty-cell">暂无已拉取交易日</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </article>
</template>
