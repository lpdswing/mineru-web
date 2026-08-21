"""
统一的数据库管理模块
提供数据库引擎、会话管理和依赖注入功能
"""
import os
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager


def _normalize_db_url(url: str) -> str:
    """
    归一化数据库连接串，使 SQLite / PostgreSQL 切换更"丝滑"：
    - 部分云厂商给的 postgres:// 规范为 postgresql://（SQLAlchemy 要求后者）
    - 对于裸 postgresql://（未指定驱动）自动补上 +psycopg2，避免用户漏写驱动而报错
    SQLite 及其它协议原样返回。
    """
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    scheme_prefix = url.split(":", 1)[0]
    if scheme_prefix == "postgresql":
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url


# 数据库配置
DATABASE_URL = _normalize_db_url(os.getenv('DATABASE_URL', 'sqlite:///./mineru.db'))

# 创建数据库引擎（整个应用共享一个实例）
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith('sqlite') else {},
    pool_pre_ping=True,  # 连接前检测连接是否有效
    pool_recycle=3600,   # 连接回收时间（秒）
)

# 创建会话工厂
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,  # 改为 False，避免不必要的数据库操作
    bind=engine
)


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI 依赖注入函数
    使用 yield 确保会话自动关闭

    用法：
        @router.get("/example")
        async def example(db: Session = Depends(get_db)):
            # 使用 db
            pass
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_context():
    """
    上下文管理器，用于非依赖注入场景

    用法：
        with get_db_context() as db:
            # 使用 db
            pass
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """初始化数据库（创建所有表）"""
    from app.models.base import Base
    Base.metadata.create_all(bind=engine)
