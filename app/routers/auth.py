from datetime import datetime, timezone

import jwt
from fastapi import APIRouter, Cookie, HTTPException, Response, status
from sqlalchemy import select

from app.config import settings
from app.dependencies import (
    DbSession,
    create_access_token,
    create_refresh_token,
)
from app.models.invite import Invite
from app.models.user import User
from app.schemas.auth import (
    AccessTokenResponse,
    LoginRequest,
    RegisterRequest,
)

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE_NAME = "boone_refresh_token"
REFRESH_COOKIE_MAX_AGE = settings.refresh_token_expire_days * 86400


def set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=True,
        samesite="none",
        path="/auth",
        max_age=REFRESH_COOKIE_MAX_AGE,
    )


def delete_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        httponly=True,
        secure=True,
        samesite="none",
        path="/auth",
    )


@router.post("/login", response_model=AccessTokenResponse)
def login(request: LoginRequest, response: Response, db: DbSession):
    user = db.execute(
        select(User).where(User.email == request.email)
    ).scalar_one_or_none()

    if user is None or not user.check_password(request.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    set_refresh_cookie(response, create_refresh_token(user))
    return AccessTokenResponse(access_token=create_access_token(user))


@router.post("/register", response_model=AccessTokenResponse)
def register(request: RegisterRequest, response: Response, db: DbSession):
    invite = db.execute(
        select(Invite).where(Invite.token == request.token)
    ).scalar_one_or_none()

    if invite is None or not invite.is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired invite.",
        )

    user = User(
        email=invite.email,
        name=request.name,
        role=invite.role,
        password_hash="",
    )
    user.set_password(request.password)
    db.add(user)

    invite.used_at = datetime.now(timezone.utc)

    db.flush()

    set_refresh_cookie(response, create_refresh_token(user))
    return AccessTokenResponse(access_token=create_access_token(user))


@router.post("/refresh", response_model=AccessTokenResponse)
def refresh(
    response: Response,
    db: DbSession,
    boone_refresh_token: str | None = Cookie(default=None),
):
    if boone_refresh_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    try:
        payload = jwt.decode(
            boone_refresh_token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    set_refresh_cookie(response, create_refresh_token(user))
    return AccessTokenResponse(access_token=create_access_token(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response):
    delete_refresh_cookie(response)
