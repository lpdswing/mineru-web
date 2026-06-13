# Worker Concurrency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add static per-worker parse concurrency so total parse capacity is controlled by `WORKER_REPLICAS * WORKER_CONCURRENCY`.

**Architecture:** Keep Redis Stream and synchronous parser code, but wrap task execution in a `ThreadPoolExecutor`. The worker main loop tracks in-flight futures, reads at most the number of free slots, and acknowledges each Redis message only after its future completes. Each task thread creates its own DB session.

**Tech Stack:** Python `concurrent.futures.ThreadPoolExecutor`, Redis Stream consumer groups, SQLAlchemy session context, pytest, Docker Compose environment variables.

---

## File Structure

- Modify `backend/app/services/file_parser_worker.py`
  - Add `parse_worker_concurrency()` for safe env parsing.
  - Add `decode_task_message()` for isolated message decoding.
  - Add `process_stream_message()` to run one Redis message inside a task thread with its own DB session.
  - Add `run_worker_loop_once()` so scheduling behavior is testable without an infinite loop.
  - Rewrite `run_worker()` to use `ThreadPoolExecutor` and in-flight future tracking.
- Create `backend/tests/test_file_parser_worker.py`
  - Unit tests for concurrency parsing, slot-based reads, ack timing, failure ack, and invalid JSON behavior.
- Modify `docker-compose.yml`
  - Add `WORKER_CONCURRENCY=${WORKER_CONCURRENCY:-1}` to worker environment.
  - Add `MINERU_API_USE_ASYNC_TASKS=${MINERU_API_USE_ASYNC_TASKS:-0}` to worker environment.
- Modify `docker-compose.mac.yml`
  - Add the same worker environment variables for local macOS testing.
- Modify `docs/deployment.md`
  - Document total concurrency and multi-GPU example.

---

### Task 1: Add worker concurrency config parsing

**Files:**
- Modify: `backend/app/services/file_parser_worker.py`
- Test: `backend/tests/test_file_parser_worker.py`

- [ ] **Step 1: Write failing tests for config parsing**

Create `backend/tests/test_file_parser_worker.py`:

```python
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
```

- [ ] **Step 2: Run the new test and verify it fails**

Run:

```bash
.venv/bin/pytest backend/tests/test_file_parser_worker.py::test_parse_worker_concurrency_defaults_to_one_for_invalid_values -q
```

Expected: FAIL with `AttributeError: module 'app.services.file_parser_worker' has no attribute 'parse_worker_concurrency'`.

- [ ] **Step 3: Implement minimal config parser**

In `backend/app/services/file_parser_worker.py`, replace the `WORK_BATCH` global with:

```python
def parse_worker_concurrency(raw_value=None) -> int:
    value = raw_value if raw_value is not None else os.getenv("WORKER_CONCURRENCY", "1")
    try:
        concurrency = int(value)
    except (TypeError, ValueError):
        return 1
    return concurrency if concurrency >= 1 else 1
```

Do not keep `WORK_BATCH`; the new scheduler reads by free slots only.

- [ ] **Step 4: Run the config test and verify it passes**

Run:

```bash
.venv/bin/pytest backend/tests/test_file_parser_worker.py::test_parse_worker_concurrency_defaults_to_one_for_invalid_values -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/file_parser_worker.py backend/tests/test_file_parser_worker.py
git commit -m "Add worker concurrency config parsing"
```

---

### Task 2: Extract single-message processing for threaded execution

**Files:**
- Modify: `backend/app/services/file_parser_worker.py`
- Test: `backend/tests/test_file_parser_worker.py`

- [ ] **Step 1: Write failing tests for single-message processing**

Append to `backend/tests/test_file_parser_worker.py`:

```python
import json


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
```

- [ ] **Step 2: Run these tests and verify they fail**

Run:

```bash
.venv/bin/pytest backend/tests/test_file_parser_worker.py::test_process_stream_message_decodes_json_and_uses_fresh_db_context backend/tests/test_file_parser_worker.py::test_process_stream_message_raises_json_decode_error_for_bad_payload -q
```

Expected: FAIL with `AttributeError` for `process_stream_message`.

- [ ] **Step 3: Implement message decoding and task wrapper**

In `backend/app/services/file_parser_worker.py`, add:

```python
def decode_task_message(message: dict) -> dict:
    return json.loads(message[b"data"].decode("utf-8"))


def process_stream_message(stream_id, message: dict) -> None:
    task_data = decode_task_message(message)
    logger.info(f"Processing task: {task_data}")
    with get_db_context() as db:
        process_task(task_data, db)
```

- [ ] **Step 4: Run the message-processing tests and verify they pass**

Run:

```bash
.venv/bin/pytest backend/tests/test_file_parser_worker.py::test_process_stream_message_decodes_json_and_uses_fresh_db_context backend/tests/test_file_parser_worker.py::test_process_stream_message_raises_json_decode_error_for_bad_payload -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/file_parser_worker.py backend/tests/test_file_parser_worker.py
git commit -m "Extract worker stream message processing"
```

---

### Task 3: Add testable scheduler loop with slot-based reads and ack after completion

**Files:**
- Modify: `backend/app/services/file_parser_worker.py`
- Test: `backend/tests/test_file_parser_worker.py`

- [ ] **Step 1: Write failing tests for scheduler behavior**

Append to `backend/tests/test_file_parser_worker.py`:

```python
from concurrent.futures import Future


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
```

- [ ] **Step 2: Run scheduler tests and verify they fail**

Run:

```bash
.venv/bin/pytest backend/tests/test_file_parser_worker.py::test_run_worker_loop_once_reads_only_free_slots backend/tests/test_file_parser_worker.py::test_run_worker_loop_once_acks_only_after_future_completion backend/tests/test_file_parser_worker.py::test_run_worker_loop_once_acks_failed_future_and_keeps_running -q
```

Expected: FAIL with `AttributeError` for `run_worker_loop_once`.

- [ ] **Step 3: Implement scheduler loop helper**

In `backend/app/services/file_parser_worker.py`, add imports:

```python
from concurrent.futures import Future, ThreadPoolExecutor
```

Then add:

```python
def run_worker_loop_once(
    redis,
    executor,
    in_flight: dict[Future, bytes],
    concurrency: int,
    block_ms: int = 1000,
) -> None:
    for future in list(in_flight):
        if not future.done():
            continue
        stream_id = in_flight.pop(future)
        try:
            future.result()
        except Exception as exc:
            logger.error(f"Error processing message {stream_id}: {exc}")
        redis.ack_message(PARSER_STREAM, CONSUMER_GROUP, stream_id)
        logger.info(f"Task {stream_id} processed and acknowledged")

    free_slots = concurrency - len(in_flight)
    if free_slots <= 0:
        return

    messages = redis.read_stream(
        PARSER_STREAM,
        CONSUMER_GROUP,
        CONSUMER_NAME,
        count=free_slots,
        block=block_ms,
    )
    if not messages:
        return

    logger.info(
        f"in_flight={len(in_flight)} free_slots={free_slots} received={len(messages)}"
    )
    for stream_id, message in messages:
        future = executor.submit(process_stream_message, stream_id, message)
        in_flight[future] = stream_id
```

- [ ] **Step 4: Run scheduler tests and verify they pass**

Run:

```bash
.venv/bin/pytest backend/tests/test_file_parser_worker.py::test_run_worker_loop_once_reads_only_free_slots backend/tests/test_file_parser_worker.py::test_run_worker_loop_once_acks_only_after_future_completion backend/tests/test_file_parser_worker.py::test_run_worker_loop_once_acks_failed_future_and_keeps_running -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/file_parser_worker.py backend/tests/test_file_parser_worker.py
git commit -m "Add worker slot scheduler"
```

---

### Task 4: Rewrite `run_worker()` to use the threaded scheduler

**Files:**
- Modify: `backend/app/services/file_parser_worker.py`
- Test: `backend/tests/test_file_parser_worker.py`

- [ ] **Step 1: Write a failing test for `run_worker()` startup wiring**

Append to `backend/tests/test_file_parser_worker.py`:

```python
class FakeWorkerRedis:
    def __init__(self):
        self.created_groups = []

    def create_consumer_group(self, stream, group):
        self.created_groups.append((stream, group))


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
```

- [ ] **Step 2: Run the startup wiring test and verify it fails**

Run:

```bash
.venv/bin/pytest backend/tests/test_file_parser_worker.py::test_run_worker_uses_configured_concurrency_and_creates_group -q
```

Expected: FAIL because `run_worker()` still uses serial loop and does not create a `ThreadPoolExecutor`.

- [ ] **Step 3: Rewrite `run_worker()`**

Replace the body of `run_worker()` in `backend/app/services/file_parser_worker.py` with:

```python
def run_worker():
    logger.info("Starting file parser worker...")
    concurrency = parse_worker_concurrency()
    logger.info(f"WORKER_CONCURRENCY={concurrency}")

    try:
        redis_client.create_consumer_group(PARSER_STREAM, CONSUMER_GROUP)
    except Exception as e:
        logger.error(f"Failed to create consumer group: {e}")
        return

    in_flight = {}
    try:
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            while True:
                try:
                    run_worker_loop_once(redis_client, executor, in_flight, concurrency)
                except Exception as e:
                    logger.error(f"Error reading from stream: {e}")
                    time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
    except Exception as e:
        logger.error(f"Worker error: {e}")
    finally:
        logger.info("清理资源。。。")
        clean_memory()
```

This waits for in-flight futures on normal `ThreadPoolExecutor` shutdown.

- [ ] **Step 4: Run all worker tests**

Run:

```bash
.venv/bin/pytest backend/tests/test_file_parser_worker.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/file_parser_worker.py backend/tests/test_file_parser_worker.py
git commit -m "Run worker tasks with thread pool"
```

---

### Task 5: Add worker concurrency deployment configuration

**Files:**
- Modify: `docker-compose.yml`
- Modify: `docker-compose.mac.yml`
- Modify: `docs/deployment.md`

- [ ] **Step 1: Update compose environment variables**

In `docker-compose.yml`, under `worker.environment`, add:

```yaml
      - WORKER_CONCURRENCY=${WORKER_CONCURRENCY:-1}
      - MINERU_API_USE_ASYNC_TASKS=${MINERU_API_USE_ASYNC_TASKS:-0}
```

In `docker-compose.mac.yml`, under `worker.environment`, add:

```yaml
      - WORKER_CONCURRENCY=${WORKER_CONCURRENCY:-1}
      - MINERU_API_USE_ASYNC_TASKS=${MINERU_API_USE_ASYNC_TASKS:-0}
```

- [ ] **Step 2: Update deployment docs**

In `docs/deployment.md`, near existing worker deployment settings, add:

```markdown
### Worker 并发

worker 侧总解析并发为：

```text
WORKER_REPLICAS * WORKER_CONCURRENCY
```

默认 `WORKER_CONCURRENCY=1`。多 GPU 部署可以按 MinerU API 可承载的解析槽位调大，例如：

```text
WORKER_REPLICAS=2
WORKER_CONCURRENCY=2
MINERU_API_USE_ASYNC_TASKS=1
```

`MINERU_API_USE_ASYNC_TASKS=1` 只切换 MinerU API 调用方式为 `/tasks` 提交、轮询、取结果，不会单独增加 worker 并发。
```

- [ ] **Step 3: Validate compose files**

Run:

```bash
MINIO_ENDPOINT=10.10.10.16:9000 docker compose -f docker-compose.yml config --services
MINIO_ENDPOINT=10.10.10.16:9000 docker compose -f docker-compose.mac.yml config --services
```

Expected: both commands exit 0 and list services.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml docker-compose.mac.yml docs/deployment.md
git commit -m "Document worker parse concurrency settings"
```

---

### Task 6: Full verification and graph update

**Files:**
- Modify: `graphify-out/*` generated files if graphify accepts the update; these are ignored.

- [ ] **Step 1: Run backend tests**

Run:

```bash
.venv/bin/pytest backend/tests -q
```

Expected: PASS for all backend tests.

- [ ] **Step 2: Run worker-focused tests with verbose output**

Run:

```bash
.venv/bin/pytest backend/tests/test_file_parser_worker.py -q
```

Expected: PASS.

- [ ] **Step 3: Validate compose files**

Run:

```bash
MINIO_ENDPOINT=10.10.10.16:9000 docker compose -f docker-compose.yml config --services
MINIO_ENDPOINT=10.10.10.16:9000 docker compose -f docker-compose.mac.yml config --services
```

Expected: both commands exit 0.

- [ ] **Step 4: Update graphify**

Run:

```bash
graphify update .
```

Expected: graph updates, or if graphify refuses due to known node-count shrinkage, record the refusal in the final implementation notes.

- [ ] **Step 5: Confirm final git status**

Run:

```bash
git status --short
```

Expected: no tracked source/config/doc files are modified. `graphify-out/` is ignored and should not appear in status.
