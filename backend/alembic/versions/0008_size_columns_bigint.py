"""Widen byte_size and size_bytes columns to BigInteger.

Revision ID: 0008_size_columns_bigint
Revises: 0007_reports
Create Date: 2026-06-25

The original schema declared these columns as Integer, which overflows for
recordings or model archives larger than 2 GiB. Production deployments need
to store values up to several gigabytes.
"""

import sqlalchemy as sa

from alembic import op

revision = "0008_size_columns_bigint"
down_revision = "0007_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("media_assets") as batch_op:
        batch_op.alter_column(
            "byte_size",
            existing_type=sa.Integer(),
            type_=sa.BigInteger(),
            existing_nullable=False,
        )
    with op.batch_alter_table("model_catalog") as batch_op:
        batch_op.alter_column(
            "size_bytes",
            existing_type=sa.Integer(),
            type_=sa.BigInteger(),
            existing_nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("model_catalog") as batch_op:
        batch_op.alter_column(
            "size_bytes",
            existing_type=sa.BigInteger(),
            type_=sa.Integer(),
            existing_nullable=True,
        )
    with op.batch_alter_table("media_assets") as batch_op:
        batch_op.alter_column(
            "byte_size",
            existing_type=sa.BigInteger(),
            type_=sa.Integer(),
            existing_nullable=False,
        )
