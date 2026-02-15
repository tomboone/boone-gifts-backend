from fastapi import APIRouter, Query, status
from sqlalchemy import select, or_

from app.dependencies import CurrentUser, DbSession, OwnedList, ViewableList
from app.models.gift_list import GiftList
from app.models.list_share import ListShare
from app.schemas.gift_list import (
    GiftListCreate,
    GiftListDetailOwner,
    GiftListDetailViewer,
    GiftListRead,
    GiftListUpdate,
)

router = APIRouter(prefix="/lists", tags=["lists"])


@router.post("", response_model=GiftListRead, status_code=status.HTTP_201_CREATED)
def create_list(request: GiftListCreate, user: CurrentUser, db: DbSession):
    gift_list = GiftList(
        name=request.name,
        description=request.description,
        owner_id=user.id,
    )
    db.add(gift_list)
    db.flush()
    return gift_list


@router.get("", response_model=list[GiftListRead])
def list_lists(
    user: CurrentUser,
    db: DbSession,
    filter: str | None = Query(default=None, pattern="^(owned|shared)$"),
):
    if filter == "owned":
        query = select(GiftList).where(GiftList.owner_id == user.id)
    elif filter == "shared":
        shared_list_ids = select(ListShare.list_id).where(
            ListShare.user_id == user.id
        )
        query = select(GiftList).where(GiftList.id.in_(shared_list_ids))
    else:
        shared_list_ids = select(ListShare.list_id).where(
            ListShare.user_id == user.id
        )
        query = select(GiftList).where(
            or_(
                GiftList.owner_id == user.id,
                GiftList.id.in_(shared_list_ids),
            )
        )
    return db.execute(query).scalars().all()


@router.get("/{list_id}")
def get_list(gift_list: ViewableList, user: CurrentUser):
    if gift_list.owner_id == user.id:
        return GiftListDetailOwner.model_validate(gift_list)
    return GiftListDetailViewer.model_validate(gift_list)


@router.put("/{list_id}", response_model=GiftListRead)
def update_list(
    updates: GiftListUpdate, gift_list: OwnedList, db: DbSession
):
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(gift_list, field, value)
    db.flush()
    return gift_list


@router.delete("/{list_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_list(gift_list: OwnedList, db: DbSession):
    db.delete(gift_list)
    db.flush()
