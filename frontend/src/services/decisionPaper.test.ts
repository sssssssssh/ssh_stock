import { beforeEach, expect, it, vi } from "vitest";
import { clearPaperRequest, paperPage, paperRequestId, paperWrite } from "./decisionPaper";
beforeEach(() => { sessionStorage.clear(); vi.restoreAllMocks(); });
it("persists only an owner-scoped opaque retry ID, never credentials or notes", () => {
  const id = paperRequestId("owner-a", "approve", "proposal-a");
  expect(paperRequestId("owner-a", "approve", "proposal-a")).toBe(id);
  expect(paperRequestId("owner-b", "approve", "proposal-a")).not.toBe(id);
  expect(id).toMatch(/^[0-9a-f]{32}$/);
  expect(sessionStorage.getItem("space.paper.request.owner-a.approve.proposal-a")).toBe(id);
  clearPaperRequest("owner-a", "approve", "proposal-a");
  expect(paperRequestId("owner-a", "approve", "proposal-a")).not.toBe(id);
});
it("uses authenticated fetch and immutable decimal request strings", async () => {
  const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ code: 0, data: { id: "approved" }, meta: {} })));
  await paperWrite("/decisions/proposals/p/approve", { request_id: "request", target_weight: "0.08", confirmed: true });
  expect(fetch).toHaveBeenCalledWith("/api/v1/decisions/proposals/p/approve", expect.objectContaining({ credentials: "include", body: expect.stringContaining('"target_weight":"0.08"') }));
});
it("scopes pages to account and preserves limit/offset filters", async () => {
  const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ code: 0, data: [], meta: { total: 0 } })));
  await paperPage("proposals", "account-1", { offset: 20, stage: "TREND" });
  expect(String(fetch.mock.calls[0][0])).toContain("account_id=account-1");
  expect(String(fetch.mock.calls[0][0])).toContain("offset=20");
});
