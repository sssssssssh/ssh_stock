import uuid
from types import SimpleNamespace

from app.api.v1.agent import require_agent_user
from app.api.v1.agent_reports import get_report_application
from app.domain.agent.report_errors import report_not_found
from app.main import app
from fastapi.testclient import TestClient


class Dumpable:
    def __init__(self, value: dict[str, object]) -> None:
        self.value = value

    def model_dump(self, *, mode: str) -> dict[str, object]:
        assert mode == "json"
        return self.value


class StubReportService:
    def create_report(self, *, user, body):
        return Dumpable({"report_id": str(uuid.uuid4()), "request_id": body.request_id})

    def list_reports(self, **kwargs):
        return [], 0

    def get_report(self, **kwargs):
        return Dumpable({"report_id": str(kwargs["report_id"])})

    def archive_report(self, **kwargs):
        return Dumpable({"report_id": str(kwargs["report_id"]), "archived_at": "now"})

    def export_report(self, **kwargs):
        extension = "md" if kwargs["export_format"] == "markdown" else "html"
        media_type = (
            "text/markdown; charset=utf-8"
            if extension == "md"
            else "text/html; charset=utf-8"
        )
        return "safe export\n", media_type, f"report.{extension}"

    def create_comparison(self, **kwargs):
        return Dumpable({"comparison_id": str(uuid.uuid4()), "state": "COMPARABLE"})

    def get_comparison(self, **kwargs):
        return Dumpable({"comparison_id": str(kwargs["comparison_id"])})


def _client(service: object) -> TestClient:
    app.dependency_overrides[require_agent_user] = lambda: SimpleNamespace(
        id=uuid.uuid4(), username="report-owner"
    )
    app.dependency_overrides[get_report_application] = lambda: service
    return TestClient(app)


def test_report_api_is_strict_and_returns_safe_export_headers() -> None:
    client = _client(StubReportService())
    try:
        payload = {
            "source_chat_id": str(uuid.uuid4()),
            "source_message_id": str(uuid.uuid4()),
            "report_type": "strategy_review",
            "request_id": "report-request",
        }
        created = client.post("/api/v1/agent/reports", json=payload)
        assert created.status_code == 201
        rejected = client.post(
            "/api/v1/agent/reports", json={**payload, "unknown_field": True}
        )
        assert rejected.status_code == 422

        report_id = uuid.uuid4()
        exported = client.get(
            f"/api/v1/agent/reports/{report_id}/export?format=html"
        )
        assert exported.status_code == 200
        assert exported.headers["x-content-type-options"] == "nosniff"
        assert exported.headers["content-security-policy"].startswith("default-src 'none'")
        assert exported.headers["content-disposition"] == 'attachment; filename="report.html"'
    finally:
        app.dependency_overrides.clear()


def test_owner_hidden_report_maps_to_404() -> None:
    class HiddenService(StubReportService):
        def get_report(self, **kwargs):
            raise report_not_found()

    client = _client(HiddenService())
    try:
        response = client.get(f"/api/v1/agent/reports/{uuid.uuid4()}")
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "REPORT_NOT_FOUND"
    finally:
        app.dependency_overrides.clear()
