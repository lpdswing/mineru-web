from fastapi import APIRouter, Query, HTTPException, Depends
from sqlalchemy import or_
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.file import File as FileModel
from app.models.parsed_content import ParsedContent
from app.utils.minio_client import minio_client, MINIO_BUCKET
from app.utils.user_dep import get_user_id

router = APIRouter()

@router.get("/files")
def list_files(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str = Query('', description="按文件名搜索"),
    status: str = Query('', description="按状态筛选"),
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db)
):
    query = db.query(FileModel).filter(FileModel.user_id == user_id)
    if search:
        query = query.filter(FileModel.filename.contains(search))
    if status:
        query = query.filter(FileModel.status == status.upper())
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
        minio_client.remove_object(MINIO_BUCKET, file.minio_path)

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