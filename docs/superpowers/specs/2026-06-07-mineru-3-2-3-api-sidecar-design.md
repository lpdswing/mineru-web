# MinerU 3.2.3 API Sidecar Compatibility Design

## Summary

Upgrade mineru-web to track MinerU 3.2.3 by moving parsing integration from MinerU internal Python modules to the official MinerU 3.x API service. mineru-web remains responsible for upload management, task state, MinIO/S3 persistence, Markdown URL rewriting, preview data, and enterprise-facing operational visibility.

The first phase does not include MCP service exposure. MCP and broader enterprise administration features are reserved for phase two.

## Goals

- Release mineru-web with the same visible version as the compatible MinerU release: `v3.2.3`.
- Align the MinerU parsing container with the official MinerU Dockerfile strategy for MinerU 3.2.3.
- Stop importing MinerU internal modules such as `mineru.backend.*` from the mineru-web backend.
- Use the official MinerU API sidecar as the parsing boundary.
- Preserve the existing S3/MinIO behavior for generated Markdown and images.
- Add lightweight operational visibility for the MinerU API service.
- Keep existing upload, parse queue, file list, preview, settings, Redis, MinIO, and database workflows working.

## Non-Goals

- Do not implement MCP in phase one.
- Do not add RBAC, audit logs, tenant management, SSO, or API key management in phase one.
- Do not depend on undocumented MinerU writer internals for S3 output.
- Do not make the mineru-web business backend a GPU/vLLM runtime.
- Do not guarantee compatibility with every future MinerU release without running the compatibility checks.

## Current State

The current backend imports and calls MinerU internals directly in `backend/app/services/parser.py`, including pipeline, VLM, hybrid analysis functions, middle JSON conversion, and Markdown generation helpers. This allowed a direct S3 writer integration, but it couples mineru-web to MinerU internal module paths and function signatures.

The current release workflow builds Docker images from GitHub Release tags and uses the release tag as the image tag. Existing compose files and UI version text are manually aligned to the mineru-web release version.

## Target Architecture

Phase one introduces a dedicated MinerU API sidecar:

- `mineru-api`: official MinerU 3.2.3-compatible parsing service.
- `backend`: mineru-web business API, no direct MinerU internal imports.
- `worker`: existing async parser worker, now using HTTP to call `mineru-api`.
- `redis`: existing task queue.
- `minio`: existing object storage.
- `frontend`: existing Vue UI with minimal operational status additions.

The sidecar exposes official MinerU endpoints such as `/health`, `/file_parse`, `/tasks`, `/tasks/{task_id}`, and `/tasks/{task_id}/result`. mineru-web calls these endpoints through a small client layer.

## Version And Release Strategy

mineru-web release versions track the compatible MinerU version:

- MinerU 3.2.3 compatibility ships as mineru-web `v3.2.3`.
- Docker image tags use the same release tag:
  - `lpdswing/mineru-web-backend:v3.2.3`
  - `lpdswing/mineru-web-frontend:v3.2.3`
  - `lpdswing/mineru-web-backend-npu:v3.2.3`
  - if a dedicated parser image is published, `lpdswing/mineru-web-mineru-api:v3.2.3`

If mineru-web needs a patch without changing MinerU compatibility, use a suffix such as `v3.2.3-web.1`.

The release notes must state the MinerU version verified by the release. `README.md`, compose image tags, and visible UI version text should be updated to the same release version.

## Docker Strategy

The MinerU parsing service Dockerfile should follow the official MinerU Dockerfile strategy for the target version:

- Default NVIDIA base image aligns with official MinerU 3.2.3 guidance: `vllm/vllm-openai:v0.21.0`.
- Provide a clear CUDA 12.9 fallback path using `vllm/vllm-openai:v0.21.0-cu129` for hosts whose drivers cannot support CUDA 13.
- Preserve required system packages such as Noto fonts, fontconfig, and OpenCV runtime libraries.
- Use the official service command shape for `mineru-api`.
- Keep GPU reservations, large shared memory, IPC configuration, models, and `mineru.json` on the MinerU API service.

The mineru-web backend Dockerfile should stay lightweight. It should install only business backend dependencies such as FastAPI, SQLAlchemy, Redis, MinIO, HTTP client libraries, and app code. It should not install vLLM or import MinerU internals.

## Backend Components

### MineruApiClient

Responsibilities:

- Read `MINERU_API_URL`, request timeout, polling interval, and task result timeout from environment variables.
- Call `/health` for service status and version/protocol information.
- Submit parse requests through `/file_parse` for synchronous parsing or `/tasks` plus polling for asynchronous parsing.
- Pass parse options such as backend, method, language, formula enable, table enable, page range, and HTTP client server URL when supported by MinerU 3.2.3 API.
- Normalize errors into explicit exception types for timeout, unavailable service, failed task, invalid response, and result download failure.

### MineruArtifactSync

Responsibilities:

- Consume MinerU API results, including returned ZIP artifacts or local result payloads supported by the API.
- Locate the main Markdown file, optional page-aware Markdown, middle JSON, model JSON, content list, and image directory.
- Upload generated Markdown and images to the existing `mds` bucket using the current MinIO/S3 configuration.
- Rewrite Markdown image references to HTTP-accessible S3 URLs.
- Return the Markdown content that should be saved to `ParsedContent.content`.
- Preserve enough auxiliary artifacts for preview/debug workflows where feasible.

This layer intentionally owns S3 behavior inside mineru-web. It does not rely on MinerU's internal `S3DataWriter` behavior.

### ParserService

Responsibilities:

- Keep the current user settings lookup, file status transitions, Redis queue behavior, and database writes.
- Fetch the original uploaded file from MinIO.
- Submit file bytes and settings to `MineruApiClient`.
- Call `MineruArtifactSync` after parsing.
- Store parsed Markdown in the database.
- Record clearer failure messages for parse failures.

## Configuration

New or changed environment variables:

- `MINERU_API_URL`: base URL for the MinerU API sidecar, default `http://mineru-api:8000`.
- `MINERU_API_TIMEOUT_SECONDS`: request timeout for API submission/download.
- `MINERU_API_POLL_INTERVAL_SECONDS`: polling interval for async task status.
- `MINERU_API_TASK_TIMEOUT_SECONDS`: maximum wait time for a parse task.
- `MINERU_API_USE_ASYNC_TASKS`: optional switch between `/file_parse` and `/tasks`.

Existing environment variables remain for Redis, MinIO, database, and MinerU parsing options where still relevant.

## Compose Changes

`docker-compose.yml` should add a `mineru-api` service and point `backend` and `worker` to it.

The `mineru-api` service owns:

- GPU resource reservation.
- `shm_size` and `ipc` settings.
- `mineru.json` mount.
- model directory mount.
- MinerU API health check.
- optional `SERVER_URL` or OpenAI-compatible VLM server configuration when using `*-http-client` backends.

`backend` and `worker` own:

- Redis, MinIO, and database settings.
- `MINERU_API_URL`.
- no GPU reservation by default.

## Frontend And Operational Visibility

Phase one adds only lightweight enterprise usability:

- Settings or status area shows MinerU API URL, health state, protocol/version details, processing window size, and max concurrent requests when available from `/health`.
- File list and preview keep existing workflow.
- Failure information should be clearer when MinerU API is unavailable, times out, or returns a failed task.
- Existing backend tags, parse start time, finish time, and duration remain visible.

Larger enterprise features are deferred to phase two.

## Data Flow

1. User uploads a document through the existing frontend.
2. Backend stores the original file in MinIO and queues parsing as before.
3. Worker fetches the original file bytes from MinIO.
4. Worker reads user settings and calls `MineruApiClient`.
5. MinerU API parses the document and returns or exposes result artifacts.
6. `MineruArtifactSync` reads artifacts, uploads generated images and Markdown to MinIO/S3, and rewrites Markdown image URLs.
7. Backend stores final Markdown in `ParsedContent`.
8. File status changes to `parsed` or `parse_failed`.
9. Frontend preview loads the Markdown through existing APIs.

## Error Handling

- MinerU API unavailable: mark file as `parse_failed` with a service unavailable reason.
- MinerU API timeout: mark file as `parse_failed` with timeout context.
- Failed MinerU task: preserve MinerU task error text where available.
- Missing Markdown artifact: mark file as `parse_failed` with an artifact validation error.
- Missing images: keep Markdown where possible, but record a warning if image sync fails.
- S3 upload failure: mark file as `parse_failed` unless the main Markdown can be safely stored and image loss is explicitly allowed in a future setting.

## Testing And Verification

Phase one acceptance checks:

- Backend starts without importing `mineru.backend.*`.
- Compose starts frontend, backend, worker, Redis, MinIO, and MinerU API.
- `/health` from MinerU API is visible through mineru-web status API/UI.
- PDF upload parses successfully.
- Image upload parses successfully.
- Pipeline backend settings are passed correctly.
- Hybrid HTTP client settings are passed correctly when configured.
- Generated images are uploaded to MinIO.
- Markdown image URLs are rewritten to HTTP-accessible S3 URLs.
- Preview renders Markdown and images.
- Failed MinerU API requests produce clear `parse_failed` states.
- Existing tests still pass, with focused tests added for `MineruApiClient` and `MineruArtifactSync`.

## Phase Two

Phase two can add MCP and broader enterprise features:

- Expose document parsing as an MCP service.
- MCP tools can include `parse_document`, `get_parse_status`, `get_parsed_content`, `list_files`, and `retry_parse`.
- Add API key authentication for machine clients.
- Add audit logs, RBAC, tenant isolation, and admin dashboards.
- Add richer queue monitoring and worker management.

## References

- MinerU 3.2.3 release: https://github.com/opendatalab/MinerU/releases/tag/mineru-3.2.3-released
- MinerU CLI and API usage: https://opendatalab.github.io/MinerU/usage/cli_tools/
- MinerU quick usage and API endpoints: https://opendatalab.github.io/MinerU/usage/quick_usage/
- MinerU Docker deployment: https://opendatalab.github.io/MinerU/quick_start/docker_deployment/
