from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import or_, select, update

from app.dependencies import CurrentUser, DbSession
from app.models.collection import Collection
from app.models.collection_item import CollectionItem
from app.models.connection import Connection
from app.models.gift import Gift
from app.models.gift_list import GiftList
from app.models.list_share import ListShare
from app.models.user import User
from app.schemas.connection import ConnectionCreate, ConnectionRead, ConnectionUserRead

router = APIRouter(prefix="/connections", tags=["connections"])


def _build_response(connection: Connection, current_user: User, db) -> dict:
    """Build a ConnectionRead-compatible dict with the other user's info.

    Parameters:
        connection: The connection record.
        current_user: The authenticated user.
        db: Database session.

    Returns:
        Dict matching ConnectionRead schema.
    """
    other_id: int = (
        connection.addressee_id
        if connection.requester_id == current_user.id
        else connection.requester_id
    )
    other_user: User | None = db.get(User, other_id)
    return {
        "id": connection.id,
        "status": connection.status,
        "user": {
            "id": other_user.id,
            "name": other_user.name,
            "email": other_user.email,
        },
        "created_at": connection.created_at,
        "accepted_at": connection.accepted_at,
    }


@router.post("", response_model=ConnectionRead, status_code=status.HTTP_201_CREATED)
def create_connection(
    request: ConnectionCreate, user: CurrentUser, db: DbSession
) -> dict:
    """Send a connection request to another user.

    Parameters:
        request: Connection request with user_id or email.
        user: The authenticated user.
        db: Database session.

    Returns:
        The created connection.

    Raises:
        HTTPException: 400 if targeting yourself, 404 if user not found, 409 if duplicate.
    """
    target: User | None
    if request.user_id is not None:
        target = db.get(User, request.user_id)
    else:
        target = db.execute(
            select(User).where(User.email == request.email)
        ).scalar_one_or_none()

    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    if target.id == user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot connect with yourself.",
        )

    existing: Connection | None = db.execute(
        select(Connection).where(
            or_(
                (Connection.requester_id == user.id)
                & (Connection.addressee_id == target.id),
                (Connection.requester_id == target.id)
                & (Connection.addressee_id == user.id),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT)

    connection: Connection = Connection(
        requester_id=user.id, addressee_id=target.id
    )
    db.add(connection)
    db.flush()
    return _build_response(connection, user, db)


@router.get("", response_model=list[ConnectionRead])
def list_connections(user: CurrentUser, db: DbSession) -> list[dict]:
    """List all accepted connections for the current user.

    Parameters:
        user: The authenticated user.
        db: Database session.

    Returns:
        List of accepted connections.
    """
    connections: list[Connection] = db.execute(
        select(Connection).where(
            Connection.status == "accepted",
            or_(
                Connection.requester_id == user.id,
                Connection.addressee_id == user.id,
            ),
        )
    ).scalars().all()
    return [_build_response(c, user, db) for c in connections]


@router.get("/requests", response_model=list[ConnectionRead])
def list_requests(user: CurrentUser, db: DbSession) -> list[dict]:
    """List pending connection requests received by the current user.

    Parameters:
        user: The authenticated user.
        db: Database session.

    Returns:
        List of pending incoming requests.
    """
    connections: list[Connection] = db.execute(
        select(Connection).where(
            Connection.status == "pending",
            Connection.addressee_id == user.id,
        )
    ).scalars().all()
    return [_build_response(c, user, db) for c in connections]


@router.post("/{connection_id}/accept", response_model=ConnectionRead)
def accept_connection(
    connection_id: int, user: CurrentUser, db: DbSession
) -> dict:
    """Accept a pending connection request.

    Parameters:
        connection_id: The connection to accept.
        user: The authenticated user.
        db: Database session.

    Returns:
        The updated connection.

    Raises:
        HTTPException: 404 if not found, 403 if not addressee, 409 if already accepted.
    """
    connection: Connection | None = db.get(Connection, connection_id)
    if connection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if connection.addressee_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    if connection.status == "accepted":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT)
    connection.status = "accepted"
    connection.accepted_at = datetime.now(timezone.utc)
    db.flush()
    return _build_response(connection, user, db)


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_connection(
    connection_id: int, user: CurrentUser, db: DbSession
) -> None:
    """Remove a connection or reject/cancel a request.

    Parameters:
        connection_id: The connection to delete.
        user: The authenticated user.
        db: Database session.

    Raises:
        HTTPException: 404 if not found, 403 if not a party to the connection.
    """
    connection: Connection | None = db.get(Connection, connection_id)
    if connection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if connection.requester_id != user.id and connection.addressee_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    if connection.status == "accepted":
        user_a: int = connection.requester_id
        user_b: int = connection.addressee_id

        list_ids_a = select(GiftList.id).where(GiftList.owner_id == user_a)
        list_ids_b = select(GiftList.id).where(GiftList.owner_id == user_b)

        # Unclaim gifts claimed by user_b on user_a's lists
        db.execute(
            update(Gift)
            .where(Gift.list_id.in_(list_ids_a), Gift.claimed_by_id == user_b)
            .values(claimed_by_id=None, claimed_at=None)
        )
        # Unclaim gifts claimed by user_a on user_b's lists
        db.execute(
            update(Gift)
            .where(Gift.list_id.in_(list_ids_b), Gift.claimed_by_id == user_a)
            .values(claimed_by_id=None, claimed_at=None)
        )

        # Revoke shares between both users
        shares_to_delete: list[ListShare] = db.execute(
            select(ListShare).where(
                or_(
                    (ListShare.list_id.in_(list_ids_a))
                    & (ListShare.user_id == user_b),
                    (ListShare.list_id.in_(list_ids_b))
                    & (ListShare.user_id == user_a),
                )
            )
        ).scalars().all()
        for share in shares_to_delete:
            db.delete(share)

        # Remove collection items for both users referencing each other's lists
        collection_ids_a = select(Collection.id).where(
            Collection.owner_id == user_a
        )
        collection_ids_b = select(Collection.id).where(
            Collection.owner_id == user_b
        )
        collection_items_to_delete = db.execute(
            select(CollectionItem).where(
                or_(
                    (CollectionItem.collection_id.in_(collection_ids_a))
                    & (CollectionItem.list_id.in_(list_ids_b)),
                    (CollectionItem.collection_id.in_(collection_ids_b))
                    & (CollectionItem.list_id.in_(list_ids_a)),
                )
            )
        ).scalars().all()
        for ci in collection_items_to_delete:
            db.delete(ci)

    db.delete(connection)
    db.flush()
