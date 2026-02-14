from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status

from app.dependencies import CurrentUser, DbSession, OwnedList, ViewableList
from app.models.gift import Gift
from app.schemas.gift import GiftCreate, GiftUpdate
from app.schemas.gift_list import GiftOwnerRead, GiftRead

router = APIRouter(prefix="/lists/{list_id}/gifts", tags=["gifts"])


@router.post("", response_model=GiftOwnerRead, status_code=status.HTTP_201_CREATED)
def create_gift(request: GiftCreate, gift_list: OwnedList, db: DbSession):
    gift = Gift(
        list_id=gift_list.id,
        name=request.name,
        description=request.description,
        url=request.url,
        price=request.price,
    )
    db.add(gift)
    db.flush()
    return gift


@router.put("/{gift_id}", response_model=GiftOwnerRead)
def update_gift(
    gift_id: int, updates: GiftUpdate, gift_list: OwnedList, db: DbSession
):
    gift = db.get(Gift, gift_id)
    if gift is None or gift.list_id != gift_list.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(gift, field, value)
    db.flush()
    return gift


@router.delete("/{gift_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_gift(gift_id: int, gift_list: OwnedList, db: DbSession):
    gift = db.get(Gift, gift_id)
    if gift is None or gift.list_id != gift_list.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if gift.claimed_by_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This gift cannot be deleted right now.",
        )
    db.delete(gift)
    db.flush()


@router.post("/{gift_id}/claim", response_model=GiftRead)
def claim_gift(
    gift_id: int, gift_list: ViewableList, user: CurrentUser, db: DbSession
):
    if gift_list.owner_id == user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    gift = db.get(Gift, gift_id)
    if gift is None or gift.list_id != gift_list.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if gift.claimed_by_id is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT)
    gift.claimed_by_id = user.id
    gift.claimed_at = datetime.now(timezone.utc)
    db.flush()
    return gift


@router.delete("/{gift_id}/claim", response_model=GiftRead)
def unclaim_gift(
    gift_id: int, gift_list: ViewableList, user: CurrentUser, db: DbSession
):
    gift = db.get(Gift, gift_id)
    if gift is None or gift.list_id != gift_list.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if gift.claimed_by_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    gift.claimed_by_id = None
    gift.claimed_at = None
    db.flush()
    return gift
