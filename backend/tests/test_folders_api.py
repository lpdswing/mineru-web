from datetime import datetime

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import get_db
from app.models.base import Base
from app.models.enums import FileStatus
from app.models.file import File
from app.models.folder import Folder
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


def register(client: TestClient) -> str:
    response = client.post(
        "/api/auth/register",
        json={"email": "ada@example.com", "password": "secret123"},
    )
    return str(response.json()["user"]["id"])


def add_file(testing_session, user_id: str, filename: str) -> int:
    db = testing_session()
    try:
        db_file = File(
            user_id=user_id,
            filename=filename,
            size=1024,
            status=FileStatus.PENDING,
            upload_time=datetime.utcnow(),
            minio_path=filename,
        )
        db.add(db_file)
        db.commit()
        db.refresh(db_file)
        return db_file.id
    finally:
        db.close()


def test_folder_lifecycle_and_file_filtering(client_and_session):
    client, testing_session = client_and_session
    user_id = register(client)
    file_id = add_file(testing_session, user_id, "contract.pdf")

    create_response = client.post("/api/folders", json={"name": "合同"})

    assert create_response.status_code == 200
    folder = create_response.json()
    assert folder["name"] == "合同"

    list_response = client.get("/api/folders")

    assert list_response.status_code == 200
    assert list_response.json()["folders"] == [folder]

    move_response = client.patch(
        f"/api/files/{file_id}/folder",
        json={"folder_id": folder["id"]},
    )

    assert move_response.status_code == 200
    assert move_response.json()["folder_id"] == folder["id"]

    filtered_response = client.get("/api/files", params={"folder_id": folder["id"]})
    unfiled_response = client.get("/api/files", params={"folder_id": "none"})

    assert filtered_response.json()["total"] == 1
    assert filtered_response.json()["files"][0]["folder_id"] == folder["id"]
    assert unfiled_response.json()["total"] == 0

    delete_response = client.delete(f"/api/folders/{folder['id']}")
    unfiled_after_delete = client.get("/api/files", params={"folder_id": "none"})

    assert delete_response.status_code == 200
    assert unfiled_after_delete.json()["total"] == 1
    assert unfiled_after_delete.json()["files"][0]["folder_id"] is None


def test_folders_are_scoped_to_authenticated_user(client_and_session):
    client, testing_session = client_and_session
    user_id = register(client)
    file_id = add_file(testing_session, user_id, "mine.pdf")

    client.post("/api/folders", json={"name": "我的文件夹"})
    client.post("/api/auth/logout")
    client.post(
        "/api/auth/register",
        json={"email": "other@example.com", "password": "secret123"},
    )

    folders_response = client.get("/api/folders")
    move_response = client.patch(
        f"/api/files/{file_id}/folder",
        json={"folder_id": None},
    )

    assert folders_response.status_code == 200
    assert folders_response.json()["folders"] == []
    assert move_response.status_code == 404


def test_upload_can_assign_file_to_folder(client_and_session, monkeypatch):
    client, testing_session = client_and_session
    user_id = register(client)

    db = testing_session()
    try:
        folder = Folder(user_id=user_id, name="合同")
        db.add(folder)
        db.commit()
        db.refresh(folder)
        folder_id = folder.id
    finally:
        db.close()

    monkeypatch.setattr("app.api.upload.upload_file", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.parser.ParserService.queue_parse_file", lambda *args, **kwargs: None)

    response = client.post(
        "/api/upload",
        data={"folder_id": str(folder_id)},
        files={"files": ("contract.pdf", b"pdf content", "application/pdf")},
    )

    assert response.status_code == 200
    uploaded_file = response.json()["files"][0]
    assert uploaded_file["folder_id"] == folder_id

    db = testing_session()
    try:
        saved_file = db.query(File).filter(File.filename == "contract.pdf").first()
        assert saved_file.folder_id == folder_id
    finally:
        db.close()


def test_upload_rejects_other_users_folder(client_and_session, monkeypatch):
    client, testing_session = client_and_session
    register(client)

    db = testing_session()
    try:
        folder = Folder(user_id="other-user", name="别人的文件夹")
        db.add(folder)
        db.commit()
        db.refresh(folder)
        folder_id = folder.id
    finally:
        db.close()

    monkeypatch.setattr("app.api.upload.upload_file", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.parser.ParserService.queue_parse_file", lambda *args, **kwargs: None)

    response = client.post(
        "/api/upload",
        data={"folder_id": str(folder_id)},
        files={"files": ("contract.pdf", b"pdf content", "application/pdf")},
    )

    assert response.status_code == 404
