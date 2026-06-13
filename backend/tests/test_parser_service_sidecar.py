from types import SimpleNamespace

import pytest

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
        return SimpleNamespace(markdown="# parsed", markdown_path="sample.md", uploaded_paths=[])


class FakeArtifactSyncWithPaths:
    def sync_zip(self, content, output_name):
        assert output_name == "sample"
        return SimpleNamespace(
            markdown="# parsed",
            markdown_path="sample.md",
            uploaded_paths=[
                "sample/auto/sample_middle.json",
                "sample/auto/sample_content_list.json",
                "sample/auto/sample_model.json",
            ],
        )


class FakePopoPostprocessor:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    def postprocess(self, bucket, prefix, uploaded_paths, source_pdf_path=None, source_bucket=None):
        self.calls.append((bucket, prefix, uploaded_paths, source_pdf_path, source_bucket))
        if self.fail:
            raise RuntimeError("popo failed")


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


@pytest.mark.parametrize("extension", [".docx", ".pptx", ".xlsx"])
def test_parse_file_accepts_mineru_office_formats(monkeypatch, extension):
    fake_client = FakeApiClient()
    db = FakeDb()
    service = ParserService(
        db,
        mineru_api_client=fake_client,
        artifact_sync_factory=lambda bucket: FakeArtifactSync(),
    )
    file = SimpleNamespace(
        id=1,
        minio_path=f"uploads/sample{extension}",
        status=FileStatus.PENDING,
        start_at=None,
        finish_at=None,
        error_message=None,
    )

    monkeypatch.setattr("app.services.parser.minio_client", FakeMinio())
    monkeypatch.setattr("app.services.parser.get_buckets", lambda: ["mds"])

    assert service.parse_file(file, user_id="u1") == {"status": "success"}
    assert fake_client.kwargs["filename"] == f"sample{extension}"
    assert file.status == FileStatus.PARSED


def test_parse_file_rejects_legacy_xls(monkeypatch):
    service = ParserService(
        FakeDb(),
        mineru_api_client=FakeApiClient(),
        artifact_sync_factory=lambda bucket: FakeArtifactSync(),
    )
    file = SimpleNamespace(
        id=1,
        minio_path="uploads/sample.xls",
        status=FileStatus.PENDING,
        start_at=None,
        finish_at=None,
        error_message=None,
    )

    monkeypatch.setattr("app.services.parser.minio_client", FakeMinio())
    monkeypatch.setattr("app.services.parser.get_buckets", lambda: ["mds"])

    with pytest.raises(Exception, match="不支持的文件类型: \\.xls"):
        service.parse_file(file, user_id="u1")
    assert file.status == FileStatus.PARSE_FAILED


def test_parse_file_triggers_popo_after_artifact_sync(monkeypatch):
    fake_client = FakeApiClient()
    fake_popo = FakePopoPostprocessor()
    db = FakeDb()
    service = ParserService(
        db,
        mineru_api_client=fake_client,
        artifact_sync_factory=lambda bucket: FakeArtifactSyncWithPaths(),
        popo_postprocessor=fake_popo,
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

    assert service.parse_file(file, user_id="u1") == {"status": "success"}
    assert fake_popo.calls == [
        (
            "mds",
            "sample",
            [
                "sample/auto/sample_middle.json",
                "sample/auto/sample_content_list.json",
                "sample/auto/sample_model.json",
            ],
            "uploads/sample.pdf",
            "mineru-files",
        )
    ]


def test_parse_file_keeps_success_when_popo_fails(monkeypatch):
    fake_popo = FakePopoPostprocessor(fail=True)
    service = ParserService(
        FakeDb(),
        mineru_api_client=FakeApiClient(),
        artifact_sync_factory=lambda bucket: FakeArtifactSyncWithPaths(),
        popo_postprocessor=fake_popo,
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
    assert file.status == FileStatus.PARSED
