from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.dependencies import AdminUser, DbSession
from app.models.invite import Invite
from app.schemas.invite import InviteCreate, InviteRead

router = APIRouter(prefix="/invites", tags=["invites"])


@router.post("", response_model=InviteRead, status_code=status.HTTP_201_CREATED)
def create_invite(request: InviteCreate, admin: AdminUser, db: DbSession):
    invite = Invite(
        email=request.email,
        role=request.role,
        expires_at=datetime.now(timezone.utc) + timedelta(days=request.expires_in_days),
        invited_by_id=admin.id,
    )
    db.add(invite)
    db.flush()
    return invite


@router.get("", response_model=list[InviteRead])
def list_invites(admin: AdminUser, db: DbSession):
    invites = db.execute(select(Invite)).scalars().all()
    return invites


@router.delete("/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_invite(invite_id: int, admin: AdminUser, db: DbSession):
    invite = db.get(Invite, invite_id)
    if invite is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    db.delete(invite)
    db.flush()
