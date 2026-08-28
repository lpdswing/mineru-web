from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
from ..models.file import File

# 业务展示按北京时间（东八区）统计，避免依赖数据库会话时区
CN_TZ = timezone(timedelta(hours=8))

class StatsService:
    def __init__(self, db: Session):
        self.db = db

    def get_stats(self, user_id: str) -> dict:
        """获取统计数据"""
        # 计算总文件数
        user_files = self.db.query(File).filter(File.user_id == user_id)
        total_files = user_files.count()

        # 计算今日上传数（按北京时间零点，aware 比较）
        today_start = datetime.combine(
            datetime.now(CN_TZ).date(), datetime.min.time(), tzinfo=CN_TZ
        )
        today_uploads = user_files.filter(
            File.upload_time >= today_start
        ).count()

        # 计算已用空间（MB）
        used_space = user_files.with_entities(
            func.sum(File.size)
        ).scalar() or 0
        used_space = round(used_space / (1024 * 1024), 2)  # 转换为MB

        return {
            'totalFiles': total_files,
            'todayUploads': today_uploads,
            'usedSpace': used_space
        } 
