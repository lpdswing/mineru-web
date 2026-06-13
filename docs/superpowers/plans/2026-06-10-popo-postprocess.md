# MinerU-Popo Postprocessing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add optional MinerU-Popo postprocessing as an independent service triggered by the worker after MinerU artifacts are synced to MinIO, with backend APIs and frontend preview/export support for Popo Markdown.

**Architecture:** Keep Popo isolated in a `popo-postprocessor` HTTP service. The business worker discovers MinerU artifacts already uploaded to MinIO, calls the Popo service through a lightweight client, and treats Popo failures as non-fatal. Backend preview/export APIs read Popo outputs from MinIO, and the frontend adds a Markdown variant switch.

**Tech Stack:** FastAPI, httpx, MinIO Python client, SQLAlchemy tests with fakes, Vue 3 Composition API, Element Plus, Docker Compose.

---

## File Structure

- Create `backend/app/services/popo.py`
  - Business-side Popo client, env parsing, artifact discovery, output path construction, status artifact writing.
- Modify `backend/app/services/parser.py`
  - Inject and invoke Popo postprocessor after `MineruArtifactSync.sync_zip()`.
- Modify `backend/app/api/parsed.py`
  - Add Markdown variants, Popo status endpoint, and `markdown_popo` export.
- Modify `backend/tests/test_parser_service_sidecar.py`
  - Parser integration tests for Popo enabled/disabled/failure.
- Modify `backend/tests/test_export_api.py`
  - API tests for `variant=popo`, `markdown_popo`, and Popo status.
- Modify `frontend/src/types/file.ts`
  - Add Popo export format and Markdown variant/status types.
- Modify `frontend/src/api/files.ts`
  - Add variant support and Popo status API helpers.
- Modify `frontend/src/views/FilePreview.vue`
  - Add Markdown variant switch and Popo unavailable/status handling.
- Create `popo-postprocessor/`
  - Independent FastAPI wrapper around the MinerU-Popo pipeline.
- Modify `.env.example`, `docker-compose.yml`, `docker-compose.mac.yml`, and `docs/deployment.md`
  - Document and pass Popo config; default remains disabled.
- Create `docker-compose.popo.yml`
  - Optional Popo service profile/override.

## Task 1: Business-Side Popo Client

**Files:**
- Create: `backend/app/services/popo.py`
- Test: `backend/tests/test_popo_client.py`

- [ ] **Step 1: Write failing tests for env parsing, artifact discovery, and status writing**

Create `backend/tests/test_popo_client.py`:

```python
import json

from app.services.popo import (
    PopoConfig,
    PopoPostprocessor,
    build_popo_outputs,
    discover_popo_artifacts,
    parse_popo_enabled,
)


def test_parse_popo_enabled_accepts_common_truthy_values():
    assert parse_popo_enabled("1") is True
    assert parse_popo_enabled("true") is True
    assert parse_popo_enabled("yes") is True
    assert parse_popo_enabled("0") is False
    assert parse_popo_enabled("") is False
    assert parse_popo_enabled(None) is False


def test_discover_popo_artifacts_finds_mineru_json_outputs():
    artifacts = discover_popo_artifacts(
        [
            "sample/auto/sample_middle.json",
            "sample/auto/sample_content_list.json",
            "sample/auto/sample_model.json",
            "sample/images/a.png",
        ]
    )

    assert artifacts == {
        "middle_json": "sample/auto/sample_middle.json",
        "content_list_json": "sample/auto/sample_content_list.json",
        "model_json": "sample/auto/sample_model.json",
    }


def test_build_popo_outputs_uses_export_level_paths():
    assert build_popo_outputs("sample") == {
        "markdown": "sample_popo.md",
        "json": "sample_popo.json",
        "status": "sample_popo_status.json",
    }


class FakeMinio:
    def __init__(self):
        self.objects = {}

    def put_object(self, bucket, path, data, length, content_type=None):
        self.objects[(bucket, path)] = {
            "content": data.read(),
            "content_type": content_type,
        }


def test_write_status_uploads_json_status():
    fake_minio = FakeMinio()
    postprocessor = PopoPostprocessor(
        config=PopoConfig(enabled=True, api_url="http://popo:8010", timeout_seconds=10),
        minio=fake_minio,
    )

    postprocessor.write_status("mds", "sample_popo_status.json", "skipped", "missing model")

    payload = json.loads(fake_minio.objects[("mds", "sample_popo_status.json")]["content"])
    assert payload["status"] == "skipped"
    assert payload["message"] == "missing model"
    assert fake_minio.objects[("mds", "sample_popo_status.json")]["content_type"] == "application/json"
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
.venv/bin/pytest backend/tests/test_popo_client.py -q
```

Expected: fail because `app.services.popo` does not exist.

- [ ] **Step 3: Implement `backend/app/services/popo.py`**

Create the file with these public functions/classes:

```python
import io
import json
import os
from dataclasses import dataclass
from typing import Any

import httpx
from loguru import logger


def parse_popo_enabled(value: str | None = None) -> bool:
    raw = os.getenv("POPO_ENABLED", "0") if value is None else value
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class PopoConfig:
    enabled: bool
    api_url: str
    timeout_seconds: float

    @classmethod
    def from_env(cls) -> "PopoConfig":
        return cls(
            enabled=parse_popo_enabled(),
            api_url=os.getenv("POPO_API_URL", "http://popo-postprocessor:8010").rstrip("/"),
            timeout_seconds=float(os.getenv("POPO_TIMEOUT_SECONDS", "1800")),
        )


def discover_popo_artifacts(uploaded_paths: list[str]) -> dict[str, str]:
    artifacts: dict[str, str] = {}
    suffix_map = {
        "_middle.json": "middle_json",
        "_content_list.json": "content_list_json",
        "_model.json": "model_json",
    }
    for path in uploaded_paths:
        for suffix, key in suffix_map.items():
            if path.endswith(suffix):
                artifacts[key] = path
    return artifacts


def build_popo_outputs(prefix: str) -> dict[str, str]:
    return {
        "markdown": f"{prefix}_popo.md",
        "json": f"{prefix}_popo.json",
        "status": f"{prefix}_popo_status.json",
    }


class PopoPostprocessor:
    def __init__(
        self,
        config: PopoConfig | None = None,
        minio=None,
        http_client: httpx.Client | None = None,
    ):
        self.config = config or PopoConfig.from_env()
        self.minio = minio
        self.http_client = http_client or httpx.Client(timeout=self.config.timeout_seconds)

    def postprocess(self, bucket: str, prefix: str, uploaded_paths: list[str]) -> None:
        if not self.config.enabled:
            return
        outputs = build_popo_outputs(prefix)
        artifacts = discover_popo_artifacts(uploaded_paths)
        missing = [key for key in ("middle_json", "content_list_json", "model_json") if key not in artifacts]
        if missing:
            self.write_status(bucket, outputs["status"], "skipped", f"Missing Popo artifacts: {', '.join(missing)}")
            return
        try:
            response = self.http_client.post(
                f"{self.config.api_url}/v1/postprocess",
                json={"bucket": bucket, "prefix": prefix, "artifacts": artifacts, "outputs": outputs},
            )
            response.raise_for_status()
        except Exception as exc:
            logger.warning(f"Popo postprocess failed for {prefix}: {exc}")
            self.write_status(bucket, outputs["status"], "failed", str(exc)[:1024])

    def write_status(self, bucket: str, path: str, status: str, message: str = "") -> None:
        if not self.minio:
            return
        payload: dict[str, Any] = {"status": status, "message": message}
        content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.minio.put_object(bucket, path, io.BytesIO(content), len(content), content_type="application/json")
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```bash
.venv/bin/pytest backend/tests/test_popo_client.py -q
```

Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/popo.py backend/tests/test_popo_client.py
git commit -m "Add Popo postprocess client"
```

## Task 2: Trigger Popo From ParserService

**Files:**
- Modify: `backend/app/services/parser.py`
- Modify: `backend/tests/test_parser_service_sidecar.py`

- [ ] **Step 1: Write failing parser integration tests**

Append tests to `backend/tests/test_parser_service_sidecar.py`:

```python
class FakeArtifactSyncWithPaths:
    def sync_zip(self, content, output_name):
        assert output_name == "sample"
        return SimpleNamespace(
            markdown="# parsed",
            markdown_path="sample.md",
            uploaded_paths=[
                "sample/auto/sample_middle.json",
                "sample/auto/sample_content_list.json",
                "sample/auto/sample_model.json",
            ],
        )


class FakePopoPostprocessor:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    def postprocess(self, bucket, prefix, uploaded_paths):
        self.calls.append((bucket, prefix, uploaded_paths))
        if self.fail:
            raise RuntimeError("popo failed")


def test_parse_file_triggers_popo_after_artifact_sync(monkeypatch):
    fake_client = FakeApiClient()
    fake_popo = FakePopoPostprocessor()
    db = FakeDb()
    service = ParserService(
        db,
        mineru_api_client=fake_client,
        artifact_sync_factory=lambda bucket: FakeArtifactSyncWithPaths(),
        popo_postprocessor=fake_popo,
    )
    file = SimpleNamespace(id=1, minio_path="uploads/sample.pdf", status=FileStatus.PENDING, start_at=None, finish_at=None, error_message=None)

    monkeypatch.setattr("app.services.parser.minio_client", FakeMinio())
    monkeypatch.setattr("app.services.parser.get_buckets", lambda: ["mds"])

    assert service.parse_file(file, user_id="u1") == {"status": "success"}
    assert fake_popo.calls == [
        (
            "mds",
            "sample",
            [
                "sample/auto/sample_middle.json",
                "sample/auto/sample_content_list.json",
                "sample/auto/sample_model.json",
            ],
        )
    ]


def test_parse_file_keeps_success_when_popo_fails(monkeypatch):
    fake_popo = FakePopoPostprocessor(fail=True)
    service = ParserService(
        FakeDb(),
        mineru_api_client=FakeApiClient(),
        artifact_sync_factory=lambda bucket: FakeArtifactSyncWithPaths(),
        popo_postprocessor=fake_popo,
    )
    file = SimpleNamespace(id=1, minio_path="uploads/sample.pdf", status=FileStatus.PENDING, start_at=None, finish_at=None, error_message=None)

    monkeypatch.setattr("app.services.parser.minio_client", FakeMinio())
    monkeypatch.setattr("app.services.parser.get_buckets", lambda: ["mds"])

    result = service.parse_file(file, user_id="u1")

    assert result == {"status": "success"}
    assert file.status == FileStatus.PARSED
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
.venv/bin/pytest backend/tests/test_parser_service_sidecar.py -q
```

Expected: fail because `ParserService.__init__()` does not accept `popo_postprocessor`.

- [ ] **Step 3: Implement ParserService integration**

Modify `backend/app/services/parser.py`:

```python
from app.services.popo import PopoPostprocessor
```

Update `ParserService.__init__`:

```python
def __init__(
    self,
    db: Session,
    mineru_api_client: MineruApiClient | None = None,
    artifact_sync_factory=None,
    popo_postprocessor: PopoPostprocessor | None = None,
):
    self.db = db
    self.mineru_api_client = mineru_api_client or MineruApiClient()
    self.artifact_sync_factory = artifact_sync_factory or self._default_artifact_sync_factory
    self.popo_postprocessor = popo_postprocessor or PopoPostprocessor(minio=minio_client)
```

Update `process_file()` after `sync_zip()`:

```python
synced = artifact_sync.sync_zip(result.content, output_name=file_name)
try:
    self.popo_postprocessor.postprocess(mds_bucket, file_name, synced.uploaded_paths)
except Exception as exc:
    logger.warning(f"Popo postprocess skipped for {file_name}: {exc}")
return [synced.markdown]
```

- [ ] **Step 4: Run parser tests**

Run:

```bash
.venv/bin/pytest backend/tests/test_parser_service_sidecar.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Run Popo client tests**

Run:

```bash
.venv/bin/pytest backend/tests/test_popo_client.py backend/tests/test_parser_service_sidecar.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/parser.py backend/tests/test_parser_service_sidecar.py
git commit -m "Trigger Popo postprocessing after parsing"
```

## Task 3: Backend Popo Preview, Export, and Status APIs

**Files:**
- Modify: `backend/app/api/parsed.py`
- Modify: `backend/tests/test_export_api.py`

- [ ] **Step 1: Add failing API tests**

Extend `FakeMinio` in `backend/tests/test_export_api.py` so it can return object content:

```python
class FakeObject:
    def __init__(self, content):
        self.content = content

    def read(self):
        return self.content
```

Update `FakeMinio.existing_objects` to include:

```python
("mds", "sample_popo.md"): b"# Popo",
("mds", "sample_popo_status.json"): b'{"status":"success","message":""}',
```

Add method:

```python
def get_object(self, bucket, path):
    if (bucket, path) not in self.existing_objects:
        raise FileNotFoundError(path)
    return FakeObject(self.existing_objects[(bucket, path)])
```

Add tests:

```python
def test_parsed_content_endpoint_returns_popo_markdown(monkeypatch):
    fake_file = SimpleNamespace(id=3, user_id="u1", filename="sample.pdf", minio_path="uploads/sample.pdf")
    fake_minio = FakeMinio()
    app.dependency_overrides[get_db] = lambda: FakeDb(fake_file)
    monkeypatch.setattr("app.api.parsed.get_buckets", lambda: ["mds"])
    monkeypatch.setattr("app.api.parsed.minio_client", fake_minio)

    try:
        response = TestClient(app).get(
            "/api/files/3/parsed_content",
            params={"variant": "popo"},
            headers={"X-User-Id": "u1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == "# Popo"


def test_export_endpoint_returns_popo_markdown_download_url(monkeypatch):
    fake_file = SimpleNamespace(id=3, user_id="u1", filename="sample.pdf", minio_path="uploads/sample.pdf")
    fake_minio = FakeMinio()
    app.dependency_overrides[get_db] = lambda: FakeDb(fake_file)
    monkeypatch.setattr("app.api.parsed.get_buckets", lambda: ["mds"])
    monkeypatch.setattr("app.api.parsed.minio_client", fake_minio)
    monkeypatch.setattr("app.api.parsed.get_presigned_url", lambda bucket, path, expires=3600: f"http://minio/{bucket}/{path}?signed=1")

    try:
        response = TestClient(app).get(
            "/api/files/3/export",
            params={"format": "markdown_popo"},
            headers={"X-User-Id": "u1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert fake_minio.stat_calls == [("mds", "sample_popo.md")]
    assert response.json()["download_url"] == "http://minio/mds/sample_popo.md?signed=1"
    assert response.json()["filename"] == "sample_popo.md"


def test_popo_status_endpoint_returns_status_json(monkeypatch):
    fake_file = SimpleNamespace(id=3, user_id="u1", filename="sample.pdf", minio_path="uploads/sample.pdf")
    fake_minio = FakeMinio()
    app.dependency_overrides[get_db] = lambda: FakeDb(fake_file)
    monkeypatch.setattr("app.api.parsed.get_buckets", lambda: ["mds"])
    monkeypatch.setattr("app.api.parsed.minio_client", fake_minio)

    try:
        response = TestClient(app).get("/api/files/3/popo/status", headers={"X-User-Id": "u1"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "success"
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
.venv/bin/pytest backend/tests/test_export_api.py -q
```

Expected: fail because `variant=popo`, `markdown_popo`, and `/popo/status` are not implemented.

- [ ] **Step 3: Implement path helpers and API variants**

Modify `backend/app/api/parsed.py` with focused helpers:

```python
def _artifact_stem(file: FileModel) -> str:
    return Path(file.minio_path).stem


def _markdown_path_for_variant(file: FileModel, variant: str) -> str:
    stem = _artifact_stem(file)
    if variant == "markdown":
        return f"{stem}.md"
    if variant == "markdown_page":
        return f"{stem}_pages.md"
    if variant in {"popo", "markdown_popo"}:
        return f"{stem}_popo.md"
    raise HTTPException(status_code=400, detail="不支持的 Markdown 变体")


def _popo_status_path(file: FileModel) -> str:
    return f"{_artifact_stem(file)}_popo_status.json"
```

Update `get_parsed_content()` signature:

```python
def get_parsed_content(
    file_id: int,
    variant: str = Query("markdown", description="markdown、markdown_page 或 popo"),
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    file = db.query(FileModel).filter(FileModel.id == file_id, FileModel.user_id == user_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="文件不存在")
    if variant == "markdown":
        parser = ParserService(db)
        return parser.get_parsed_content(file_id, user_id)
    buckets = get_buckets()
    output_path = _markdown_path_for_variant(file, variant)
    try:
        response = minio_client.get_object(buckets[0], output_path)
        return response.read().decode("utf-8")
    except Exception:
        raise HTTPException(status_code=404, detail="导出文件不存在")
```

Keep existing DB behavior only for `variant == "markdown"`. For `markdown_page` and `popo`, read from MinIO with `get_object()` and return decoded text. Missing object returns 404.

Update `export_content()` so `format == "markdown_popo"` maps to `{stem}_popo.md` and download filename `{original_filename}_popo.md`.

Add:

```python
@router.get("/files/{file_id}/popo/status")
def get_popo_status(
    file_id: int,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    file = db.query(FileModel).filter(FileModel.id == file_id, FileModel.user_id == user_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="文件不存在")
    try:
        response = minio_client.get_object(get_buckets()[0], _popo_status_path(file))
        return json.loads(response.read().decode("utf-8"))
    except Exception:
        return {"status": "not_available", "message": ""}
```

Return `{"status": "not_available", "message": ""}` if status object is missing.

- [ ] **Step 4: Run API tests**

Run:

```bash
.venv/bin/pytest backend/tests/test_export_api.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Run backend tests**

Run:

```bash
.venv/bin/pytest backend/tests -q
```

Expected: all backend tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/parsed.py backend/tests/test_export_api.py
git commit -m "Add Popo preview and export APIs"
```

## Task 4: Popo Postprocessor Service Wrapper

**Files:**
- Create: `popo-postprocessor/app/main.py`
- Create: `popo-postprocessor/app/pipeline.py`
- Create: `popo-postprocessor/requirements.txt`
- Create: `popo-postprocessor/Dockerfile`
- Create: `popo-postprocessor/README.md`

- [ ] **Step 1: Create service files with a runnable pipeline wrapper**

Create `popo-postprocessor/app/pipeline.py`. This file owns MinIO I/O, MinerU-Popo directory layout, subprocess calls, and output uploads:

```python
import io
import json
import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from minio import Minio


def parse_minio_endpoint(endpoint: str) -> tuple[str, bool]:
    parsed = urlparse(endpoint)
    if parsed.scheme:
        return parsed.netloc, parsed.scheme == "https"
    return endpoint, os.getenv("MINIO_SECURE", "false").lower() == "true"


class PopoPipeline:
    def __init__(self):
        self.repo_dir = Path(os.getenv("POPO_REPO_DIR", "/opt/MinerU-Popo"))
        self.workspace = Path(os.getenv("POPO_WORKSPACE", "/workspace"))
        self.model_path = os.getenv("POPO_MODEL_PATH", "/models/MinerU-Popo")
        endpoint, secure = parse_minio_endpoint(os.getenv("MINIO_ENDPOINT", "localhost:9000"))
        self.minio = Minio(
            endpoint,
            access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
            secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
            secure=secure,
        )

    def run(self, request):
        job_dir = self.workspace / request.prefix
        if job_dir.exists():
            shutil.rmtree(job_dir)
        input_dir = job_dir / "post-process" / "mineru" / request.prefix / "vlm"
        input_dir.mkdir(parents=True, exist_ok=True)

        self.download_artifact(request.bucket, request.artifacts["middle_json"], input_dir / f"{request.prefix}_middle.json")
        self.download_artifact(request.bucket, request.artifacts["content_list_json"], input_dir / f"{request.prefix}_content_list.json")
        self.download_artifact(request.bucket, request.artifacts["model_json"], input_dir / f"{request.prefix}_model.json")

        self.run_popo_commands(job_dir, request.prefix)

        tree_path = job_dir / "outputs" / "build_tree" / "mineru" / f"{request.prefix}.json"
        text_path = job_dir / "outputs" / "build_tree_txt" / "mineru" / f"{request.prefix}.txt"
        self.upload_file(request.bucket, request.outputs["json"], tree_path, "application/json")
        self.upload_file(request.bucket, request.outputs["markdown"], text_path, "text/markdown; charset=utf-8")
        self.write_status(request.bucket, request.outputs["status"], "success", "")
        return {
            "status": "success",
            "markdown_path": request.outputs["markdown"],
            "json_path": request.outputs["json"],
        }

    def download_artifact(self, bucket: str, object_name: str, target: Path) -> None:
        response = self.minio.get_object(bucket, object_name)
        try:
            target.write_bytes(response.read())
        finally:
            response.close()
            response.release_conn()

    def upload_file(self, bucket: str, object_name: str, path: Path, content_type: str) -> None:
        content = path.read_bytes()
        self.minio.put_object(bucket, object_name, io.BytesIO(content), len(content), content_type=content_type)

    def write_status(self, bucket: str, object_name: str, status: str, message: str) -> None:
        content = json.dumps({"status": status, "message": message}, ensure_ascii=False).encode("utf-8")
        self.minio.put_object(bucket, object_name, io.BytesIO(content), len(content), content_type="application/json")
```

- [ ] **Step 2: Implement FastAPI wrapper**

Create `popo-postprocessor/app/main.py`:

```python
from fastapi import FastAPI
from pydantic import BaseModel

from app.pipeline import PopoPipeline


class PopoRequest(BaseModel):
    bucket: str
    prefix: str
    artifacts: dict[str, str]
    outputs: dict[str, str]


app = FastAPI(title="MinerU-Popo Postprocessor")
pipeline = PopoPipeline()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/v1/postprocess")
def postprocess(request: PopoRequest):
    return pipeline.run(request)
```

- [ ] **Step 3: Implement pipeline file layout and command runner**

Add this method to `PopoPipeline` in `popo-postprocessor/app/pipeline.py`:

```python
def run_popo_commands(self, job_dir: Path, doc_id: str) -> None:
    subprocess.run(
        [
            "python3",
            str(self.repo_dir / "post_processing" / "label_normalization.py"),
            "--model",
            "mineru",
            "--input-dir",
            str(job_dir / "post-process" / "mineru"),
            "--output-dir",
            str(job_dir / "outputs" / "label_normalization"),
            "--doc-id",
            doc_id,
            "--doc-limit",
            "0",
        ],
        cwd=self.repo_dir,
        check=True,
    )

    subprocess.run(
        [
            "python3",
            str(self.repo_dir / "post_processing" / "run_inference.py"),
            "--model",
            "mineru",
            "--input-dir",
            str(job_dir / "outputs" / "label_normalization" / "mineru"),
            "--model-path",
            self.model_path,
            "--output-dir",
            str(job_dir / "outputs" / "inference" / "mineru"),
            "--raw-output-root",
            "",
            "--limit",
            "0",
        ],
        cwd=self.repo_dir,
        check=True,
    )

    subprocess.run(
        [
            "python3",
            str(self.repo_dir / "post_processing" / "get_json_tree.py"),
            "--input-dir",
            str(job_dir / "outputs" / "inference" / "mineru"),
            "--output-dir",
            str(job_dir / "outputs" / "build_tree" / "mineru"),
            "--txt-dir",
            str(job_dir / "outputs" / "build_tree_txt" / "mineru"),
        ],
        cwd=self.repo_dir,
        check=True,
    )
```

Use Python `subprocess.run([...], check=True, cwd=self.repo_dir)` instead of shell strings.

Use the MinerU-Popo source contract from `/tmp/MinerU-Popo-ref` or the cloned repository:

```text
post-process/mineru/<doc_id>/vlm/
outputs/label_normalization/mineru/
outputs/inference/mineru/
outputs/build_tree/mineru/
outputs/build_tree_txt/mineru/
```

The wrapper calls the Python entrypoints directly instead of the repo's default shell scripts because the shell scripts hard-code debug limits and `MODEL_PATH="popo_model"`.

- [ ] **Step 4: Add Dockerfile**

Create `popo-postprocessor/Dockerfile`:

```dockerfile
FROM python:3.10-slim

WORKDIR /service

RUN apt-get update && apt-get install -y --no-install-recommends git curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /service/requirements.txt
RUN pip install --no-cache-dir -r /service/requirements.txt

RUN git clone --depth 1 https://github.com/opendatalab/MinerU-Popo.git /opt/MinerU-Popo
RUN pip install --no-cache-dir -r /opt/MinerU-Popo/requirements.txt

COPY app /service/app

ENV POPO_REPO_DIR=/opt/MinerU-Popo
ENV POPO_WORKSPACE=/workspace

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]
```

Create `popo-postprocessor/requirements.txt`:

```text
fastapi==0.115.12
uvicorn[standard]==0.34.3
minio==7.2.15
pydantic==2.11.5
```

- [ ] **Step 5: Document service setup**

Create `popo-postprocessor/README.md` with:

```markdown
# Popo Postprocessor

HTTP wrapper around opendatalab/MinerU-Popo.

The service expects MinerU artifacts in MinIO and writes Popo Markdown, JSON, and status artifacts back to MinIO.

Required env:
- MINIO_ENDPOINT
- MINIO_ACCESS_KEY
- MINIO_SECRET_KEY
- POPO_MODEL_PATH
```

- [ ] **Step 6: Build smoke check**

Run:

```bash
docker build -f popo-postprocessor/Dockerfile popo-postprocessor
```

Expected: image builds. If the build cannot download GitHub/model dependencies in the current network, record the exact failure and continue with backend/frontend tests; do not fake a successful Popo runtime.

- [ ] **Step 7: Commit**

```bash
git add popo-postprocessor
git commit -m "Add Popo postprocessor service wrapper"
```

## Task 5: Frontend API Types and File Preview UI

**Files:**
- Modify: `frontend/src/types/file.ts`
- Modify: `frontend/src/api/files.ts`
- Modify: `frontend/src/views/FilePreview.vue`

- [ ] **Step 1: Update frontend types**

In `frontend/src/types/file.ts`, update export formats:

```ts
export const ExportFormats = {
  MARKDOWN: 'markdown',
  MARKDOWN_PAGE: 'markdown_page',
  MARKDOWN_POPO: 'markdown_popo'
} as const

export type MarkdownVariant = 'markdown' | 'markdown_page' | 'popo'
export type PopoStatusValue = 'not_available' | 'processing' | 'success' | 'failed' | 'skipped'

export interface PopoStatus {
  status: PopoStatusValue
  message?: string
}
```

Add display name:

```ts
[ExportFormats.MARKDOWN_POPO]: 'Popo Markdown'
```

- [ ] **Step 2: Update frontend API wrapper**

In `frontend/src/api/files.ts`, update imports and methods:

```ts
import type { FileItem, ExportFormat, MarkdownVariant, PopoStatus } from '@/types/file'

getParsedContent(fileId: string, variant: MarkdownVariant = 'markdown') {
  return api.get<string>(`/files/${fileId}/parsed_content`, { params: { variant } })
    .then(res => res.data)
},

getPopoStatus(fileId: string) {
  return api.get<PopoStatus>(`/files/${fileId}/popo/status`)
    .then(res => res.data)
},
```

- [ ] **Step 3: Update FilePreview local state**

In `frontend/src/views/FilePreview.vue`, add a Markdown variant state:

```ts
type MarkdownVariant = 'markdown' | 'markdown_page' | 'popo'
type PopoStatusValue = 'not_available' | 'processing' | 'success' | 'failed' | 'skipped'

const markdownVariant = ref<MarkdownVariant>('markdown')
const popoStatus = ref<{ status: PopoStatusValue; message?: string } | null>(null)
const markdownVariantNames: Record<MarkdownVariant, string> = {
  markdown: '原始 Markdown',
  markdown_page: '按页 Markdown',
  popo: 'Popo 增强',
}
```

Update `fetchParsedContent()` to pass `variant` and handle Popo 404:

```ts
const fetchParsedContent = async () => {
  if (!currentFile.value) return
  loading.value = true
  try {
    const res = await axios.get(`/api/files/${currentFile.value.id}/parsed_content`, {
      params: { variant: markdownVariant.value },
      headers: { 'X-User-Id': getUserId() }
    })
    parsedContent.value = res.data || ''
    popoStatus.value = null
  } catch (e) {
    parsedContent.value = ''
    if (markdownVariant.value === 'popo') {
      await fetchPopoStatus()
      return
    }
    ElMessage.error('获取解析内容失败')
  } finally {
    loading.value = false
  }
}
```

Add:

```ts
const fetchPopoStatus = async () => {
  if (!currentFile.value) return
  try {
    const res = await axios.get(`/api/files/${currentFile.value.id}/popo/status`, {
      headers: { 'X-User-Id': getUserId() }
    })
    popoStatus.value = res.data
  } catch (e) {
    popoStatus.value = { status: 'not_available', message: '' }
  }
}

const handleMarkdownVariant = (variant: MarkdownVariant) => {
  markdownVariant.value = variant
  fetchParsedContent()
}
```

- [ ] **Step 4: Update FilePreview template**

Inside the Markdown panel, above the loading state, add a compact segmented control:

```vue
<div class="markdown-toolbar">
  <button
    v-for="(name, variant) in markdownVariantNames"
    :key="variant"
    class="markdown-tab"
    :class="{ active: markdownVariant === variant }"
    @click="handleMarkdownVariant(variant as MarkdownVariant)"
  >
    {{ name }}
  </button>
</div>
```

Replace the content body with:

```vue
<div v-if="loading" class="loading-state">
  <el-icon class="is-loading" :size="32"><Loading /></el-icon>
  <span>加载中...</span>
</div>
<el-empty
  v-else-if="markdownVariant === 'popo' && !parsedContent"
  :description="popoStatus?.message || 'Popo 结果暂不可用'"
  :image-size="100"
/>
<div v-else class="markdown-content" v-html="renderedContent"></div>
```

- [ ] **Step 5: Update local export formats in FilePreview**

Replace local `ExportFormats` with:

```ts
const ExportFormats = { MARKDOWN: 'markdown', MARKDOWN_PAGE: 'markdown_page', MARKDOWN_POPO: 'markdown_popo' } as const
```

Add name:

```ts
[ExportFormats.MARKDOWN_POPO]: 'Popo Markdown'
```

- [ ] **Step 6: Add CSS**

Add scoped styles:

```css
.markdown-toolbar {
  display: flex;
  gap: 4px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border-light);
}

.markdown-tab {
  height: 30px;
  padding: 0 10px;
  border: 1px solid var(--border-light);
  background: var(--bg-primary);
  color: var(--text-secondary);
  border-radius: var(--radius-sm);
  cursor: pointer;
}

.markdown-tab.active {
  color: var(--primary-color);
  border-color: var(--primary-color);
  background: var(--primary-light);
}
```

- [ ] **Step 7: Build frontend**

Run:

```bash
cd frontend
npm run build
```

Expected: `vue-tsc -b && vite build` succeeds.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/types/file.ts frontend/src/api/files.ts frontend/src/views/FilePreview.vue
git commit -m "Add Popo preview controls"
```

## Task 6: Compose, Env, and Deployment Docs

**Files:**
- Modify: `.env.example`
- Modify: `docker-compose.yml`
- Modify: `docker-compose.mac.yml`
- Create: `docker-compose.popo.yml`
- Modify: `docs/deployment.md`

- [ ] **Step 1: Add env defaults**

Append to `.env.example`:

```text
# MinerU-Popo 后处理：默认关闭
POPO_ENABLED=0
POPO_API_URL=http://popo-postprocessor:8010
POPO_TIMEOUT_SECONDS=1800
```

- [ ] **Step 2: Pass Popo env to worker**

Add these to worker environment in both compose files:

```yaml
- POPO_ENABLED=${POPO_ENABLED:-0}
- POPO_API_URL=${POPO_API_URL:-http://popo-postprocessor:8010}
- POPO_TIMEOUT_SECONDS=${POPO_TIMEOUT_SECONDS:-1800}
```

- [ ] **Step 3: Add optional Popo compose override**

Create `docker-compose.popo.yml`:

```yaml
services:
  popo-postprocessor:
    build:
      context: ./popo-postprocessor
    image: mineru-web-popo-postprocessor:local
    profiles:
      - popo
    ports:
      - "8010:8010"
    environment:
      - MINIO_ENDPOINT=${MINIO_ENDPOINT:?set MINIO_ENDPOINT}
      - MINIO_ACCESS_KEY=${MINIO_ACCESS_KEY:-minioadmin}
      - MINIO_SECRET_KEY=${MINIO_SECRET_KEY:-minioadmin}
      - POPO_MODEL_PATH=${POPO_MODEL_PATH:-/models/MinerU-Popo}
    volumes:
      - popo_models:/models
      - popo_workspace:/workspace
    networks:
      - mineru-network

volumes:
  popo_models:
  popo_workspace:

networks:
  mineru-network:
    external: false
```

- [ ] **Step 4: Update deployment docs**

In `docs/deployment.md`, add a `MinerU-Popo 后处理` section with:

```markdown
默认关闭：

```text
POPO_ENABLED=0
```

启用时：

```bash
docker compose --env-file .env -f docker-compose.yml -f docker-compose.popo.yml --profile popo up -d
```

Popo 作为独立服务运行，worker 只通过 `POPO_API_URL` 调用它。Popo 失败不会把文件解析状态改成失败。
```
```

- [ ] **Step 5: Validate compose**

Run:

```bash
MINIO_ENDPOINT=10.10.10.16:9000 docker compose -f docker-compose.yml config worker
MINIO_ENDPOINT=10.10.10.16:9000 docker compose -f docker-compose.mac.yml config worker
MINIO_ENDPOINT=10.10.10.16:9000 docker compose -f docker-compose.yml -f docker-compose.popo.yml --profile popo config popo-postprocessor
```

Expected: worker configs include `POPO_*`; Popo service config renders.

- [ ] **Step 6: Commit**

```bash
git add .env.example docker-compose.yml docker-compose.mac.yml docker-compose.popo.yml docs/deployment.md
git commit -m "Document Popo postprocessing deployment"
```

## Task 7: Final Verification

**Files:**
- No code changes unless verification exposes a defect.

- [ ] **Step 1: Run backend tests**

Run:

```bash
.venv/bin/pytest backend/tests -q
```

Expected: all backend tests pass.

- [ ] **Step 2: Run frontend build**

Run:

```bash
cd frontend
npm run build
```

Expected: frontend typecheck and build pass.

- [ ] **Step 3: Validate compose files**

Run:

```bash
MINIO_ENDPOINT=10.10.10.16:9000 docker compose -f docker-compose.yml config --quiet
MINIO_ENDPOINT=10.10.10.16:9000 docker compose -f docker-compose.mac.yml config --quiet
MINIO_ENDPOINT=10.10.10.16:9000 docker compose -f docker-compose.yml -f docker-compose.popo.yml --profile popo config --quiet
```

Expected: all commands exit 0.

- [ ] **Step 4: Update graphify**

Run:

```bash
graphify update .
```

Expected: graph updates successfully. If graphify refuses due node-count shrinkage, record the exact message in the final summary.

- [ ] **Step 5: Check worktree**

Run:

```bash
git status --short
```

Expected: clean worktree after all commits.

## Self-Review

- Spec coverage: independent Popo service is covered by Task 4 and Task 6; worker trigger by Task 1 and Task 2; MinIO artifact inputs and outputs by Task 1 and Task 4; backend preview/export/status by Task 3; frontend Popo display by Task 5; deployment and defaults by Task 6; verification by Task 7.
- No database schema change is planned, matching the spec's first-version scope.
- Historical data is not backfilled; Popo is only triggered for new parse completions.
- Popo failures are non-fatal in both client and parser tasks.
