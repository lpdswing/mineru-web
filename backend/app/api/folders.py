from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.file import File as FileModel
from app.models.folder import Folder
from app.utils.user_dep import get_user_id


router = APIRouter()


class FolderPayload(BaseModel):
    name: str


def _clean_folder_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="文件夹名称不能为空")
    if len(cleaned) > 128:
        raise HTTPException(status_code=400, detail="文件夹名称不能超过128个字符")
    return cleaned


def _get_folder(folder_id: int, user_id: str, db: Session) -> Folder:
    folder = db.query(Folder).filter(Folder.id == folder_id, Folder.user_id == user_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="文件夹不存在")
    return folder


def _ensure_unique_name(name: str, user_id: str, db: Session, exclude_id: int | None = None) -> None:
    query = db.query(Folder).filter(Folder.user_id == user_id, Folder.name == name)
    if exclude_id is not None:
        query = query.filter(Folder.id != exclude_id)
    if query.first():
        raise HTTPException(status_code=409, detail="文件夹名称已存在")


@router.get("/folders")
def list_folders(
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    folders = db.query(Folder).filter(Folder.user_id == user_id).order_by(Folder.created_at.asc()).all()
    return {"folders": [folder.to_dict() for folder in folders]}


@router.post("/folders")
def create_folder(
    payload: FolderPayload,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    name = _clean_folder_name(payload.name)
    _ensure_unique_name(name, user_id, db)

    folder = Folder(user_id=user_id, name=name)
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return folder.to_dict()


@router.patch("/folders/{folder_id}")
def rename_folder(
    folder_id: int,
    payload: FolderPayload,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    folder = _get_folder(folder_id, user_id, db)
    name = _clean_folder_name(payload.name)
    _ensure_unique_name(name, user_id, db, exclude_id=folder_id)

    folder.name = name
    db.commit()
    db.refresh(folder)
    return folder.to_dict()


@router.delete("/folders/{folder_id}")
def delete_folder(
    folder_id: int,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    folder = _get_folder(folder_id, user_id, db)
    db.query(FileModel).filter(
        FileModel.user_id == user_id,
        FileModel.folder_id == folder_id,
    ).update({FileModel.folder_id: None})
    db.delete(folder)
    db.commit()
    return {"msg": "删除成功"}
