import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from pwdlib import PasswordHash
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.auth import AppUser, AuthSession

_password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _password_hash.verify(password, password_hash)


def validate_new_password(current_password: str, new_password: str) -> None:
    if len(new_password) < 8:
        raise ValueError("PASSWORD_TOO_SHORT")
    if new_password == current_password:
        raise ValueError("PASSWORD_UNCHANGED")


def authenticate(db: Session, username: str, password: str) -> AppUser | None:
    user = db.query(AppUser).filter(AppUser.username == username).one_or_none()
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        return None
    return user


def create_session(db: Session, user: AppUser, *, hours: int) -> tuple[str, AuthSession]:
    token = secrets.token_urlsafe(48)
    now = datetime.now(UTC)
    session = AuthSession(
        user_id=user.id,
        token_hash=session_token_hash(token),
        created_at=now,
        expires_at=now + timedelta(hours=hours),
        last_seen_at=now,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return token, session


def session_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def revoke_session(db: Session, session: AuthSession) -> None:
    session.revoked_at = datetime.now(UTC)
    db.add(session)
    db.commit()


def revoke_user_sessions(db: Session, user_id) -> None:
    db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


def change_password(db: Session, user: AppUser, current_password: str, new_password: str) -> None:
    if not verify_password(current_password, user.password_hash):
        raise ValueError("INVALID_CURRENT_PASSWORD")
    validate_new_password(current_password, new_password)
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    user.password_changed_at = datetime.now(UTC)
    db.add(user)
    revoke_user_sessions(db, user.id)
    db.commit()


def reset_admin_password(db: Session, username: str, new_password: str) -> AppUser:
    if len(new_password) < 8:
        raise ValueError("PASSWORD_TOO_SHORT")
    user = db.query(AppUser).filter(AppUser.username == username).one_or_none()
    if user is None:
        raise ValueError("ADMIN_NOT_FOUND")
    user.password_hash = hash_password(new_password)
    user.must_change_password = True
    user.password_changed_at = datetime.now(UTC)
    db.add(user)
    revoke_user_sessions(db, user.id)
    db.commit()
    return user
