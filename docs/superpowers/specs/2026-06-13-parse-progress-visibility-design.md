# Parse Progress Visibility Design

## Summary

Add parse-progress visibility to mineru-web so users can see what stage a file is in, how long it has been running, whether MinerU async task mode has reported an upstream state, and whether a parsing task appears stale. The first version is observability only: it does not add cancel, pause, retry orchestration, or worker/process management.

The design favors persisted progress data on the existing `files` table so both the file list and single-file status endpoints can expose the same view of progress. When MinerU async task mode is enabled, mineru-web should surface the upstream task id and latest task payload. When MinerU does not expose a real percent complete, the UI should fall back to local stage-based progress and elapsed-time hints without pretending the percentage is exact.

## Goals

- Show per-file parse progress in the file list.
- Persist progress state in the database so refreshes and page switches do not lose visibility.
- Surface MinerU async task status when `MINERU_API_USE_ASYNC_TASKS=1`.
- Expose a stale-task hint when parsing appears stuck.
- Keep the current parse success/failure flow intact.
- Reuse existing `/api/files` and `/api/files/{file_id}/parse/status` instead of adding a parallel progress API.

## Non-Goals

- Do not add cancel, pause, resume, or force-kill controls.
- Do not add queue scheduling, queue reordering, or automatic retries.
- Do not promise a real internal MinerU percentage when the upstream API does not provide one.
- Do not add WebSocket or SSE transport in the first version; existing polling stays in place.

## Current State

`File` rows currently persist:

- coarse status: `pending`, `parsing`, `parsed`, `parse_failed`
- timestamps: `upload_time`, `start_at`, `finish_at`
- `error_message`

The frontend file list polls `/api/files` every 3 seconds and renders status text, finish time, and error tooltip. `MineruApiClient` already supports async MinerU task mode by submitting `/tasks`, polling `/tasks/{task_id}`, and downloading `/tasks/{task_id}/result`, but that upstream state is not stored or exposed to the frontend.

## Data Model

Extend `backend/app/models/file.py` and add an Alembic migration with these nullable columns:

- `parse_stage: String(64)`
- `progress_percent: Integer`
- `progress_message: String(255)`
- `last_heartbeat_at: DateTime(timezone=True)`
- `mineru_task_id: String(128)`
- `mineru_task_status: String(64)`
- `mineru_task_payload: Text`

Semantics:

- `parse_stage` is mineru-web's local stage label.
- `progress_percent` is either a real upstream percent when safely detected, or a local stage-based estimate.
- `progress_message` is short user-facing text for the file list.
- `last_heartbeat_at` is updated whenever mineru-web records progress.
- `mineru_task_id` is set only in async task mode.
- `mineru_task_status` stores the latest normalized MinerU task state.
- `mineru_task_payload` stores the latest upstream task payload as JSON text for debugging and future UI expansion.

`File.to_dict()` must return these fields so `/api/files` naturally includes them.

## Progress Sources

### 1. Upstream MinerU task state

When `MINERU_API_USE_ASYNC_TASKS=1`, `MineruApiClient` should:

1. submit `/tasks`
2. capture `task_id`
3. poll `/tasks/{task_id}`
4. pass each polled payload to a progress callback
5. fetch `/tasks/{task_id}/result` only after a success terminal state

`ParserService` should persist:

- `mineru_task_id`
- `mineru_task_status`
- `mineru_task_payload`
- `last_heartbeat_at`

If the upstream payload contains a trustworthy numeric progress field such as `progress`, `percent`, or `percentage`, mineru-web may use that value directly after bounds-checking it to `0..100`.

### 2. Local fallback stages

Regardless of sync or async mode, mineru-web should also track local stages:

- `queued`
- `fetching_source`
- `submitting_mineru`
- `waiting_mineru`
- `downloading_result`
- `syncing_artifacts`
- `postprocessing_popo`
- `completed`
- `failed`

Recommended fallback percentages:

- `queued` → `0`
- `fetching_source` → `10`
- `submitting_mineru` → `20`
- `waiting_mineru` → `35`
- `downloading_result` → `70`
- `syncing_artifacts` → `85`
- `postprocessing_popo` → `92`
- `completed` → `100`
- `failed` → keep the last known value unless empty, then `0`

These are estimates only. The UI should avoid implying that a fallback value is an upstream-verified percentage.

## Parser and Worker Flow

### Queue time

`queue_parse_file()` should initialize:

- `status = pending`
- `parse_stage = queued`
- `progress_percent = 0`
- `progress_message = "队列等待中"`
- `last_heartbeat_at = now`
- clear any previous `mineru_task_*` values

### Parse start

`parse_file()` should update:

- `status = parsing`
- `start_at = now`
- `parse_stage = fetching_source`
- `progress_percent = 10`
- `progress_message = "正在读取源文件"`
- `last_heartbeat_at = now`

### MinerU request lifecycle

Before submitting MinerU:

- `parse_stage = submitting_mineru`
- `progress_percent = 20`
- `progress_message = "正在提交 MinerU 任务"`

When async task mode returns a task id:

- set `mineru_task_id`
- `parse_stage = waiting_mineru`
- `progress_message = "等待 MinerU 返回任务状态"`

Each async poll refreshes:

- `mineru_task_status`
- `mineru_task_payload`
- `last_heartbeat_at`
- `progress_message` derived from MinerU status/message
- `progress_percent` from upstream progress if present, otherwise keep local fallback

After MinerU result download begins:

- `parse_stage = downloading_result`
- `progress_percent = max(current, 70)`
- `progress_message = "正在下载解析结果"`

Before artifact sync:

- `parse_stage = syncing_artifacts`
- `progress_percent = max(current, 85)`
- `progress_message = "正在同步解析产物"`

Before Popo postprocess:

- only if `POPO_ENABLED=1`
- `parse_stage = postprocessing_popo`
- `progress_percent = max(current, 92)`
- `progress_message = "正在执行 Popo 后处理"`

On success:

- `status = parsed`
- `parse_stage = completed`
- `progress_percent = 100`
- `progress_message = "解析完成"`
- `finish_at = now`
- `last_heartbeat_at = now`

On failure:

- `status = parse_failed`
- `parse_stage = failed`
- `progress_message` should keep a short failure summary
- `last_heartbeat_at = now`
- preserve latest `mineru_task_*` info when available

## API Contract

### `/api/files`

No new endpoint. Extend each file item with:

- `parse_stage`
- `progress_percent`
- `progress_message`
- `last_heartbeat_at`
- `mineru_task_id`
- `mineru_task_status`

Do not return raw `mineru_task_payload` in the list response; it is heavier than the table needs.

### `/api/files/{file_id}/parse/status`

Extend the existing single-file status response with:

- `parse_stage`
- `progress_percent`
- `progress_message`
- `last_heartbeat_at`
- `mineru_task_id`
- `mineru_task_status`
- `mineru_task_payload` parsed back to JSON when valid, otherwise omitted

This endpoint becomes the detailed per-file progress view, while `/api/files` remains list-friendly.

## Frontend Design

Use the chosen file-list layout: **add a dedicated progress column** in `frontend/src/views/Files.vue`.

For each row:

- `pending`
  - show `队列等待`
  - show `progress_message`
  - show `前方 N 个任务` only if mineru-web can compute it cheaply from current page data; otherwise omit
- `parsing`
  - show progress bar
  - show `progress_message`
  - show elapsed time from `start_at`
  - show rough remaining time when `start_at` and a `1..99` progress percentage are available
  - show `MinerU: <status>` if `mineru_task_status` exists
  - show short task id like the last 8-12 chars if `mineru_task_id` exists
- `parsed`
  - show `100%`
  - show total duration from `start_at` to `finish_at`
- `parse_failed`
  - keep existing error tooltip
  - show failure stage and last progress message in the progress column

### Stale task hint

If:

- `status === parsing`
- `last_heartbeat_at` exists
- `now - last_heartbeat_at > PARSE_STALE_AFTER_SECONDS`

then the progress column should display a warning hint such as `可能卡住` and `X 分钟无更新`.

Default threshold:

- `PARSE_STALE_AFTER_SECONDS=600`

The hint is observational only. It does not mutate file status.

### Progress bar behavior

- If the current value came from a real upstream progress field, show that percentage normally.
- If the value is only a local stage estimate, the UI may still render the bar, but supporting text should emphasize the stage and elapsed time rather than precise remaining time.
- ETA is optional and should be coarse. If insufficient historical evidence exists, omit ETA rather than inventing one.

## ETA Policy

The first version should not require a sophisticated ETA engine.

Allowed:

- coarse display like `已耗时 18 分钟`
- optional hint like `预计较久` when file is large or still in `waiting_mineru`

Optional lightweight ETA:

- estimate from recent completed files with the same backend and same broad size bucket

But if the estimate cannot be made confidently, the UI should show no ETA. Avoid fake precision.

## Error Handling

- If persisting MinerU task payload fails, log and continue parsing.
- If upstream task status is malformed, keep parsing and store only safe string fields.
- If upstream task status is `failed`, `error`, or `cancelled`, raise the existing parse failure path and preserve the latest task metadata.
- If Popo fails, keep the current behavior: main parse can still succeed; progress may briefly show `postprocessing_popo` before settling to `parsed`.

## Testing

Backend tests:

- migration covers new columns
- `File.to_dict()` includes new progress fields
- queueing a parse task initializes progress fields
- sync parse path updates local stages and heartbeat
- async task path stores `mineru_task_id`, latest task status, and latest payload
- async task path uses upstream progress when present
- `/api/files/{file_id}/parse/status` returns detailed progress metadata
- parse failure preserves useful upstream task status when available

Frontend tests or checks:

- file type definitions include progress fields
- file list renders dedicated progress column
- parsing rows show stage text, elapsed time, and task status when present
- stale rows show warning hint after threshold logic is met
- completed rows show total duration
- failed rows still expose the current tooltip and progress summary

## Open Choices Resolved

- Chosen layout: dedicated progress column in the file list
- Chosen storage: database-persisted progress fields on `files`
- Chosen scope: observability only, no task control
- Chosen priority: prefer real MinerU task state over local estimated progress
