import json
import traceback
from io import BytesIO
from fastapi import APIRouter, Query, HTTPException, Depends, Request
from sqlalchemy.orm import Session
from pathlib import Path
from app.database import get_db
from app.models.file import File as FileModel
from app.models.enums import FileStatus
from app.models.parsed_content import ParsedContent
from app.services.parser import ParserService, get_buckets
from app.utils.minio_client import get_presigned_url, minio_client
from app.utils.user_dep import get_user_id

router = APIRouter()


def _artifact_stem(file: FileModel) -> str:
    return Path(file.minio_path).stem


def _markdown_path_for_preview_variant(file: FileModel, variant: str) -> str:
    stem = _artifact_stem(file)
    if variant == "markdown":
        return f"{stem}.md"
    if variant == "markdown_page":
        return f"{stem}_pages.md"
    if variant == "popo":
        return f"{stem}_popo.md"
    raise HTTPException(status_code=400, detail="不支持的 Markdown 变体")


def _markdown_path_for_export_format(file: FileModel, format: str) -> str:
    stem = _artifact_stem(file)
    if format == "markdown":
        return f"{stem}.md"
    if format == "markdown_page":
        return f"{stem}_pages.md"
    if format == "markdown_popo":
        return f"{stem}_popo.md"
    raise HTTPException(status_code=400, detail="不支持的 Markdown 变体")


def _popo_status_path(file: FileModel) -> str:
    return f"{_artifact_stem(file)}_popo_status.json"


def _read_minio_object(bucket: str, path: str) -> bytes:
    response = minio_client.get_object(bucket, path)
    try:
        return response.read()
    finally:
        close = getattr(response, "close", None)
        if close:
            close()
        release_conn = getattr(response, "release_conn", None)
        if release_conn:
            release_conn()


@router.get("/files/{file_id}/parsed_content")
def get_parsed_content(
    file_id: int,
    variant: str = Query("markdown", description="markdown、markdown_page 或 popo"),
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db)
):
    # 检查文件是否存在
    file = db.query(FileModel).filter(FileModel.id == file_id, FileModel.user_id == user_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="文件不存在")

    if variant == "markdown":
        # 使用解析服务获取内容
        parser = ParserService(db)
        content = parser.get_parsed_content(file_id, user_id)
        return content

    output_path = _markdown_path_for_preview_variant(file, variant)
    buckets = get_buckets()
    mds_bucket = buckets[0]

    try:
        return _read_minio_object(mds_bucket, output_path).decode("utf-8")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="导出文件不存在")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/files/{file_id}/parse")
def parse_file(
    request: Request,
    file_id: int,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db)
):
    # 检查文件是否存在
    file = db.query(FileModel).filter(FileModel.id == file_id, FileModel.user_id == user_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="文件不存在")

    # 检查文件状态
    if file.status == FileStatus.PARSED:
        return {"msg": "文件已解析完成"}
    elif file.status == FileStatus.PARSING:
        return {"msg": "文件正在解析中"}

    try:
        # 执行解析
        parser = ParserService(db)
        result = parser.parse_file(file, user_id, predictor=request.app.state.predictor)

        return {
            "msg": "解析完成",
            "file_id": file_id,
            "details": result
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/files/{file_id}/parse/status")
def get_parse_status(
    file_id: int,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db)
):
    file = db.query(FileModel).filter(FileModel.id == file_id, FileModel.user_id == user_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="文件不存在")

    return {
        "file_id": file_id,
        "status": file.status.value,
        "message": {
            FileStatus.PENDING.value: "等待解析",
            FileStatus.PARSING.value: "正在解析",
            FileStatus.PARSED.value: "解析完成",
            FileStatus.PARSE_FAILED.value: "解析失败"
        }.get(file.status.value, "未知状态")
    }

@router.get("/files/{file_id}/export")
def export_content(
    file_id: int,
    format: str = Query('markdown', description="导出格式：markdown、markdown_page 或 markdown_popo"),
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db)
):
    """导出文件内容

    Args:
        file_id: 文件ID
        format: 导出格式，支持 markdown、markdown_page 和 markdown_popo
        user_id: 用户ID

    Returns:
        dict: 包含下载URL的响应
    """
    # 检查文件是否存在
    file = db.query(FileModel).filter(FileModel.id == file_id, FileModel.user_id == user_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="文件不存在")

    # 获取 MinIO bucket
    buckets = get_buckets()
    mds_bucket = buckets[0]  # markdown 文件存储的 bucket

    output_path = _markdown_path_for_export_format(file, format)

    # 检查文件是否存在于 MinIO
    try:
        minio_client.stat_object(mds_bucket, output_path)
    except Exception:
        if format != 'markdown':
            raise HTTPException(status_code=404, detail="导出文件不存在")

        parsed_content = db.query(ParsedContent).filter(
            ParsedContent.file_id == file_id,
            ParsedContent.user_id == user_id,
        ).first()
        if not parsed_content or not parsed_content.content:
            raise HTTPException(status_code=404, detail="导出文件不存在")

        content = parsed_content.content.encode("utf-8")
        minio_client.put_object(
            mds_bucket,
            output_path,
            BytesIO(content),
            len(content),
            content_type="text/markdown; charset=utf-8",
        )

    # 生成下载URL
    download_url = get_presigned_url(mds_bucket, output_path, expires=3600)

    # 构建下载文件名
    original_filename = Path(file.filename).stem
    if format == 'markdown_page':
        download_filename = f"{original_filename}_pages.md"
    elif format == 'markdown_popo':
        download_filename = f"{original_filename}_popo.md"
    else:
        download_filename = f"{original_filename}.md"

    return {
        "status": "success",
        "download_url": download_url,
        "filename": download_filename
    }


@router.get("/files/{file_id}/popo/status")
def get_popo_status(
    file_id: int,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    file = db.query(FileModel).filter(FileModel.id == file_id, FileModel.user_id == user_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="文件不存在")

    buckets = get_buckets()
    mds_bucket = buckets[0]

    try:
        content = _read_minio_object(mds_bucket, _popo_status_path(file)).decode("utf-8")
    except FileNotFoundError:
        return {"status": "not_available", "message": ""}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=str(e))
