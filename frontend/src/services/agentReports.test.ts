import { afterEach, expect, it, vi } from "vitest";

import {
  archiveResearchReport,
  createReportComparison,
  createResearchReport,
  fetchResearchReports
} from "./agentReports";

afterEach(() => vi.restoreAllMocks());

function response(data: unknown, meta: unknown = {}): Response {
  return new Response(JSON.stringify({ code: 0, message: "ok", data, meta }), {
    status: 200,
    headers: { "Content-Type": "application/json" }
  });
}

it("maps report list, creation, archive and frozen comparison requests", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(response([], { total: 0 }))
    .mockResolvedValueOnce(response({ report_id: "report-1" }))
    .mockResolvedValueOnce(response({ report_id: "report-1", archived_at: "now" }))
    .mockResolvedValueOnce(response({ comparison_id: "comparison-1" }));

  await fetchResearchReports(20, 40, true);
  await createResearchReport({
    source_chat_id: "chat-1",
    source_message_id: "message-1",
    report_type: "strategy_review",
    request_id: "request-1"
  });
  await archiveResearchReport("report-1");
  await createReportComparison({
    left_report_id: "report-1",
    right_report_id: "report-2",
    request_id: "comparison-request"
  });

  expect(fetchMock.mock.calls[0][0]).toContain("include_archived=true");
  expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body))).toMatchObject({
    report_type: "strategy_review",
    request_id: "request-1"
  });
  expect(fetchMock.mock.calls[2][1]).toMatchObject({ method: "POST" });
  expect(JSON.parse(String(fetchMock.mock.calls[3][1]?.body))).toEqual({
    left_report_id: "report-1",
    right_report_id: "report-2",
    request_id: "comparison-request"
  });
});
