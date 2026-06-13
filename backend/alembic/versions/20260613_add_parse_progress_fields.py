"""add parse progress fields

Revision ID: 20260613_add_parse_progress_fields
Revises: 20260613_add_users
Create Date: 2026-06-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260613_add_parse_progress_fields"
down_revision: Union[str, None] = "20260613_add_users"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("files", sa.Column("parse_stage", sa.String(length=64), nullable=True))
    op.add_column("files", sa.Column("progress_percent", sa.Integer(), nullable=True))
    op.add_column("files", sa.Column("progress_message", sa.String(length=255), nullable=True))
    op.add_column("files", sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("files", sa.Column("mineru_task_id", sa.String(length=128), nullable=True))
    op.add_column("files", sa.Column("mineru_task_status", sa.String(length=64), nullable=True))
    op.add_column("files", sa.Column("mineru_task_payload", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("files", "mineru_task_payload")
    op.drop_column("files", "mineru_task_status")
    op.drop_column("files", "mineru_task_id")
    op.drop_column("files", "last_heartbeat_at")
    op.drop_column("files", "progress_message")
    op.drop_column("files", "progress_percent")
    op.drop_column("files", "parse_stage")
