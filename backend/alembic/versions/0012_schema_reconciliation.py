"""Reconcile known schema drift in already-deployed databases.

Revision ID: 0012_schema_reconciliation
Revises: 0011_media_derivatives_retention
"""

import sqlalchemy as sa

from alembic import op

revision = "0012_schema_reconciliation"
down_revision = "0011_media_derivatives_retention"
branch_labels = None
depends_on = None

ASSET_STATUS_LENGTH = 19


def _status_length() -> int:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "media_assets" not in inspector.get_table_names():
        raise RuntimeError("Cannot reconcile schema: table media_assets is missing")
    status_column = next(
        (column for column in inspector.get_columns("media_assets") if column["name"] == "status"),
        None,
    )
    if status_column is None:
        raise RuntimeError("Cannot reconcile schema: column media_assets.status is missing")
    column_type = status_column["type"]
    if not isinstance(column_type, sa.String) or column_type.length is None:
        raise RuntimeError("Cannot reconcile schema: media_assets.status is not a bounded string")
    return column_type.length


def upgrade() -> None:
    current_length = _status_length()
    if current_length == ASSET_STATUS_LENGTH:
        return
    if current_length > ASSET_STATUS_LENGTH:
        raise RuntimeError(
            "Cannot reconcile schema safely: media_assets.status is wider than the canonical length 19"
        )
    with op.batch_alter_table("media_assets") as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=sa.String(length=current_length),
            type_=sa.String(length=ASSET_STATUS_LENGTH),
            existing_nullable=False,
        )


def downgrade() -> None:
    return None
