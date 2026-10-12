import { afterEach, expect, it, vi } from "vitest";

import { archiveAgentChat, fetchAgentChats, fetchLatestAgentChat, fetchEarlierAgentMessages, fetchAgentTurnStatus, fetchWalkForwardValidationWindow, normalizeAgentRequestContent, sendAgentMessage } from "./agent";

afterEach(() => vi.restoreAllMocks());

function response(data: unknown, meta: unknown = {}): Response {
  return new Response(JSON.stringify({ code: 0, message: "ok", data, meta }), {
    status: 200,
    headers: { "Content-Type": "application/json" }
  });
}

it("maps paginated chats, idempotent messages, and archive requests", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(response([], { total: 0 }))
    .mockResolvedValueOnce(response({ answer_status: "COMPLETED" }))
    .mockResolvedValueOnce(response({ chat_id: "chat-1", status: "ARCHIVED" }));

  await fetchAgentChats(20, 40);
  await sendAgentMessage("chat-1", "question", "request-1");
  await archiveAgentChat("chat-1");

  expect(fetchMock.mock.calls[0][0]).toContain("limit=20&offset=40");
  expect(fetchMock.mock.calls[1][1]).toMatchObject({ method: "POST" });
  expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body))).toEqual({
    content: "question",
    request_id: "request-1"
  });
  expect(fetchMock.mock.calls[2][1]).toMatchObject({ method: "DELETE" });
});

it("uses bounded keyset reads and safely encodes request identities", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => response({}, { total: 201, has_more: true, next_cursor: 152 }));
  await fetchLatestAgentChat("chat/a");
  await fetchEarlierAgentMessages("chat/a", 152);
  await fetchAgentTurnStatus("chat/a", "request/a");
  await fetchWalkForwardValidationWindow("study-a", "validation-a", 301);
  expect(fetchMock.mock.calls[0][0]).toContain("chat%2Fa?limit=50&latest=true");
  expect(fetchMock.mock.calls[1][0]).toContain("before_sequence=152");
  expect(fetchMock.mock.calls[2][0]).toContain("turns/request%2Fa");
  expect(fetchMock.mock.calls[3][0]).toContain("limit=1&window_no=301");
});

it("matches the server's NFKC, newline and trailing-space normalization", () => {
  expect(normalizeAgentRequestContent("  ＡＢＣ\r\nsecond  \rthird  ")).toBe("ABC\nsecond\nthird");
});
