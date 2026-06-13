# Parse Progress Visibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-file parse progress visibility with persisted local stages, MinerU async task metadata, heartbeat-based stale hints, and a dedicated frontend progress column.

**Architecture:** Store progress metadata on the existing `files` table and return list-safe fields through `File.to_dict()`. `ParserService` owns local stage updates and receives async MinerU task callbacks from `MineruApiClient`. The Vue file list keeps its existing polling loop and renders progress from the expanded file item payload.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, pytest, Vue 3, TypeScript, Element Plus.

---

### Task 1: Backend Progress Model And API Contract

**Files:**
- Modify: `backend/app/models/file.py`
- Create: `backend/alembic/versions/20260613_add_parse_progress_fields.py`
- Modify: `backend/app/api/parsed.py`
- Test: `backend/tests/test_parse_progress_api.py`

- [ ] **Step 1: Write failing tests for file serialization and parse status**

Create `backend/tests/test_parse_progress_api.py` with tests that construct a `File` row with progress fields and assert `to_dict()` and `/api/files/{id}/parse/status` return list-safe and detailed progress metadata.

- [ ] **Step 2: Run tests and verify RED**

Run: `cd backend && uv run pytest tests/test_parse_progress_api.py -v`
Expected: FAIL because the new columns and response fields do not exist.

- [ ] **Step 3: Add model fields and migration**

Add nullable columns for `parse_stage`, `progress_percent`, `progress_message`, `last_heartbeat_at`, `mineru_task_id`, `mineru_task_status`, and `mineru_task_payload`.

- [ ] **Step 4: Extend serialization and status API**

Return list-safe fields from `File.to_dict()`. Extend `/api/files/{id}/parse/status` with those fields and parse `mineru_task_payload` into JSON when valid.

- [ ] **Step 5: Run tests and verify GREEN**

Run: `cd backend && uv run pytest tests/test_parse_progress_api.py -v`
Expected: PASS.

### Task 2: Parser Progress Persistence

**Files:**
- Modify: `backend/app/services/parser.py`
- Test: `backend/tests/test_parser_service_sidecar.py`

- [ ] **Step 1: Write failing tests for queue and sync parse stages**

Add tests asserting `queue_parse_file()` initializes queued progress, sync parse records local stages and success/failure progress, and previous MinerU task metadata is cleared when a file is re-queued.

- [ ] **Step 2: Run focused parser tests and verify RED**

Run: `cd backend && uv run pytest tests/test_parser_service_sidecar.py -v`
Expected: FAIL on new progress assertions.

- [ ] **Step 3: Implement progress helper methods**

Add small helpers on `ParserService` to update progress fields, serialize MinerU payloads, clamp percentages, and commit after stage changes.

- [ ] **Step 4: Wire progress updates through queue and sync parse flow**

Update queue, parse start, MinerU submit, result download, artifact sync, Popo, success, and failure stages.

- [ ] **Step 5: Run parser tests and verify GREEN**

Run: `cd backend && uv run pytest tests/test_parser_service_sidecar.py -v`
Expected: PASS.

### Task 3: MinerU Async Task Progress Callback

**Files:**
- Modify: `backend/app/services/mineru_api.py`
- Modify: `backend/app/services/parser.py`
- Test: `backend/tests/test_mineru_api_client.py`
- Test: `backend/tests/test_parser_service_sidecar.py`

- [ ] **Step 1: Write failing callback tests**

Add a `MineruApiClient` async test that verifies the client invokes a callback with submitted task id and each `/tasks/{id}` payload. Add a parser-service test that verifies async task status and payload are persisted.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `cd backend && uv run pytest tests/test_mineru_api_client.py tests/test_parser_service_sidecar.py -v`
Expected: FAIL on missing callback behavior and persistence.

- [ ] **Step 3: Add progress callback support to MineruApiClient**

Accept an optional callback parameter in `parse_file()` / `_parse_file_async()`. Call it after task submission and after every status poll.

- [ ] **Step 4: Persist callback payloads in ParserService**

Pass a callback from `ParserService.process_file()` and update `mineru_task_id`, `mineru_task_status`, `mineru_task_payload`, `last_heartbeat_at`, `progress_message`, and upstream progress percent when available.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run: `cd backend && uv run pytest tests/test_mineru_api_client.py tests/test_parser_service_sidecar.py -v`
Expected: PASS.

### Task 4: Frontend Progress Column

**Files:**
- Modify: `frontend/src/types/file.ts`
- Modify: `frontend/src/views/Files.vue`

- [ ] **Step 1: Add TypeScript fields**

Extend `FileItem` with progress fields returned by the backend.

- [ ] **Step 2: Add render helpers in Files.vue**

Add helpers for progress percentage, stage label, elapsed time, task short id, stale hint, and progress status color.

- [ ] **Step 3: Add dedicated progress column**

Insert a table column after status with progress bar, stage/message, elapsed time, MinerU status/task id, and stale hint.

- [ ] **Step 4: Run frontend checks**

Run: `cd frontend && npm run test:theme`
Expected: PASS.

Run: `cd frontend && npm run build`
Expected: PASS.

### Task 5: Full Verification And Graph Update

**Files:**
- Update only files touched above if verification finds issues.

- [ ] **Step 1: Run backend full tests**

Run: `cd backend && uv run pytest tests -v`
Expected: PASS.

- [ ] **Step 2: Run frontend verification**

Run: `cd frontend && npm run test:theme`
Expected: PASS.

Run: `cd frontend && npm run build`
Expected: PASS.

- [ ] **Step 3: Update graph**

Run: `graphify update .`
Expected: graph update succeeds.

- [ ] **Step 4: Review git diff**

Run: `git diff --stat`
Expected: only planned backend, frontend, spec, and plan files are changed.

