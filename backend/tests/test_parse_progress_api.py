import json
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.database import get_db
from app.models.enums import FileStatus
from app.models.file import File as FileModel
from main import app


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


def test_file_to_dict_includes_parse_progress_fields():
    heartbeat = datetime(2026, 6, 13, 5, 30, tzinfo=timezone.utc)
    file = FileModel(
        user_id="u1",
        filename="sample.pdf",
        size=123,
        status=FileStatus.PARSING,
        minio_path="uploads/sample.pdf",
        parse_stage="waiting_mineru",
        progress_percent=42,
        progress_message="MinerU running",
        last_heartbeat_at=heartbeat,
        mineru_task_id="task-1234567890",
        mineru_task_status="running",
        mineru_task_payload=json.dumps({"status": "running", "progress": 42}),
    )

    result = file.to_dict()

    assert result["parse_stage"] == "waiting_mineru"
    assert result["progress_percent"] == 42
    assert result["progress_message"] == "MinerU running"
    assert result["last_heartbeat_at"] == heartbeat.isoformat()
    assert result["mineru_task_id"] == "task-1234567890"
    assert result["mineru_task_status"] == "running"
    assert "mineru_task_payload" not in result


def test_parse_status_returns_detailed_progress_payload():
    heartbeat = datetime(2026, 6, 13, 5, 30, tzinfo=timezone.utc)
    fake_file = SimpleNamespace(
        id=7,
        user_id="u1",
        status=FileStatus.PARSING,
        parse_stage="waiting_mineru",
        progress_percent=55,
        progress_message="MinerU queued",
        last_heartbeat_at=heartbeat,
        mineru_task_id="task-abcdef",
        mineru_task_status="queued",
        mineru_task_payload=json.dumps({"status": "queued", "message": "waiting"}),
    )

    app.dependency_overrides[get_db] = lambda: FakeDb(fake_file)
    try:
        response = TestClient(app).get(
            "/api/files/7/parse/status",
            headers={"X-User-Id": "u1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "file_id": 7,
        "status": "parsing",
        "message": "正在解析",
        "parse_stage": "waiting_mineru",
        "progress_percent": 55,
        "progress_message": "MinerU queued",
        "last_heartbeat_at": heartbeat.isoformat(),
        "mineru_task_id": "task-abcdef",
        "mineru_task_status": "queued",
        "mineru_task_payload": {"status": "queued", "message": "waiting"},
    }
