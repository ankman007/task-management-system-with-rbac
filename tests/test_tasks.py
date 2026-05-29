import pytest
from app.models import User, RoleName, Role


@pytest.fixture
def normal_user(db_session):
    user_role = db_session.query(Role).filter(Role.name == RoleName.USER).first()
    user = User(email="user@example.com", hashed_password="fake", role_id=user_role.id)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def admin_user(db_session):
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
    # Mocking dependency override for get_current_user is cleaner than generating real JWTs
    from app.core.dependency import get_current_user
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: normal_user
    return {"Authorization": "Bearer fake-token"}


@pytest.fixture
def auth_headers_admin(client, admin_user):
    from app.core.dependency import get_current_user
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: admin_user
    return {"Authorization": "Bearer fake-token"}
