import io
import json
import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_ARTIFACT_SUFFIXES = {
    "_middle.json": "middle_json",
    "_content_list.json": "content_list_json",
    "_model.json": "model_json",
}


def parse_popo_enabled(value: str | None = None) -> bool:
    if value is None:
        value = os.getenv("POPO_ENABLED")
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


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
    for path in uploaded_paths:
        for suffix, name in _ARTIFACT_SUFFIXES.items():
            if path.endswith(suffix):
                artifacts[name] = path
                break
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
        minio: Any | None = None,
        http_client: httpx.Client | None = None,
    ):
        self.config = config or PopoConfig.from_env()
        self.minio = minio
        self._http_client = http_client

    def postprocess(
        self,
        bucket: str,
        prefix: str,
        uploaded_paths: list[str],
        source_pdf_path: str | None = None,
        source_bucket: str | None = None,
    ) -> None:
        if not self.config.enabled:
            return

        outputs = build_popo_outputs(prefix)
        artifacts = discover_popo_artifacts(uploaded_paths)
        if source_pdf_path:
            artifacts["source_pdf"] = source_pdf_path
        missing = [name for name in _required_artifacts() if name not in artifacts]
        if missing:
            self._write_status_best_effort(
                bucket,
                outputs["status"],
                "skipped",
                f"Missing Popo artifacts: {', '.join(missing)}",
            )
            return

        payload = {
            "bucket": bucket,
            "source_bucket": source_bucket or bucket,
            "prefix": prefix,
            "artifacts": artifacts,
            "outputs": outputs,
        }

        try:
            response = self._client().post(f"{self.config.api_url}/v1/postprocess", json=payload)
            response.raise_for_status()
        except Exception as exc:
            message = str(exc)[:1024]
            logger.warning("Popo postprocess failed: %s", message)
            self._write_status_best_effort(bucket, outputs["status"], "failed", message)

    def write_status(self, bucket: str, path: str, status: str, message: str = "") -> None:
        if not self.minio:
            return

        content = json.dumps(
            {"status": status, "message": message},
            ensure_ascii=False,
        ).encode("utf-8")
        self.minio.put_object(
            bucket,
            path,
            io.BytesIO(content),
            len(content),
            content_type="application/json",
        )

    def _write_status_best_effort(self, bucket: str, path: str, status: str, message: str = "") -> None:
        try:
            self.write_status(bucket, path, status, message)
        except Exception as exc:
            logger.warning("Popo status write failed: %s", str(exc)[:1024])

    def _client(self) -> httpx.Client:
        if self._http_client is None:
            self._http_client = httpx.Client(timeout=self.config.timeout_seconds)
        return self._http_client


def _required_artifacts() -> list[str]:
    return ["middle_json", "content_list_json", "model_json", "source_pdf"]
