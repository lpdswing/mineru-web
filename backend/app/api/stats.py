from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.stats import StatsService
from app.utils.user_dep import get_user_id

router = APIRouter()

@router.get("/stats")
def get_stats(
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db)
):
    """获取统计数据"""
    stats_service = StatsService(db)
    result = stats_service.get_stats()
    return result 