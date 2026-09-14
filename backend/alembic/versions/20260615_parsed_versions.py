"""add parsed content versions

Revision ID: 20260615_parsed_versions
Revises: 20260614_add_file_folders
Create Date: 2026-08-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260615_parsed_versions"
down_revision: Union[str, None] = "20260614_add_file_folders"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "parsed_content_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("file_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("file_id", "version", name="uq_parsed_content_version_file_version"),
    )
    op.create_index(op.f("ix_parsed_content_versions_user_id"), "parsed_content_versions", ["user_id"], unique=False)
    op.create_index(op.f("ix_parsed_content_versions_file_id"), "parsed_content_versions", ["file_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_parsed_content_versions_file_id"), table_name="parsed_content_versions")
    op.drop_index(op.f("ix_parsed_content_versions_user_id"), table_name="parsed_content_versions")
    op.drop_table("parsed_content_versions")
