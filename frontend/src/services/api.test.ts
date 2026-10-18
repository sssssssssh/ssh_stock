import { afterEach, describe, expect, it, vi } from "vitest";

import {
  enqueueBackfillJob,
  cancelJob,
  fetchJobs,
  fetchDataCalendar,
  fetchRealtimeKline,
  fetchSystemRuntime,
  request,
  requestPage
} from "./api";

afterEach(() => vi.restoreAllMocks());

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" }
  });
}

describe("API request mapping", () => {
  it("merges complete active queue over a recent history page", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => response({
      code: 0, data: String(url).includes("/queue") ? {
        running: [{ id: "old-running", status: "RUNNING" }],
        queued: [{ id: "old-queued", status: "QUEUED", queue_position: 1 }]
      } : [{ id: "recent", status: "SUCCESS" }], meta: {}
    }));
    const jobs = await fetchJobs();
    expect(jobs.map((job) => job.id)).toEqual(["recent", "old-running", "old-queued"]);
  });

  it("preserves deduplication feedback and posts cancellation", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(async () => response({
      code: 0, data: { id: "queued", status: "QUEUED" }, meta: { accepted: false, deduplicated: true }
    }));
    expect((await enqueueBackfillJob({ start: "2026-01-01", end: "2026-01-02" })).submission_deduplicated).toBe(true);
    await cancelJob("queued");
    expect(fetch.mock.calls[1]).toMatchObject(["/api/v1/jobs/queued/cancel", { method: "POST" }]);
  });
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

  it("preserves pagination metadata with requestPage", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      response({ code: 0, message: "ok", data: [{ id: 1 }], meta: { total: 3 } })
    );
    await expect(requestPage<{ id: number }[], { total: number }>("/page")).resolves.toEqual({
      data: [{ id: 1 }],
      meta: { total: 3 }
    });
  });
});
