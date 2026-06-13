import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger
from sqlalchemy.orm import Session

from app.models.enums import FileStatus
from app.models.file import File as FileModel
from app.models.parsed_content import ParsedContent
from app.models.settings import Settings
from app.services.artifact_sync import MineruArtifactSync
from app.services.mineru_api import MineruApiClient
from app.services.popo import PopoPostprocessor
from app.utils.minio_client import MINIO_BUCKET, minio_client
from app.utils.redis_client import redis_client

PDF_EXTENSIONS = [".pdf"]
IMAGE_EXTENSIONS = [".png", ".jpeg", ".jp2", ".webp", ".gif", ".bmp", ".jpg", ".tiff"]
OFFICE_EXTENSIONS = [".docx", ".pptx", ".xlsx"]

PARSER_CHANNEL = "file_parser_tasks"
PARSER_STREAM = "file_parser_stream"
CONSUMER_GROUP = "parser_workers"


STAGE_PROGRESS = {
    "queued": 0,
    "fetching_source": 10,
    "submitting_mineru": 20,
    "waiting_mineru": 35,
    "downloading_result": 70,
    "syncing_artifacts": 85,
    "postprocessing_popo": 92,
    "completed": 100,
}


def read_config() -> dict[str, Any]:
    config_path = Path(os.getenv("MINERU_CONFIG_PATH", "/root/mineru.json"))
    if not config_path.exists():
        local_config = Path("mineru.json")
        if local_config.exists():
            config_path = local_config
    if not config_path.exists():
        return {}
    with config_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def get_s3_config(bucket: str) -> tuple[str, str, str]:
    config = read_config()
    bucket_info = config.get("bucket_info", {})
    values = bucket_info.get(bucket)
    if not values or len(values) < 3:
        endpoint = os.getenv("MINIO_ENDPOINT", "localhost:9000")
        if not endpoint.startswith(("http://", "https://")):
            endpoint = f"http://{endpoint}"
        return (
            os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
            os.getenv("MINIO_SECRET_KEY", "minioadmin"),
            endpoint,
        )
    return values[0], values[1], values[2]


def get_buckets() -> list[str]:
    config = read_config()
    bucket_info = config.get("bucket_info", {})
    if not bucket_info:
        return [os.getenv("MINIO_MDS_BUCKET", "mds")]
    return list(bucket_info.keys())


class ParserService:
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

    @staticmethod
    def _default_artifact_sync_factory(bucket: str) -> MineruArtifactSync:
        _, _, endpoint = get_s3_config(bucket)
        return MineruArtifactSync(
            minio_client,
            bucket=bucket,
            endpoint=endpoint,
            public_endpoint=endpoint,
        )

    @staticmethod
    def _clamp_progress(value: int | float | None) -> int | None:
        if value is None:
            return None
        try:
            number = int(value)
        except (TypeError, ValueError):
            return None
        return max(0, min(100, number))

    def _update_progress(
        self,
        file: FileModel,
        stage: str,
        message: str,
        percent: int | float | None = None,
        *,
        status: FileStatus | None = None,
        clear_mineru_task: bool = False,
    ) -> None:
        if status is not None:
            file.status = status
        file.parse_stage = stage
        progress = self._clamp_progress(percent if percent is not None else STAGE_PROGRESS.get(stage))
        if progress is not None:
            current = self._clamp_progress(getattr(file, "progress_percent", None))
            if current is not None and stage not in {"queued", "completed", "failed"}:
                progress = max(current, progress)
            file.progress_percent = progress
        file.progress_message = message[:255]
        file.last_heartbeat_at = datetime.now()
        if clear_mineru_task:
            file.mineru_task_id = None
            file.mineru_task_status = None
            file.mineru_task_payload = None
        self.db.commit()

    @staticmethod
    def _extract_upstream_progress(payload: dict[str, Any]) -> int | None:
        for key in ("progress", "percent", "percentage"):
            value = payload.get(key)
            if value is None:
                continue
            try:
                progress = float(value)
            except (TypeError, ValueError):
                continue
            if 0 <= progress <= 1:
                progress *= 100
            return max(0, min(100, int(progress)))
        return None

    @staticmethod
    def _progress_message_from_payload(status: str, payload: dict[str, Any]) -> str:
        for key in ("message", "msg", "detail", "stage"):
            value = payload.get(key)
            if value:
                return str(value)[:255]
        if status == "submitted":
            return "MinerU 任务已提交"
        return f"MinerU 状态: {status}"[:255]

    def _record_mineru_task_progress(self, file: FileModel, event: dict[str, Any]) -> None:
        try:
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            status = str(event.get("status") or payload.get("status") or "").lower() or None
            stage = str(event.get("stage") or "waiting_mineru")
            if stage not in STAGE_PROGRESS:
                stage = "waiting_mineru"
            message = str(event.get("message") or self._progress_message_from_payload(status or "unknown", payload))
            file.mineru_task_id = str(event.get("task_id") or payload.get("task_id") or payload.get("id") or "")
            file.mineru_task_status = status
            file.mineru_task_payload = json.dumps(payload, ensure_ascii=False)
            self._update_progress(
                file,
                stage,
                message,
                self._extract_upstream_progress(payload) or STAGE_PROGRESS[stage],
                status=FileStatus.PARSING,
            )
        except Exception as exc:
            logger.warning(f"Failed to persist MinerU task progress: {exc}")

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
        source_pdf_path: str,
        progress_callback=None,
        mineru_progress_callback=None,
    ) -> list[str]:
        if file_extension not in PDF_EXTENSIONS + IMAGE_EXTENSIONS + OFFICE_EXTENSIONS:
            raise ValueError(f"不支持的文件类型: {file_extension}")

        if progress_callback:
            progress_callback("submitting_mineru", "正在提交 MinerU 任务", STAGE_PROGRESS["submitting_mineru"])
        result = self.mineru_api_client.parse_file(
            filename=f"{file_name}{file_extension}",
            file_bytes=file_bytes,
            backend=backend,
            parse_method=parse_method,
            lang=lang,
            formula_enable=formula_enable,
            table_enable=table_enable,
            progress_callback=mineru_progress_callback,
        )
        if progress_callback:
            progress_callback("syncing_artifacts", "正在同步解析产物", STAGE_PROGRESS["syncing_artifacts"])
        artifact_sync = self.artifact_sync_factory(mds_bucket)
        synced = artifact_sync.sync_zip(result.content, output_name=file_name)
        try:
            if progress_callback and getattr(getattr(self.popo_postprocessor, "config", None), "enabled", False):
                progress_callback("postprocessing_popo", "正在执行 Popo 后处理", STAGE_PROGRESS["postprocessing_popo"])
            self.popo_postprocessor.postprocess(
                mds_bucket,
                file_name,
                synced.uploaded_paths,
                source_pdf_path=source_pdf_path,
                source_bucket=MINIO_BUCKET,
            )
        except Exception as exc:
            logger.warning(f"Popo postprocess skipped for {file_name}: {exc}")
        return [synced.markdown]

    def parse_file(self, file: FileModel, user_id: str, parse_method: str = "auto", predictor=None) -> dict[str, Any]:
        """同步解析文件。predictor 参数保留用于兼容旧调用方，当前通过 MinerU API sidecar 解析。"""
        try:
            user_settings = self.db.query(Settings).filter(Settings.user_id == user_id).first()
            if not user_settings:
                user_settings = Settings(
                    user_id=user_id,
                    force_ocr=False,
                    ocr_lang="ch",
                    formula_recognition=True,
                    table_recognition=True,
                )
            settings = user_settings.to_dict()
            logger.info(settings)
            if settings.get("force_ocr", False):
                parse_method = "ocr"

            backend = settings.get("backend", "pipeline")
            file.error_message = None
            file.start_at = datetime.now()
            self._update_progress(
                file,
                "fetching_source",
                "正在读取源文件",
                STAGE_PROGRESS["fetching_source"],
                status=FileStatus.PARSING,
            )

            response = minio_client.get_object(MINIO_BUCKET, file.minio_path)
            file_bytes = response.read()
            file_extension = Path(file.minio_path).suffix.lower()
            file_name_stem = Path(file.minio_path).stem

            buckets = get_buckets()
            mds_bucket = buckets[0]

            md_content_list = self.process_file(
                file_name_stem,
                file_bytes,
                file_extension,
                parse_method,
                settings.get("ocr_lang", "ch"),
                settings.get("formula_recognition", True),
                settings.get("table_recognition", True),
                backend=backend,
                mds_bucket=mds_bucket,
                source_pdf_path=file.minio_path,
                progress_callback=lambda stage, message, percent=None: self._update_progress(
                    file,
                    stage,
                    message,
                    percent,
                ),
                mineru_progress_callback=lambda event: self._record_mineru_task_progress(file, event),
            )

            parsed_content = ParsedContent(
                user_id=user_id,
                file_id=file.id,
                content=md_content_list[0],
            )
            self.db.add(parsed_content)

            file.error_message = None
            file.finish_at = datetime.now()
            self._update_progress(
                file,
                "completed",
                "解析完成",
                STAGE_PROGRESS["completed"],
                status=FileStatus.PARSED,
            )

            return {"status": "success"}

        except Exception as e:
            self.db.rollback()
            file.error_message = str(e)[:1024]
            self._update_progress(
                file,
                "failed",
                file.error_message,
                getattr(file, "progress_percent", None) or 0,
                status=FileStatus.PARSE_FAILED,
            )
            raise Exception(f"解析失败: {str(e)}")

    def get_parsed_content(self, file_id: int, user_id: str):
        query = self.db.query(ParsedContent).filter(
            ParsedContent.file_id == file_id,
            ParsedContent.user_id == user_id,
        )
        content_obj = query.first()
        return content_obj.content if content_obj else ""

    def queue_parse_file(self, file: FileModel, user_id: str, parse_method: str = "auto") -> dict[str, Any]:
        try:
            self._update_progress(
                file,
                "queued",
                "队列等待中",
                STAGE_PROGRESS["queued"],
                status=FileStatus.PENDING,
                clear_mineru_task=True,
            )

            task_data = {
                "file_id": file.id,
                "user_id": user_id,
                "parse_method": parse_method,
            }

            logger.info(f"Publishing task to stream {PARSER_STREAM}: {task_data}")
            redis_client.publish_task(PARSER_STREAM, task_data)

            return {
                "status": "queued",
                "message": "File parsing task has been queued",
                "file_id": file.id,
            }

        except Exception as e:
            self.db.rollback()
            file.status = FileStatus.PARSE_FAILED
            file.error_message = str(e)[:1024]
            self.db.commit()
            raise Exception(f"Failed to queue parsing task: {str(e)}")
