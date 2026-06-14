from sqlalchemy import Column, DateTime, Integer, String, Index
from sqlalchemy.sql import func

from app.models.base import Base


class Folder(Base):
    __tablename__ = 'folders'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index('idx_folder_user_name', 'user_id', 'name', unique=True),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'name': self.name,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
