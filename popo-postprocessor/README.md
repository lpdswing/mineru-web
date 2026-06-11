# MinerU-Popo Postprocessor

This service is an HTTP wrapper around
[opendatalab/MinerU-Popo](https://github.com/opendatalab/MinerU-Popo). It reads
MinerU artifacts from MinIO, lays them out in the directory structure expected by
MinerU-Popo, runs the Popo post-processing scripts, and writes Popo Markdown,
JSON, and status artifacts back to MinIO.

## API

- `GET /health` returns `{"status": "ok"}`.
- `POST /v1/postprocess` runs post-processing for one document.

Request body:

```json
{
  "bucket": "mineru",
  "prefix": "document-id",
  "artifacts": {
    "middle_json": "path/to/document-id_middle.json",
    "content_list_json": "path/to/document-id_content_list.json",
    "model_json": "path/to/document-id_model.json"
  },
  "outputs": {
    "json": "path/to/popo.json",
    "markdown": "path/to/popo.md",
    "status": "path/to/popo-status.json"
  }
}
```

## Configuration

Required environment variables:

- `MINIO_ENDPOINT`
- `MINIO_ACCESS_KEY`
- `MINIO_SECRET_KEY`
- `POPO_OPENAI_BASE_URL`

Optional environment variables:

- `MINIO_SECURE` controls TLS when `MINIO_ENDPOINT` has no scheme. Set to `true`
  to enable TLS.
- `POPO_REPO_DIR` defaults to `/opt/MinerU-Popo`.
- `POPO_WORKSPACE` defaults to `/workspace`.
- `POPO_ARTIFACT_ROOT` points to a read-only mounted MinerU output directory.
  Local files are used before falling back to MinIO.
- `POPO_OPENAI_BASE_URL`, `POPO_OPENAI_API_KEY`, and `POPO_OPENAI_MODEL`
  configure the OpenAI-compatible/vLLM endpoint used by upstream MinerU-Popo.

## Build Notes

The Dockerfile clones the upstream MinerU-Popo repository but does not install
its full requirements. The wrapper installs only the lightweight API path
dependencies and patches upstream `model_utils.py` to read Popo API settings
from environment variables.
