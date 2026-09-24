import { describe, expect, it } from "vitest";

import { businessDaysAgoIso, businessTodayIso } from "./businessTime";

describe("businessTime", () => {
  it("uses the Asia/Shanghai date across the UTC day boundary", () => {
    const now = new Date("2026-09-24T16:30:00Z");

    expect(businessTodayIso(now)).toBe("2026-09-25");
    expect(businessDaysAgoIso(1, now)).toBe("2026-09-24");
  });
});
