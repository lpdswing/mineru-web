from fastapi import APIRouter, HTTPException, Depends, Body
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.settings import Settings
from app.models.enums import SettingsBackendType
from app.utils.user_dep import get_user_id

router = APIRouter()

@router.get("/settings")
def get_settings(
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db)
):
    settings = db.query(Settings).filter(Settings.user_id == user_id).first()

    if not settings:
        settings = Settings(
            user_id=user_id,
            ocr_lang="ch",
            force_ocr=False,
            table_recognition=True,
            formula_recognition=True,
            backend=SettingsBackendType.PIPELINE
        )

    result = settings.to_dict()
    return result

@router.put("/settings")
def update_settings(
    settings: dict = Body(...),
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db)
):
    db_settings = db.query(Settings).filter(Settings.user_id == user_id).first()
    if not db_settings:
        db_settings = Settings(user_id=user_id)
        db.add(db_settings)

    for key, value in settings.items():
        if hasattr(db_settings, key):
            if key == "backend":
                try:
                    setattr(db_settings, key, SettingsBackendType(value))  # 字符串转 Enum
                except ValueError:
                    raise HTTPException(status_code=400, detail=f"Invalid backend type: {value}")
            else:
                setattr(db_settings, key, value)

    db.commit()
    db.refresh(db_settings)
    return db_settings.to_dict()
