from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import get_db
from app.models.base import Base
from main import app


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_register_sets_session_cookie_and_me_returns_user(client):
    response = client.post(
        "/api/auth/register",
        json={"email": "Ada@Example.com", "password": "secret123"},
    )

    assert response.status_code == 200
    assert client.cookies.get("mineru_session")
    assert response.json()["user"]["email"] == "ada@example.com"

    me_response = client.get("/api/auth/me")

    assert me_response.status_code == 200
    assert me_response.json()["email"] == "ada@example.com"


def test_register_rejects_duplicate_email(client):
    client.post(
        "/api/auth/register",
        json={"email": "ada@example.com", "password": "secret123"},
    )

    response = client.post(
        "/api/auth/register",
        json={"email": "ADA@example.com", "password": "secret123"},
    )

    assert response.status_code == 409


def test_login_sets_session_for_existing_user(client):
    client.post(
        "/api/auth/register",
        json={"email": "ada@example.com", "password": "secret123"},
    )
    client.post("/api/auth/logout")

    response = client.post(
        "/api/auth/login",
        json={"email": "ada@example.com", "password": "secret123"},
    )

    assert response.status_code == 200
    assert client.cookies.get("mineru_session")
    assert response.json()["user"]["email"] == "ada@example.com"


def test_login_rejects_wrong_password(client):
    client.post(
        "/api/auth/register",
        json={"email": "ada@example.com", "password": "secret123"},
    )
    client.post("/api/auth/logout")

    response = client.post(
        "/api/auth/login",
        json={"email": "ada@example.com", "password": "wrongpass"},
    )

    assert response.status_code == 401


def test_authenticated_cookie_can_access_files(client):
    client.post(
        "/api/auth/register",
        json={"email": "ada@example.com", "password": "secret123"},
    )

    response = client.get("/api/files")

    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_auth_required_for_current_user_and_files(client):
    me_response = client.get("/api/auth/me")
    files_response = client.get("/api/files")

    assert me_response.status_code == 401
    assert files_response.status_code == 401
