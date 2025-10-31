import traceback
import os
import uuid
from datetime import datetime
from typing import List
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.file import File as FileModel
from app.models.enums import FileStatus, BackendType as FileBackendType
from app.models.settings import Settings
from app.models.enums import SettingsBackendType
from app.utils.minio_client import upload_file
from app.utils.user_dep import get_user_id
from app.services.parser import ParserService

router = APIRouter()

@router.post("/upload")
async def upload_files(
    files: List[UploadFile] = File(...),
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db)
):
    results = []

    for file in files:
        try:
            # 生成唯一文件名
            ext = os.path.splitext(file.filename)[1]
            unique_filename = f"{uuid.uuid4()}{ext}"

            # 保存到 MinIO
            upload_file(
                file.file,
                unique_filename,
                file.content_type
            )

            # 获取用户设置并转换后端类型
            settings = db.query(Settings).filter(Settings.user_id == user_id).first()
            backend = FileBackendType.PIPELINE
            if settings and settings.backend:
                backend = settings.backend.to_file_backend()

            # 保存到数据库
            db_file = FileModel(
                user_id=user_id,
                filename=file.filename,
                size=file.size,
                status=FileStatus.PENDING,
                upload_time=datetime.utcnow(),
                minio_path=unique_filename,
                content_type=file.content_type,
                backend=backend
            )
            db.add(db_file)
            db.commit()
            db.refresh(db_file)

            # 将解析任务加入队列
            parser_service = ParserService(db)
            parser_service.queue_parse_file(db_file, user_id)

            results.append(db_file.to_dict())

        except Exception as e:
            db.rollback()
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"文件 {file.filename} 上传失败: {str(e)}")

    return {
        "total": len(results),
        "files": results
    } 