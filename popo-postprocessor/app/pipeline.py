import io
import json
import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from minio import Minio

_MAX_STATUS_MESSAGE_LENGTH = 1024


def parse_minio_endpoint(endpoint: str) -> tuple[str, bool]:
    parsed = urlparse(endpoint)
    if parsed.scheme:
        return parsed.netloc, parsed.scheme == "https"
    return endpoint, os.getenv("MINIO_SECURE", "false").lower() == "true"


class PopoPipeline:
    def __init__(self) -> None:
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

    def run(self, request) -> dict[str, str]:
        job_dir = self.build_job_dir(request.prefix)

        try:
            self.write_status(request.bucket, request.outputs["status"], "processing", "")
            if job_dir.exists():
                shutil.rmtree(job_dir)

            vlm_dir = job_dir / "post-process" / "mineru" / request.prefix / "vlm"
            vlm_dir.mkdir(parents=True, exist_ok=True)

            self.download_artifact(
                request.bucket,
                request.artifacts["middle_json"],
                vlm_dir / f"{request.prefix}_middle.json",
            )
            self.download_artifact(
                request.bucket,
                request.artifacts["content_list_json"],
                vlm_dir / f"{request.prefix}_content_list.json",
            )
            self.download_artifact(
                request.bucket,
                request.artifacts["model_json"],
                vlm_dir / f"{request.prefix}_model.json",
            )

            self.run_popo_commands(job_dir, request.prefix)

            json_path = job_dir / "outputs" / "build_tree" / "mineru" / f"{request.prefix}.json"
            markdown_path = (
                job_dir / "outputs" / "build_tree_txt" / "mineru" / f"{request.prefix}.txt"
            )

            self.upload_file(
                request.bucket,
                request.outputs["json"],
                json_path,
                "application/json",
            )
            self.upload_file(
                request.bucket,
                request.outputs["markdown"],
                markdown_path,
                "text/markdown; charset=utf-8",
            )
            self.write_status(request.bucket, request.outputs["status"], "success", "")
        except Exception as exc:
            message = str(exc)[:_MAX_STATUS_MESSAGE_LENGTH]
            try:
                self.write_status(request.bucket, request.outputs["status"], "failed", message)
            except Exception:
                pass
            raise

        return {
            "status": "success",
            "markdown_path": request.outputs["markdown"],
            "json_path": request.outputs["json"],
        }

    def build_job_dir(self, prefix: str) -> Path:
        prefix_path = Path(prefix)
        if not prefix or prefix_path.is_absolute() or any(part in {"", ".."} for part in prefix_path.parts):
            raise ValueError("Invalid Popo prefix")
        if len(prefix_path.parts) != 1:
            raise ValueError("Invalid Popo prefix")

        workspace = self.workspace.resolve()
        job_dir = (workspace / prefix).resolve()
        if job_dir == workspace or workspace not in job_dir.parents:
            raise ValueError("Invalid Popo prefix")
        return job_dir

    def download_artifact(self, bucket: str, object_name: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        response = self.minio.get_object(bucket, object_name)
        try:
            with destination.open("wb") as output:
                for chunk in response.stream(32 * 1024):
                    output.write(chunk)
        finally:
            response.close()
            response.release_conn()

    def upload_file(
        self,
        bucket: str,
        object_name: str,
        source: Path,
        content_type: str,
    ) -> None:
        self.minio.fput_object(
            bucket,
            object_name,
            str(source),
            content_type=content_type,
        )

    def write_status(self, bucket: str, object_name: str, status: str, message: str) -> None:
        payload = json.dumps({"status": status, "message": message}, ensure_ascii=False).encode("utf-8")
        self.minio.put_object(
            bucket,
            object_name,
            data=io.BytesIO(payload),
            length=len(payload),
            content_type="application/json",
        )

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
