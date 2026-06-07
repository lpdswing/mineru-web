from types import SimpleNamespace

from app.models.enums import FileStatus
from app.services.parser import ParserService


class FakeDb:
    def __init__(self):
        self.commits = 0
        self.added = []

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def add(self, item):
        self.added.append(item)

    def query(self, model):
        return self

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return SimpleNamespace(
            to_dict=lambda: {
                "force_ocr": False,
                "ocr_lang": "ch",
                "formula_recognition": True,
                "table_recognition": True,
                "backend": "pipeline",
            }
        )


class FakeResponse:
    def read(self):
        return b"%PDF"


class FakeMinio:
    def get_object(self, bucket, path):
        return FakeResponse()


class FakeApiClient:
    def parse_file(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(content=b"zip", content_type="application/zip")


class FakeArtifactSync:
    def sync_zip(self, content, output_name):
        assert content == b"zip"
        assert output_name == "sample"
        return SimpleNamespace(markdown="# parsed")


def test_parse_file_uses_mineru_api_and_artifact_sync(monkeypatch):
    fake_client = FakeApiClient()
    db = FakeDb()
    service = ParserService(
        db,
        mineru_api_client=fake_client,
        artifact_sync_factory=lambda bucket: FakeArtifactSync(),
    )
    file = SimpleNamespace(
        id=1,
        minio_path="uploads/sample.pdf",
        status=FileStatus.PENDING,
        start_at=None,
        finish_at=None,
        error_message=None,
    )

    monkeypatch.setattr("app.services.parser.minio_client", FakeMinio())
    monkeypatch.setattr("app.services.parser.get_buckets", lambda: ["mds"])

    result = service.parse_file(file, user_id="u1")

    assert result == {"status": "success"}
    assert fake_client.kwargs["filename"] == "sample.pdf"
    assert fake_client.kwargs["backend"] == "pipeline"
    assert file.status == FileStatus.PARSED
    assert file.error_message is None
    assert db.added[0].content == "# parsed"
