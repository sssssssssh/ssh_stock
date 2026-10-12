import { afterEach, expect, it, vi } from "vitest";

import { archiveAgentChat, fetchAgentChats, sendAgentMessage } from "./agent";

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
