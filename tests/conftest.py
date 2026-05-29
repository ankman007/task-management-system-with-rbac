import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db.session import get_db
from app.models import Base, RoleName, Role, User

# Use an in-memory SQLite database for fast, isolated tests
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function", autouse=True)
def setup_database():
    """Creates tables before each test and drops them after."""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    # Seed required roles
    admin_role = Role(name=RoleName.ADMIN)
    manager_role = Role(name=RoleName.MANAGER)
    user_role = Role(name=RoleName.USER)
    db.add_all([admin_role, manager_role, user_role])
    db.commit()

    db.close()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session():
    """Provides a clean SQLAlchemy session for a test."""
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db_session):
    """Overrides the get_db dependency in FastAPI with our test database."""

    def _get_test_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _get_test_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def normal_user(db_session):
    """Create a normal user for testing."""
    user_role = db_session.query(Role).filter(Role.name == RoleName.USER).first()
    user = User(email="user@example.com", hashed_password="fake", role_id=user_role.id)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def admin_user(db_session):
    """Create an admin user for testing."""
    admin_role = db_session.query(Role).filter(Role.name == RoleName.ADMIN).first()
    user = User(
        email="admin@example.com", hashed_password="fake", role_id=admin_role.id
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers_user(client, normal_user):
    """Get auth headers for normal user."""
    from app.core.dependency import get_current_user
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: normal_user
    return {"Authorization": "Bearer fake-token"}


@pytest.fixture
def auth_headers_admin(client, admin_user):
    """Get auth headers for admin user."""
    from app.core.dependency import get_current_user
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: admin_user
    return {"Authorization": "Bearer fake-token"}
