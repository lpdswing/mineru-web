"""add file error message

Revision ID: 9a4f2e8b6c31
Revises: 4ef1cec9a436
Create Date: 2026-06-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9a4f2e8b6c31"
down_revision: Union[str, None] = "4ef1cec9a436"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("files", sa.Column("error_message", sa.String(length=1024), nullable=True))


def downgrade() -> None:
    op.drop_column("files", "error_message")
