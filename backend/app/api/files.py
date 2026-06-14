import mimetypes
import os
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Query, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.file import File as FileModel
from app.models.folder import Folder
from app.models.parsed_content import ParsedContent
from app.utils.minio_client import minio_client, MINIO_BUCKET
from app.utils.user_dep import get_user_id

try:
    from minio.error import S3Error
except ImportError:
    S3Error = None

router = APIRouter()
MINIO_MDS_BUCKET = os.getenv("MINIO_MDS_BUCKET", "mds")
_MINIO_MISSING_ERROR_CODES = {"NoSuchKey", "NoSuchObject", "NoSuchBucket", "NotFound"}


class FileFolderPayload(BaseModel):
    folder_id: int | None = None


def _artifact_stem(file: FileModel) -> str:
    return Path(file.minio_path).stem


def _parsed_artifact_paths(file: FileModel) -> list[str]:
    stem = _artifact_stem(file)
    return [
        f"{stem}.md",
        f"{stem}_pages.md",
        f"{stem}_popo.md",
        f"{stem}_popo_status.json",
        f"{stem}_middle.json",
    ]


def _is_missing_minio_error(exc: Exception) -> bool:
    if isinstance(exc, FileNotFoundError):
        return True
    if S3Error and isinstance(exc, S3Error):
        return exc.code in _MINIO_MISSING_ERROR_CODES
    return False


def _remove_minio_object(bucket: str, path: str) -> None:
    try:
        minio_client.remove_object(bucket, path)
    except Exception as exc:
        if _is_missing_minio_error(exc):
            return
        raise


def _remove_minio_prefix(bucket: str, prefix: str) -> None:
    try:
        for obj in minio_client.list_objects(bucket, prefix=prefix, recursive=True):
            _remove_minio_object(bucket, obj.object_name)
    except Exception as exc:
        if _is_missing_minio_error(exc):
            return
        raise


def _remove_parsed_artifacts(file: FileModel) -> None:
    for path in _parsed_artifact_paths(file):
        _remove_minio_object(MINIO_MDS_BUCKET, path)

    prefix = f"{_artifact_stem(file)}/"
    _remove_minio_prefix(MINIO_MDS_BUCKET, prefix)


@router.get("/files")
def list_files(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str = Query('', description="按文件名搜索"),
    status: str = Query('', description="按状态筛选"),
    folder_id: str = Query('', description="按文件夹筛选，none 表示未分类"),
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db)
):
    query = db.query(FileModel).filter(FileModel.user_id == user_id)
    if search:
        query = query.filter(FileModel.filename.contains(search))
    if status:
        query = query.filter(FileModel.status == status.upper())
    if folder_id == "none":
        query = query.filter(FileModel.folder_id.is_(None))
    elif folder_id:
        try:
            query = query.filter(FileModel.folder_id == int(folder_id))
        except ValueError:
            raise HTTPException(status_code=400, detail="文件夹参数无效")
    total = query.count()
    files = query.order_by(FileModel.upload_time.desc()) \
        .offset((page-1)*page_size).limit(page_size).all()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "files": [f.to_dict() for f in files]
    }

@router.get("/files/{file_id}")
def file_detail(
    file_id: int,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db)
):
    file = db.query(FileModel).filter(FileModel.id == file_id, FileModel.user_id == user_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="文件不存在")
    return file.to_dict()

@router.get("/files/{file_id}/download_url")
def file_download_url(
    file_id: int,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db)
):
    file = db.query(FileModel).filter(FileModel.id == file_id, FileModel.user_id == user_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="文件不存在")
    from app.utils.minio_client import get_file_url
    url = get_file_url(file.minio_path)
    return {"url": url}


@router.get("/files/{file_id}/content")
def file_content(
    file_id: int,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    file = db.query(FileModel).filter(FileModel.id == file_id, FileModel.user_id == user_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="文件不存在")

    try:
        response = minio_client.get_object(MINIO_BUCKET, file.minio_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取文件失败: {str(e)}")

    def iter_file():
        try:
            stream = getattr(response, "stream", None)
            if stream:
                yield from stream(32 * 1024)
            else:
                yield response.read()
        finally:
            close = getattr(response, "close", None)
            if close:
                close()
            release_conn = getattr(response, "release_conn", None)
            if release_conn:
                release_conn()

    content_type = (
        getattr(response, "headers", {}).get("Content-Type")
        or mimetypes.guess_type(file.filename)[0]
        or "application/octet-stream"
    )
    encoded_filename = quote(file.filename)
    return StreamingResponse(
        iter_file(),
        media_type=content_type,
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{encoded_filename}"},
    )


@router.patch("/files/{file_id}/folder")
def move_file_to_folder(
    file_id: int,
    payload: FileFolderPayload,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    file = db.query(FileModel).filter(FileModel.id == file_id, FileModel.user_id == user_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="文件不存在")

    if payload.folder_id is not None:
        folder = db.query(Folder).filter(Folder.id == payload.folder_id, Folder.user_id == user_id).first()
        if not folder:
            raise HTTPException(status_code=404, detail="文件夹不存在")

    file.folder_id = payload.folder_id
    db.commit()
    db.refresh(file)
    return file.to_dict()

@router.delete("/files/{file_id}")
def delete_file(
    file_id: int,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db)
):
    file = db.query(FileModel).filter(FileModel.id == file_id, FileModel.user_id == user_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="文件不存在")

    try:
        # 删除 MinIO 对象
        _remove_minio_object(MINIO_BUCKET, file.minio_path)
        _remove_parsed_artifacts(file)

        # 删除解析内容
        db.query(ParsedContent).filter(
            ParsedContent.file_id == file_id,
            ParsedContent.user_id == user_id
        ).delete()

        # 删除文件记录
        db.delete(file)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")

    return {"msg": "删除成功"}
