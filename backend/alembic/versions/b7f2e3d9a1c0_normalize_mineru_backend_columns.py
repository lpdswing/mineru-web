"""normalize mineru backend columns

Revision ID: b7f2e3d9a1c0
Revises: 9a4f2e8b6c31
Create Date: 2026-06-08 21:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7f2e3d9a1c0"
down_revision: Union[str, None] = "9a4f2e8b6c31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


LEGACY_BACKEND_SQL = """
CASE backend
    WHEN 'PIPELINE' THEN 'pipeline'
    WHEN 'VLM' THEN 'vlm'
    WHEN 'HYBRID' THEN 'hybrid'
    WHEN 'VLM_TRANSFORMERS' THEN 'vlm-auto-engine'
    WHEN 'VLM_SGLANG_ENGINE' THEN 'vlm-auto-engine'
    WHEN 'VLM_SGLANG_CLIENT' THEN 'vlm-http-client'
    WHEN 'VLM_AUTO_ENGINE' THEN 'vlm-auto-engine'
    WHEN 'VLM_HTTP_CLIENT' THEN 'vlm-http-client'
    WHEN 'HYBRID_AUTO_ENGINE' THEN 'hybrid-auto-engine'
    WHEN 'HYBRID_HTTP_CLIENT' THEN 'hybrid-http-client'
    ELSE backend
END
"""


def _alter_backend_column(table_name: str) -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.alter_column(
                "backend",
                existing_type=sa.String(),
                type_=sa.String(length=64),
                existing_nullable=True,
            )
    else:
        op.alter_column(
            table_name,
            "backend",
            existing_type=sa.String(),
            type_=sa.String(length=64),
            existing_nullable=True,
            postgresql_using="backend::text",
        )


def upgrade() -> None:
    _alter_backend_column("files")
    _alter_backend_column("settings")
    op.execute(f"UPDATE files SET backend = {LEGACY_BACKEND_SQL} WHERE backend IS NOT NULL")
    op.execute(f"UPDATE settings SET backend = {LEGACY_BACKEND_SQL} WHERE backend IS NOT NULL")


def downgrade() -> None:
    pass
