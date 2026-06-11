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
- `POPO_MODEL_PATH`

Optional environment variables:

- `MINIO_SECURE` controls TLS when `MINIO_ENDPOINT` has no scheme. Set to `true`
  to enable TLS.
- `POPO_REPO_DIR` defaults to `/opt/MinerU-Popo`.
- `POPO_WORKSPACE` defaults to `/workspace`.

## Build Notes

The Dockerfile clones the upstream MinerU-Popo repository and installs its
requirements. It adjusts the upstream `click==8.3.1` pin to `click==8.2.1`
because `ray==2.52.1` excludes the `8.3.*` click series.
