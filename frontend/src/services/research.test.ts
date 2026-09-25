import { beforeEach, expect, it, vi } from "vitest";

import * as api from "./api";
import {
  fetchContext,
  fetchOpportunityBuckets,
  fetchThemeBuckets,
  fetchThemeStats,
  fetchTrendTopN,
  queueResearchEvaluation
} from "./research";

beforeEach(() => vi.spyOn(api, "request").mockResolvedValue([]));

it("maps research filters and queue payloads without losing identity inputs", async () => {
  const window = { start: "2026-01-01", end: "2026-09-25" };
  await fetchThemeStats(window);
  await fetchThemeBuckets(window, "heat_score");
  await fetchTrendTopN(window);
  await fetchOpportunityBuckets(window, "position_score", "TREND");
  await fetchContext(window, "market_regime", "RIGHT");
  await queueResearchEvaluation(window);

  const calls = vi.mocked(api.request).mock.calls;
  expect(calls[0][0]).toContain("/research/themes/stats?start=2026-01-01&end=2026-09-25");
  expect(calls[1][0]).toContain("field=heat_score");
  expect(calls[3][0]).toContain("research_type=TREND");
  expect(calls[4][0]).toContain("group_by=market_regime");
  expect(calls[5][1]).toMatchObject({ method: "POST" });
  expect(calls[5][1]?.body).toBe(JSON.stringify(window));
});
