from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.v1.common import envelope
from app.core.config import get_settings
from app.core.db import get_db
from app.models.auth import AppUser, AuthSession
from app.services.auth.dependencies import SESSION_COOKIE, require_auth_session
from app.services.auth.service import (
    authenticate,
    change_password,
    create_session,
    revoke_session,
)

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


def _user_payload(user: AppUser) -> dict[str, object]:
    return {
        "username": user.username,
        "must_change_password": user.must_change_password,
    }


@router.post("/login")
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = authenticate(db, payload.username, payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail={"code": "INVALID_CREDENTIALS"})
    settings = get_settings()
    token, _ = create_session(db, user, hours=settings.auth_session_hours)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="strict",
        path="/",
        max_age=settings.auth_session_hours * 3600,
    )
    return envelope(_user_payload(user))


@router.get("/me")
def me(auth: Annotated[tuple[AppUser, AuthSession], Depends(require_auth_session)]):
    return envelope(_user_payload(auth[0]))


@router.post("/change-password")
def change_password_endpoint(
    payload: ChangePasswordRequest,
    response: Response,
    auth: Annotated[tuple[AppUser, AuthSession], Depends(require_auth_session)],
    db: Session = Depends(get_db),
):
    try:
        change_password(db, auth[0], payload.current_password, payload.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": str(exc)}) from exc
    response.delete_cookie(SESSION_COOKIE, path="/")
    return envelope({"password_changed": True, "login_required": True})


@router.post("/logout")
def logout(
    response: Response,
    auth: Annotated[tuple[AppUser, AuthSession], Depends(require_auth_session)],
    db: Session = Depends(get_db),
):
    revoke_session(db, auth[1])
    response.delete_cookie(SESSION_COOKIE, path="/")
    return envelope({"logged_out": True})
