import { afterEach, describe, expect, it, vi } from "vitest";

import {
  enqueueBackfillJob,
  fetchDataCalendar,
  fetchRealtimeKline,
  fetchSystemRuntime,
  request
} from "./api";

afterEach(() => vi.restoreAllMocks());

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" }
  });
}

describe("API request mapping", () => {
  it("unwraps successful envelopes and maps representative endpoints", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async () => response({ code: 0, message: "ok", data: { value: 1 } }));

    await expect(fetchSystemRuntime()).resolves.toEqual({ value: 1 });
    await fetchDataCalendar("2026-09-01", "2026-09-25");
    await fetchRealtimeKline("000001.SZ", 60);
    await enqueueBackfillJob({ start: "2026-09-01", end: "2026-09-25" });

    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/system/runtime");
    expect(fetchMock.mock.calls[1][0]).toContain("start=2026-09-01&end=2026-09-25");
    expect(fetchMock.mock.calls[2][0]).toContain("000001.SZ/realtime-kline?days=60");
    expect(fetchMock.mock.calls[3][1]).toMatchObject({ method: "POST" });
  });

  it("dispatches auth events and preserves API error codes", async () => {
    const authRequired = vi.fn();
    const passwordRequired = vi.fn();
    window.addEventListener("auth-required", authRequired);
    window.addEventListener("password-change-required", passwordRequired);
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(response({ detail: "expired" }, 401))
      .mockResolvedValueOnce(
        response({ detail: { code: "PASSWORD_CHANGE_REQUIRED" } }, 403)
      );

    await expect(request("/private")).rejects.toThrow("expired");
    await expect(request("/private")).rejects.toThrow("PASSWORD_CHANGE_REQUIRED");
    expect(authRequired).toHaveBeenCalledOnce();
    expect(passwordRequired).toHaveBeenCalledOnce();
  });

  it("rejects malformed success envelopes", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(response({ message: "bad" }));
    await expect(request("/bad")).rejects.toThrow("bad");
  });
});
