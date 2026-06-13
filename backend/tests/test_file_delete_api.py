from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.database import get_db
from app.models.file import File as FileModel
from app.models.parsed_content import ParsedContent
from main import app


class FakeObject:
    def __init__(self, object_name):
        self.object_name = object_name


class FakeMinio:
    def __init__(self, prefix_objects=None, fail_on_remove=None, missing_on_remove=None):
        self.prefix_objects = prefix_objects or []
        self.fail_on_remove = fail_on_remove or set()
        self.missing_on_remove = missing_on_remove or set()
        self.remove_calls = []
        self.list_calls = []

    def remove_object(self, bucket, path):
        self.remove_calls.append((bucket, path))
        if (bucket, path) in self.fail_on_remove:
            raise RuntimeError("minio unavailable")
        if (bucket, path) in self.missing_on_remove:
            raise FileNotFoundError(path)

    def list_objects(self, bucket, prefix, recursive):
        self.list_calls.append((bucket, prefix, recursive))
        return [FakeObject(path) for path in self.prefix_objects]


class FakeQuery:
    def __init__(self, item=None, delete_callback=None):
        self.item = item
        self.delete_callback = delete_callback

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.item

    def delete(self):
        if self.delete_callback:
            self.delete_callback()
        return 1


class FakeDb:
    def __init__(self, file):
        self.file = file
        self.parsed_deletes = 0
        self.deleted_files = []
        self.committed = False
        self.rolled_back = False

    def query(self, model):
        if model is FileModel:
            return FakeQuery(self.file)
        if model is ParsedContent:
            return FakeQuery(delete_callback=self._delete_parsed_content)
        return FakeQuery()

    def _delete_parsed_content(self):
        self.parsed_deletes += 1

    def delete(self, file):
        self.deleted_files.append(file)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def _delete_file(monkeypatch, fake_db, fake_minio):
    app.dependency_overrides[get_db] = lambda: fake_db
    monkeypatch.setattr("app.api.files.MINIO_BUCKET", "mineru-files")
    monkeypatch.setattr("app.api.files.MINIO_MDS_BUCKET", "mds", raising=False)
    monkeypatch.setattr("app.api.files.minio_client", fake_minio)

    try:
        return TestClient(app).delete(
            "/api/files/7",
            headers={"X-User-Id": "u1"},
        )
    finally:
        app.dependency_overrides.clear()


def test_delete_file_removes_original_and_parsed_minio_artifacts(monkeypatch):
    fake_file = SimpleNamespace(
        id=7,
        user_id="u1",
        filename="sample.pdf",
        minio_path="uploads/sample.pdf",
    )
    fake_db = FakeDb(fake_file)
    fake_minio = FakeMinio(
        prefix_objects=[
            "sample/auto/sample_middle.json",
            "sample/images/page-1.png",
        ]
    )

    response = _delete_file(monkeypatch, fake_db, fake_minio)

    assert response.status_code == 200
    assert fake_minio.list_calls == [("mds", "sample/", True)]
    assert fake_minio.remove_calls == [
        ("mineru-files", "uploads/sample.pdf"),
        ("mds", "sample.md"),
        ("mds", "sample_pages.md"),
        ("mds", "sample_popo.md"),
        ("mds", "sample_popo_status.json"),
        ("mds", "sample_middle.json"),
        ("mds", "sample/auto/sample_middle.json"),
        ("mds", "sample/images/page-1.png"),
    ]
    assert fake_db.parsed_deletes == 1
    assert fake_db.deleted_files == [fake_file]
    assert fake_db.committed is True
    assert fake_db.rolled_back is False


def test_delete_file_rolls_back_when_parsed_artifact_cleanup_fails(monkeypatch):
    fake_file = SimpleNamespace(
        id=7,
        user_id="u1",
        filename="sample.pdf",
        minio_path="uploads/sample.pdf",
    )
    fake_db = FakeDb(fake_file)
    fake_minio = FakeMinio(
        prefix_objects=["sample/images/page-1.png"],
        fail_on_remove={("mds", "sample/images/page-1.png")},
    )

    response = _delete_file(monkeypatch, fake_db, fake_minio)

    assert response.status_code == 500
    assert "删除失败" in response.json()["detail"]
    assert fake_db.parsed_deletes == 0
    assert fake_db.deleted_files == []
    assert fake_db.committed is False
    assert fake_db.rolled_back is True


def test_delete_file_ignores_missing_minio_objects(monkeypatch):
    fake_file = SimpleNamespace(
        id=7,
        user_id="u1",
        filename="sample.pdf",
        minio_path="uploads/sample.pdf",
    )
    fake_db = FakeDb(fake_file)
    missing_objects = {
        ("mineru-files", "uploads/sample.pdf"),
        ("mds", "sample.md"),
        ("mds", "sample_pages.md"),
        ("mds", "sample_popo.md"),
        ("mds", "sample_popo_status.json"),
        ("mds", "sample_middle.json"),
        ("mds", "sample/images/page-1.png"),
    }
    fake_minio = FakeMinio(
        prefix_objects=["sample/images/page-1.png"],
        missing_on_remove=missing_objects,
    )

    response = _delete_file(monkeypatch, fake_db, fake_minio)

    assert response.status_code == 200
    assert fake_db.parsed_deletes == 1
    assert fake_db.deleted_files == [fake_file]
    assert fake_db.committed is True
    assert fake_db.rolled_back is False
