from datetime import UTC, datetime, timedelta

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.models.auth import AppUser, AuthSession
from app.services.auth.service import session_token_hash

SESSION_COOKIE = "ssh_stock_session"


def _auth_error(status_code: int, code: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code})


def require_auth_session(
    token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    db: Session = Depends(get_db),
) -> tuple[AppUser, AuthSession]:
    if not token:
        raise _auth_error(401, "AUTHENTICATION_REQUIRED")
    row = db.execute(
        select(AppUser, AuthSession)
        .join(AuthSession, AuthSession.user_id == AppUser.id)
        .where(AuthSession.token_hash == session_token_hash(token))
    ).first()
    now = datetime.now(UTC)
    user, auth_session = (row[0], row[1]) if row is not None else (None, None)
    expires_at = auth_session.expires_at if auth_session is not None else now
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if (
        row is None
        or not user.is_active
        or auth_session.revoked_at is not None
        or expires_at <= now
    ):
        raise _auth_error(401, "INVALID_SESSION")
    last_seen_at = auth_session.last_seen_at
    if last_seen_at.tzinfo is None:
        last_seen_at = last_seen_at.replace(tzinfo=UTC)
    update_interval = timedelta(minutes=get_settings().auth_last_seen_update_minutes)
    if now - last_seen_at >= update_interval:
        auth_session.last_seen_at = now
        db.add(auth_session)
        db.commit()
    return user, auth_session


def require_authenticated_user(
    auth: tuple[AppUser, AuthSession] = Depends(require_auth_session),
) -> AppUser:
    user, _ = auth
    if user.must_change_password:
        raise _auth_error(403, "PASSWORD_CHANGE_REQUIRED")
    return user
