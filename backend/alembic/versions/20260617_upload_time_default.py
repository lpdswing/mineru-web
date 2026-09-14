"""add upload_time database default

Revision ID: 20260617_upload_time_default
Revises: 20260616_fix_timezone_columns
Create Date: 2026-08-28 23:55:00.000000

files.upload_time 从「Python 端 default=datetime.utcnow」改为「server_default=func.now()」
时，20260616 只改了列类型、未补 DB DEFAULT，导致 ORM 插入省略该列后 DB 落 NULL。
本迁移：
1. 给 upload_time 补 DEFAULT now()（DB 层兜底）；
2. 用 created_at 回填存量 NULL（上传与建行几乎同时，created_at 最接近）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260617_upload_time_default"
down_revision: Union[str, None] = "20260616_fix_timezone_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("files") as batch_op:
            batch_op.alter_column(
                "upload_time",
                existing_type=sa.DateTime(timezone=True),
                existing_nullable=True,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            )
        op.execute(
            "UPDATE files SET upload_time = created_at WHERE upload_time IS NULL"
        )
        return

    op.execute("ALTER TABLE files ALTER COLUMN upload_time SET DEFAULT now()")
    op.execute(
        "UPDATE files SET upload_time = created_at WHERE upload_time IS NULL"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("files") as batch_op:
            batch_op.alter_column(
                "upload_time",
                existing_type=sa.DateTime(timezone=True),
                existing_nullable=True,
                server_default=None,
            )
        return

    op.execute("ALTER TABLE files ALTER COLUMN upload_time DROP DEFAULT")
