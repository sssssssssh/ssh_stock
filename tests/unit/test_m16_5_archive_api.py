import uuid
from types import SimpleNamespace

from app.api.v1.agent import require_agent_user
from app.api.v1.agent_archive import get_archive_application
from app.api.v1.agent_chat import get_chat_application
from app.domain.agent.archive import archive_error
from app.main import app
from fastapi.testclient import TestClient
from test_m16_2_agent_chat_api import StubChatService


class StubArchive:
    def turn_archive(self, **kwargs):
        return {"archive_status": "UNAVAILABLE"}

    def report_evidence(self, **kwargs):
        return [], {"archive_status": "UNAVAILABLE", "total": 0}

    def evidence_detail(self, **kwargs):
        return {"archive_status": "UNAVAILABLE"}

    def verify_report_archive(self, **kwargs):
        return {"archive_status": "UNAVAILABLE", "calculation_reproduced": False}


def test_archive_api_is_strict_bounded_and_preserves_legacy_unavailable():
    app.dependency_overrides[require_agent_user] = lambda: SimpleNamespace(id=uuid.uuid4())
    app.dependency_overrides[get_archive_application] = lambda: StubArchive()
    try:
        client = TestClient(app)
        report = uuid.uuid4()
        assert client.get(f"/api/v1/agent/reports/{report}/evidence?limit=101").status_code == 422
        assert (
            client.post(
                f"/api/v1/agent/reports/{report}/verify", json={"force_llm": True}
            ).status_code
            == 422
        )
        result = client.post(f"/api/v1/agent/reports/{report}/verify", json={})
        assert (
            result.status_code == 200 and result.json()["data"]["archive_status"] == "UNAVAILABLE"
        )
        result = client.get(f"/api/v1/agent/chats/{uuid.uuid4()}/turn-archives/request/part")
        assert (
            result.status_code == 200 and result.json()["data"]["archive_status"] == "UNAVAILABLE"
        )
        app.dependency_overrides[get_chat_application] = lambda: StubChatService()
        original = client.get(f"/api/v1/agent/chats/{uuid.uuid4()}/turns/request/archive")
        assert original.status_code == 200
        assert original.json()["data"]["request_id"] == "request/archive"
    finally:
        app.dependency_overrides.clear()


def test_archive_integrity_errors_are_safe_and_distinguishable():
    class BrokenArchive(StubArchive):
        def verify_report_archive(self, **kwargs):
            raise archive_error("ARCHIVE_INTEGRITY_MISMATCH")

    app.dependency_overrides[require_agent_user] = lambda: SimpleNamespace(id=uuid.uuid4())
    app.dependency_overrides[get_archive_application] = lambda: BrokenArchive()
    try:
        response = TestClient(app).post(f"/api/v1/agent/reports/{uuid.uuid4()}/verify", json={})
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "ARCHIVE_INTEGRITY_MISMATCH"
        assert "payload_json" not in response.text and "SELECT" not in response.text
    finally:
        app.dependency_overrides.clear()
