import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services import user_service  # noqa: E402

Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def user_factory(db_session):
    def factory(email=None, password="TestPass1!", name="Test User", role="user"):
        email = email or f"user_{uuid.uuid4().hex[:8]}@example.com"
        user = user_service.create_user(db_session, email, password, name)
        if role == "admin":
            user.role = "admin"
            db_session.commit()
            db_session.refresh(user)
        return user, password
    return factory


@pytest.fixture
def regular_user(user_factory):
    user, _ = user_factory()
    return user


@pytest.fixture
def admin_user(user_factory):
    user, _ = user_factory(role="admin")
    return user


@pytest.fixture
def regular_headers(regular_user):
    token = user_service.create_access_token(regular_user.id, regular_user.role)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers(admin_user):
    token = user_service.create_access_token(admin_user.id, admin_user.role)
    return {"Authorization": f"Bearer {token}"}
