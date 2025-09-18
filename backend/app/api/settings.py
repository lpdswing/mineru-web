from fastapi import APIRouter, HTTPException, Depends, Body
from app.models.settings import Settings, BackendType
from app.utils.user_dep import get_user_id
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os

router = APIRouter()

DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./mineru.db')
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=True, bind=engine)

@router.get("/settings")
def get_settings(user_id: str = Depends(get_user_id)):
    db = SessionLocal()
    settings = db.query(Settings).filter(Settings.user_id == user_id).first()

    if not settings:
        settings = Settings(
            user_id=user_id,
            ocr_lang="ch",
            force_ocr=False,
            table_recognition=True,
            formula_recognition=True,
            backend=BackendType.PIPELINE
        )
    
    result = settings.to_dict()
    db.close()
    return result

@router.put("/settings")
def update_settings(
    settings: dict = Body(...),
    user_id: str = Depends(get_user_id)
):
    db = SessionLocal()
    db_settings = db.query(Settings).filter(Settings.user_id == user_id).first()
    if not db_settings:
        db_settings = Settings(user_id=user_id)
        db.add(db_settings)

    for key, value in settings.items():
        if hasattr(db_settings, key):
            if key == "backend":
                try:
                    setattr(db_settings, key, BackendType(value))  # 字符串转 Enum
                except ValueError:
                    db.close()
                    raise HTTPException(status_code=400, detail=f"Invalid backend type: {value}")
            else:
                setattr(db_settings, key, value)
    
    db.commit()
    db.refresh(db_settings)
    db.close()
    return db_settings.to_dict()
