import json
import re
import traceback
from io import BytesIO
from typing import Any
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

try:
    from minio.error import S3Error
except ImportError:
    S3Error = None

router = APIRouter()

_MINIO_MISSING_ERROR_CODES = {"NoSuchKey", "NoSuchObject", "NoSuchBucket", "NotFound"}


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


def _middle_json_candidates(file: FileModel) -> list[str]:
    stem = _artifact_stem(file)
    return [
        f"{stem}/{stem}_middle.json",
        f"{stem}/auto/{stem}_middle.json",
        f"{stem}_middle.json",
    ]


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


def _is_missing_object_error(exc: Exception) -> bool:
    if isinstance(exc, FileNotFoundError):
        return True
    if S3Error and isinstance(exc, S3Error):
        return exc.code in _MINIO_MISSING_ERROR_CODES
    return False


def _coerce_number(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return value
    if isinstance(value, str):
        try:
            number = float(value)
        except ValueError:
            return None
        if number.is_integer():
            return int(number)
        return number
    return None


def _flatten_numbers(value: Any) -> list[int | float]:
    if isinstance(value, list | tuple):
        numbers: list[int | float] = []
        for item in value:
            numbers.extend(_flatten_numbers(item))
        return numbers
    number = _coerce_number(value)
    return [number] if number is not None else []


def _normalize_bbox(value: Any) -> list[int | float] | None:
    numbers = _flatten_numbers(value)
    if len(numbers) == 4:
        return numbers
    if len(numbers) >= 8 and len(numbers) % 2 == 0:
        xs = numbers[0::2]
        ys = numbers[1::2]
        return [min(xs), min(ys), max(xs), max(ys)]
    return None


def _extract_bbox(item: dict[str, Any]) -> list[int | float] | None:
    for key in ("bbox", "layout_bbox", "line_bbox", "span_bbox", "poly"):
        bbox = _normalize_bbox(item.get(key))
        if bbox:
            return bbox
    return None


def _clean_source_text(value: Any) -> str:
    text = str(value)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _join_source_text(parts: list[str]) -> str:
    seen = set()
    unique_parts = []
    for part in parts:
        if part and part not in seen:
            seen.add(part)
            unique_parts.append(part)
    return " ".join(unique_parts).strip()


def _extract_text(value: Any) -> str:
    if isinstance(value, str):
        return _clean_source_text(value)
    if isinstance(value, list):
        return _join_source_text([_extract_text(item) for item in value])
    if not isinstance(value, dict):
        return ""

    parts = []
    for key in ("text", "content"):
        item = value.get(key)
        if isinstance(item, str):
            parts.append(_clean_source_text(item))
        elif isinstance(item, dict | list):
            parts.append(_extract_text(item))
    if parts:
        return _join_source_text(parts)

    for key in ("spans", "lines", "blocks"):
        item = value.get(key)
        if isinstance(item, dict | list):
            parts.append(_extract_text(item))
    return _join_source_text(parts)


def _extract_block_type(item: dict[str, Any]) -> str:
    for key in ("type", "block_type", "category_type", "sub_type"):
        value = item.get(key)
        if value:
            return str(value)
    return "block"


def _page_index(page_info: dict[str, Any], fallback_index: int) -> int:
    page_idx = _coerce_number(page_info.get("page_idx"))
    return int(page_idx) if page_idx is not None else fallback_index


def _page_dimensions(page_info: dict[str, Any]) -> tuple[int | float | None, int | float | None]:
    size = page_info.get("page_size") or page_info.get("size")
    if isinstance(size, dict):
        return _coerce_number(size.get("width")), _coerce_number(size.get("height"))
    numbers = _flatten_numbers(size)
    if len(numbers) >= 2:
        return numbers[0], numbers[1]

    width = (
        _coerce_number(page_info.get("width"))
        or _coerce_number(page_info.get("page_width"))
        or _coerce_number(page_info.get("w"))
    )
    height = (
        _coerce_number(page_info.get("height"))
        or _coerce_number(page_info.get("page_height"))
        or _coerce_number(page_info.get("h"))
    )
    return width, height


def _collect_source_blocks(value: Any, page_number: int, blocks: list[dict[str, Any]], seen: set[tuple]) -> None:
    if isinstance(value, list):
        for item in value:
            _collect_source_blocks(item, page_number, blocks, seen)
        return
    if not isinstance(value, dict):
        return

    bbox = _extract_bbox(value)
    text = _extract_text(value)
    block_type = _extract_block_type(value)
    if bbox and text:
        bounded_text = text[:1200]
        key = (tuple(bbox), bounded_text, block_type)
        if key not in seen:
            seen.add(key)
            blocks.append(
                {
                    "id": f"p{page_number}-b{len(blocks) + 1}",
                    "type": block_type,
                    "text": bounded_text,
                    "bbox": bbox,
                }
            )
        return

    for item in value.values():
        if isinstance(item, dict | list):
            _collect_source_blocks(item, page_number, blocks, seen)


def _normalize_source_map(middle_json: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    pdf_info = middle_json.get("pdf_info")
    if not isinstance(pdf_info, list):
        return {"pages": []}

    pages = []
    for index, page_info in enumerate(pdf_info):
        if not isinstance(page_info, dict):
            continue
        page_idx = _page_index(page_info, index)
        page_number = page_idx + 1
        width, height = _page_dimensions(page_info)
        blocks: list[dict[str, Any]] = []
        _collect_source_blocks(page_info, page_number, blocks, set())
        pages.append(
            {
                "page": page_number,
                "page_idx": page_idx,
                "width": width,
                "height": height,
                "blocks": blocks,
            }
        )
    return {"pages": pages}


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
    except Exception as e:
        if _is_missing_object_error(e):
            raise HTTPException(status_code=404, detail="导出文件不存在")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/files/{file_id}/source_map")
def get_source_map(
    file_id: int,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    file = db.query(FileModel).filter(FileModel.id == file_id, FileModel.user_id == user_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="文件不存在")

    buckets = get_buckets()
    mds_bucket = buckets[0]

    content = None
    for path in _middle_json_candidates(file):
        try:
            content = _read_minio_object(mds_bucket, path)
            break
        except Exception as e:
            if _is_missing_object_error(e):
                continue
            raise HTTPException(status_code=500, detail=str(e))

    if content is None:
        return {"pages": []}

    try:
        middle_json = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not isinstance(middle_json, dict):
        return {"pages": []}
    return _normalize_source_map(middle_json)

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
    except Exception as e:
        if not _is_missing_object_error(e):
            raise HTTPException(status_code=500, detail=str(e))
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
    except Exception as e:
        if _is_missing_object_error(e):
            return {"status": "not_available", "message": ""}
        raise HTTPException(status_code=500, detail=str(e))

    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=str(e))
