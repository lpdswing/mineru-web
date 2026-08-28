import difflib
import json
import re
import time
import traceback
from datetime import datetime
from io import BytesIO
from typing import Any
from fastapi import APIRouter, Query, HTTPException, Depends, Request
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from pathlib import Path
from app.database import get_db
from app.models.file import File as FileModel
from app.models.enums import FileStatus
from app.models.parsed_content import ParsedContent
from app.models.parsed_content_version import ParsedContentVersion
from app.services.parser import ParserService, get_buckets
from app.utils.minio_client import get_presigned_url, minio_client
from app.utils.user_dep import get_user_id

try:
    from minio.error import S3Error
except ImportError:
    S3Error = None

router = APIRouter()

_MINIO_MISSING_ERROR_CODES = {"NoSuchKey", "NoSuchObject", "NoSuchBucket", "NotFound"}


def _artifact_stem_from_path(minio_path: str) -> str:
    return Path(minio_path).stem


def _artifact_stem(file: FileModel) -> str:
    return _artifact_stem_from_path(file.minio_path)


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


def _popo_tree_path(file: FileModel) -> str:
    return f"{_artifact_stem(file)}_popo.json"


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


def _source_text_signature(text: str) -> str:
    return re.sub(r"[^\w]+", "", text, flags=re.UNICODE).lower()


def _merge_duplicate_source_block(
    blocks: list[dict[str, Any]],
    bbox: list[int | float],
    block_type: str,
    text: str,
) -> bool:
    text_signature = _source_text_signature(text)
    if not text_signature:
        return False

    for block in blocks:
        if block.get("type") != block_type or block.get("bbox") != bbox:
            continue

        existing_text = str(block.get("text") or "")
        existing_signature = _source_text_signature(existing_text)
        if not existing_signature:
            continue
        if text_signature not in existing_signature and existing_signature not in text_signature:
            continue

        if len(text_signature) > len(existing_signature):
            block["text"] = text
        return True
    return False


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
        if _merge_duplicate_source_block(blocks, bbox, block_type, bounded_text):
            return
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

    payload = None
    raw_payload = getattr(file, "mineru_task_payload", None)
    if raw_payload:
        try:
            payload = json.loads(raw_payload)
        except (TypeError, ValueError):
            payload = None

    result = {
        "file_id": file_id,
        "status": file.status.value,
        "message": {
            FileStatus.PENDING.value: "等待解析",
            FileStatus.PARSING.value: "正在解析",
            FileStatus.PARSED.value: "解析完成",
            FileStatus.PARSE_FAILED.value: "解析失败"
        }.get(file.status.value, "未知状态"),
        "parse_stage": getattr(file, "parse_stage", None),
        "progress_percent": getattr(file, "progress_percent", None),
        "progress_message": getattr(file, "progress_message", None),
        "last_heartbeat_at": file.last_heartbeat_at.isoformat() if getattr(file, "last_heartbeat_at", None) else None,
        "mineru_task_id": getattr(file, "mineru_task_id", None),
        "mineru_task_status": getattr(file, "mineru_task_status", None),
    }
    if payload is not None:
        result["mineru_task_payload"] = payload
    return result

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
        # 对象本应存在却缺失，说明对象存储侧出过问题，记一条告警便于排查
        logger.warning(f"[export] file={file_id} 对象 {output_path} 缺失，已由数据库内容重建")

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


@router.get("/files/{file_id}/popo/tree")
def get_popo_tree(
    file_id: int,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """返回 Popo 后处理生成的文档结构树（{stem}_popo.json）。"""
    file = db.query(FileModel).filter(FileModel.id == file_id, FileModel.user_id == user_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="文件不存在")

    buckets = get_buckets()
    mds_bucket = buckets[0]

    try:
        content = _read_minio_object(mds_bucket, _popo_tree_path(file)).decode("utf-8")
    except Exception as e:
        if _is_missing_object_error(e):
            raise HTTPException(status_code=404, detail="Popo 结构树不存在")
        raise HTTPException(status_code=500, detail=str(e))

    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ 识别结果 Markdown 手动编辑 / 历史版本 / 恢复 ============

class SaveParsedContentRequest(BaseModel):
    content: str
    note: str | None = Field(default=None, max_length=255)


def _get_versioned_file(db: Session, file_id: int, user_id: str) -> tuple[FileModel, ParsedContent]:
    """校验文件可编辑并返回 (file, parsed_content)。"""
    file = db.query(FileModel).filter(FileModel.id == file_id, FileModel.user_id == user_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="文件不存在")
    if file.status != FileStatus.PARSED:
        raise HTTPException(status_code=400, detail="文件尚未解析完成，无法编辑")
    pc = db.query(ParsedContent).filter(
        ParsedContent.file_id == file_id,
        ParsedContent.user_id == user_id,
    ).first()
    if not pc:
        raise HTTPException(status_code=404, detail="识别结果不存在")
    return file, pc


_MAX_VERSION_RETRIES = 3


def _lock_file_row(db: Session, file_id: int) -> None:
    """串行化同一文件的版本写入。

    PostgreSQL 走 SELECT ... FOR UPDATE 行锁；SQLite 的 dialect 会静默忽略该子句
    （不报错），降级为「整库写锁 + busy_timeout」串行，对本场景已足够。
    """
    db.query(FileModel.id).filter(FileModel.id == file_id).with_for_update().first()


def _ensure_initial_version(db: Session, file_id: int, user_id: str) -> None:
    """惰性补建 v1（原始解析结果快照），不改动解析链路。

    供只读接口（历史列表）调用，自身是一个独立小事务。
    """
    for attempt in range(_MAX_VERSION_RETRIES):
        try:
            file = db.query(FileModel).filter(
                FileModel.id == file_id, FileModel.user_id == user_id
            ).first()
            if not file or file.status != FileStatus.PARSED:
                return
            pc = db.query(ParsedContent).filter(
                ParsedContent.file_id == file_id,
                ParsedContent.user_id == user_id,
            ).first()
            if not pc:
                return

            _lock_file_row(db, file.id)

            exists = db.query(ParsedContentVersion.id).filter(
                ParsedContentVersion.file_id == file.id
            ).first()
            if exists:
                db.commit()  # 无改动，仅释放行锁
                return
            db.add(ParsedContentVersion(
                user_id=pc.user_id,
                file_id=file.id,
                version=1,
                content=pc.content or "",
                source='parse',
            ))
            db.commit()
            return
        except HTTPException:
            raise
        except IntegrityError:
            db.rollback()  # session 内对象全部 expire，下一轮重新查询
            time.sleep(0.05 * (attempt + 1))
    raise HTTPException(status_code=503, detail="版本初始化冲突，请重试")


def _commit_new_version(
    db: Session,
    file_id: int,
    user_id: str,
    content: str,
    source: str,
    note: str | None,
) -> tuple[int, int]:
    """单一事务完成「惰性补 v1 + 追加新版本 + 更新 parsed_contents」，只 commit 一次。

    版本记录与当前内容必须在同一事务内落库，否则第二次提交失败时会出现
    「最新版本已存在但 parsed_contents 仍是旧值」，历史列表的 is_current 也会标错。

    唯一约束冲突时重试**整个事务**，而不是只重试单条版本插入。

    Returns:
        (max_version, new_version)；new_version 为 0 表示内容未变化、未生成新版本。
    """
    for attempt in range(_MAX_VERSION_RETRIES):
        try:
            file = db.query(FileModel).filter(
                FileModel.id == file_id, FileModel.user_id == user_id
            ).first()
            if not file:
                raise HTTPException(status_code=404, detail="文件不存在")
            if file.status != FileStatus.PARSED:
                raise HTTPException(status_code=400, detail="文件尚未解析完成，无法编辑")
            pc = db.query(ParsedContent).filter(
                ParsedContent.file_id == file_id,
                ParsedContent.user_id == user_id,
            ).first()
            if not pc:
                raise HTTPException(status_code=404, detail="识别结果不存在")

            _lock_file_row(db, file.id)

            row = db.query(ParsedContentVersion.version).filter(
                ParsedContentVersion.file_id == file.id
            ).order_by(ParsedContentVersion.version.desc()).limit(1).first()
            max_version = row[0] if row else 0

            if max_version == 0:
                # 惰性补 v1；空内容也是合法快照，保证空识别结果同样可进入历史
                db.add(ParsedContentVersion(
                    user_id=pc.user_id,
                    file_id=file.id,
                    version=1,
                    content=pc.content or "",
                    source='parse',
                ))
                max_version = 1

            new_version = 0
            if content != pc.content:
                new_version = max_version + 1
                db.add(ParsedContentVersion(
                    user_id=file.user_id,
                    file_id=file.id,
                    version=new_version,
                    content=content,
                    source=source,
                    note=note,
                ))
                pc.content = content
                max_version = new_version

            db.commit()
            return max_version, new_version

        except HTTPException:
            db.rollback()
            raise
        except IntegrityError:
            db.rollback()
            time.sleep(0.05 * (attempt + 1))

    raise HTTPException(status_code=503, detail="版本写入冲突，请重试")


def _ensure_minio_markdown(file: FileModel, content: str) -> bool:
    """确保 MinIO 的 {stem}.md 与 content 一致；已一致则跳过 PUT。

    Returns:
        True 表示执行了 PUT；False 表示对象已一致（跳过写）。
    """
    path = f"{_artifact_stem(file)}.md"
    mds_bucket = get_buckets()[0]
    data = content.encode("utf-8")
    try:
        resp = minio_client.get_object(mds_bucket, path)
        try:
            existing = resp.read()
        finally:
            resp.close()
            resp.release_conn()
        if existing == data:
            return False
    except Exception as e:
        # 对象不存在时落到下面的 PUT（重建/自愈）；真实故障则上抛，由调用方降级处理
        if not _is_missing_object_error(e):
            raise
    minio_client.put_object(
        mds_bucket,
        path,
        BytesIO(data),
        len(data),
        content_type="text/markdown; charset=utf-8",
    )
    return True


# 与前端 parseMarkdownPages 的 /^#\s+Page\s+(\d+)\s*$/gim 保持一致
_PAGE_MARKER_RE = re.compile(r'^#\s+Page\s+\d+\s*$')


def _is_page_marker_line(line: str) -> bool:
    return bool(_PAGE_MARKER_RE.match(line.rstrip('\r\n')))


def _apply_plain_to_pages(old_pages: str, new_plain: str) -> str:
    """把编辑后的普通 Markdown 应用到分页产物上，保留 # Page N 标记位置。

    做法：old_pages 去掉标记行后作为旧文本，与 new_plain 做行级 diff；
    equal 段保留原行，非 equal 段替换/插入/删除为新行，标记行原样保留。
    这样溯源视图（markdown_page）能显示编辑后的内容，且 PDF↔Markdown
    分页同步不受影响。

    追加/插入的内容归属到「插入点之后的标记所在页」，页级归属可能有
    一页的偏差（追加文本的归属本身就有歧义），可接受。
    """
    pages_lines = old_pages.splitlines(keepends=True)
    old_plain_lines = [l for l in pages_lines if not _is_page_marker_line(l)]
    new_plain_lines = new_plain.splitlines(keepends=True)

    sm = difflib.SequenceMatcher(a=old_plain_lines, b=new_plain_lines, autojunk=False)
    inserts: dict[int, list[str]] = {}
    skip: set[int] = set()
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            continue
        if tag in ('insert', 'replace'):
            inserts[i1] = new_plain_lines[j1:j2]
        if tag in ('delete', 'replace'):
            skip.update(range(i1, i2))

    out: list[str] = []
    oi = 0
    for line in pages_lines:
        if _is_page_marker_line(line):
            out.append(line)
            continue
        if oi in inserts:
            out.extend(inserts.pop(oi))
        if oi in skip:
            oi += 1
            continue
        out.append(line)
        oi += 1
    # 末尾追加（i1 == len(old_plain_lines)）的插入在所有行之后补上
    for i1 in sorted(inserts):
        out.extend(inserts[i1])
    return ''.join(out)


def _sync_pages_markdown(file: FileModel, content: str, old_content: str | None = None) -> bool:
    """把编辑后的内容同步进 {stem}_pages.md（保留分页标记）；已一致或对象不存在则跳过。

    对齐校验（防「正文本身含 # Page N 字样」被误当标记）：
    a) pages 去掉标记行后 == 编辑前内容 → 标记是解析期插入的，走 diff 应用；
    b) pages 与编辑前内容完全相同 → 无分页结构（如 test.pdf），直接整篇覆盖；
    c) 都不满足（pages 陈旧/结构未知）→ 退化 diff，尽力同步。

    Returns:
        True 表示执行了 PUT；False 表示跳过（无对象/内容已一致）。
    """
    path = f"{_artifact_stem(file)}_pages.md"
    mds_bucket = get_buckets()[0]
    try:
        resp = minio_client.get_object(mds_bucket, path)
        try:
            existing = resp.read().decode("utf-8", errors="replace")
        finally:
            resp.close()
            resp.release_conn()
    except Exception as e:
        # 分页产物不存在（非 PDF / 早期解析）就不生成，保持原状
        if _is_missing_object_error(e):
            return False
        raise

    if old_content is not None:
        pages_minus_markers = "".join(
            l for l in existing.splitlines(keepends=True) if not _is_page_marker_line(l)
        )
        if pages_minus_markers == old_content:
            # 正常路径：标记结构可信
            new_pages = _apply_plain_to_pages(existing, content)
        elif existing == old_content:
            # 无分页结构（或标记即正文），直接覆盖为新内容
            new_pages = content
        else:
            # pages 与 DB 脱节（如历史同步失败），盲 diff 兜底
            new_pages = _apply_plain_to_pages(existing, content)
    else:
        new_pages = _apply_plain_to_pages(existing, content)

    if new_pages == existing:
        return False

    data = new_pages.encode("utf-8")
    minio_client.put_object(
        mds_bucket,
        path,
        BytesIO(data),
        len(data),
        content_type="text/markdown; charset=utf-8",
    )
    return True


def _sync_minio_after_commit(
    file: FileModel, content: str, old_content: str | None = None
) -> tuple[bool, str | None]:
    """提交后同步对象存储；失败只降级不抛异常（数据库已提交，是权威数据源）。

    同步两处：{stem}.md（普通 Markdown）与 {stem}_pages.md（分页溯源产物，
    保留 # Page N 结构地应用编辑）。{stem}_popo.md 及其余产物始终不动。

    Returns:
        (synced, sync_error)
    """
    errors: list[str] = []
    try:
        _ensure_minio_markdown(file, content)
    except Exception as e:
        logger.error(f"[parsed_content] file={file.id} 同步 {_artifact_stem(file)}.md 失败: {e}")
        errors.append(f"markdown: {e}")
    try:
        _sync_pages_markdown(file, content, old_content)
    except Exception as e:
        logger.error(f"[parsed_content] file={file.id} 同步 {_artifact_stem(file)}_pages.md 失败: {e}")
        errors.append(f"pages: {e}")
    if errors:
        return False, "; ".join(errors)
    return True, None


@router.put("/files/{file_id}/parsed_content")
def save_parsed_content(
    file_id: int,
    body: SaveParsedContentRequest,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """手动编辑并保存识别结果 Markdown；内容变化时生成一个新版本快照。

    数据库是权威数据源：即使对象存储同步失败也返回 200，由 synced 标志区分。
    """
    file, pc = _get_versioned_file(db, file_id, user_id)
    old_content = pc.content or ""
    content = body.content or ""
    max_version, new_version = _commit_new_version(
        db, file_id, user_id, content, "save", body.note
    )
    synced, sync_error = _sync_minio_after_commit(file, content, old_content)
    return {
        "changed": new_version > 0,
        "version": new_version or max_version,
        "synced": synced,
        "sync_error": sync_error,
    }


@router.get("/files/{file_id}/parsed_content/versions")
def list_parsed_content_versions(
    file_id: int,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """返回该文件的编辑历史版本列表（按版本号倒序）。"""
    _get_versioned_file(db, file_id, user_id)
    _ensure_initial_version(db, file_id, user_id)

    versions = db.query(ParsedContentVersion).filter(
        ParsedContentVersion.file_id == file_id,
        ParsedContentVersion.user_id == user_id,
    ).order_by(ParsedContentVersion.version.desc()).all()

    # 已按版本号倒序，首条即当前版本
    max_version = versions[0].version if versions else 0
    return [
        {**v.to_dict(), "is_current": v.version == max_version}
        for v in versions
    ]


@router.get("/files/{file_id}/parsed_content/versions/{version_id}")
def get_parsed_content_version(
    file_id: int,
    version_id: int,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """返回单个历史版本的完整内容（含 markdown 快照）。"""
    file, _ = _get_versioned_file(db, file_id, user_id)
    version_obj = db.query(ParsedContentVersion).filter(
        ParsedContentVersion.id == version_id,
        ParsedContentVersion.file_id == file_id,
        ParsedContentVersion.user_id == user_id,
    ).first()
    if not version_obj:
        raise HTTPException(status_code=404, detail="版本不存在")
    return version_obj.to_detail()


@router.post("/files/{file_id}/parsed_content/versions/{version_id}/restore")
def restore_parsed_content_version(
    file_id: int,
    version_id: int,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """恢复到指定历史版本。

    恢复动作本身会新增一条内容为目标版本的记录（source='restore'）；被覆盖的当前
    内容不会单独快照，但它仍保留在其原有历史版本中，可通过再次恢复来撤销本次恢复。
    """
    file, pc = _get_versioned_file(db, file_id, user_id)
    _ensure_initial_version(db, file_id, user_id)

    target = db.query(ParsedContentVersion).filter(
        ParsedContentVersion.id == version_id,
        ParsedContentVersion.file_id == file_id,
        ParsedContentVersion.user_id == user_id,
    ).first()
    if not target:
        raise HTTPException(status_code=404, detail="版本不存在")

    old_content = pc.content or ""
    max_version, new_version = _commit_new_version(
        db, file_id, user_id, target.content, "restore", f"恢复自 v{target.version}"
    )
    synced, sync_error = _sync_minio_after_commit(file, target.content, old_content)
    return {
        "restored": new_version > 0,
        "version": new_version or max_version,
        "synced": synced,
        "sync_error": sync_error,
    }
