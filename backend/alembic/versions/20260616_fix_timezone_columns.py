"""fix timezone columns

Revision ID: 20260616_fix_timezone_columns
Revises: 20260615_parsed_versions
Create Date: 2026-08-28 22:10:00.000000

修复时区显示偏差（前端早 8 小时）：
1. files.upload_time 原先用 datetime.utcnow 写入 timestamp without time zone，
   值其实是 UTC 裸值，前端按本地时区解析导致早 8 小时。改为 timestamptz，
   并把存量 UTC 裸值按 UTC 解释（一次性校正）。
2. parsed_content_versions.created_at 存量因历史 utcnow 缺陷被多扣 8 小时，
   统一 +8h 补回。
"""
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260616_fix_timezone_columns"
down_revision: Union[str, None] = "20260615_parsed_versions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_offline() -> bool:
    """离线模式（--sql）下没有真实连接，查询 information_schema 会得到 None。"""
    return context.is_offline_mode()


def _column_data_type(bind, table: str, column: str) -> str | None:
    """读取 PG 列类型，用于幂等判断（SQLite 无 information_schema，调用方需先排除）。"""
    if _is_offline():
        return None
    row = bind.execute(
        sa.text(
            "SELECT data_type FROM information_schema.columns "
            f"WHERE table_name = '{table}' AND column_name = '{column}'"
        )
    ).first()
    return row[0] if row else None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        # SQLite 无原生时区语义，DateTime(timezone=True) 与无时区在 DDL 上等价，
        # 且该场景为全新初始化，无存量数据，跳过校正。
        return

    if _is_offline():
        # 离线模式（--sql）读不到列类型，直接输出原始语句，交由执行者按实际库状态确认
        op.execute(
            "ALTER TABLE files ALTER COLUMN upload_time "
            "TYPE timestamptz USING upload_time AT TIME ZONE 'UTC'"
        )
        op.execute(
            "UPDATE parsed_content_versions "
            "SET created_at = created_at + interval '8 hours'"
        )
        return

    # 1) upload_time: naive UTC -> timestamptz，存量按 UTC 解释（校正 +8h 偏差）。
    #    幂等：仅当列仍为 timestamp without time zone 才转换。若已通过
    #    create_all/手工 ALTER 变成 timestamptz，则跳过，避免二次偏移。
    if _column_data_type(bind, "files", "upload_time") == "timestamp without time zone":
        op.execute(
            "ALTER TABLE files ALTER COLUMN upload_time "
            "TYPE timestamptz USING upload_time AT TIME ZONE 'UTC'"
        )

    # 2) created_at 存量 +8h 补回（历史 utcnow 缺陷）。
    #    本表为本次 PR 新增、从未发布，全新库表空（无行可改）；仅开发期用
    #    datetime.utcnow 写入过数据的库需要校正。与 downgrade 的 -8h 严格互逆。
    op.execute(
        "UPDATE parsed_content_versions "
        "SET created_at = created_at + interval '8 hours'"
    )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return

    if _is_offline():
        op.execute(
            "UPDATE parsed_content_versions "
            "SET created_at = created_at - interval '8 hours'"
        )
        op.execute(
            "ALTER TABLE files ALTER COLUMN upload_time "
            "TYPE timestamp USING upload_time AT TIME ZONE 'UTC'"
        )
        return

    # 与 upgrade 严格互逆，使 downgrade -> upgrade 往返可重复执行而不叠加偏差。
    op.execute(
        "UPDATE parsed_content_versions "
        "SET created_at = created_at - interval '8 hours'"
    )

    if _column_data_type(bind, "files", "upload_time") == "timestamp with time zone":
        op.execute(
            "ALTER TABLE files ALTER COLUMN upload_time "
            "TYPE timestamp USING upload_time AT TIME ZONE 'UTC'"
        )
