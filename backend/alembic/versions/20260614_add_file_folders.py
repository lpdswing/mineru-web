"""add file folders

Revision ID: 20260614_add_file_folders
Revises: 20260613_add_parse_progress_fields
Create Date: 2026-06-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260614_add_file_folders"
down_revision: Union[str, None] = "20260613_add_parse_progress_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "folders",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_folders_user_id"), "folders", ["user_id"], unique=False)
    op.create_index("idx_folder_user_name", "folders", ["user_id", "name"], unique=True)

    op.add_column("files", sa.Column("folder_id", sa.Integer(), nullable=True))
    op.create_index(op.f("ix_files_folder_id"), "files", ["folder_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_files_folder_id"), table_name="files")
    op.drop_column("files", "folder_id")
    op.drop_index("idx_folder_user_name", table_name="folders")
    op.drop_index(op.f("ix_folders_user_id"), table_name="folders")
    op.drop_table("folders")
