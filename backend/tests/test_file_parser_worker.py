import json
from concurrent.futures import Future

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


class FakeRedis:
    def __init__(self, messages):
        self.messages = list(messages)
        self.read_counts = []
        self.acked = []

    def read_stream(self, stream, group, consumer, count=1, block=1000):
        self.read_counts.append(count)
        batch = self.messages[:count]
        self.messages = self.messages[count:]
        return batch

    def ack_message(self, stream, group, message_id):
        self.acked.append(message_id)


class CapturingExecutor:
    def __init__(self):
        self.submitted = []
        self.futures = []

    def submit(self, fn, *args):
        future = Future()
        self.submitted.append((fn, args, future))
        self.futures.append(future)
        return future


def make_message(file_id):
    return (
        f"{file_id}-0".encode("utf-8"),
        {b"data": json.dumps({"file_id": file_id, "user_id": "u1"}).encode("utf-8")},
    )


def test_run_worker_loop_once_reads_only_free_slots(monkeypatch):
    fake_redis = FakeRedis([make_message(1), make_message(2), make_message(3)])
    executor = CapturingExecutor()

    monkeypatch.setattr(worker, "process_stream_message", lambda stream_id, message: None)

    in_flight = {}
    worker.run_worker_loop_once(fake_redis, executor, in_flight, concurrency=2, block_ms=0)

    assert fake_redis.read_counts == [2]
    assert len(in_flight) == 2
    assert len(executor.submitted) == 2

    worker.run_worker_loop_once(fake_redis, executor, in_flight, concurrency=2, block_ms=0)

    assert fake_redis.read_counts == [2]
    assert len(in_flight) == 2


def test_run_worker_loop_once_acks_only_after_future_completion(monkeypatch):
    fake_redis = FakeRedis([make_message(1)])
    executor = CapturingExecutor()

    monkeypatch.setattr(worker, "process_stream_message", lambda stream_id, message: None)

    in_flight = {}
    worker.run_worker_loop_once(fake_redis, executor, in_flight, concurrency=1, block_ms=0)

    assert fake_redis.acked == []
    future = executor.futures[0]
    future.set_result(None)

    worker.run_worker_loop_once(fake_redis, executor, in_flight, concurrency=1, block_ms=0)

    assert fake_redis.acked == [b"1-0"]
    assert in_flight == {}


def test_run_worker_loop_once_acks_failed_future_and_keeps_running(monkeypatch):
    fake_redis = FakeRedis([make_message(1), make_message(2)])
    executor = CapturingExecutor()

    monkeypatch.setattr(worker, "process_stream_message", lambda stream_id, message: None)

    in_flight = {}
    worker.run_worker_loop_once(fake_redis, executor, in_flight, concurrency=2, block_ms=0)
    executor.futures[0].set_exception(RuntimeError("boom"))

    worker.run_worker_loop_once(fake_redis, executor, in_flight, concurrency=2, block_ms=0)

    assert fake_redis.acked == [b"1-0"]
    assert len(in_flight) == 1


class FakeWorkerRedis:
    def __init__(self):
        self.created_groups = []

    def create_consumer_group(self, stream, group):
        self.created_groups.append((stream, group))

    def read_stream(self, *args, **kwargs):
        raise KeyboardInterrupt


def test_run_worker_uses_configured_concurrency_and_creates_group(monkeypatch):
    fake_redis = FakeWorkerRedis()
    calls = []

    class FakeExecutor:
        def __init__(self, max_workers):
            calls.append(("executor", max_workers))

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def loop_once(redis, executor, in_flight, concurrency, block_ms=1000):
        calls.append(("loop", redis, executor, concurrency, block_ms))
        raise KeyboardInterrupt

    monkeypatch.setenv("WORKER_CONCURRENCY", "4")
    monkeypatch.setattr(worker, "redis_client", fake_redis)
    monkeypatch.setattr(worker, "ThreadPoolExecutor", FakeExecutor)
    monkeypatch.setattr(worker, "run_worker_loop_once", loop_once)

    worker.run_worker()

    assert fake_redis.created_groups == [(worker.PARSER_STREAM, worker.CONSUMER_GROUP)]
    assert calls[0] == ("executor", 4)
    assert calls[1][0] == "loop"
    assert calls[1][3] == 4
