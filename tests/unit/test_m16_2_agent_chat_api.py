import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from app.api.v1.agent import require_agent_user
from app.api.v1.agent_chat import get_chat_application
from app.domain.agent.chat import (
    ChatAnswer,
    ChatMessageView,
    ChatSessionSummary,
)
from app.domain.agent.chat_errors import chat_not_found, llm_disabled
from app.main import app
from fastapi.testclient import TestClient

CHAT_ID = uuid.UUID("10000000-0000-0000-0000-000000000001")
MESSAGE_ID = uuid.UUID("20000000-0000-0000-0000-000000000001")
TRACE_ID = uuid.UUID("30000000-0000-0000-0000-000000000001")
NOW = datetime(2026, 10, 11, tzinfo=UTC)


class StubChatService:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    def create_chat(self, **kwargs):
        return _chat()

    def list_chats(self, **kwargs):
        return [_chat()], 1

    def get_chat(self, **kwargs):
        return (
            _chat(),
            [
                ChatMessageView(
                    message_id=MESSAGE_ID,
                    role="USER",
                    content="问题",
                    status="COMPLETED",
                    sequence_no=1,
                    created_at=NOW,
                )
            ],
            1,
        )

    def send_message(self, **kwargs):
        self.sent.append(kwargs)
        return ChatAnswer(
            chat_id=CHAT_ID,
            message_id=MESSAGE_ID,
            status="INSUFFICIENT_EVIDENCE",
            answer="请提供 run_id。",
            warnings=["INSUFFICIENT_EVIDENCE"],
            trace_id=TRACE_ID,
        )

    def archive_chat(self, **kwargs):
        return _chat(status="ARCHIVED")


def _chat(status: str = "ACTIVE") -> ChatSessionSummary:
    return ChatSessionSummary(
        chat_id=CHAT_ID,
        title="研究会话",
        status=status,
        created_at=NOW,
        updated_at=NOW,
    )


def _client(service: object) -> TestClient:
    app.dependency_overrides[require_agent_user] = lambda: SimpleNamespace(
        id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        username="test-admin",
        must_change_password=False,
    )
    app.dependency_overrides[get_chat_application] = lambda: service
    return TestClient(app)


def test_chat_crud_and_send_use_authenticated_envelope() -> None:
    service = StubChatService()
    client = _client(service)
    try:
        created = client.post("/api/v1/agent/chats", json={"title": "研究会话"})
        assert created.status_code == 201
        assert created.json()["data"]["chat_id"] == str(CHAT_ID)

        listing = client.get("/api/v1/agent/chats?limit=10&offset=0")
        assert listing.status_code == 200
        assert listing.json()["meta"]["total"] == 1

        detail = client.get(f"/api/v1/agent/chats/{CHAT_ID}")
        assert detail.status_code == 200
        assert detail.json()["data"]["messages"][0]["role"] == "USER"

        sent = client.post(
            f"/api/v1/agent/chats/{CHAT_ID}/messages",
            json={"content": "这个回测怎么样？", "request_id": "request-1"},
        )
        assert sent.status_code == 200
        assert sent.json()["data"]["status"] == "INSUFFICIENT_EVIDENCE"
        assert sent.json()["meta"]["request_id"] == "request-1"
        assert service.sent[0]["content"] == "这个回测怎么样？"

        archived = client.delete(f"/api/v1/agent/chats/{CHAT_ID}")
        assert archived.status_code == 200
        assert archived.json()["data"]["status"] == "ARCHIVED"
    finally:
        app.dependency_overrides.clear()


def test_chat_api_rejects_extra_fields_and_bounds() -> None:
    client = _client(StubChatService())
    try:
        extra = client.post(
            "/api/v1/agent/chats", json={"title": "x", "owner_user_id": str(uuid.uuid4())}
        )
        assert extra.status_code == 422
        injected_role = client.post(
            f"/api/v1/agent/chats/{CHAT_ID}/messages",
            json={"content": "hello", "role": "system"},
        )
        assert injected_role.status_code == 422
        too_long = client.post(
            f"/api/v1/agent/chats/{CHAT_ID}/messages",
            json={"content": "x" * 8001},
        )
        assert too_long.status_code == 422
        invalid_page = client.get("/api/v1/agent/chats?limit=101")
        assert invalid_page.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_chat_errors_are_safe_and_resource_visibility_is_hidden() -> None:
    class DisabledService(StubChatService):
        def send_message(self, **kwargs):
            raise llm_disabled()

        def get_chat(self, **kwargs):
            raise chat_not_found()

    client = _client(DisabledService())
    try:
        disabled = client.post(
            f"/api/v1/agent/chats/{CHAT_ID}/messages",
            json={"content": "hello"},
        )
        assert disabled.status_code == 503
        assert disabled.json()["detail"] == {
            "code": "LLM_DISABLED",
            "message": "LLM chat is disabled",
        }
        missing = client.get(f"/api/v1/agent/chats/{CHAT_ID}")
        assert missing.status_code == 404
        assert missing.json()["detail"]["code"] == "CHAT_NOT_FOUND"
    finally:
        app.dependency_overrides.clear()


def test_chat_endpoints_require_authentication() -> None:
    app.dependency_overrides.clear()
    app.dependency_overrides[get_chat_application] = lambda: StubChatService()
    client = TestClient(app)
    try:
        responses = [
            client.post("/api/v1/agent/chats", json={}),
            client.get("/api/v1/agent/chats"),
            client.get(f"/api/v1/agent/chats/{CHAT_ID}"),
            client.post(
                f"/api/v1/agent/chats/{CHAT_ID}/messages",
                json={"content": "hello"},
            ),
            client.delete(f"/api/v1/agent/chats/{CHAT_ID}"),
        ]
        assert all(response.status_code == 401 for response in responses)
        assert all(
            response.json()["detail"]["code"] == "UNAUTHORIZED"
            for response in responses
        )
    finally:
        app.dependency_overrides.clear()
