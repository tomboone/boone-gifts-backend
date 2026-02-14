from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.dependencies import CurrentUser, DbSession, OwnedList, require_connection
from app.models.list_share import ListShare
from app.schemas.list_share import ListShareCreate, ListShareRead

router = APIRouter(prefix="/lists/{list_id}/shares", tags=["shares"])


@router.post("", response_model=ListShareRead, status_code=status.HTTP_201_CREATED)
def create_share(
    request: ListShareCreate, gift_list: OwnedList, user: CurrentUser, db: DbSession
):
    if request.user_id == user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot share a list with yourself.",
        )
    require_connection(request.user_id, user, db)
    existing = db.execute(
        select(ListShare).where(
            ListShare.list_id == gift_list.id,
            ListShare.user_id == request.user_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT)
    share = ListShare(list_id=gift_list.id, user_id=request.user_id)
    db.add(share)
    db.flush()
    return share


@router.get("", response_model=list[ListShareRead])
def list_shares(gift_list: OwnedList, db: DbSession):
    shares = db.execute(
        select(ListShare).where(ListShare.list_id == gift_list.id)
    ).scalars().all()
    return shares


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_share(user_id: int, gift_list: OwnedList, db: DbSession):
    share = db.execute(
        select(ListShare).where(
            ListShare.list_id == gift_list.id,
            ListShare.user_id == user_id,
        )
    ).scalar_one_or_none()
    if share is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    db.delete(share)
    db.flush()
