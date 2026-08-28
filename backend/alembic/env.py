from logging.config import fileConfig
import os

from sqlalchemy import engine_from_config, inspect
from sqlalchemy import pool
import sqlalchemy as sa

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config
database_url = os.getenv("DATABASE_URL")
if database_url:
    # 与 app/database.py 保持一致：postgres:// -> postgresql:// 并补默认驱动，
    # 保证迁移在 PostgreSQL 连接串下可直接运行。
    if database_url.startswith("postgres://"):
        database_url = "postgresql://" + database_url[len("postgres://"):]
    if database_url.split(":", 1)[0] == "postgresql":
        database_url = "postgresql+psycopg2://" + database_url[len("postgresql://"):]
    config.set_main_option("sqlalchemy.url", database_url)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
from app.models.base import Base
from app import models

target_metadata = Base.metadata

# 已发布 revision 的重命名映射（旧 ID -> 新 ID）。
# 背景：旧 ID 超过 Alembic 默认 alembic_version 表的 VARCHAR(32) 长度，在全新库上
# 会写入失败，故重命名为短 ID 属于修复。此处兼容极少数「手动建了 VARCHAR(255) 宽表
# 且恰好停靠在旧 ID」的历史库，将其版本号平移到新 ID，否则 alembic 会报
# ``Can't locate revision identified by '<old>'``。
_RENAMED_REVISIONS = {
    "20260613_add_parse_progress_fields": "20260613_parse_progress",
}


def _heal_renamed_revisions(connection) -> None:
    """在 run_migrations 之前，把停靠在旧 revision ID 的库平移到新 ID。"""
    inspector = inspect(connection)
    if not inspector.has_table("alembic_version"):
        return
    for old, new in _RENAMED_REVISIONS.items():
        connection.execute(
            sa.text(
                "UPDATE alembic_version SET version_num = :new "
                "WHERE version_num = :old"
            ),
            {"new": new, "old": old},
        )


# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            # 必须在事务内部执行：否则 heal 的 execute 会先开启隐式事务，
            # 使 begin_transaction 退化为 no-op，最终连接关闭时整体回滚。
            _heal_renamed_revisions(connection)
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
