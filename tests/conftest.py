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
