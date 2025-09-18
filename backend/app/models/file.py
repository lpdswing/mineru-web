from sqlalchemy import Column, Integer, String, DateTime, Enum
from sqlalchemy.sql import func
from app.models.base import Base
from datetime import datetime
import enum

class FileStatus(enum.Enum):
    PENDING = 'pending'
    PARSING = 'parsing'
    PARSED = 'parsed'
    PARSE_FAILED = 'parse_failed'

class BackendType(enum.Enum):
    PIPELINE = 'pipeline'
    VLM = 'vlm'

class File(Base):
    __tablename__ = 'files'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True)
    filename = Column(String(256), nullable=False)
    size = Column(Integer, nullable=False)
    status = Column(Enum(FileStatus), default=FileStatus.PENDING)
    upload_time = Column(DateTime, default=datetime.utcnow)
    minio_path = Column(String(512), nullable=False)
    content_type = Column(String(64), nullable=True)
    version = Column(String(32), nullable=True)
    backend = Column(Enum(BackendType), default=BackendType.PIPELINE)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    start_at = Column(DateTime(timezone=True), nullable=True)
    finish_at = Column(DateTime(timezone=True), nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'filename': self.filename,
            'size': self.size,
            'status': self.status.value if self.status else None,
            'upload_time': self.upload_time.isoformat() if self.upload_time else None,
            'minio_path': self.minio_path,
            'content_type': self.content_type,
            'version': self.version,
            'backend': self.backend.value if self.backend else BackendType.PIPELINE.value,
            'start_at': self.start_at.isoformat() if self.start_at else None,
            'finish_at': self.finish_at.isoformat() if self.finish_at else None
        }