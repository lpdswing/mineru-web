from fastapi import APIRouter, Depends
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from ..services.stats import StatsService
from ..utils.user_dep import get_user_id
import os

router = APIRouter()

DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./mineru.db')
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=True, bind=engine)

@router.get("/stats")
def get_stats(user_id: str = Depends(get_user_id)):
    """获取统计数据"""
    db = SessionLocal()
    stats_service = StatsService(db)
    result = stats_service.get_stats()
    db.close()
    return result 