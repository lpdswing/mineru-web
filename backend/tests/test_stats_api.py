from datetime import date, datetime

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import get_db
from app.models.base import Base
from app.models.enums import FileStatus
from app.models.file import File
from main import app


@pytest.fixture()
def client_and_session():
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
        yield TestClient(app), testing_session
    finally:
        app.dependency_overrides.clear()


def test_stats_are_scoped_to_authenticated_user(client_and_session):
    client, testing_session = client_and_session
    register_response = client.post(
        "/api/auth/register",
        json={"email": "ada@example.com", "password": "secret123"},
    )
    user_id = str(register_response.json()["user"]["id"])

    uploaded_today = datetime.combine(date.today(), datetime.min.time())
    db = testing_session()
    try:
        db.add_all(
            [
                File(
                    user_id=user_id,
                    filename="mine.pdf",
                    size=1024 * 1024,
                    status=FileStatus.PARSED,
                    upload_time=uploaded_today,
                    minio_path="mine.pdf",
                ),
                File(
                    user_id="other-user",
                    filename="other.pdf",
                    size=2 * 1024 * 1024,
                    status=FileStatus.PARSED,
                    upload_time=uploaded_today,
                    minio_path="other.pdf",
                ),
            ]
        )
        db.commit()
    finally:
        db.close()

    response = client.get("/api/stats")

    assert response.status_code == 200
    assert response.json() == {
        "totalFiles": 1,
        "todayUploads": 1,
        "usedSpace": 1.0,
    }
