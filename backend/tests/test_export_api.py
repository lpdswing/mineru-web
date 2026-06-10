from types import SimpleNamespace
from fastapi.testclient import TestClient

from app.database import get_db
from app.models.file import File as FileModel
from app.models.parsed_content import ParsedContent
from main import app


class FakeObject:
    def __init__(self, content):
        self.content = content
        self.closed = False
        self.released = False

    def read(self):
        return self.content

    def close(self):
        self.closed = True

    def release_conn(self):
        self.released = True


class FakeQuery:
    def __init__(self, item):
        self.item = item

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.item


class FakeDb:
    def __init__(self, file, parsed_content=None):
        self.file = file
        self.parsed_content = parsed_content

    def query(self, model):
        if model is FileModel:
            return FakeQuery(self.file)
        if model is ParsedContent:
            return FakeQuery(self.parsed_content)
        return FakeQuery(None)


class FakeMinio:
    def __init__(self):
        self.stat_calls = []
        self.get_calls = []
        self.get_responses = []
        self.objects = {}
        self.existing_objects = {
            ("mds", "sample.md"): b"# Main",
            ("mds", "sample_pages.md"): b"# Pages",
            ("mds", "sample_popo.md"): b"# Popo",
            ("mds", "sample_popo_status.json"): b'{"status":"success","message":""}',
        }

    def stat_object(self, bucket, path):
        self.stat_calls.append((bucket, path))
        if (bucket, path) not in self.existing_objects and (bucket, path) not in self.objects:
            raise FileNotFoundError(path)

    def put_object(self, bucket, path, data, length, content_type=None):
        self.objects[(bucket, path)] = {
            "content": data.read(),
            "content_type": content_type,
        }

    def get_object(self, bucket, path):
        self.get_calls.append((bucket, path))
        if (bucket, path) in self.objects:
            response = FakeObject(self.objects[(bucket, path)]["content"])
            self.get_responses.append(response)
            return response
        if (bucket, path) in self.existing_objects:
            response = FakeObject(self.existing_objects[(bucket, path)])
            self.get_responses.append(response)
            return response
        raise FileNotFoundError(path)


class MissingMinio(FakeMinio):
    def stat_object(self, bucket, path):
        self.stat_calls.append((bucket, path))
        raise FileNotFoundError(path)


class FailingStatMinio(FakeMinio):
    def stat_object(self, bucket, path):
        self.stat_calls.append((bucket, path))
        raise RuntimeError("minio down")


def test_export_endpoint_returns_main_markdown_download_url(monkeypatch):
    fake_file = SimpleNamespace(
        id=3,
        user_id="u1",
        filename="原文件.pdf",
        minio_path="uploads/sample.pdf",
    )
    fake_minio = FakeMinio()

    app.dependency_overrides[get_db] = lambda: FakeDb(fake_file)
    monkeypatch.setattr("app.api.parsed.get_buckets", lambda: ["mds"])
    monkeypatch.setattr("app.api.parsed.minio_client", fake_minio)
    monkeypatch.setattr(
        "app.api.parsed.get_presigned_url",
        lambda bucket, path, expires=3600: f"http://minio/{bucket}/{path}?signed=1",
    )

    try:
        response = TestClient(app).get(
            "/api/files/3/export",
            params={"format": "markdown"},
            headers={"X-User-Id": "u1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert fake_minio.stat_calls == [("mds", "sample.md")]
    assert response.json() == {
        "status": "success",
        "download_url": "http://minio/mds/sample.md?signed=1",
        "filename": "原文件.md",
    }


def test_export_endpoint_returns_page_markdown_download_url(monkeypatch):
    fake_file = SimpleNamespace(
        id=3,
        user_id="u1",
        filename="sample.pdf",
        minio_path="uploads/sample.pdf",
    )
    fake_minio = FakeMinio()

    app.dependency_overrides[get_db] = lambda: FakeDb(fake_file)
    monkeypatch.setattr("app.api.parsed.get_buckets", lambda: ["mds"])
    monkeypatch.setattr("app.api.parsed.minio_client", fake_minio)
    monkeypatch.setattr(
        "app.api.parsed.get_presigned_url",
        lambda bucket, path, expires=3600: f"http://minio/{bucket}/{path}?signed=1",
    )

    try:
        response = TestClient(app).get(
            "/api/files/3/export",
            params={"format": "markdown_page"},
            headers={"X-User-Id": "u1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert fake_minio.stat_calls == [("mds", "sample_pages.md")]
    assert response.json()["download_url"] == "http://minio/mds/sample_pages.md?signed=1"
    assert response.json()["filename"] == "sample_pages.md"


def test_export_endpoint_repairs_missing_main_markdown_from_database(monkeypatch):
    fake_file = SimpleNamespace(
        id=3,
        user_id="u1",
        filename="sample.pdf",
        minio_path="uploads/sample.pdf",
    )
    fake_content = SimpleNamespace(content="# Parsed")
    fake_minio = MissingMinio()

    app.dependency_overrides[get_db] = lambda: FakeDb(fake_file, parsed_content=fake_content)
    monkeypatch.setattr("app.api.parsed.get_buckets", lambda: ["mds"])
    monkeypatch.setattr("app.api.parsed.minio_client", fake_minio)
    monkeypatch.setattr(
        "app.api.parsed.get_presigned_url",
        lambda bucket, path, expires=3600: f"http://minio/{bucket}/{path}?signed=1",
    )

    try:
        response = TestClient(app).get(
            "/api/files/3/export",
            params={"format": "markdown"},
            headers={"X-User-Id": "u1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert fake_minio.stat_calls == [("mds", "sample.md")]
    assert fake_minio.objects[("mds", "sample.md")] == {
        "content": b"# Parsed",
        "content_type": "text/markdown; charset=utf-8",
    }
    assert response.json()["download_url"] == "http://minio/mds/sample.md?signed=1"


def test_export_endpoint_returns_404_when_page_markdown_artifact_missing(monkeypatch):
    fake_file = SimpleNamespace(
        id=3,
        user_id="u1",
        filename="sample.pdf",
        minio_path="uploads/sample.pdf",
    )
    fake_minio = MissingMinio()

    app.dependency_overrides[get_db] = lambda: FakeDb(fake_file)
    monkeypatch.setattr("app.api.parsed.get_buckets", lambda: ["mds"])
    monkeypatch.setattr("app.api.parsed.minio_client", fake_minio)
    monkeypatch.setattr(
        "app.api.parsed.get_presigned_url",
        lambda bucket, path, expires=3600: f"http://minio/{bucket}/{path}?signed=1",
    )

    try:
        response = TestClient(app).get(
            "/api/files/3/export",
            params={"format": "markdown_page"},
            headers={"X-User-Id": "u1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert fake_minio.stat_calls == [("mds", "sample_pages.md")]


def test_export_endpoint_returns_500_when_minio_stat_fails(monkeypatch):
    fake_file = SimpleNamespace(
        id=3,
        user_id="u1",
        filename="sample.pdf",
        minio_path="uploads/sample.pdf",
    )
    fake_minio = FailingStatMinio()

    app.dependency_overrides[get_db] = lambda: FakeDb(fake_file)
    monkeypatch.setattr("app.api.parsed.get_buckets", lambda: ["mds"])
    monkeypatch.setattr("app.api.parsed.minio_client", fake_minio)

    try:
        response = TestClient(app).get(
            "/api/files/3/export",
            params={"format": "markdown_page"},
            headers={"X-User-Id": "u1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 500
    assert response.json()["detail"] == "minio down"
    assert fake_minio.stat_calls == [("mds", "sample_pages.md")]


def test_parsed_content_returns_popo_markdown(monkeypatch):
    fake_file = SimpleNamespace(
        id=3,
        user_id="u1",
        filename="sample.pdf",
        minio_path="uploads/sample.pdf",
    )
    fake_minio = FakeMinio()

    app.dependency_overrides[get_db] = lambda: FakeDb(fake_file)
    monkeypatch.setattr("app.api.parsed.get_buckets", lambda: ["mds"])
    monkeypatch.setattr("app.api.parsed.minio_client", fake_minio)

    try:
        response = TestClient(app).get(
            "/api/files/3/parsed_content",
            params={"variant": "popo"},
            headers={"X-User-Id": "u1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == "# Popo"
    assert fake_minio.get_responses[0].closed is True
    assert fake_minio.get_responses[0].released is True


def test_parsed_content_rejects_markdown_popo_variant(monkeypatch):
    fake_file = SimpleNamespace(
        id=3,
        user_id="u1",
        filename="sample.pdf",
        minio_path="uploads/sample.pdf",
    )

    app.dependency_overrides[get_db] = lambda: FakeDb(fake_file)

    try:
        response = TestClient(app).get(
            "/api/files/3/parsed_content",
            params={"variant": "markdown_popo"},
            headers={"X-User-Id": "u1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400


def test_export_endpoint_returns_popo_markdown_download_url(monkeypatch):
    fake_file = SimpleNamespace(
        id=3,
        user_id="u1",
        filename="sample.pdf",
        minio_path="uploads/sample.pdf",
    )
    fake_minio = FakeMinio()

    app.dependency_overrides[get_db] = lambda: FakeDb(fake_file)
    monkeypatch.setattr("app.api.parsed.get_buckets", lambda: ["mds"])
    monkeypatch.setattr("app.api.parsed.minio_client", fake_minio)
    monkeypatch.setattr(
        "app.api.parsed.get_presigned_url",
        lambda bucket, path, expires=3600: f"http://minio/{bucket}/{path}?signed=1",
    )

    try:
        response = TestClient(app).get(
            "/api/files/3/export",
            params={"format": "markdown_popo"},
            headers={"X-User-Id": "u1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert fake_minio.stat_calls == [("mds", "sample_popo.md")]
    assert response.json()["download_url"] == "http://minio/mds/sample_popo.md?signed=1"
    assert response.json()["filename"] == "sample_popo.md"


def test_export_endpoint_rejects_popo_format(monkeypatch):
    fake_file = SimpleNamespace(
        id=3,
        user_id="u1",
        filename="sample.pdf",
        minio_path="uploads/sample.pdf",
    )

    app.dependency_overrides[get_db] = lambda: FakeDb(fake_file)

    try:
        response = TestClient(app).get(
            "/api/files/3/export",
            params={"format": "popo"},
            headers={"X-User-Id": "u1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400


def test_popo_status_returns_status_json(monkeypatch):
    fake_file = SimpleNamespace(
        id=3,
        user_id="u1",
        filename="sample.pdf",
        minio_path="uploads/sample.pdf",
    )
    fake_minio = FakeMinio()

    app.dependency_overrides[get_db] = lambda: FakeDb(fake_file)
    monkeypatch.setattr("app.api.parsed.get_buckets", lambda: ["mds"])
    monkeypatch.setattr("app.api.parsed.minio_client", fake_minio)

    try:
        response = TestClient(app).get(
            "/api/files/3/popo/status",
            headers={"X-User-Id": "u1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"status": "success", "message": ""}
    assert fake_minio.get_responses[0].closed is True
    assert fake_minio.get_responses[0].released is True


def test_popo_status_returns_not_available_when_artifact_missing(monkeypatch):
    fake_file = SimpleNamespace(
        id=3,
        user_id="u1",
        filename="sample.pdf",
        minio_path="uploads/sample.pdf",
    )
    fake_minio = FakeMinio()
    del fake_minio.existing_objects[("mds", "sample_popo_status.json")]

    app.dependency_overrides[get_db] = lambda: FakeDb(fake_file)
    monkeypatch.setattr("app.api.parsed.get_buckets", lambda: ["mds"])
    monkeypatch.setattr("app.api.parsed.minio_client", fake_minio)

    try:
        response = TestClient(app).get(
            "/api/files/3/popo/status",
            headers={"X-User-Id": "u1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"status": "not_available", "message": ""}


def test_popo_status_returns_500_when_status_json_is_corrupt(monkeypatch):
    fake_file = SimpleNamespace(
        id=3,
        user_id="u1",
        filename="sample.pdf",
        minio_path="uploads/sample.pdf",
    )
    fake_minio = FakeMinio()
    fake_minio.existing_objects[("mds", "sample_popo_status.json")] = b"{"

    app.dependency_overrides[get_db] = lambda: FakeDb(fake_file)
    monkeypatch.setattr("app.api.parsed.get_buckets", lambda: ["mds"])
    monkeypatch.setattr("app.api.parsed.minio_client", fake_minio)

    try:
        response = TestClient(app).get(
            "/api/files/3/popo/status",
            headers={"X-User-Id": "u1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 500
    assert response.json() != {"status": "not_available", "message": ""}
    assert fake_minio.get_responses[0].closed is True
    assert fake_minio.get_responses[0].released is True
