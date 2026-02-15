from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.dependencies import CurrentUser, DbSession, OwnedCollection
from app.models.collection import Collection
from app.models.collection_item import CollectionItem
from app.models.gift_list import GiftList
from app.models.list_share import ListShare
from app.schemas.collection import (
    CollectionCreate,
    CollectionDetail,
    CollectionItemCreate,
    CollectionRead,
    CollectionUpdate,
)

router = APIRouter(prefix="/collections", tags=["collections"])


@router.post("", response_model=CollectionRead, status_code=status.HTTP_201_CREATED)
def create_collection(
    request: CollectionCreate, user: CurrentUser, db: DbSession
):
    """Create a new collection.

    Parameters:
        request: Collection name and optional description.
        user: The authenticated user.
        db: Database session.

    Returns:
        The created collection.
    """
    collection: Collection = Collection(
        name=request.name,
        description=request.description,
        owner_id=user.id,
    )
    db.add(collection)
    db.flush()
    return collection


@router.get("", response_model=list[CollectionRead])
def list_collections(user: CurrentUser, db: DbSession):
    """List all collections owned by the current user.

    Parameters:
        user: The authenticated user.
        db: Database session.

    Returns:
        List of collections.
    """
    collections: list[Collection] = db.execute(
        select(Collection).where(Collection.owner_id == user.id)
    ).scalars().all()
    return collections


@router.get("/{collection_id}", response_model=CollectionDetail)
def get_collection(collection: OwnedCollection, db: DbSession):
    """Get a collection with its lists.

    Parameters:
        collection: The collection (verified owner).
        db: Database session.

    Returns:
        Collection detail with lists.
    """
    list_ids: list[int] = [item.list_id for item in collection.items]
    lists: list[GiftList] = []
    if list_ids:
        lists = db.execute(
            select(GiftList).where(GiftList.id.in_(list_ids))
        ).scalars().all()
    return {
        "id": collection.id,
        "name": collection.name,
        "description": collection.description,
        "owner_id": collection.owner_id,
        "lists": lists,
        "created_at": collection.created_at,
        "updated_at": collection.updated_at,
    }


@router.put("/{collection_id}", response_model=CollectionRead)
def update_collection(
    request: CollectionUpdate, collection: OwnedCollection, db: DbSession
):
    """Update a collection's name or description.

    Parameters:
        request: Fields to update.
        collection: The collection (verified owner).
        db: Database session.

    Returns:
        The updated collection.
    """
    update_data: dict = request.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(collection, key, value)
    db.flush()
    return collection


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_collection(collection: OwnedCollection, db: DbSession):
    """Delete a collection and its items.

    Parameters:
        collection: The collection (verified owner).
        db: Database session.
    """
    db.delete(collection)
    db.flush()


@router.post(
    "/{collection_id}/items",
    status_code=status.HTTP_201_CREATED,
)
def add_item(
    request: CollectionItemCreate,
    collection: OwnedCollection,
    user: CurrentUser,
    db: DbSession,
):
    """Add a list to a collection.

    Parameters:
        request: The list_id to add.
        collection: The collection (verified owner).
        user: The authenticated user.
        db: Database session.

    Raises:
        HTTPException: 404 if list not found, 403 if no access, 409 if duplicate.
    """
    gift_list: GiftList | None = db.get(GiftList, request.list_id)
    if gift_list is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if gift_list.owner_id != user.id:
        share: ListShare | None = db.execute(
            select(ListShare).where(
                ListShare.list_id == request.list_id,
                ListShare.user_id == user.id,
            )
        ).scalar_one_or_none()
        if share is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    existing: CollectionItem | None = db.execute(
        select(CollectionItem).where(
            CollectionItem.collection_id == collection.id,
            CollectionItem.list_id == request.list_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT)

    item: CollectionItem = CollectionItem(
        collection_id=collection.id, list_id=request.list_id
    )
    db.add(item)
    db.flush()


@router.delete(
    "/{collection_id}/items/{list_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_item(
    list_id: int, collection: OwnedCollection, db: DbSession
):
    """Remove a list from a collection.

    Parameters:
        list_id: The list to remove.
        collection: The collection (verified owner).
        db: Database session.

    Raises:
        HTTPException: 404 if the list is not in the collection.
    """
    item: CollectionItem | None = db.execute(
        select(CollectionItem).where(
            CollectionItem.collection_id == collection.id,
            CollectionItem.list_id == list_id,
        )
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    db.delete(item)
    db.flush()
