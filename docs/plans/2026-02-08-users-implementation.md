# Users Feature Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement invite-based user system with JWT authentication, admin-only user management, and TDD.

**Architecture:** FastAPI app with SQLAlchemy models, Pydantic schemas, and modular routers. MySQL database on shared Docker network. Tests run against a separate test database using pytest + httpx.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, pydantic-settings, PyJWT, bcrypt, pymysql, pytest, httpx, Alembic

**Additional concerns:** `.env` file for config (DB URL, JWT secret), CORS middleware for frontend access, health check endpoint.

---

### Task 1: Install Dependencies

**Context:** We need additional packages beyond what's already in requirements.in (fastapi, uvicorn, sqlalchemy, pydantic).

**Step 1: Install new dependencies**

Run these inside the container:
```bash
task app:add -- pydantic-settings
task app:add -- pymysql
task app:add -- pyjwt
task app:add -- bcrypt
task app:add -- pytest
task app:add -- httpx
task app:add -- alembic
```

**Step 2: Verify**

Run: `docker compose exec app python -c "import pymysql, jwt, bcrypt, pytest, httpx, alembic; print('OK')"`
Expected: `OK`

**Step 3: Add test task to Taskfile.yaml**

Add to `Taskfile.yaml`:
```yaml
  app:test:
    desc: Run tests
    cmd: docker compose exec app pytest tests/ -v

  app:create-admin:
    desc: "Create an admin user (usage: task app:create-admin)"
    cmd: docker compose exec app python -m app.cli.create_admin
```

---

### Task 2: Project Scaffolding

**Context:** Create the directory structure and boilerplate files. The top-level `main.py` becomes a thin entrypoint that imports from the `app` package.

**Files to create:**
- `app/__init__.py`
- `app/main.py`
- `app/config.py`
- `app/database.py`
- `app/models/__init__.py`
- `app/schemas/__init__.py`
- `app/routers/__init__.py`
- `app/dependencies.py`
- `app/cli/__init__.py`
- `tests/__init__.py`
- `tests/conftest.py`
- `tests/models/__init__.py`
- `tests/routers/__init__.py`

**Files to modify:**
- `main.py` — replace with thin entrypoint

**Step 1: Create directory structure**

```bash
docker compose exec app sh -c 'mkdir -p app/models app/schemas app/routers app/cli tests/models tests/routers'
```

**Step 2: Create `app/config.py`**

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "mysql+pymysql://user:password@mysql_db:3306/boone_gifts"
    test_database_url: str = "mysql+pymysql://user:password@mysql_db:3306/boone_gifts_test"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    cors_origins: list[str] = ["http://localhost:3000"]

    model_config = {"env_prefix": "APP_", "env_file": ".env"}


settings = Settings()
```

Also create `.env` in the project root:
```
APP_DATABASE_URL=mysql+pymysql://user:password@mysql_db:3306/boone_gifts
APP_TEST_DATABASE_URL=mysql+pymysql://user:password@mysql_db:3306/boone_gifts_test
APP_JWT_SECRET=change-me-in-production
APP_CORS_ORIGINS=["http://localhost:3000"]
```

And add `.env` to `.gitignore` (it should already be there) and create a `.env.example` with the same keys but placeholder values.

**Step 3: Create `app/database.py`**

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass
```

**Step 4: Create `app/main.py`**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings
from app.database import engine
from app.routers import auth, users, invites


def create_app() -> FastAPI:
    application = FastAPI(title="Boone Gifts API")

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(auth.router)
    application.include_router(users.router)
    application.include_router(invites.router)

    @application.get("/health")
    def health():
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return {"status": "healthy"}
        except Exception:
            return {"status": "unhealthy"}, 503

    return application


app = create_app()
```

**Step 5: Create stub routers**

`app/routers/auth.py`:
```python
from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["auth"])
```

`app/routers/users.py`:
```python
from fastapi import APIRouter

router = APIRouter(prefix="/users", tags=["users"])
```

`app/routers/invites.py`:
```python
from fastapi import APIRouter

router = APIRouter(prefix="/invites", tags=["invites"])
```

**Step 6: Create `app/dependencies.py`**

```python
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.database import SessionLocal


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DbSession = Annotated[Session, Depends(get_db)]
```

**Step 7: Create all `__init__.py` files**

Create empty `__init__.py` in: `app/`, `app/models/`, `app/schemas/`, `app/routers/`, `app/cli/`, `tests/`, `tests/models/`, `tests/routers/`.

**Step 8: Replace top-level `main.py`**

```python
from app.main import app  # noqa: F401
```

**Step 9: Create `tests/conftest.py`**

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.config import settings
from app.database import Base
from app.dependencies import get_db
from app.main import app

test_engine = create_engine(settings.test_database_url)
TestSession = sessionmaker(bind=test_engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db():
    connection = test_engine.connect()
    transaction = connection.begin()
    session = TestSession(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
```

**Step 10: Verify the app starts**

Run: `task app:run`
Expected: Uvicorn starts without import errors.

Run: `task app:test`
Expected: `no tests ran` (no test files yet), exits 0.

---

### Task 3: User Model

**Files to create:**
- `app/models/user.py`
- `tests/models/test_user.py`

**Step 1: Write the failing test**

`tests/models/test_user.py`:
```python
from app.models.user import User


def test_create_user(db):
    user = User(
        email="test@example.com",
        name="Test User",
        password_hash="hashed",
        role="admin",
    )
    db.add(user)
    db.flush()

    assert user.id is not None
    assert user.email == "test@example.com"
    assert user.name == "Test User"
    assert user.role == "admin"
    assert user.is_active is True
    assert user.created_at is not None
    assert user.updated_at is not None


def test_user_default_role(db):
    user = User(
        email="member@example.com",
        name="Member",
        password_hash="hashed",
    )
    db.add(user)
    db.flush()

    assert user.role == "member"


def test_user_email_unique(db):
    import sqlalchemy

    user1 = User(email="dupe@example.com", name="First", password_hash="h")
    db.add(user1)
    db.flush()

    user2 = User(email="dupe@example.com", name="Second", password_hash="h")
    db.add(user2)

    with pytest.raises(sqlalchemy.exc.IntegrityError):
        db.flush()


def test_user_password_hashing():
    user = User(email="a@b.com", name="A", password_hash="x")
    user.set_password("secret123")
    assert user.password_hash != "secret123"
    assert user.check_password("secret123") is True
    assert user.check_password("wrong") is False
```

Add missing import at top:
```python
import pytest
```

**Step 2: Run test to verify it fails**

Run: `task app:test`
Expected: ImportError — `app.models.user` does not exist yet.

**Step 3: Write the implementation**

`app/models/user.py`:
```python
from datetime import datetime

import bcrypt
from sqlalchemy import String, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default="member")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    def set_password(self, password: str) -> None:
        self.password_hash = bcrypt.hashpw(
            password.encode(), bcrypt.gensalt()
        ).decode()

    def check_password(self, password: str) -> bool:
        return bcrypt.checkpw(
            password.encode(), self.password_hash.encode()
        )
```

**Step 4: Run test to verify it passes**

Run: `task app:test`
Expected: 4 passed.

---

### Task 4: Invite Model

**Files to create:**
- `app/models/invite.py`
- `tests/models/test_invite.py`

**Step 1: Write the failing test**

`tests/models/test_invite.py`:
```python
from datetime import datetime, timedelta, timezone

from app.models.invite import Invite
from app.models.user import User


def test_create_invite(db):
    admin = User(email="admin@test.com", name="Admin", password_hash="h", role="admin")
    db.add(admin)
    db.flush()

    invite = Invite(
        email="new@test.com",
        role="member",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        invited_by_id=admin.id,
    )
    db.add(invite)
    db.flush()

    assert invite.id is not None
    assert invite.token is not None
    assert len(invite.token) == 36  # UUID4 format
    assert invite.used_at is None
    assert invite.created_at is not None


def test_invite_is_valid(db):
    admin = User(email="admin2@test.com", name="Admin", password_hash="h", role="admin")
    db.add(admin)
    db.flush()

    invite = Invite(
        email="valid@test.com",
        role="member",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        invited_by_id=admin.id,
    )
    db.add(invite)
    db.flush()

    assert invite.is_valid is True


def test_invite_expired(db):
    admin = User(email="admin3@test.com", name="Admin", password_hash="h", role="admin")
    db.add(admin)
    db.flush()

    invite = Invite(
        email="expired@test.com",
        role="member",
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        invited_by_id=admin.id,
    )
    db.add(invite)
    db.flush()

    assert invite.is_valid is False


def test_invite_used(db):
    admin = User(email="admin4@test.com", name="Admin", password_hash="h", role="admin")
    db.add(admin)
    db.flush()

    invite = Invite(
        email="used@test.com",
        role="member",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        invited_by_id=admin.id,
    )
    invite.used_at = datetime.now(timezone.utc)
    db.add(invite)
    db.flush()

    assert invite.is_valid is False
```

**Step 2: Run test to verify it fails**

Run: `task app:test`
Expected: ImportError — `app.models.invite` does not exist yet.

**Step 3: Write the implementation**

`app/models/invite.py`:
```python
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Invite(Base):
    __tablename__ = "invites"

    id: Mapped[int] = mapped_column(primary_key=True)
    token: Mapped[str] = mapped_column(
        String(36), unique=True, index=True, default=lambda: str(uuid.uuid4())
    )
    email: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default="member")
    expires_at: Mapped[datetime] = mapped_column()
    used_at: Mapped[datetime | None] = mapped_column(default=None)
    invited_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    @property
    def is_valid(self) -> bool:
        return self.used_at is None and self.expires_at > datetime.now(timezone.utc)
```

**Step 4: Run test to verify it passes**

Run: `task app:test`
Expected: 8 passed (4 user + 4 invite).

---

### Task 5: User Schemas

**Files to create:**
- `app/schemas/user.py`
- `app/schemas/auth.py`

**Context:** No separate test file needed — schemas are validated through router tests. Create them now so router tests can use them.

**Step 1: Create `app/schemas/user.py`**

```python
from datetime import datetime

from pydantic import BaseModel, EmailStr


class UserRead(BaseModel):
    id: int
    email: str
    name: str
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    email: str | None = None
    name: str | None = None
    role: str | None = None
    is_active: bool | None = None
```

**Step 2: Create `app/schemas/auth.py`**

```python
from pydantic import BaseModel


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    token: str
    name: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
```

---

### Task 6: Invite Schemas

**Files to create:**
- `app/schemas/invite.py`

**Step 1: Create `app/schemas/invite.py`**

```python
from datetime import datetime

from pydantic import BaseModel


class InviteCreate(BaseModel):
    email: str
    role: str = "member"
    expires_in_days: int = 7


class InviteRead(BaseModel):
    id: int
    token: str
    email: str
    role: str
    expires_at: datetime
    used_at: datetime | None
    invited_by_id: int
    created_at: datetime

    model_config = {"from_attributes": True}
```

---

### Task 7: Auth Dependencies

**Files to modify:**
- `app/dependencies.py`

**Context:** Add JWT token creation/verification and auth dependencies that routers will use.

**Step 1: Update `app/dependencies.py`**

```python
from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.user import User


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DbSession = Annotated[Session, Depends(get_db)]

security = HTTPBearer()


def create_access_token(user: User) -> str:
    payload = {
        "sub": user.id,
        "email": user.email,
        "role": user.role,
        "exp": datetime.now(timezone.utc)
        + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(user: User) -> str:
    payload = {
        "sub": user.id,
        "type": "refresh",
        "exp": datetime.now(timezone.utc)
        + timedelta(days=settings.refresh_token_expire_days),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: DbSession,
) -> User:
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    if payload.get("type") == "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    user = db.get(User, payload["sub"])
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return user


def require_admin(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_admin)]
```

---

### Task 8: Test Fixtures Enhancement

**Files to modify:**
- `tests/conftest.py`

**Context:** Add fixtures for creating test users and auth tokens before writing router tests.

**Step 1: Update `tests/conftest.py`**

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.config import settings
from app.database import Base
from app.dependencies import get_db, create_access_token
from app.main import app
from app.models.user import User

test_engine = create_engine(settings.test_database_url)
TestSession = sessionmaker(bind=test_engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db():
    connection = test_engine.connect()
    transaction = connection.begin()
    session = TestSession(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def admin_user(db):
    user = User(email="admin@test.com", name="Admin", role="admin", password_hash="x")
    user.set_password("admin123")
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def member_user(db):
    user = User(email="member@test.com", name="Member", role="member", password_hash="x")
    user.set_password("member123")
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def admin_token(admin_user):
    return create_access_token(admin_user)


@pytest.fixture
def member_token(member_user):
    return create_access_token(member_user)


@pytest.fixture
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def member_headers(member_token):
    return {"Authorization": f"Bearer {member_token}"}
```

---

### Task 9: Auth Router

**Files to create:**
- `tests/routers/test_auth.py`

**Files to modify:**
- `app/routers/auth.py`

**Step 1: Write the failing tests**

`tests/routers/test_auth.py`:
```python
from datetime import datetime, timedelta, timezone

from app.models.invite import Invite


def test_login_success(client, admin_user):
    response = client.post("/auth/login", json={
        "email": "admin@test.com",
        "password": "admin123",
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


def test_login_wrong_password(client, admin_user):
    response = client.post("/auth/login", json={
        "email": "admin@test.com",
        "password": "wrong",
    })
    assert response.status_code == 401


def test_login_nonexistent_user(client):
    response = client.post("/auth/login", json={
        "email": "nobody@test.com",
        "password": "whatever",
    })
    assert response.status_code == 401


def test_login_inactive_user(client, admin_user, db):
    admin_user.is_active = False
    db.flush()
    response = client.post("/auth/login", json={
        "email": "admin@test.com",
        "password": "admin123",
    })
    assert response.status_code == 401


def test_register_with_valid_invite(client, admin_user, db):
    invite = Invite(
        email="new@test.com",
        role="member",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        invited_by_id=admin_user.id,
    )
    db.add(invite)
    db.flush()

    response = client.post("/auth/register", json={
        "token": invite.token,
        "name": "New User",
        "password": "newpass123",
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data


def test_register_with_expired_invite(client, admin_user, db):
    invite = Invite(
        email="expired@test.com",
        role="member",
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        invited_by_id=admin_user.id,
    )
    db.add(invite)
    db.flush()

    response = client.post("/auth/register", json={
        "token": invite.token,
        "name": "Expired",
        "password": "pass123",
    })
    assert response.status_code == 400


def test_register_with_used_invite(client, admin_user, db):
    invite = Invite(
        email="used@test.com",
        role="member",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        invited_by_id=admin_user.id,
    )
    invite.used_at = datetime.now(timezone.utc)
    db.add(invite)
    db.flush()

    response = client.post("/auth/register", json={
        "token": invite.token,
        "name": "Used",
        "password": "pass123",
    })
    assert response.status_code == 400


def test_register_with_invalid_token(client):
    response = client.post("/auth/register", json={
        "token": "nonexistent-token",
        "name": "Bad",
        "password": "pass123",
    })
    assert response.status_code == 400


def test_refresh_token(client, admin_user):
    login = client.post("/auth/login", json={
        "email": "admin@test.com",
        "password": "admin123",
    })
    refresh_token = login.json()["refresh_token"]

    response = client.post("/auth/refresh", json={
        "refresh_token": refresh_token,
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" not in data


def test_refresh_with_access_token_fails(client, admin_token):
    response = client.post("/auth/refresh", json={
        "refresh_token": admin_token,
    })
    assert response.status_code == 401


def test_refresh_with_invalid_token(client):
    response = client.post("/auth/refresh", json={
        "refresh_token": "garbage",
    })
    assert response.status_code == 401
```

**Step 2: Run test to verify they fail**

Run: `task app:test`
Expected: Failures — no routes defined yet.

**Step 3: Write the implementation**

`app/routers/auth.py`:
```python
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

    user = db.get(User, payload["sub"])
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    return AccessTokenResponse(access_token=create_access_token(user))
```

**Step 4: Run test to verify they pass**

Run: `task app:test`
Expected: All auth tests pass.

---

### Task 10: Users Router

**Files to create:**
- `tests/routers/test_users.py`

**Files to modify:**
- `app/routers/users.py`

**Step 1: Write the failing tests**

`tests/routers/test_users.py`:
```python
def test_list_users_as_admin(client, admin_user, admin_headers):
    response = client.get("/users", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert data[0]["email"] == "admin@test.com"


def test_list_users_as_member(client, member_user, member_headers):
    response = client.get("/users", headers=member_headers)
    assert response.status_code == 403


def test_list_users_unauthenticated(client):
    response = client.get("/users")
    assert response.status_code == 403


def test_get_user_as_admin(client, admin_user, admin_headers):
    response = client.get(f"/users/{admin_user.id}", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["email"] == "admin@test.com"


def test_get_user_not_found(client, admin_user, admin_headers):
    response = client.get("/users/99999", headers=admin_headers)
    assert response.status_code == 404


def test_update_user_as_admin(client, member_user, admin_headers):
    response = client.put(
        f"/users/{member_user.id}",
        headers=admin_headers,
        json={"name": "Updated Name"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Updated Name"


def test_update_user_as_member(client, admin_user, member_headers):
    response = client.put(
        f"/users/{admin_user.id}",
        headers=member_headers,
        json={"name": "Hacked"},
    )
    assert response.status_code == 403


def test_delete_user_as_admin(client, member_user, admin_headers):
    response = client.delete(
        f"/users/{member_user.id}", headers=admin_headers
    )
    assert response.status_code == 204


def test_delete_user_as_member(client, admin_user, member_headers):
    response = client.delete(
        f"/users/{admin_user.id}", headers=member_headers
    )
    assert response.status_code == 403
```

**Step 2: Run test to verify they fail**

Run: `task app:test`
Expected: Failures — no user routes defined.

**Step 3: Write the implementation**

`app/routers/users.py`:
```python
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
```

**Step 4: Run test to verify they pass**

Run: `task app:test`
Expected: All user router tests pass.

---

### Task 11: Invites Router

**Files to create:**
- `tests/routers/test_invites.py`

**Files to modify:**
- `app/routers/invites.py`

**Step 1: Write the failing tests**

`tests/routers/test_invites.py`:
```python
def test_create_invite_as_admin(client, admin_user, admin_headers):
    response = client.post(
        "/invites",
        headers=admin_headers,
        json={"email": "invitee@test.com", "role": "member", "expires_in_days": 7},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "invitee@test.com"
    assert data["role"] == "member"
    assert data["token"] is not None
    assert data["used_at"] is None


def test_create_invite_as_member(client, member_user, member_headers):
    response = client.post(
        "/invites",
        headers=member_headers,
        json={"email": "nope@test.com"},
    )
    assert response.status_code == 403


def test_create_invite_default_role(client, admin_user, admin_headers):
    response = client.post(
        "/invites",
        headers=admin_headers,
        json={"email": "default@test.com"},
    )
    assert response.status_code == 201
    assert response.json()["role"] == "member"


def test_list_invites_as_admin(client, admin_user, admin_headers):
    client.post(
        "/invites",
        headers=admin_headers,
        json={"email": "list@test.com"},
    )
    response = client.get("/invites", headers=admin_headers)
    assert response.status_code == 200
    assert len(response.json()) >= 1


def test_list_invites_as_member(client, member_user, member_headers):
    response = client.get("/invites", headers=member_headers)
    assert response.status_code == 403


def test_delete_invite_as_admin(client, admin_user, admin_headers):
    create = client.post(
        "/invites",
        headers=admin_headers,
        json={"email": "delete@test.com"},
    )
    invite_id = create.json()["id"]

    response = client.delete(f"/invites/{invite_id}", headers=admin_headers)
    assert response.status_code == 204


def test_delete_invite_as_member(client, admin_user, member_user, admin_headers, member_headers):
    create = client.post(
        "/invites",
        headers=admin_headers,
        json={"email": "nodelete@test.com"},
    )
    invite_id = create.json()["id"]

    response = client.delete(f"/invites/{invite_id}", headers=member_headers)
    assert response.status_code == 403
```

**Step 2: Run test to verify they fail**

Run: `task app:test`
Expected: Failures — no invite routes defined.

**Step 3: Write the implementation**

`app/routers/invites.py`:
```python
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
```

**Step 4: Run test to verify they pass**

Run: `task app:test`
Expected: All invite router tests pass.

---

### Task 12: Create Admin CLI Command

**Files to create:**
- `app/cli/create_admin.py`

**Context:** Provides `task app:create-admin` to seed the first admin user. Reads email, name, and password from environment variables or stdin.

**Step 1: Create `app/cli/create_admin.py`**

```python
import sys

from sqlalchemy import select

from app.database import SessionLocal, engine, Base
from app.models.user import User


def main():
    Base.metadata.create_all(bind=engine)

    email = input("Email: ").strip()
    name = input("Name: ").strip()
    password = input("Password: ").strip()

    if not all([email, name, password]):
        print("All fields are required.")
        sys.exit(1)

    db = SessionLocal()
    try:
        existing = db.execute(
            select(User).where(User.email == email)
        ).scalar_one_or_none()

        if existing:
            print(f"User with email {email} already exists.")
            sys.exit(1)

        user = User(email=email, name=name, role="admin", password_hash="")
        user.set_password(password)
        db.add(user)
        db.commit()
        print(f"Admin user '{name}' created successfully.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
```

**Step 2: Verify it works**

Run: `task app:create-admin`
Enter test values when prompted. Expected: `Admin user 'Name' created successfully.`

---

### Task 13: Database Migration Setup

**Context:** Initialize Alembic for managing database migrations so schema changes are versioned.

**Step 1: Initialize Alembic**

```bash
docker compose exec app alembic init alembic
```

**Step 2: Update `alembic/env.py`**

Replace the `target_metadata` line and `run_migrations_online` to use our models and database URL:

Set `target_metadata = Base.metadata` and import `Base` from `app.database` and all models from `app.models`.

Set `sqlalchemy.url` from `app.config.settings.database_url`.

**Step 3: Generate initial migration**

```bash
docker compose exec app alembic revision --autogenerate -m "create users and invites tables"
```

**Step 4: Add migration task to Taskfile.yaml**

```yaml
  app:migrate:
    desc: Run database migrations
    cmd: docker compose exec app alembic upgrade head

  app:migration:
    desc: "Create a new migration (usage: task app:migration -- 'description')"
    cmd: docker compose exec app alembic revision --autogenerate -m "{{.CLI_ARGS}}"
```

**Step 5: Run migrations**

```bash
task app:migrate
```

---

### Task 14: Final Integration Test

**Context:** Run the full test suite and verify the app starts and serves requests.

**Step 1: Run full test suite**

Run: `task app:test`
Expected: All tests pass.

**Step 2: Run migrations against dev database**

Run: `task app:migrate`

**Step 3: Start the app and test manually**

Run: `task app:run`

Create first admin: `task app:create-admin`

Test login:
```bash
curl -sk -X POST https://boone-gifts-api.localhost/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"yourpassword"}'
```

Expected: JSON response with `access_token` and `refresh_token`.

---

### Task 15: Update CLAUDE.md

**Files to modify:**
- `CLAUDE.md`

**Step 1: Update CLAUDE.md**

Update the Project Structure section and add new task commands (`app:test`, `app:create-admin`, `app:migrate`, `app:migration`). Update the App Entrypoint section to reflect the new `app/` package structure.
