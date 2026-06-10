# Worker Concurrency Design

## Context

MinerU API can use multiple GPUs through `mineru-router`, but the current `mineru-web` worker processes Redis Stream messages serially inside each worker process. `WORKER_REPLICAS` can increase total throughput by adding containers, but there is no per-worker concurrency control. `WORK_BATCH` only controls how many messages are read in one call; the messages are still processed one by one.

The goal is to use MinerU API capacity more effectively with a simple static concurrency limit. This design does not add dynamic MinerU capacity detection, automatic retry, pending-message reclaim, or a dead-letter queue.

## Goals

- Add per-worker static concurrency with `WORKER_CONCURRENCY`.
- Keep the deployment-level concurrency model simple:

  ```text
  total parse concurrency = WORKER_REPLICAS * WORKER_CONCURRENCY
  ```

- Default to current behavior when not configured: one worker container processes one task at a time.
- Ensure a worker never claims more Redis messages than it has free execution slots.
- Keep task failures isolated so one failed parse does not block other in-flight parses.
- Keep the existing failure semantics: failed parses mark the file as `parse_failed` and the Redis message is acknowledged after processing.

## Non-Goals

- No automatic retry or dead-letter queue.
- No Redis pending entry reclaim.
- No dynamic capacity probing from MinerU health/status endpoints.
- No async rewrite of Redis, SQLAlchemy, MinIO, or HTTP client code.
- No Prometheus metrics in this change.

## Configuration

Add:

```text
WORKER_CONCURRENCY=1
```

Rules:

- Missing, invalid, or less-than-one values fall back to `1`.
- `WORKER_REPLICAS` continues to control worker container count.
- `WORKER_CONCURRENCY` controls max in-flight tasks inside each worker process.
- `WORK_BATCH` is not part of the new scheduling model and should not be documented as a tuning knob for parse concurrency.

Recommended multi-GPU deployment:

```text
WORKER_REPLICAS=2
WORKER_CONCURRENCY=2
MINERU_API_USE_ASYNC_TASKS=1
```

This gives four worker-side parse slots. `MINERU_API_USE_ASYNC_TASKS=1` switches each slot from synchronous `/file_parse` calls to `/tasks` submit/poll/result calls. It does not itself increase worker concurrency.

## Worker Scheduling Model

Each worker process owns a `ThreadPoolExecutor`:

```python
ThreadPoolExecutor(max_workers=WORKER_CONCURRENCY)
```

The main loop tracks in-flight futures and only reads new Redis Stream messages when there are free slots:

```text
free_slots = WORKER_CONCURRENCY - len(in_flight)
if free_slots > 0:
    read up to free_slots messages
    submit each message to the thread pool
```

The worker acknowledges a Redis message only after its future completes. This means a worker does not claim work it cannot start, and other worker replicas can keep consuming available messages.

## Task Lifecycle

Each Redis message follows this lifecycle:

```text
XREADGROUP -> submit to thread -> process_task -> future complete -> XACK
```

Each task thread creates its own database session:

```python
with get_db_context() as db:
    process_task(task_data, db)
```

`ParserService`, `MineruApiClient`, and MinIO operations stay inside the task thread. SQLAlchemy sessions are not shared across threads.

On success:

- The parser stores artifacts and parsed content as it does today.
- The worker acknowledges the Redis message.

On failure:

- The file is marked `parse_failed` using the existing parser/worker semantics.
- The worker logs the failure.
- The worker acknowledges the Redis message.
- Other in-flight tasks continue running.

## Shutdown Behavior

On normal interruption, the worker should stop reading new messages and wait for currently running futures to finish before exiting. This keeps the existing at-most-once practical behavior: a task that was already started is allowed to finish and ack.

Hard container termination can still interrupt in-flight tasks. Handling that with Redis pending reclaim is outside this design.

## Logging

At startup, log:

```text
Worker Consumer Name: worker_...
WORKER_CONCURRENCY=N
```

During scheduling, log concise state changes such as:

```text
in_flight=X free_slots=Y received=Z
```

Per-task logs keep the current shape:

```text
Processing task: ...
Processing file ...
File ... processed successfully
Error processing task ...
Task ... processed and acknowledged
```

## Tests

Add worker scheduling tests with fake Redis and fake task processing:

- `WORKER_CONCURRENCY=1` runs at most one task at a time.
- `WORKER_CONCURRENCY=3` runs at most three tasks at a time.
- Redis reads are capped by free slots.
- Messages are acknowledged only after task futures complete.
- Failed tasks are acknowledged and do not block other in-flight tasks.
- Invalid `WORKER_CONCURRENCY` values fall back to `1`.

Existing parser and MinerU API client tests should continue to pass. No test should call real MinerU inference.

## Deployment Notes

For a MinerU API router with known capacity, set:

```text
WORKER_REPLICAS * WORKER_CONCURRENCY <= MinerU parse slot capacity
```

Start conservatively and increase until GPU utilization is high without causing excessive MinerU queueing or timeouts.

For multi-GPU deployments, prefer:

```text
MINERU_API_USE_ASYNC_TASKS=1
```

This avoids holding a single long-running `/file_parse` HTTP request open for each parse slot.
