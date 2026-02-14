from datetime import datetime, timezone

import jwt
from fastapi import APIRouter, HTTPException, status
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
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, db: DbSession):
    user = db.execute(
        select(User).where(User.email == request.email)
    ).scalar_one_or_none()

    if user is None or not user.check_password(request.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    return TokenResponse(
        access_token=create_access_token(user),
        refresh_token=create_refresh_token(user),
    )


@router.post("/register", response_model=TokenResponse)
def register(request: RegisterRequest, db: DbSession):
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

    return TokenResponse(
        access_token=create_access_token(user),
        refresh_token=create_refresh_token(user),
    )


@router.post("/refresh", response_model=AccessTokenResponse)
def refresh(request: RefreshRequest, db: DbSession):
    try:
        payload = jwt.decode(
            request.refresh_token,
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

    return AccessTokenResponse(access_token=create_access_token(user))
