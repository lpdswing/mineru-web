from types import SimpleNamespace

import pytest

from app.models.enums import FileStatus
from app.services.parser import ParserService


class FakeDb:
    def __init__(self):
        self.commits = 0
        self.added = []
        self.tracked_file = None
        self.snapshots = []

    def commit(self):
        self.commits += 1
        if self.tracked_file is not None:
            self.snapshots.append(
                {
                    "status": self.tracked_file.status,
                    "parse_stage": getattr(self.tracked_file, "parse_stage", None),
                    "progress_percent": getattr(self.tracked_file, "progress_percent", None),
                    "progress_message": getattr(self.tracked_file, "progress_message", None),
                    "mineru_task_id": getattr(self.tracked_file, "mineru_task_id", None),
                }
            )

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


class FailingApiClient:
    def parse_file(self, **kwargs):
        self.kwargs = kwargs
        raise RuntimeError("mineru exploded")


class CallbackApiClient:
    def parse_file(self, **kwargs):
        self.kwargs = kwargs
        callback = kwargs["progress_callback"]
        callback({"task_id": "task-123456", "status": "submitted", "payload": {"task_id": "task-123456"}})
        callback(
            {
                "task_id": "task-123456",
                "status": "running",
                "payload": {"status": "running", "progress": 66, "message": "layout analysis"},
            }
        )
        callback(
            {
                "task_id": "task-123456",
                "status": "success",
                "stage": "downloading_result",
                "message": "正在下载解析结果",
                "payload": {"status": "success", "progress": 100, "message": "done"},
            }
        )
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


class FakeRedis:
    def __init__(self):
        self.published = []

    def publish_task(self, stream, task_data):
        self.published.append((stream, task_data))


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


def test_queue_parse_file_initializes_progress_and_clears_mineru_task(monkeypatch):
    fake_redis = FakeRedis()
    db = FakeDb()
    service = ParserService(db)
    file = SimpleNamespace(
        id=1,
        status=FileStatus.PARSE_FAILED,
        parse_stage="failed",
        progress_percent=78,
        progress_message="old failure",
        last_heartbeat_at=None,
        mineru_task_id="old-task",
        mineru_task_status="failed",
        mineru_task_payload='{"status":"failed"}',
    )

    monkeypatch.setattr("app.services.parser.redis_client", fake_redis)

    result = service.queue_parse_file(file, user_id="u1")

    assert result["status"] == "queued"
    assert file.status == FileStatus.PENDING
    assert file.parse_stage == "queued"
    assert file.progress_percent == 0
    assert file.progress_message == "队列等待中"
    assert file.last_heartbeat_at is not None
    assert file.mineru_task_id is None
    assert file.mineru_task_status is None
    assert file.mineru_task_payload is None
    assert fake_redis.published == [
        ("file_parser_stream", {"file_id": 1, "user_id": "u1", "parse_method": "auto"})
    ]


def test_parse_file_records_local_progress_stages(monkeypatch):
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
        parse_stage=None,
        progress_percent=None,
        progress_message=None,
        last_heartbeat_at=None,
        mineru_task_id=None,
        mineru_task_status=None,
        mineru_task_payload=None,
    )
    db.tracked_file = file

    monkeypatch.setattr("app.services.parser.minio_client", FakeMinio())
    monkeypatch.setattr("app.services.parser.get_buckets", lambda: ["mds"])

    result = service.parse_file(file, user_id="u1")

    assert result == {"status": "success"}
    assert file.status == FileStatus.PARSED
    assert file.parse_stage == "completed"
    assert file.progress_percent == 100
    assert file.progress_message == "解析完成"
    assert file.last_heartbeat_at is not None
    assert [snapshot["parse_stage"] for snapshot in db.snapshots] == [
        "fetching_source",
        "submitting_mineru",
        "syncing_artifacts",
        "completed",
    ]


def test_parse_file_records_failed_progress_stage(monkeypatch):
    db = FakeDb()
    service = ParserService(
        db,
        mineru_api_client=FailingApiClient(),
        artifact_sync_factory=lambda bucket: FakeArtifactSync(),
    )
    file = SimpleNamespace(
        id=1,
        minio_path="uploads/sample.pdf",
        status=FileStatus.PENDING,
        start_at=None,
        finish_at=None,
        error_message=None,
        parse_stage=None,
        progress_percent=None,
        progress_message=None,
        last_heartbeat_at=None,
        mineru_task_id=None,
        mineru_task_status=None,
        mineru_task_payload=None,
    )

    monkeypatch.setattr("app.services.parser.minio_client", FakeMinio())
    monkeypatch.setattr("app.services.parser.get_buckets", lambda: ["mds"])

    with pytest.raises(Exception, match="mineru exploded"):
        service.parse_file(file, user_id="u1")

    assert file.status == FileStatus.PARSE_FAILED
    assert file.parse_stage == "failed"
    assert file.progress_message == "mineru exploded"
    assert file.last_heartbeat_at is not None


def test_parse_file_persists_mineru_task_progress_callback(monkeypatch):
    db = FakeDb()
    service = ParserService(
        db,
        mineru_api_client=CallbackApiClient(),
        artifact_sync_factory=lambda bucket: FakeArtifactSync(),
    )
    file = SimpleNamespace(
        id=1,
        minio_path="uploads/sample.pdf",
        status=FileStatus.PENDING,
        start_at=None,
        finish_at=None,
        error_message=None,
        parse_stage=None,
        progress_percent=None,
        progress_message=None,
        last_heartbeat_at=None,
        mineru_task_id=None,
        mineru_task_status=None,
        mineru_task_payload=None,
    )

    monkeypatch.setattr("app.services.parser.minio_client", FakeMinio())
    monkeypatch.setattr("app.services.parser.get_buckets", lambda: ["mds"])

    assert service.parse_file(file, user_id="u1") == {"status": "success"}

    assert file.mineru_task_id == "task-123456"
    assert file.mineru_task_status == "success"
    assert '"done"' in file.mineru_task_payload
    assert file.progress_percent == 100
    assert file.parse_stage == "completed"
