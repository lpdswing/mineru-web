from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.database import get_db
from app.models.file import File as FileModel
from main import app


class FakeObject:
    def __init__(self, chunks, headers=None):
        self.chunks = chunks
        self.headers = headers or {}
        self.closed = False
        self.released = False

    def stream(self, chunk_size=32 * 1024):
        for chunk in self.chunks:
            yield chunk

    def close(self):
        self.closed = True

    def release_conn(self):
        self.released = True


class FakeMinio:
    def __init__(self):
        self.get_calls = []
        self.responses = []

    def get_object(self, bucket, path):
        self.get_calls.append((bucket, path))
        response = FakeObject([b"%PDF", b"-body"], headers={"Content-Type": "application/pdf"})
        self.responses.append(response)
        return response


class FakeQuery:
    def __init__(self, item):
        self.item = item

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.item


class FakeDb:
    def __init__(self, file):
        self.file = file

    def query(self, model):
        if model is FileModel:
            return FakeQuery(self.file)
        return FakeQuery(None)


def test_file_content_streams_original_file_inline(monkeypatch):
    fake_file = SimpleNamespace(
        id=10,
        user_id="u1",
        filename="DeepSeek_R1.pdf",
        minio_path="uploads/deepseek.pdf",
    )
    fake_minio = FakeMinio()

    app.dependency_overrides[get_db] = lambda: FakeDb(fake_file)
    monkeypatch.setattr("app.api.files.MINIO_BUCKET", "mineru-files")
    monkeypatch.setattr("app.api.files.minio_client", fake_minio)

    try:
        response = TestClient(app).get(
            "/api/files/10/content",
            headers={"X-User-Id": "u1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.content == b"%PDF-body"
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.headers["content-disposition"] == (
        "inline; filename*=UTF-8''DeepSeek_R1.pdf"
    )
    assert fake_minio.get_calls == [("mineru-files", "uploads/deepseek.pdf")]
    assert fake_minio.responses[0].closed is True
    assert fake_minio.responses[0].released is True
