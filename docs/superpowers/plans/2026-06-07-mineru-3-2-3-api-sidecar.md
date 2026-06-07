# MinerU 3.2.3 API Sidecar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade mineru-web to `v3.2.3` by routing parsing through an official MinerU API sidecar while preserving MinIO/S3 Markdown and image storage.

**Architecture:** The business backend stops importing MinerU internals and uses a focused HTTP client to submit parse jobs to `mineru-api`. A separate artifact sync component unpacks ZIP parse results, uploads Markdown/images to MinIO, rewrites image URLs, and returns the Markdown stored in the database. Docker Compose owns the MinerU API GPU runtime, while backend and worker stay lightweight.

**Tech Stack:** FastAPI, SQLAlchemy, Redis Streams, MinIO Python SDK, HTTPX, Vue 3, Element Plus, Docker Compose, MinerU 3.2.3 API.

---

## File Structure

- Create `backend/app/services/mineru_api.py`: HTTP client, request/response models, health check, sync parse call, optional async polling.
- Create `backend/app/services/artifact_sync.py`: ZIP extraction, Markdown/image discovery, MinIO uploads, Markdown URL rewriting.
- Create `backend/app/api/health.py`: backend-facing status endpoint that proxies MinerU API health.
- Modify `backend/app/services/parser.py`: remove MinerU internal imports and call `MineruApiClient` plus `MineruArtifactSync`.
- Modify `backend/app/models/file.py`: add `error_message` to expose clearer parse failures.
- Add Alembic migration under `backend/alembic/versions/`: add nullable `files.error_message`.
- Modify `backend/app/api/__init__.py` and `backend/main.py`: register the health router.
- Modify `backend/requirements.txt`: remove `mineru[core]`, add direct backend runtime dependencies and `httpx`.
- Create `backend/mineru-api.Dockerfile`: official-MinerU-aligned API sidecar image.
- Modify `backend/Dockerfile` and `backend/npu.Dockerfile`: keep business backend lightweight.
- Modify compose files: add `mineru-api`, move GPU settings to it, point backend/worker at `MINERU_API_URL`.
- Modify `.github/workflows/docker-build.yml`: optionally build/push `mineru-web-mineru-api` image.
- Modify `frontend/src/api/settings.ts`: add MinerU health API types/client.
- Modify `frontend/src/views/Settings.vue`: display API URL and health status.
- Modify `frontend/src/types/file.ts`, `frontend/src/views/Files.vue`: show parse failure reason and keep duration/status display.
- Modify `frontend/src/App.vue`, `README.md`, compose image tags: release version `v3.2.3`.
- Add tests under `backend/tests/`: focused tests for client, artifact sync, parser orchestration, and health API.

## Task 1: Add MinerU API Client

**Files:**
- Create: `backend/app/services/mineru_api.py`
- Test: `backend/tests/test_mineru_api_client.py`
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Add HTTPX dependency**

Modify `backend/requirements.txt` to:

```txt
fastapi==0.115.12
uvicorn[standard]==0.34.3
python-multipart==0.0.20
loguru==0.7.3
alembic==1.16.1
minio==7.2.15
SQLAlchemy==2.0.41
redis
httpx==0.28.1
pytest==8.4.0
```

Expected: business backend no longer installs `mineru[core]`, but still has direct runtime and test dependencies.

- [ ] **Step 2: Write failing client tests**

Create `backend/tests/test_mineru_api_client.py`:

```python
import io
import zipfile

import httpx
import pytest

from app.services.mineru_api import MineruApiClient, MineruApiUnavailable, MineruApiError


def make_zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("sample/sample.md", "![](images/a.png)")
        zf.writestr("sample/images/a.png", b"png")
    return buffer.getvalue()


def test_health_returns_normalized_payload():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health"
        return httpx.Response(200, json={"status": "healthy", "version": "3.2.3"})

    client = MineruApiClient(
        base_url="http://mineru-api:8000",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = client.health()

    assert result["available"] is True
    assert result["base_url"] == "http://mineru-api:8000"
    assert result["status"] == "healthy"
    assert result["version"] == "3.2.3"


def test_health_handles_unavailable_service():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    client = MineruApiClient(
        base_url="http://mineru-api:8000",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = client.health()

    assert result["available"] is False
    assert "refused" in result["error"]


def test_parse_file_posts_zip_request_and_returns_bytes():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/file_parse"
        body = request.read()
        assert b"response_format_zip" in body
        assert b"return_md" in body
        return httpx.Response(200, content=make_zip_bytes(), headers={"content-type": "application/zip"})

    client = MineruApiClient(
        base_url="http://mineru-api:8000",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = client.parse_file(
        filename="sample.pdf",
        file_bytes=b"%PDF",
        backend="pipeline",
        parse_method="auto",
        lang="ch",
        formula_enable=True,
        table_enable=True,
    )

    assert result.filename == "sample.pdf"
    assert result.content_type == "application/zip"
    assert result.content.startswith(b"PK")


def test_parse_file_raises_on_non_success_status():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "boom"})

    client = MineruApiClient(
        base_url="http://mineru-api:8000",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(MineruApiError) as exc:
        client.parse_file(
            filename="sample.pdf",
            file_bytes=b"%PDF",
            backend="pipeline",
            parse_method="auto",
            lang="ch",
            formula_enable=True,
            table_enable=True,
        )

    assert "boom" in str(exc.value)
```

- [ ] **Step 3: Run client tests and verify failure**

Run:

```bash
cd backend && python3 -m pytest tests/test_mineru_api_client.py -v
```

Expected: FAIL because `app.services.mineru_api` does not exist.

- [ ] **Step 4: Implement `MineruApiClient`**

Create `backend/app/services/mineru_api.py`:

```python
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx


class MineruApiError(Exception):
    """Base error for MinerU API failures."""


class MineruApiUnavailable(MineruApiError):
    """Raised when the MinerU API service cannot be reached."""


class MineruApiTimeout(MineruApiError):
    """Raised when the MinerU API request or task polling times out."""


@dataclass
class MineruParseResult:
    filename: str
    content: bytes
    content_type: str


class MineruApiClient:
    def __init__(
        self,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        poll_interval_seconds: float | None = None,
        task_timeout_seconds: float | None = None,
        use_async_tasks: bool | None = None,
        http_client: httpx.Client | None = None,
    ):
        self.base_url = (base_url or os.getenv("MINERU_API_URL", "http://mineru-api:8000")).rstrip("/")
        self.timeout_seconds = timeout_seconds or float(os.getenv("MINERU_API_TIMEOUT_SECONDS", "300"))
        self.poll_interval_seconds = poll_interval_seconds or float(os.getenv("MINERU_API_POLL_INTERVAL_SECONDS", "2"))
        self.task_timeout_seconds = task_timeout_seconds or float(os.getenv("MINERU_API_TASK_TIMEOUT_SECONDS", "1800"))
        self.use_async_tasks = use_async_tasks if use_async_tasks is not None else os.getenv("MINERU_API_USE_ASYNC_TASKS", "0") == "1"
        self.http_client = http_client or httpx.Client(timeout=self.timeout_seconds)

    def health(self) -> dict[str, Any]:
        try:
            response = self.http_client.get(f"{self.base_url}/health")
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                payload = {"raw": payload}
            return {"available": True, "base_url": self.base_url, **payload}
        except Exception as exc:
            return {"available": False, "base_url": self.base_url, "error": str(exc)}

    def parse_file(
        self,
        filename: str,
        file_bytes: bytes,
        backend: str,
        parse_method: str,
        lang: str,
        formula_enable: bool,
        table_enable: bool,
    ) -> MineruParseResult:
        if self.use_async_tasks:
            return self._parse_file_async(filename, file_bytes, backend, parse_method, lang, formula_enable, table_enable)
        return self._parse_file_sync(filename, file_bytes, backend, parse_method, lang, formula_enable, table_enable)

    def _parse_file_sync(
        self,
        filename: str,
        file_bytes: bytes,
        backend: str,
        parse_method: str,
        lang: str,
        formula_enable: bool,
        table_enable: bool,
    ) -> MineruParseResult:
        data = self._form_data(backend, parse_method, lang, formula_enable, table_enable)
        files = {"file": (filename, file_bytes, "application/octet-stream")}
        response = self._request("post", "/file_parse", data=data, files=files)
        return MineruParseResult(
            filename=filename,
            content=response.content,
            content_type=response.headers.get("content-type", ""),
        )

    def _parse_file_async(
        self,
        filename: str,
        file_bytes: bytes,
        backend: str,
        parse_method: str,
        lang: str,
        formula_enable: bool,
        table_enable: bool,
    ) -> MineruParseResult:
        data = self._form_data(backend, parse_method, lang, formula_enable, table_enable)
        files = {"file": (filename, file_bytes, "application/octet-stream")}
        submit = self._request("post", "/tasks", data=data, files=files).json()
        task_id = submit.get("task_id") or submit.get("id")
        if not task_id:
            raise MineruApiError(f"MinerU API task response missing task id: {submit}")

        deadline = time.time() + self.task_timeout_seconds
        while time.time() < deadline:
            status_payload = self._request("get", f"/tasks/{task_id}").json()
            status = str(status_payload.get("status", "")).lower()
            if status in {"done", "completed", "success", "finished"}:
                result = self._request("get", f"/tasks/{task_id}/result")
                return MineruParseResult(filename=filename, content=result.content, content_type=result.headers.get("content-type", ""))
            if status in {"failed", "error", "cancelled"}:
                raise MineruApiError(f"MinerU API task {task_id} failed: {status_payload}")
            time.sleep(self.poll_interval_seconds)

        raise MineruApiTimeout(f"MinerU API task {task_id} exceeded {self.task_timeout_seconds} seconds")

    def _form_data(
        self,
        backend: str,
        parse_method: str,
        lang: str,
        formula_enable: bool,
        table_enable: bool,
    ) -> dict[str, str]:
        return {
            "backend": backend,
            "parse_method": parse_method,
            "lang": lang,
            "formula_enable": str(formula_enable).lower(),
            "table_enable": str(table_enable).lower(),
            "return_md": "true",
            "return_middle_json": "true",
            "return_model_output": "true",
            "return_content_list": "true",
            "response_format_zip": "true",
        }

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = self.http_client.request(method, f"{self.base_url}{path}", **kwargs)
            response.raise_for_status()
            return response
        except httpx.TimeoutException as exc:
            raise MineruApiTimeout(f"MinerU API request timed out: {exc}") from exc
        except httpx.ConnectError as exc:
            raise MineruApiUnavailable(f"MinerU API unavailable: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            raise MineruApiError(self._status_error_message(exc.response)) from exc

    @staticmethod
    def _status_error_message(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            payload = response.text
        return f"MinerU API returned {response.status_code}: {payload}"
```

- [ ] **Step 5: Run client tests and verify pass**

Run:

```bash
cd backend && python3 -m pytest tests/test_mineru_api_client.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/requirements.txt backend/app/services/mineru_api.py backend/tests/test_mineru_api_client.py
git commit -m "feat: add MinerU API client"
```

## Task 2: Add Artifact Sync

**Files:**
- Create: `backend/app/services/artifact_sync.py`
- Test: `backend/tests/test_artifact_sync.py`

- [ ] **Step 1: Write failing artifact sync tests**

Create `backend/tests/test_artifact_sync.py`:

```python
import io
import zipfile

from app.services.artifact_sync import MineruArtifactSync


class FakeMinioClient:
    def __init__(self):
        self.objects = {}
        self.buckets = set()

    def bucket_exists(self, bucket):
        return bucket in self.buckets

    def make_bucket(self, bucket):
        self.buckets.add(bucket)

    def put_object(self, bucket, path, data, length, content_type=None):
        self.buckets.add(bucket)
        self.objects[(bucket, path)] = data.read()


def build_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("sample/sample.md", "# Title\n\n![](images/a.png)")
        zf.writestr("sample/sample_middle.json", "{\"pdf_info\": []}")
        zf.writestr("sample/images/a.png", b"PNG")
    return buffer.getvalue()


def test_sync_zip_uploads_markdown_images_and_rewrites_urls():
    client = FakeMinioClient()
    sync = MineruArtifactSync(
        minio=client,
        bucket="mds",
        endpoint="http://minio:9000",
        public_endpoint="http://localhost:9000",
    )

    result = sync.sync_zip(build_zip(), output_name="sample")

    assert result.markdown == "# Title\n\n![](http://localhost:9000/mds/sample/images/a.png)"
    assert client.objects[("mds", "sample/sample.md")] == result.markdown.encode("utf-8")
    assert client.objects[("mds", "sample/images/a.png")] == b"PNG"
    assert client.objects[("mds", "sample/sample_middle.json")] == b"{\"pdf_info\": []}"


def test_sync_zip_raises_when_markdown_missing():
    client = FakeMinioClient()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("sample/images/a.png", b"PNG")

    sync = MineruArtifactSync(minio=client, bucket="mds", endpoint="http://minio:9000")

    try:
        sync.sync_zip(buffer.getvalue(), output_name="sample")
    except ValueError as exc:
        assert "Markdown artifact not found" in str(exc)
    else:
        raise AssertionError("expected ValueError")
```

- [ ] **Step 2: Run artifact sync tests and verify failure**

Run:

```bash
cd backend && python3 -m pytest tests/test_artifact_sync.py -v
```

Expected: FAIL because `app.services.artifact_sync` does not exist.

- [ ] **Step 3: Implement artifact sync**

Create `backend/app/services/artifact_sync.py`:

```python
import io
import mimetypes
import posixpath
import re
import zipfile
from dataclasses import dataclass


@dataclass
class SyncedArtifact:
    markdown: str
    markdown_path: str
    uploaded_paths: list[str]


class MineruArtifactSync:
    def __init__(self, minio, bucket: str, endpoint: str, public_endpoint: str | None = None):
        self.minio = minio
        self.bucket = bucket
        self.endpoint = endpoint.rstrip("/")
        self.public_endpoint = (public_endpoint or endpoint).rstrip("/")

    def sync_zip(self, zip_bytes: bytes, output_name: str) -> SyncedArtifact:
        self._ensure_bucket()
        uploaded_paths: list[str] = []
        prefix = self._safe_prefix(output_name)

        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
            names = [name for name in archive.namelist() if not name.endswith("/")]
            markdown_name = self._find_markdown(names)
            if not markdown_name:
                raise ValueError("Markdown artifact not found in MinerU result")

            for name in names:
                target_path = self._target_path(prefix, name)
                content = archive.read(name)
                if name == markdown_name:
                    markdown = content.decode("utf-8")
                    markdown = self._rewrite_markdown_urls(markdown, prefix)
                    content = markdown.encode("utf-8")
                content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
                self.minio.put_object(
                    self.bucket,
                    target_path,
                    io.BytesIO(content),
                    len(content),
                    content_type=content_type,
                )
                uploaded_paths.append(target_path)

        markdown_path = self._target_path(prefix, markdown_name)
        return SyncedArtifact(markdown=markdown, markdown_path=markdown_path, uploaded_paths=uploaded_paths)

    def _ensure_bucket(self) -> None:
        if not self.minio.bucket_exists(self.bucket):
            self.minio.make_bucket(self.bucket)

    @staticmethod
    def _safe_prefix(output_name: str) -> str:
        return output_name.replace("\\", "/").strip("/").replace("..", "")

    @staticmethod
    def _find_markdown(names: list[str]) -> str | None:
        md_files = [name for name in names if name.endswith(".md") and not name.endswith("_pages.md")]
        if md_files:
            return sorted(md_files, key=lambda item: (item.count("/"), len(item)))[0]
        page_md_files = [name for name in names if name.endswith(".md")]
        return sorted(page_md_files)[0] if page_md_files else None

    @staticmethod
    def _target_path(prefix: str, artifact_name: str) -> str:
        parts = artifact_name.split("/")
        if len(parts) > 1:
            artifact_name = "/".join(parts[1:])
        return posixpath.join(prefix, artifact_name)

    def _rewrite_markdown_urls(self, markdown: str, prefix: str) -> str:
        pattern = r"!\[([^\]]*)\]\(([^)]+)\)"

        def replace(match):
            alt = match.group(1)
            url = match.group(2)
            if url.startswith(("http://", "https://", "data:")):
                return match.group(0)
            image_path = posixpath.join(prefix, url.lstrip("./"))
            return f"![{alt}]({self.public_endpoint}/{self.bucket}/{image_path})"

        return re.sub(pattern, replace, markdown)
```

- [ ] **Step 4: Run artifact sync tests and verify pass**

Run:

```bash
cd backend && python3 -m pytest tests/test_artifact_sync.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/artifact_sync.py backend/tests/test_artifact_sync.py
git commit -m "feat: sync MinerU artifacts to object storage"
```

## Task 3: Refactor ParserService To Use API Sidecar

**Files:**
- Modify: `backend/app/services/parser.py`
- Modify: `backend/app/models/file.py`
- Create: `backend/alembic/versions/<revision>_add_file_error_message.py`
- Test: `backend/tests/test_parser_service_sidecar.py`

- [ ] **Step 1: Write parser orchestration test**

Create `backend/tests/test_parser_service_sidecar.py`:

```python
from types import SimpleNamespace

from app.models.enums import FileStatus
from app.services.parser import ParserService


class FakeDb:
    def __init__(self):
        self.commits = 0
        self.added = []

    def commit(self):
        self.commits += 1

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


class FakeArtifactSync:
    def sync_zip(self, content, output_name):
        assert content == b"zip"
        assert output_name == "sample"
        return SimpleNamespace(markdown="# parsed")


def test_parse_file_uses_mineru_api_and_artifact_sync(monkeypatch):
    fake_client = FakeApiClient()
    db = FakeDb()
    service = ParserService(db, mineru_api_client=fake_client, artifact_sync_factory=lambda bucket: FakeArtifactSync())
    file = SimpleNamespace(id=1, minio_path="uploads/sample.pdf", status=FileStatus.PENDING, start_at=None, finish_at=None, error_message=None)

    monkeypatch.setattr("app.services.parser.minio_client", FakeMinio())
    monkeypatch.setattr("app.services.parser.get_buckets", lambda: ["mds"])

    result = service.parse_file(file, user_id="u1")

    assert result == {"status": "success"}
    assert fake_client.kwargs["filename"] == "sample.pdf"
    assert fake_client.kwargs["backend"] == "pipeline"
    assert file.status == FileStatus.PARSED
    assert file.error_message is None
    assert db.added[0].content == "# parsed"
```

- [ ] **Step 2: Run parser test and verify failure**

Run:

```bash
cd backend && python3 -m pytest tests/test_parser_service_sidecar.py -v
```

Expected: FAIL because `ParserService.__init__` does not accept the new dependencies and still imports MinerU internals.

- [ ] **Step 3: Add `error_message` model field**

Modify `backend/app/models/file.py`:

```python
error_message = Column(String(1024), nullable=True)
```

Add it to `to_dict()`:

```python
'error_message': self.error_message,
```

Create Alembic migration `backend/alembic/versions/9a4f2e8b6c31_add_file_error_message.py`:

```python
"""add file error message

Revision ID: 9a4f2e8b6c31
Revises: d6c47750e1f7
Create Date: 2026-06-07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9a4f2e8b6c31"
down_revision: Union[str, None] = "d6c47750e1f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("files", sa.Column("error_message", sa.String(length=1024), nullable=True))


def downgrade() -> None:
    op.drop_column("files", "error_message")
```

- [ ] **Step 4: Refactor `ParserService` imports and constructor**

In `backend/app/services/parser.py`, remove all imports from `mineru.*`. Keep only app, stdlib, SQLAlchemy, MinIO, and the new services.

Use this constructor:

```python
class ParserService:
    def __init__(self, db: Session, mineru_api_client: MineruApiClient | None = None, artifact_sync_factory=None):
        self.db = db
        self.mineru_api_client = mineru_api_client or MineruApiClient()
        self.artifact_sync_factory = artifact_sync_factory or self._default_artifact_sync_factory

    @staticmethod
    def _default_artifact_sync_factory(bucket: str) -> MineruArtifactSync:
        _, _, endpoint = get_s3_config(bucket)
        public_endpoint = os.getenv("MINIO_PUBLIC_ENDPOINT", endpoint)
        return MineruArtifactSync(minio_client, bucket=bucket, endpoint=endpoint, public_endpoint=public_endpoint)
```

- [ ] **Step 5: Replace `process_file` with API call**

Use this implementation shape:

```python
def process_file(
        self,
        file_name: str,
        file_bytes: bytes,
        file_extension: str,
        parse_method: str,
        lang: str,
        formula_enable: bool,
        table_enable: bool,
        backend: str,
        mds_bucket: str,
):
    if file_extension not in PDF_EXTENSIONS + IMAGE_EXTENSIONS:
        raise ValueError(f"不支持的文件类型: {file_extension}")

    result = self.mineru_api_client.parse_file(
        filename=f"{file_name}{file_extension}",
        file_bytes=file_bytes,
        backend=backend,
        parse_method=parse_method,
        lang=lang,
        formula_enable=formula_enable,
        table_enable=table_enable,
    )
    artifact_sync = self.artifact_sync_factory(mds_bucket)
    synced = artifact_sync.sync_zip(result.content, output_name=file_name)
    return [synced.markdown]
```

- [ ] **Step 6: Update `parse_file` status/error handling**

In success path set:

```python
file.status = FileStatus.PARSING
file.error_message = None
file.start_at = datetime.now()
```

In failure path set:

```python
self.db.rollback()
file.status = FileStatus.PARSE_FAILED
file.error_message = str(e)[:1024]
self.db.commit()
raise Exception(f"解析失败: {str(e)}")
```

Remove `predictor` usage from parser service. Keep endpoint signatures accepting it until the API route is updated, but ignore it.

- [ ] **Step 7: Run parser test and import scan**

Run:

```bash
cd backend && python3 -m pytest tests/test_parser_service_sidecar.py -v
rg -n "mineru\\." app
```

Expected: test PASS, and `rg` returns no MinerU internal imports in backend app code.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/parser.py backend/app/models/file.py backend/alembic/versions/9a4f2e8b6c31_add_file_error_message.py backend/tests/test_parser_service_sidecar.py
git commit -m "refactor: route parsing through MinerU API"
```

## Task 4: Add MinerU Health API

**Files:**
- Create: `backend/app/api/health.py`
- Modify: `backend/app/api/__init__.py`
- Modify: `backend/main.py`
- Test: `backend/tests/test_health_api.py`

- [ ] **Step 1: Write failing health API test**

Create `backend/tests/test_health_api.py`:

```python
from fastapi.testclient import TestClient

from main import app


def test_mineru_health_endpoint(monkeypatch):
    class FakeClient:
        def health(self):
            return {"available": True, "base_url": "http://mineru-api:8000", "status": "healthy"}

    monkeypatch.setattr("app.api.health.MineruApiClient", lambda: FakeClient())

    client = TestClient(app)
    response = client.get("/api/system/mineru-health")

    assert response.status_code == 200
    assert response.json()["available"] is True
    assert response.json()["base_url"] == "http://mineru-api:8000"
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
cd backend && python3 -m pytest tests/test_health_api.py -v
```

Expected: FAIL because `/api/system/mineru-health` does not exist.

- [ ] **Step 3: Add health router**

Create `backend/app/api/health.py`:

```python
from fastapi import APIRouter

from app.services.mineru_api import MineruApiClient

router = APIRouter()


@router.get("/system/mineru-health")
def mineru_health():
    return MineruApiClient().health()
```

Modify `backend/app/api/__init__.py`:

```python
from .health import router as health_router
```

Add `health_router` to `routers`.

Modify `backend/main.py`:

```python
from app.api import upload_router, files_router, parsed_router, settings_router, health_router
```

Add:

```python
app.include_router(health_router, prefix="/api", tags=["health"])
```

- [ ] **Step 4: Remove direct MinerU and Torch runtime code**

In `backend/main.py`, remove:

```python
import torch
from mineru.cli.fast_api import parse_pdf
app.add_api_route("/api/file_parse", parse_pdf, methods=['POST'])
```

Remove the preload branch that imports `ModelSingleton`. Replace `clean_memory()` with:

```python
def clean_memory():
    gc.collect()
```

Replace the lifespan body with:

```python
@asynccontextmanager
async def life_span(app: FastAPI):
    app.state.predictor = None
    yield
    clean_memory()
```

Keep the existing app routes and lifespan hook.

- [ ] **Step 5: Run health API test**

Run:

```bash
cd backend && python3 -m pytest tests/test_health_api.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/health.py backend/app/api/__init__.py backend/main.py backend/tests/test_health_api.py
git commit -m "feat: expose MinerU API health status"
```

## Task 5: Docker And Compose Migration

**Files:**
- Create: `backend/mineru-api.Dockerfile`
- Modify: `backend/Dockerfile`
- Modify: `backend/Dockerfile_2060`
- Modify: `backend/npu.Dockerfile`
- Modify: `docker-compose.yml`
- Modify: `docker-compose.npu.yml`
- Modify: `docker-compose.vllm.yaml`
- Modify: `docker-compose.vllm.npu.yaml`
- Modify: `docker-compose.basic.yaml`
- Modify: `.github/workflows/docker-build.yml`

- [ ] **Step 1: Create MinerU API sidecar Dockerfile**

Create `backend/mineru-api.Dockerfile`:

```dockerfile
FROM vllm/vllm-openai:v0.21.0

ARG MINERU_VERSION=3.2.3

RUN apt-get update && \
    apt-get install -y \
        fonts-noto-core \
        fonts-noto-cjk \
        fontconfig \
        libgl1 \
        libglib2.0-0 \
        curl && \
    fc-cache -fv && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install -U "mineru[core]==${MINERU_VERSION}" --break-system-packages && \
    python3 -m pip cache purge

WORKDIR /app

EXPOSE 8000

CMD ["mineru-api", "--host", "0.0.0.0", "--port", "8000"]
```

If official MinerU 3.2.3 Dockerfile uses a different command flag shape after verification, update this file to match the official command exactly.

- [ ] **Step 2: Keep backend Dockerfile lightweight**

Modify `backend/Dockerfile`:

```dockerfile
FROM python:3.12-slim

RUN apt-get update && \
    apt-get install -y \
        fonts-noto-core \
        fonts-noto-cjk \
        fontconfig \
        libgl1 \
        libglib2.0-0 && \
    fc-cache -fv && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN python3 -m pip install -U -r requirements.txt && python3 -m pip cache purge

COPY . .
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Apply the same lightweight direction to `backend/Dockerfile_2060` unless that file is removed from release usage. Keep `backend/npu.Dockerfile` for the business backend lightweight as well; NPU runtime belongs to `mineru-api` or a dedicated official NPU parser image.

- [ ] **Step 3: Update main compose**

In `docker-compose.yml`, add:

```yaml
  mineru-api:
    image: lpdswing/mineru-web-mineru-api:v3.2.3
    shm_size: "32gb"
    ipc: host
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    environment:
      - MINERU_API_OUTPUT_ROOT=/output
    volumes:
      - ./mineru.json:/root/mineru.json
      - ./models2.0:/models
      - mineru_api_output:/output
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 20s
      retries: 5
    networks:
      - mineru-network
```

For `backend` and `worker`, remove GPU reservations and add:

```yaml
      - MINERU_API_URL=http://mineru-api:8000
```

Set their `depends_on` to include:

```yaml
      mineru-api:
        condition: service_healthy
```

Add volume:

```yaml
  mineru_api_output:
```

- [ ] **Step 4: Update auxiliary compose files**

Apply the same service split to NPU and vLLM compose variants:

- `docker-compose.npu.yml`: use an NPU-compatible official MinerU API image or base image for `mineru-api`; point backend/worker to `MINERU_API_URL`.
- `docker-compose.vllm.yaml`: keep external VLM server if needed, but keep `mineru-api` as the MinerU API boundary.
- `docker-compose.vllm.npu.yaml`: keep NPU VLM server config where needed; backend still calls `mineru-api`.
- `docker-compose.basic.yaml`: either add `mineru-api` without GPU for pipeline-only mode or document that this file runs only support services.

- [ ] **Step 5: Update GitHub Actions parser image build**

Modify `.github/workflows/docker-build.yml`:

Add env:

```yaml
  MINERU_API_IMAGE: ${{ secrets.DOCKER_USERNAME }}/mineru-web-mineru-api
```

Add workflow input:

```yaml
      build_mineru_api:
        description: 'Build MinerU API image'
        required: true
        type: boolean
        default: true
```

Add metadata action:

```yaml
      - name: Generate MinerU API image metadata
        id: meta_mineru_api
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.MINERU_API_IMAGE }}
          tags: type=raw,value=${{ env.VERSION }}
```

Add build step:

```yaml
      - name: Build and push MinerU API image
        if: ${{ github.event_name == 'release' || inputs.build_mineru_api }}
        uses: docker/build-push-action@v5
        with:
          context: ./backend
          file: ./backend/mineru-api.Dockerfile
          platforms: ${{ steps.set-platforms.outputs.platforms }}
          push: true
          tags: ${{ steps.meta_mineru_api.outputs.tags }}
          labels: ${{ steps.meta_mineru_api.outputs.labels }}
          build-args: |
            MINERU_VERSION=3.2.3
          cache-from: type=gha
          cache-to: type=gha,mode=max
          provenance: false
```

- [ ] **Step 6: Validate compose syntax**

Run:

```bash
docker compose -f docker-compose.yml config
docker compose -f docker-compose.npu.yml config
```

Expected: both commands exit 0.

- [ ] **Step 7: Commit**

```bash
git add backend/mineru-api.Dockerfile backend/Dockerfile backend/Dockerfile_2060 backend/npu.Dockerfile docker-compose*.yml docker-compose*.yaml .github/workflows/docker-build.yml
git commit -m "build: split MinerU API sidecar runtime"
```

## Task 6: Frontend Health And Failure Visibility

**Files:**
- Modify: `frontend/src/api/settings.ts`
- Modify: `frontend/src/views/Settings.vue`
- Modify: `frontend/src/types/file.ts`
- Modify: `frontend/src/views/Files.vue`

- [ ] **Step 1: Add frontend health API type**

Modify `frontend/src/api/settings.ts`:

```ts
export interface MineruHealthResponse {
  available: boolean
  base_url: string
  status?: string
  version?: string
  error?: string
  [key: string]: unknown
}
```

Add:

```ts
  getMineruHealth() {
    return api.get<MineruHealthResponse>('/system/mineru-health')
      .then(res => res.data)
  }
```

- [ ] **Step 2: Add health state to settings page**

In `frontend/src/views/Settings.vue`, add:

```ts
interface MineruHealth {
  available: boolean
  base_url: string
  status?: string
  version?: string
  error?: string
}

const mineruHealth = ref<MineruHealth | null>(null)

const loadMineruHealth = async () => {
  try {
    mineruHealth.value = await settingsApi.getMineruHealth()
  } catch (error) {
    mineruHealth.value = {
      available: false,
      base_url: '',
      error: '无法获取 MinerU API 状态'
    }
  }
}
```

Call `loadMineruHealth()` inside `onMounted`.

- [ ] **Step 3: Render health section**

Add this section under backend engine settings:

```vue
<div class="form-section">
  <div class="section-title">
    <el-icon><Connection /></el-icon>
    <span>解析服务状态</span>
  </div>
  <div class="health-grid" v-if="mineruHealth">
    <div class="health-row">
      <span class="health-label">服务地址</span>
      <span class="health-value">{{ mineruHealth.base_url || '-' }}</span>
    </div>
    <div class="health-row">
      <span class="health-label">状态</span>
      <el-tag :type="mineruHealth.available ? 'success' : 'danger'">
        {{ mineruHealth.available ? '可用' : '不可用' }}
      </el-tag>
    </div>
    <div class="health-row" v-if="mineruHealth.version">
      <span class="health-label">MinerU 版本</span>
      <span class="health-value">{{ mineruHealth.version }}</span>
    </div>
    <div class="health-row" v-if="mineruHealth.error">
      <span class="health-label">错误</span>
      <span class="health-value error">{{ mineruHealth.error }}</span>
    </div>
  </div>
</div>
```

Import `Connection` from Element Plus icons.

- [ ] **Step 4: Add file failure reason type and table display**

Modify `frontend/src/types/file.ts` to include:

```ts
  error_message?: string | null
```

In `frontend/src/views/Files.vue`, add an `el-tooltip` around failed status:

```vue
<el-tooltip
  v-if="row.status === 'parse_failed' && row.error_message"
  :content="row.error_message"
  placement="top"
>
  <span class="status-error-text">{{ getStatusText(row.status) }}</span>
</el-tooltip>
<span v-else>{{ getStatusText(row.status) }}</span>
```

- [ ] **Step 5: Build frontend**

Run:

```bash
cd frontend && npm run build
```

Expected: build exits 0.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/settings.ts frontend/src/views/Settings.vue frontend/src/types/file.ts frontend/src/views/Files.vue
git commit -m "feat: show MinerU API status in settings"
```

## Task 7: Version, README, And Release Notes

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `README.md`
- Modify: `docker-compose.yml`
- Modify: `docker-compose.npu.yml`
- Modify: `docker-compose.vllm.yaml`
- Modify: `docker-compose.vllm.npu.yaml`

- [ ] **Step 1: Update visible UI version**

In `frontend/src/App.vue`, replace:

```vue
<span v-show="sidebarHover" class="version-text">v2.7.1</span>
```

with:

```vue
<span v-show="sidebarHover" class="version-text">v3.2.3</span>
```

- [ ] **Step 2: Update image tags**

Replace compose image tags:

```txt
v2.7.1
```

with:

```txt
v3.2.3
```

Expected images include backend, frontend, backend-npu, and mineru-api where present.

- [ ] **Step 3: Update README release notes**

Add at the top of the changelog:

```markdown
### [3.2.3] - 2026-06-07

- 后端
  - 适配 MinerU 3.2.3，解析入口切换为官方 MinerU API sidecar
  - 保留 MinIO/S3 图片与 Markdown 转存能力
  - 新增 MinerU API 健康状态接口
  - 后端业务镜像轻量化，不再直接依赖 MinerU 内部 Python API

- 前端
  - 设置页增加解析服务状态展示
  - 文件列表解析失败时展示更明确的失败原因
```

- [ ] **Step 4: Commit**

```bash
git add README.md frontend/src/App.vue docker-compose*.yml docker-compose*.yaml
git commit -m "chore: align release version with MinerU 3.2.3"
```

## Task 8: Full Verification

**Files:**
- No planned source changes unless verification exposes failures.

- [ ] **Step 1: Run backend unit tests**

Run:

```bash
cd backend && python3 -m pytest tests -v
```

Expected: all tests PASS.

- [ ] **Step 2: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: build exits 0.

- [ ] **Step 3: Validate no backend MinerU internal imports**

Run:

```bash
rg -n "from mineru|import mineru|mineru\\." backend/app backend/main.py
```

Expected: no output.

- [ ] **Step 4: Validate Docker Compose configs**

Run:

```bash
docker compose -f docker-compose.yml config
docker compose -f docker-compose.npu.yml config
docker compose -f docker-compose.vllm.yaml config
docker compose -f docker-compose.vllm.npu.yaml config
```

Expected: all commands exit 0.

- [ ] **Step 5: Optional smoke test with real services**

Run when GPU/model environment is available:

```bash
docker compose up -d redis minio mineru-api backend worker frontend
curl -f http://localhost:8088/api/system/mineru-health
```

Upload `backend/tests/test.pdf` through the UI and verify:

- file reaches `parsed`
- Markdown preview renders
- image URLs point to MinIO HTTP URLs
- parsed content exists in the database

- [ ] **Step 6: Final status**

Run:

```bash
git status --short
```

Expected: clean working tree after all task commits.
