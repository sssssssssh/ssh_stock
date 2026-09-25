from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import app.api.v1.auth as auth_api
import app.cli as cli_module
import app.services.auth.bootstrap as bootstrap_module
import app.services.auth.dependencies as auth_dependencies
from app.api.v1.auth import router as auth_router
from app.core.db import get_db
from app.models.auth import AppUser, AuthSession
from app.services.auth.bootstrap import bootstrap_admin
from app.services.auth.dependencies import require_authenticated_user
from app.services.auth.login_guard import InMemoryLoginFailureGuard
from app.services.auth.service import authenticate
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


def _test_app(tmp_path):
    auth_api._login_guard = None
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'auth.db'}",
        connect_args={"check_same_thread": False},
    )
    AppUser.__table__.create(engine)
    AuthSession.__table__.create(engine)
    session_local = sessionmaker(engine, expire_on_commit=False)

    def db_override():
        with session_local() as db:
            yield db

    app = FastAPI()
    app.include_router(auth_router, prefix="/api/v1/auth")
    protected = APIRouter(dependencies=[Depends(require_authenticated_user)])

    @protected.get("/private")
    def private():
        return {"ok": True}

    app.include_router(protected, prefix="/api/v1")
    app.dependency_overrides[get_db] = db_override
    return app, session_local


def _bootstrap(session_local, monkeypatch):
    settings = SimpleNamespace(
        bootstrap_admin_username="admin",
        bootstrap_admin_password="123456",
    )
    monkeypatch.setattr(bootstrap_module, "get_settings", lambda: settings)
    with session_local() as db:
        return bootstrap_admin(db)


def test_bootstrap_admin_is_idempotent_and_hashes_password(tmp_path, monkeypatch) -> None:
    _, session_local = _test_app(tmp_path)
    first = _bootstrap(session_local, monkeypatch)
    original_hash = first.password_hash
    second = _bootstrap(session_local, monkeypatch)

    assert first.id == second.id
    assert original_hash != "123456"
    assert second.password_hash == original_hash
    assert second.must_change_password is True


def test_auth_first_login_change_password_and_logout(tmp_path, monkeypatch) -> None:
    app, session_local = _test_app(tmp_path)
    _bootstrap(session_local, monkeypatch)
    monkeypatch.setattr(
        auth_api,
        "get_settings",
        lambda: SimpleNamespace(auth_session_hours=168, auth_cookie_secure=False),
    )
    client = TestClient(app)

    assert client.get("/api/v1/private").status_code == 401
    login = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "123456"}
    )
    assert login.status_code == 200
    cookie = login.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    assert client.get("/api/v1/auth/me").json()["data"]["must_change_password"] is True
    blocked = client.get("/api/v1/private")
    assert blocked.status_code == 403
    assert blocked.json()["detail"]["code"] == "PASSWORD_CHANGE_REQUIRED"

    changed = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "123456", "new_password": "new-password-123"},
    )
    assert changed.status_code == 200
    assert client.get("/api/v1/private").status_code == 401
    assert client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "123456"}
    ).status_code == 401
    assert client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "new-password-123"},
    ).status_code == 200
    assert client.get("/api/v1/private").status_code == 200
    assert client.post("/api/v1/auth/logout").status_code == 200
    assert client.get("/api/v1/private").status_code == 401

    with session_local() as db:
        user = db.scalar(select(AppUser).where(AppUser.username == "admin"))
        assert user is not None
        assert authenticate(db, "admin", "new-password-123") is not None
        assert db.query(AuthSession).filter(AuthSession.revoked_at.is_not(None)).count() >= 1


def test_secure_cookie_setting(tmp_path, monkeypatch) -> None:
    app, session_local = _test_app(tmp_path)
    _bootstrap(session_local, monkeypatch)
    monkeypatch.setattr(
        auth_api,
        "get_settings",
        lambda: SimpleNamespace(auth_session_hours=168, auth_cookie_secure=True),
    )

    response = TestClient(app).post(
        "/api/v1/auth/login", json={"username": "admin", "password": "123456"}
    )

    assert "Secure" in response.headers["set-cookie"]


def test_expired_session_is_rejected(tmp_path, monkeypatch) -> None:
    app, session_local = _test_app(tmp_path)
    _bootstrap(session_local, monkeypatch)
    monkeypatch.setattr(
        auth_api,
        "get_settings",
        lambda: SimpleNamespace(auth_session_hours=168, auth_cookie_secure=False),
    )
    client = TestClient(app)
    assert client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "123456"}
    ).status_code == 200
    with session_local() as db:
        session = db.scalar(select(AuthSession))
        session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()

    assert client.get("/api/v1/auth/me").status_code == 401


def test_reset_admin_password_cli_only_accepts_hidden_prompt(monkeypatch) -> None:
    calls = []

    class DbContext:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, traceback):
            return False

    def prompt(*args, **kwargs):
        calls.append((args, kwargs))
        return "replacement-password"

    monkeypatch.setattr(cli_module.typer, "prompt", prompt)
    monkeypatch.setattr(cli_module, "SessionLocal", DbContext)
    monkeypatch.setattr(
        cli_module,
        "get_settings",
        lambda: SimpleNamespace(bootstrap_admin_username="admin"),
    )
    monkeypatch.setattr(
        cli_module,
        "reset_admin_password_service",
        lambda db, username, password: calls.append((username, password)),
    )

    cli_module.reset_admin_password()

    assert calls[0][1]["hide_input"] is True
    assert calls[0][1]["confirmation_prompt"] is True
    assert calls[1] == ("admin", "replacement-password")


def test_login_guard_blocks_then_clears_successful_login(tmp_path, monkeypatch) -> None:
    app, session_local = _test_app(tmp_path)
    _bootstrap(session_local, monkeypatch)
    now = [0.0]
    auth_api._login_guard = InMemoryLoginFailureGuard(
        window_seconds=300,
        max_failures=2,
        lockout_seconds=60,
        clock=lambda: now[0],
    )
    monkeypatch.setattr(
        auth_api,
        "get_settings",
        lambda: SimpleNamespace(auth_session_hours=168, auth_cookie_secure=False),
    )
    client = TestClient(app)

    for _ in range(2):
        response = client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": "wrong"}
        )
        assert response.status_code == 401
        assert response.json()["detail"]["code"] == "INVALID_CREDENTIALS"
    blocked = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "123456"}
    )
    assert blocked.status_code == 401

    now[0] = 61
    assert client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "123456"}
    ).status_code == 200


def test_auth_last_seen_is_throttled(tmp_path, monkeypatch) -> None:
    app, session_local = _test_app(tmp_path)
    _bootstrap(session_local, monkeypatch)
    monkeypatch.setattr(
        auth_api,
        "get_settings",
        lambda: SimpleNamespace(auth_session_hours=168, auth_cookie_secure=False),
    )
    monkeypatch.setattr(
        auth_dependencies,
        "get_settings",
        lambda: SimpleNamespace(auth_last_seen_update_minutes=10),
    )
    client = TestClient(app)
    assert client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "123456"}
    ).status_code == 200
    with session_local() as db:
        session = db.scalar(select(AuthSession))
        initial = datetime.now(UTC) - timedelta(minutes=1)
        session.last_seen_at = initial
        db.commit()

    assert client.get("/api/v1/auth/me").status_code == 200
    with session_local() as db:
        assert db.scalar(select(AuthSession)).last_seen_at == initial.replace(tzinfo=None)

    with session_local() as db:
        session = db.scalar(select(AuthSession))
        old = datetime.now(UTC) - timedelta(minutes=20)
        session.last_seen_at = old
        db.commit()
    assert client.get("/api/v1/auth/me").status_code == 200
    with session_local() as db:
        updated = db.scalar(select(AuthSession)).last_seen_at
        assert updated > old.replace(tzinfo=None)
