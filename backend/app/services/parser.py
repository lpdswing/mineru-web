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
    ) -> list[str]:
        if file_extension not in PDF_EXTENSIONS + IMAGE_EXTENSIONS + OFFICE_EXTENSIONS:
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
        try:
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
            file.status = FileStatus.PARSING
            file.error_message = None
            file.start_at = datetime.now()
            self.db.commit()

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
            )

            parsed_content = ParsedContent(
                user_id=user_id,
                file_id=file.id,
                content=md_content_list[0],
            )
            self.db.add(parsed_content)

            file.status = FileStatus.PARSED
            file.error_message = None
            file.finish_at = datetime.now()
            self.db.commit()

            return {"status": "success"}

        except Exception as e:
            self.db.rollback()
            file.status = FileStatus.PARSE_FAILED
            file.error_message = str(e)[:1024]
            self.db.commit()
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
            file.status = FileStatus.PENDING
            self.db.commit()

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
