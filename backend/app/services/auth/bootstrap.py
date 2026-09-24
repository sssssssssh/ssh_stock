from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.auth import AppUser
from app.services.auth.service import hash_password


def bootstrap_admin(db: Session) -> AppUser:
    settings = get_settings()
    username = settings.bootstrap_admin_username
    existing = db.scalar(select(AppUser).where(AppUser.username == username))
    if existing is not None:
        return existing
    user = AppUser(
        username=username,
        password_hash=hash_password(settings.bootstrap_admin_password),
        is_active=True,
        must_change_password=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
