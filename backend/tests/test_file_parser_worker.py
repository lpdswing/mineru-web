import json

import pytest

from app.services import file_parser_worker as worker


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, 1),
        ("", 1),
        ("0", 1),
        ("-2", 1),
        ("abc", 1),
        ("3", 3),
    ],
)
def test_parse_worker_concurrency_defaults_to_one_for_invalid_values(raw, expected):
    assert worker.parse_worker_concurrency(raw) == expected


class FakeDbContext:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self.db

    def __exit__(self, exc_type, exc, tb):
        return False


def test_process_stream_message_decodes_json_and_uses_fresh_db_context(monkeypatch):
    calls = []
    fake_db = object()

    monkeypatch.setattr(worker, "get_db_context", lambda: FakeDbContext(fake_db))
    monkeypatch.setattr(
        worker,
        "process_task",
        lambda task_data, db: calls.append((task_data, db)),
    )

    message = {b"data": json.dumps({"file_id": 7, "user_id": "u1"}).encode("utf-8")}

    worker.process_stream_message(b"1-0", message)

    assert calls == [({"file_id": 7, "user_id": "u1"}, fake_db)]


def test_process_stream_message_raises_json_decode_error_for_bad_payload(monkeypatch):
    monkeypatch.setattr(worker, "get_db_context", lambda: FakeDbContext(object()))

    with pytest.raises(json.JSONDecodeError):
        worker.process_stream_message(b"1-0", {b"data": b"not-json"})
