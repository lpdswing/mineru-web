# MinerU Web

Language: English | [中文](README.zh-CN.md)

MinerU Web is a web application for document parsing and result review. It provides file upload, asynchronous parsing, original file preview, Markdown preview, PDF source tracing, Popo-enhanced result comparison, and Markdown export. The current version targets MinerU 3.3.1. The business backend now calls the official MinerU HTTP service instead of depending on MinerU internal Python APIs.

Current release: `v3.3.1`.

## Features

- FastAPI backend and Vue 3 frontend
- Email/password login with user-scoped files, statistics, and settings
- Redis-backed asynchronous parsing queue
- Configurable worker concurrency for matching MinerU API capacity
- MinIO/S3 storage for source files, Markdown outputs, and images
- Parse service health checks, with MinerU API connection and version information on the settings page
- Upload support for PDF, Office documents, and common image formats
- Original file preview for PDF, Office, images, and text
- PDF source tracing with bbox highlights, block linking, type filters, and table comparison
- Markdown preview for raw Markdown, page-based Markdown, Popo-enhanced Markdown, and OCR/Popo comparison
- MinerU task status and progress visibility on the files page
- Single-file and batch export for Markdown, page Markdown, and Popo Markdown
- Optional MinerU-Popo postprocessing; Popo failures do not block the base parsing result
- Support for official MinerU 3.3.1 backend options
- Multi-architecture images for the business backend, worker, and frontend
- Linux server deployment with `mineru-router` for unified multi-GPU scheduling
- macOS Apple Silicon deployment with MinerU API on the host and business services in Docker

## Quick Start

Create the environment file:

```bash
cp .env.example .env
```

Edit `.env` and set a MinIO endpoint that can be reached by both the browser and containers, for example:

```bash
MINIO_ENDPOINT=SERVER_IP:9000
WORKER_REPLICAS=1
WORKER_CONCURRENCY=1
```

Linux / server deployment:

```bash
docker compose --env-file .env -f docker-compose.yml up -d
```

macOS Apple Silicon deployment:

```bash
docker compose --env-file .env -f docker-compose.mac.yml up -d --build
```

After startup, open:

- Web: `http://SERVER_IP:8088`
- Backend API: `http://SERVER_IP:8000`
- MinerU router: `http://SERVER_IP:8002`
- MinIO console: `http://SERVER_IP:9001`

Register an email account on the first visit to start using the app.

For Linux server deployment, macOS Apple Silicon setup, model downloads, MinerU Router, multi-GPU scheduling, MinIO endpoint configuration, and verification commands, see [Deployment Guide](docs/deployment.md).

## Screenshots

<div align="center">
  <img src="images/home.png" alt="Home" width="800">
  <p>Home - system overview and quick actions</p>

  <img src="images/files.png" alt="File management" width="800">
  <p>Files - upload and manage multiple document formats</p>

  <img src="images/files-progress.png" alt="File parsing progress" width="800">
  <p>Files - MinerU task status, progress, task id, and elapsed time</p>

  <img src="images/preview.png" alt="Document preview" width="800">
  <p>Preview - parse and inspect document content</p>

  <img src="images/pdf-source-preview.png" alt="PDF source tracing" width="800">
  <p>PDF source tracing - source bbox highlights on the left and page/block-linked Markdown on the right</p>

  <img src="images/pdf-table-trace.png" alt="PDF table tracing" width="800">
  <p>Table tracing - filter table blocks and compare the PDF region with the Markdown table</p>

  <img src="images/setting.png" alt="Settings" width="800">
  <p>Settings - backend selection and parse service status</p>
</div>

## Project Structure

```text
mineru-web/
├── backend/                  # FastAPI backend, worker, database models, and tests
├── frontend/                 # Vue 3 frontend
├── docs/
│   └── deployment.md         # Deployment guide
├── docker-compose.yml        # Linux / server deployment
├── docker-compose.mac.yml    # macOS host MinerU API deployment
└── README.md
```

## Configuration

Common environment variables are listed in [.env.example](.env.example). Full details are in the [Deployment Guide](docs/deployment.md).

Frequently used options:

- `MINIO_ENDPOINT`: MinIO address reachable by both browser and containers.
- `WORKER_REPLICAS` / `WORKER_CONCURRENCY`: worker replica count and per-worker concurrency.
- `MINERU_API_USE_ASYNC_TASKS`: enable the MinerU `/tasks` asynchronous API.
- `POPO_ENABLED`: enable MinerU-Popo postprocessing.

## Testing

Verification commands are listed in the [Deployment Guide](docs/deployment.md).

Common checks:

```bash
cd backend
uv run pytest tests -v
```

```bash
cd frontend
npm run build
```

## Versioning And Releases

This project version follows the compatible MinerU version. Current version `v3.3.1` corresponds to MinerU `3.3.1`:

- `lpdswing/mineru-web-frontend:v3.3.1`
- `lpdswing/mineru-web-backend:v3.3.1`
- `lpdswing/mineru-web-mineru-api:v3.3.1`

Use tag `v3.3.1` when publishing the GitHub Release. After the release is published, `.github/workflows/docker-build.yml` builds and pushes Docker images with the same release tag. If only MinerU Web changes while the compatible MinerU version stays the same, use a suffix such as `v3.3.1-web.1`.

## Changelog

### 3.3.1 - 2026-06-13

- Adapted to MinerU 3.3.1
- Updated the MinerU API image build to install `mineru[core]==3.3.1`
- Updated official backend options to `vlm-engine` and `hybrid-engine`
- Kept legacy `vlm-auto-engine` and `hybrid-auto-engine` settings compatible
- Added explicit hybrid `effort=high` for MinerU 3.3.1 requests, configurable with `MINERU_API_HYBRID_EFFORT`

### 3.2.3 - 2026-06-13

- Adapted to the official MinerU 3.2.3 HTTP API
- Switched parsing to sidecar / router mode
- Preserved MinIO/S3 transfer for images and Markdown artifacts
- Removed MinerU internal dependencies from the business backend and worker
- Added parse service status to the settings page
- Added official MinerU 3.2.3 backend parameter support
- Added email login and user-scoped data isolation
- Added worker concurrency configuration and multi-GPU router deployment notes
- Added optional MinerU-Popo postprocessing, preview, and export
- Enhanced PDF source tracing with bbox highlights, source maps, type filters, and table comparison
- Added original file preview for Office, image, and text files
- Added parse progress visibility backed by MinerU task state
- Added batch delete and batch export
- Delete now cleans up parsed MinIO artifacts together with the source file

## License

This project is licensed under AGPL-3.0. See [LICENSE](LICENSE) for details.

## Acknowledgements

- [MinerU](https://github.com/opendatalab/MinerU)
- [FastAPI](https://github.com/fastapi/fastapi)
- [Vue](https://github.com/vuejs/core)
