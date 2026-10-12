import { afterEach, expect, it, vi } from "vitest";
import { fetchEvidenceDetail, fetchReportEvidence, fetchTurnArchive, verifyFrozenReport } from "./agentArchive";

afterEach(() => vi.unstubAllGlobals());
it("uses bounded owner-authenticated endpoints, safe body and cancellable reads", async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ code: 0, data: [], meta: { total: 0 } }) });
  vi.stubGlobal("fetch", fetch);
  const controller = new AbortController();
  await fetchTurnArchive("chat", "request/part", controller.signal);
  expect(fetch.mock.calls[0][0]).toContain("/turn-archives/request%2Fpart");
  await fetchReportEvidence("report", 20, controller.signal);
  expect(fetch.mock.calls[1][0]).toContain("limit=20&offset=20");
  await fetchEvidenceDetail("report", "e/1", controller.signal);
  expect(fetch.mock.calls[2][0]).toContain("/evidence/e%2F1");
  await verifyFrozenReport("report", controller.signal);
  expect(fetch.mock.calls[3][1]).toMatchObject({ method: "POST", body: "{}", credentials: "include", signal: controller.signal });
});
