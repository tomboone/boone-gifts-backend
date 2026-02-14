from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from app.dependencies import AdminUser, DbSession
from app.models.user import User
from app.schemas.user import UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserRead])
def list_users(admin: AdminUser, db: DbSession):
    users = db.execute(select(User)).scalars().all()
    return users


@router.get("/{user_id}", response_model=UserRead)
def get_user(user_id: int, admin: AdminUser, db: DbSession):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return user


@router.put("/{user_id}", response_model=UserRead)
def update_user(user_id: int, updates: UserUpdate, admin: AdminUser, db: DbSession):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(user, field, value)

    db.flush()
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, admin: AdminUser, db: DbSession):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    db.delete(user)
    db.flush()
