# Gift Lists Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement gift lists with per-user sharing and hidden claim tracking, so users can create wishlists, share them with specific people, and those people can claim gifts without the list owner knowing.

**Architecture:** Three new SQLAlchemy models (GiftList, Gift, ListShare) with nested REST endpoints under `/lists`. Authorization uses two reusable dependencies (`get_list_for_owner`, `get_list_for_viewer`) that check ownership or share access. Gift claim info is filtered from responses when the requester is the list owner.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (Mapped columns), Pydantic v2, pytest + FastAPI TestClient

**Additional concerns:** See `docs/plans/2026-02-14-gift-lists-design.md` for the full design document.

---

### Task 1: GiftList Model

**Context:** The model is named `GiftList` (not `List`) to avoid shadowing Python's built-in. The table name is `lists`.

**Files to create:**
- `app/models/gift_list.py`
- `tests/models/test_gift_list.py`

**Files to modify:**
- `app/models/__init__.py`

**Step 1: Write the failing tests**

`tests/models/test_gift_list.py`:
```python
from app.models.gift_list import GiftList
from app.models.user import User


def test_create_gift_list(db):
    owner = User(email="owner@test.com", name="Owner", password_hash="h")
    db.add(owner)
    db.flush()

    gift_list = GiftList(
        name="Christmas 2026",
        description="My holiday wishlist",
        owner_id=owner.id,
    )
    db.add(gift_list)
    db.flush()

    assert gift_list.id is not None
    assert gift_list.name == "Christmas 2026"
    assert gift_list.description == "My holiday wishlist"
    assert gift_list.owner_id == owner.id
    assert gift_list.created_at is not None
    assert gift_list.updated_at is not None


def test_create_gift_list_no_description(db):
    owner = User(email="owner2@test.com", name="Owner", password_hash="h")
    db.add(owner)
    db.flush()

    gift_list = GiftList(name="Birthday", owner_id=owner.id)
    db.add(gift_list)
    db.flush()

    assert gift_list.id is not None
    assert gift_list.description is None
```

**Step 2: Run tests to verify they fail**

Run: `task app:test-file -- tests/models/test_gift_list.py -v`
Expected: ImportError — `app.models.gift_list` does not exist yet.

**Step 3: Write the implementation**

`app/models/gift_list.py`:
```python
from datetime import datetime

from sqlalchemy import ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class GiftList(Base):
    __tablename__ = "lists"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String(500), default=None)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )
```

Update `app/models/__init__.py`:
```python
from app.models.user import User
from app.models.invite import Invite
from app.models.gift_list import GiftList

__all__ = ["User", "Invite", "GiftList"]
```

**Step 4: Run tests to verify they pass**

Run: `task app:test-file -- tests/models/test_gift_list.py -v`
Expected: 2 passed.

**Step 5: Run full suite to check for regressions**

Run: `task app:test`
Expected: 37 passed (35 existing + 2 new).

---

### Task 2: Gift Model

**Context:** Gift always belongs to a list. Has nullable fields for description, url, price, and claim tracking (claimed_by_id, claimed_at). Price uses `Numeric(10, 2)` for MySQL `DECIMAL(10,2)`.

**Files to create:**
- `app/models/gift.py`
- `tests/models/test_gift.py`

**Files to modify:**
- `app/models/__init__.py`

**Step 1: Write the failing tests**

`tests/models/test_gift.py`:
```python
from decimal import Decimal

from app.models.gift import Gift
from app.models.gift_list import GiftList
from app.models.user import User


def test_create_gift(db):
    owner = User(email="owner@test.com", name="Owner", password_hash="h")
    db.add(owner)
    db.flush()

    gift_list = GiftList(name="Birthday", owner_id=owner.id)
    db.add(gift_list)
    db.flush()

    gift = Gift(
        list_id=gift_list.id,
        name="Book",
        description="A good book",
        url="https://example.com/book",
        price=Decimal("19.99"),
    )
    db.add(gift)
    db.flush()

    assert gift.id is not None
    assert gift.list_id == gift_list.id
    assert gift.name == "Book"
    assert gift.description == "A good book"
    assert gift.url == "https://example.com/book"
    assert gift.price == Decimal("19.99")
    assert gift.claimed_by_id is None
    assert gift.claimed_at is None
    assert gift.created_at is not None
    assert gift.updated_at is not None


def test_create_gift_minimal(db):
    owner = User(email="owner2@test.com", name="Owner", password_hash="h")
    db.add(owner)
    db.flush()

    gift_list = GiftList(name="Minimal", owner_id=owner.id)
    db.add(gift_list)
    db.flush()

    gift = Gift(list_id=gift_list.id, name="Surprise")
    db.add(gift)
    db.flush()

    assert gift.id is not None
    assert gift.description is None
    assert gift.url is None
    assert gift.price is None


def test_claim_gift(db):
    owner = User(email="owner3@test.com", name="Owner", password_hash="h")
    claimer = User(email="claimer@test.com", name="Claimer", password_hash="h")
    db.add_all([owner, claimer])
    db.flush()

    gift_list = GiftList(name="Claims", owner_id=owner.id)
    db.add(gift_list)
    db.flush()

    gift = Gift(list_id=gift_list.id, name="Gadget")
    db.add(gift)
    db.flush()

    assert gift.claimed_by_id is None

    gift.claimed_by_id = claimer.id
    db.flush()

    assert gift.claimed_by_id == claimer.id
```

**Step 2: Run tests to verify they fail**

Run: `task app:test-file -- tests/models/test_gift.py -v`
Expected: ImportError — `app.models.gift` does not exist yet.

**Step 3: Write the implementation**

`app/models/gift.py`:
```python
from datetime import datetime

from sqlalchemy import ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Gift(Base):
    __tablename__ = "gifts"

    id: Mapped[int] = mapped_column(primary_key=True)
    list_id: Mapped[int] = mapped_column(ForeignKey("lists.id"))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String(500), default=None)
    url: Mapped[str | None] = mapped_column(String(2048), default=None)
    price: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), default=None
    )
    claimed_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), default=None
    )
    claimed_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )
```

Add the missing import at the top of `app/models/gift.py`:
```python
from decimal import Decimal
```

Update `app/models/__init__.py`:
```python
from app.models.user import User
from app.models.invite import Invite
from app.models.gift_list import GiftList
from app.models.gift import Gift

__all__ = ["User", "Invite", "GiftList", "Gift"]
```

**Step 4: Run tests to verify they pass**

Run: `task app:test-file -- tests/models/test_gift.py -v`
Expected: 3 passed.

**Step 5: Run full suite**

Run: `task app:test`
Expected: 40 passed (37 + 3 new).

---

### Task 3: ListShare Model

**Context:** Join table for sharing lists with specific users. Has a unique constraint on (list_id, user_id) to prevent duplicate shares.

**Files to create:**
- `app/models/list_share.py`
- `tests/models/test_list_share.py`

**Files to modify:**
- `app/models/__init__.py`

**Step 1: Write the failing tests**

`tests/models/test_list_share.py`:
```python
import sqlalchemy

import pytest

from app.models.gift_list import GiftList
from app.models.list_share import ListShare
from app.models.user import User


def test_create_list_share(db):
    owner = User(email="owner@test.com", name="Owner", password_hash="h")
    viewer = User(email="viewer@test.com", name="Viewer", password_hash="h")
    db.add_all([owner, viewer])
    db.flush()

    gift_list = GiftList(name="Shared List", owner_id=owner.id)
    db.add(gift_list)
    db.flush()

    share = ListShare(list_id=gift_list.id, user_id=viewer.id)
    db.add(share)
    db.flush()

    assert share.id is not None
    assert share.list_id == gift_list.id
    assert share.user_id == viewer.id
    assert share.created_at is not None


def test_list_share_unique_constraint(db):
    owner = User(email="owner2@test.com", name="Owner", password_hash="h")
    viewer = User(email="viewer2@test.com", name="Viewer", password_hash="h")
    db.add_all([owner, viewer])
    db.flush()

    gift_list = GiftList(name="Dupe Test", owner_id=owner.id)
    db.add(gift_list)
    db.flush()

    share1 = ListShare(list_id=gift_list.id, user_id=viewer.id)
    db.add(share1)
    db.flush()

    share2 = ListShare(list_id=gift_list.id, user_id=viewer.id)
    db.add(share2)

    with pytest.raises(sqlalchemy.exc.IntegrityError):
        db.flush()
```

**Step 2: Run tests to verify they fail**

Run: `task app:test-file -- tests/models/test_list_share.py -v`
Expected: ImportError — `app.models.list_share` does not exist yet.

**Step 3: Write the implementation**

`app/models/list_share.py`:
```python
from datetime import datetime

from sqlalchemy import ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ListShare(Base):
    __tablename__ = "list_shares"
    __table_args__ = (
        UniqueConstraint("list_id", "user_id", name="uq_list_shares_list_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    list_id: Mapped[int] = mapped_column(ForeignKey("lists.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
```

Update `app/models/__init__.py`:
```python
from app.models.user import User
from app.models.invite import Invite
from app.models.gift_list import GiftList
from app.models.gift import Gift
from app.models.list_share import ListShare

__all__ = ["User", "Invite", "GiftList", "Gift", "ListShare"]
```

**Step 4: Run tests to verify they pass**

Run: `task app:test-file -- tests/models/test_list_share.py -v`
Expected: 2 passed.

**Step 5: Run full suite**

Run: `task app:test`
Expected: 42 passed (40 + 2 new).

---

### Task 4: Schemas

**Context:** Create Pydantic schemas for lists, gifts, and shares. Gift has two read variants: `GiftRead` (with claim info, for shared users) and `GiftOwnerRead` (without claim info, for the list owner). List read schemas embed gifts.

**Files to create:**
- `app/schemas/gift_list.py`
- `app/schemas/gift.py`
- `app/schemas/list_share.py`

**Step 1: Create `app/schemas/gift_list.py`**

```python
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class GiftListCreate(BaseModel):
    name: str
    description: str | None = None


class GiftListUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class GiftOwnerRead(BaseModel):
    id: int
    name: str
    description: str | None
    url: str | None
    price: Decimal | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GiftRead(BaseModel):
    id: int
    name: str
    description: str | None
    url: str | None
    price: Decimal | None
    claimed_by_id: int | None
    claimed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GiftListRead(BaseModel):
    id: int
    name: str
    description: str | None
    owner_id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GiftListDetailOwner(BaseModel):
    id: int
    name: str
    description: str | None
    owner_id: int
    gifts: list[GiftOwnerRead]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GiftListDetailViewer(BaseModel):
    id: int
    name: str
    description: str | None
    owner_id: int
    gifts: list[GiftRead]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
```

**Step 2: Create `app/schemas/gift.py`**

```python
from decimal import Decimal

from pydantic import BaseModel


class GiftCreate(BaseModel):
    name: str
    description: str | None = None
    url: str | None = None
    price: Decimal | None = None


class GiftUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    url: str | None = None
    price: Decimal | None = None
```

**Step 3: Create `app/schemas/list_share.py`**

```python
from datetime import datetime

from pydantic import BaseModel


class ListShareCreate(BaseModel):
    user_id: int


class ListShareRead(BaseModel):
    id: int
    list_id: int
    user_id: int
    created_at: datetime

    model_config = {"from_attributes": True}
```

**Step 4: Verify no import errors**

Run: `task app:test`
Expected: 42 passed (no regressions). Schemas are validated through router tests later.

---

### Task 5: List Access Dependencies

**Context:** Two reusable dependencies for list authorization. These are used by all three routers (lists, gifts, shares) so they go in `app/dependencies.py`. The GiftList model needs a `gifts` relationship for the detail endpoints to work with `from_attributes`.

**Files to modify:**
- `app/dependencies.py`
- `app/models/gift_list.py`

**Step 1: Add `gifts` relationship to GiftList**

Update `app/models/gift_list.py` to add a relationship that loads associated gifts:
```python
from datetime import datetime

from sqlalchemy import ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class GiftList(Base):
    __tablename__ = "lists"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String(500), default=None)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    gifts: Mapped[list["Gift"]] = relationship(
        "Gift", lazy="selectin", cascade="all, delete-orphan"
    )
```

The `lazy="selectin"` ensures gifts are eagerly loaded when the list is queried (avoids N+1). The `cascade="all, delete-orphan"` ensures deleting a list deletes its gifts.

**Step 2: Add list access dependencies to `app/dependencies.py`**

Append to the end of `app/dependencies.py`:
```python
from app.models.gift_list import GiftList
from app.models.list_share import ListShare


def get_list_for_owner(
    list_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: DbSession,
) -> GiftList:
    gift_list = db.get(GiftList, list_id)
    if gift_list is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if gift_list.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return gift_list


def get_list_for_viewer(
    list_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: DbSession,
) -> GiftList:
    gift_list = db.get(GiftList, list_id)
    if gift_list is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if gift_list.owner_id == user.id:
        return gift_list
    share = db.execute(
        select(ListShare).where(
            ListShare.list_id == list_id,
            ListShare.user_id == user.id,
        )
    ).scalar_one_or_none()
    if share is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return gift_list


OwnedList = Annotated[GiftList, Depends(get_list_for_owner)]
ViewableList = Annotated[GiftList, Depends(get_list_for_viewer)]
```

Also add the missing `select` import — add it to the existing imports at the top of `app/dependencies.py`:
```python
from sqlalchemy import select
```

**Step 3: Verify no import errors**

Run: `task app:test`
Expected: 42 passed (no regressions).

---

### Task 6: Lists Router and Tests

**Context:** CRUD endpoints for lists. Any authenticated user can create lists and view lists they own or have been shared. Only the owner can update or delete. The GET single list endpoint returns gifts — with claim info filtered based on whether the requester is the owner.

**Files to create:**
- `app/routers/lists.py`
- `tests/routers/test_lists.py`

**Files to modify:**
- `app/main.py`
- `tests/conftest.py`

**Step 1: Add test fixtures to `tests/conftest.py`**

Add these fixtures at the end of `tests/conftest.py`:
```python
from app.models.gift_list import GiftList
from app.models.list_share import ListShare


@pytest.fixture
def sample_list(db, member_user):
    gift_list = GiftList(name="Member's Wishlist", owner_id=member_user.id)
    db.add(gift_list)
    db.flush()
    return gift_list


@pytest.fixture
def shared_list(db, sample_list, admin_user):
    share = ListShare(list_id=sample_list.id, user_id=admin_user.id)
    db.add(share)
    db.flush()
    return sample_list
```

**Step 2: Write the failing tests**

`tests/routers/test_lists.py`:
```python
def test_create_list(client, member_user, member_headers):
    response = client.post(
        "/lists",
        headers=member_headers,
        json={"name": "Birthday", "description": "My birthday list"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Birthday"
    assert data["description"] == "My birthday list"
    assert data["owner_id"] == member_user.id


def test_create_list_no_description(client, member_user, member_headers):
    response = client.post(
        "/lists",
        headers=member_headers,
        json={"name": "Minimal"},
    )
    assert response.status_code == 201
    assert response.json()["description"] is None


def test_create_list_unauthenticated(client):
    response = client.post("/lists", json={"name": "Nope"})
    assert response.status_code == 403


def test_list_lists_owned(client, member_user, member_headers, sample_list):
    response = client.get("/lists", headers=member_headers)
    assert response.status_code == 200
    names = [l["name"] for l in response.json()]
    assert "Member's Wishlist" in names


def test_list_lists_shared(client, admin_user, admin_headers, shared_list):
    response = client.get("/lists", headers=admin_headers)
    assert response.status_code == 200
    names = [l["name"] for l in response.json()]
    assert "Member's Wishlist" in names


def test_list_lists_excludes_unshared(client, admin_user, admin_headers, sample_list):
    response = client.get("/lists", headers=admin_headers)
    assert response.status_code == 200
    names = [l["name"] for l in response.json()]
    assert "Member's Wishlist" not in names


def test_get_list_as_owner(client, member_user, member_headers, sample_list):
    response = client.get(f"/lists/{sample_list.id}", headers=member_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Member's Wishlist"
    assert "gifts" in data


def test_get_list_as_shared_user(client, admin_user, admin_headers, shared_list):
    response = client.get(f"/lists/{shared_list.id}", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["name"] == "Member's Wishlist"


def test_get_list_forbidden(client, admin_user, admin_headers, sample_list):
    response = client.get(f"/lists/{sample_list.id}", headers=admin_headers)
    assert response.status_code == 403


def test_get_list_not_found(client, member_headers):
    response = client.get("/lists/99999", headers=member_headers)
    assert response.status_code == 404


def test_update_list_as_owner(client, member_headers, sample_list):
    response = client.put(
        f"/lists/{sample_list.id}",
        headers=member_headers,
        json={"name": "Updated Name"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Updated Name"


def test_update_list_as_shared_user(client, admin_headers, shared_list):
    response = client.put(
        f"/lists/{shared_list.id}",
        headers=admin_headers,
        json={"name": "Hacked"},
    )
    assert response.status_code == 403


def test_delete_list_as_owner(client, member_headers, sample_list):
    response = client.delete(f"/lists/{sample_list.id}", headers=member_headers)
    assert response.status_code == 204


def test_delete_list_as_shared_user(client, admin_headers, shared_list):
    response = client.delete(f"/lists/{shared_list.id}", headers=admin_headers)
    assert response.status_code == 403
```

**Step 3: Run tests to verify they fail**

Run: `task app:test-file -- tests/routers/test_lists.py -v`
Expected: Failures — no routes defined yet.

**Step 4: Write the implementation**

`app/routers/lists.py`:
```python
from fastapi import APIRouter, status
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
def list_lists(user: CurrentUser, db: DbSession):
    shared_list_ids = select(ListShare.list_id).where(
        ListShare.user_id == user.id
    )
    lists = db.execute(
        select(GiftList).where(
            or_(
                GiftList.owner_id == user.id,
                GiftList.id.in_(shared_list_ids),
            )
        )
    ).scalars().all()
    return lists


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
```

**Step 5: Register the router in `app/main.py`**

Add to imports:
```python
from app.routers import auth, users, invites, lists
```

Add after the invites router:
```python
    application.include_router(lists.router)
```

**Step 6: Run tests to verify they pass**

Run: `task app:test-file -- tests/routers/test_lists.py -v`
Expected: 14 passed.

**Step 7: Run full suite**

Run: `task app:test`
Expected: 56 passed (42 + 14 new).

---

### Task 7: Gifts Router and Tests

**Context:** Nested endpoints under `/lists/{list_id}/gifts`. Owner can create/update/delete gifts. Shared users can claim/unclaim. The gift response filtering (hiding claim info from owner) was already handled in the GET list detail endpoint — individual gift mutations return the appropriate schema too.

**Files to create:**
- `app/routers/gifts.py`
- `tests/routers/test_gifts.py`

**Files to modify:**
- `app/main.py`

**Step 1: Write the failing tests**

`tests/routers/test_gifts.py`:
```python
from app.models.gift import Gift


def test_create_gift(client, member_headers, sample_list):
    response = client.post(
        f"/lists/{sample_list.id}/gifts",
        headers=member_headers,
        json={
            "name": "Book",
            "description": "A great read",
            "url": "https://example.com/book",
            "price": "19.99",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Book"
    assert data["description"] == "A great read"
    assert data["url"] == "https://example.com/book"
    assert data["price"] == "19.99"


def test_create_gift_minimal(client, member_headers, sample_list):
    response = client.post(
        f"/lists/{sample_list.id}/gifts",
        headers=member_headers,
        json={"name": "Surprise"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["description"] is None
    assert data["url"] is None
    assert data["price"] is None


def test_create_gift_not_owner(client, admin_headers, shared_list):
    response = client.post(
        f"/lists/{shared_list.id}/gifts",
        headers=admin_headers,
        json={"name": "Nope"},
    )
    assert response.status_code == 403


def test_update_gift(client, member_headers, sample_list, db):
    gift = Gift(list_id=sample_list.id, name="Old Name")
    db.add(gift)
    db.flush()

    response = client.put(
        f"/lists/{sample_list.id}/gifts/{gift.id}",
        headers=member_headers,
        json={"name": "New Name"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "New Name"


def test_update_gift_not_owner(client, admin_headers, shared_list, db):
    gift = Gift(list_id=shared_list.id, name="Protected")
    db.add(gift)
    db.flush()

    response = client.put(
        f"/lists/{shared_list.id}/gifts/{gift.id}",
        headers=admin_headers,
        json={"name": "Hacked"},
    )
    assert response.status_code == 403


def test_update_gift_not_found(client, member_headers, sample_list):
    response = client.put(
        f"/lists/{sample_list.id}/gifts/99999",
        headers=member_headers,
        json={"name": "Ghost"},
    )
    assert response.status_code == 404


def test_delete_gift(client, member_headers, sample_list, db):
    gift = Gift(list_id=sample_list.id, name="Delete Me")
    db.add(gift)
    db.flush()

    response = client.delete(
        f"/lists/{sample_list.id}/gifts/{gift.id}",
        headers=member_headers,
    )
    assert response.status_code == 204


def test_delete_gift_not_owner(client, admin_headers, shared_list, db):
    gift = Gift(list_id=shared_list.id, name="Protected")
    db.add(gift)
    db.flush()

    response = client.delete(
        f"/lists/{shared_list.id}/gifts/{gift.id}",
        headers=admin_headers,
    )
    assert response.status_code == 403


def test_claim_gift(client, admin_user, admin_headers, shared_list, db):
    gift = Gift(list_id=shared_list.id, name="Claimable")
    db.add(gift)
    db.flush()

    response = client.post(
        f"/lists/{shared_list.id}/gifts/{gift.id}/claim",
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["claimed_by_id"] == admin_user.id
    assert data["claimed_at"] is not None


def test_claim_gift_already_claimed(client, admin_user, admin_headers, shared_list, db):
    gift = Gift(list_id=shared_list.id, name="Taken")
    gift.claimed_by_id = admin_user.id
    db.add(gift)
    db.flush()

    response = client.post(
        f"/lists/{shared_list.id}/gifts/{gift.id}/claim",
        headers=admin_headers,
    )
    assert response.status_code == 409


def test_claim_gift_as_owner(client, member_headers, sample_list, db):
    gift = Gift(list_id=sample_list.id, name="Own Gift")
    db.add(gift)
    db.flush()

    response = client.post(
        f"/lists/{sample_list.id}/gifts/{gift.id}/claim",
        headers=member_headers,
    )
    assert response.status_code == 403


def test_unclaim_gift(client, admin_user, admin_headers, shared_list, db):
    gift = Gift(list_id=shared_list.id, name="Unclaim Me")
    gift.claimed_by_id = admin_user.id
    db.add(gift)
    db.flush()

    response = client.delete(
        f"/lists/{shared_list.id}/gifts/{gift.id}/claim",
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["claimed_by_id"] is None
    assert data["claimed_at"] is None


def test_unclaim_gift_by_other_user(
    client, member_user, admin_user, member_headers, shared_list, db
):
    # member_user is the owner, so we need a second shared user scenario.
    # Instead, test that a user who didn't claim can't unclaim.
    # admin_user claimed it; create a third user to try unclaiming.
    # For simplicity: the owner tries to unclaim — should fail (owner can't see claims).
    gift = Gift(list_id=shared_list.id, name="Not Yours")
    gift.claimed_by_id = admin_user.id
    db.add(gift)
    db.flush()

    response = client.delete(
        f"/lists/{shared_list.id}/gifts/{gift.id}/claim",
        headers=member_headers,
    )
    assert response.status_code == 403


def test_get_list_hides_claims_from_owner(
    client, member_headers, admin_user, shared_list, db
):
    gift = Gift(list_id=shared_list.id, name="Secret Claim")
    gift.claimed_by_id = admin_user.id
    db.add(gift)
    db.flush()

    response = client.get(f"/lists/{shared_list.id}", headers=member_headers)
    assert response.status_code == 200
    gift_data = response.json()["gifts"][0]
    assert "claimed_by_id" not in gift_data
    assert "claimed_at" not in gift_data


def test_get_list_shows_claims_to_shared_user(
    client, admin_user, admin_headers, shared_list, db
):
    gift = Gift(list_id=shared_list.id, name="Visible Claim")
    gift.claimed_by_id = admin_user.id
    db.add(gift)
    db.flush()

    response = client.get(f"/lists/{shared_list.id}", headers=admin_headers)
    assert response.status_code == 200
    gift_data = response.json()["gifts"][0]
    assert gift_data["claimed_by_id"] == admin_user.id
```

**Step 2: Run tests to verify they fail**

Run: `task app:test-file -- tests/routers/test_gifts.py -v`
Expected: Failures — no routes defined yet.

**Step 3: Write the implementation**

`app/routers/gifts.py`:
```python
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies import (
    CurrentUser,
    DbSession,
    OwnedList,
    ViewableList,
    get_current_user,
    get_db,
)
from app.models.gift import Gift
from app.models.gift_list import GiftList
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
```

**Step 4: Register the router in `app/main.py`**

Add to imports:
```python
from app.routers import auth, users, invites, lists, gifts
```

Add after the lists router:
```python
    application.include_router(gifts.router)
```

**Step 5: Run tests to verify they pass**

Run: `task app:test-file -- tests/routers/test_gifts.py -v`
Expected: 16 passed.

**Step 6: Run full suite**

Run: `task app:test`
Expected: 72 passed (56 + 16 new).

---

### Task 8: List Shares Router and Tests

**Context:** Endpoints for managing who a list is shared with. Only the list owner can share/unshare. Sharing with yourself is rejected.

**Files to create:**
- `app/routers/list_shares.py`
- `tests/routers/test_list_shares.py`

**Files to modify:**
- `app/main.py`

**Step 1: Write the failing tests**

`tests/routers/test_list_shares.py`:
```python
from app.models.list_share import ListShare


def test_share_list(client, member_user, member_headers, sample_list, admin_user):
    response = client.post(
        f"/lists/{sample_list.id}/shares",
        headers=member_headers,
        json={"user_id": admin_user.id},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["list_id"] == sample_list.id
    assert data["user_id"] == admin_user.id


def test_share_list_not_owner(client, admin_headers, shared_list, db):
    from app.models.user import User

    other = User(email="other@test.com", name="Other", password_hash="h")
    db.add(other)
    db.flush()

    response = client.post(
        f"/lists/{shared_list.id}/shares",
        headers=admin_headers,
        json={"user_id": other.id},
    )
    assert response.status_code == 403


def test_share_list_with_self(client, member_user, member_headers, sample_list):
    response = client.post(
        f"/lists/{sample_list.id}/shares",
        headers=member_headers,
        json={"user_id": member_user.id},
    )
    assert response.status_code == 400


def test_share_list_duplicate(
    client, member_headers, shared_list, admin_user
):
    response = client.post(
        f"/lists/{shared_list.id}/shares",
        headers=member_headers,
        json={"user_id": admin_user.id},
    )
    assert response.status_code == 409


def test_list_shares(client, member_headers, shared_list, admin_user):
    response = client.get(
        f"/lists/{shared_list.id}/shares",
        headers=member_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["user_id"] == admin_user.id


def test_list_shares_not_owner(client, admin_headers, shared_list):
    response = client.get(
        f"/lists/{shared_list.id}/shares",
        headers=admin_headers,
    )
    assert response.status_code == 403


def test_unshare_list(client, member_headers, shared_list, admin_user):
    response = client.delete(
        f"/lists/{shared_list.id}/shares/{admin_user.id}",
        headers=member_headers,
    )
    assert response.status_code == 204


def test_unshare_list_not_owner(client, admin_headers, shared_list, admin_user):
    response = client.delete(
        f"/lists/{shared_list.id}/shares/{admin_user.id}",
        headers=admin_headers,
    )
    assert response.status_code == 403


def test_unshare_list_not_found(client, member_headers, sample_list):
    response = client.delete(
        f"/lists/{sample_list.id}/shares/99999",
        headers=member_headers,
    )
    assert response.status_code == 404
```

**Step 2: Run tests to verify they fail**

Run: `task app:test-file -- tests/routers/test_list_shares.py -v`
Expected: Failures — no routes defined yet.

**Step 3: Write the implementation**

`app/routers/list_shares.py`:
```python
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.dependencies import CurrentUser, DbSession, OwnedList
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
```

**Step 4: Register the router in `app/main.py`**

Add to imports:
```python
from app.routers import auth, users, invites, lists, gifts, list_shares
```

Add after the gifts router:
```python
    application.include_router(list_shares.router)
```

**Step 5: Run tests to verify they pass**

Run: `task app:test-file -- tests/routers/test_list_shares.py -v`
Expected: 9 passed.

**Step 6: Run full suite**

Run: `task app:test`
Expected: 81 passed (72 + 9 new).

---

### Task 9: Database Migration

**Context:** Generate an Alembic migration for the three new tables (lists, gifts, list_shares).

**Step 1: Generate migration**

Run: `task app:migration -- 'add lists gifts and list_shares tables'`

**Step 2: Review the generated migration**

Check the generated file in `alembic/versions/` to ensure it creates:
- `lists` table with correct columns and foreign key to `users`
- `gifts` table with correct columns and foreign keys to `lists` and `users`
- `list_shares` table with correct columns, foreign keys, and unique constraint

**Step 3: Run migration against dev database**

Run: `task app:migrate`
Expected: Migration applies without errors.

---

### Task 10: Update CLAUDE.md

**Files to modify:**
- `CLAUDE.md`

**Step 1: Update CLAUDE.md**

Update these sections:

**Project Structure** — add new files:
```
  models/
    ...
    gift_list.py     # GiftList model (name, description, owner_id)
    gift.py          # Gift model (name, description, url, price, claim tracking)
    list_share.py    # ListShare model (list_id, user_id, unique constraint)
  schemas/
    ...
    gift_list.py     # GiftListCreate, GiftListUpdate, GiftListRead, GiftListDetail*, GiftOwnerRead, GiftRead
    gift.py          # GiftCreate, GiftUpdate
    list_share.py    # ListShareCreate, ListShareRead
  routers/
    ...
    lists.py         # POST/GET/PUT/DELETE /lists
    gifts.py         # POST/PUT/DELETE /lists/{id}/gifts, POST/DELETE claim
    list_shares.py   # POST/GET/DELETE /lists/{id}/shares
tests/
  models/
    ...
    test_gift_list.py
    test_gift.py
    test_list_share.py
  routers/
    ...
    test_lists.py
    test_gifts.py
    test_list_shares.py
```

**Testing** — update test count.

Add a new **Gift Lists** section after Authentication & Authorization:
```
## Gift Lists
- Any authenticated user can create lists and add gifts
- Lists are shared with specific users via the list_shares table
- Shared users can claim gifts; claim info is hidden from the list owner
- Authorization: `get_list_for_owner` (403 if not owner), `get_list_for_viewer` (403 if not owner or shared)
- Gift responses use `GiftOwnerRead` (no claim fields) for owners, `GiftRead` (with claim fields) for shared users
- Deleting a list cascades to its gifts (`cascade="all, delete-orphan"`)
```
