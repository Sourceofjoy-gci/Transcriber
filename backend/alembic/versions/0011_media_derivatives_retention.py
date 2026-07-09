"""Add media derivatives and retention legal holds.

Revision ID: 0011_media_derivatives_retention
Revises: 0010_transcript_editor_ops
"""

from sqlalchemy import Column, DateTime, inspect

from alembic import op
from app.db.base import Base

revision = "0011_media_derivatives_retention"
down_revision = "0010_transcript_editor_ops"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("media_assets")}
    if "legal_hold_until" not in columns:
        with op.batch_alter_table("media_assets") as batch:
            batch.add_column(Column("legal_hold_until", DateTime(timezone=True), nullable=True))
    if "media_derivatives" not in inspector.get_table_names():
        Base.metadata.create_all(bind=bind, tables=[Base.metadata.tables["media_derivatives"]])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "media_derivatives" in inspector.get_table_names():
        Base.metadata.drop_all(bind=bind, tables=[Base.metadata.tables["media_derivatives"]])
    columns = {column["name"] for column in inspector.get_columns("media_assets")}
    if "legal_hold_until" in columns:
        with op.batch_alter_table("media_assets") as batch:
            batch.drop_column("legal_hold_until")
