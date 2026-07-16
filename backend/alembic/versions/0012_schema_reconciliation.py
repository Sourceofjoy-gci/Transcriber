"""Reconcile known schema drift in already-deployed databases.

Revision ID: 0012_schema_reconciliation
Revises: 0011_media_derivatives_retention
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0012_schema_reconciliation"
down_revision = "0011_media_derivatives_retention"
branch_labels = None
depends_on = None

ASSET_STATUS_LENGTH = 19


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _column(table_name: str, column_name: str) -> dict | None:
    return next(
        (
            column
            for column in _inspector().get_columns(table_name)
            if column["name"] == column_name
        ),
        None,
    )


def _require_tables(*table_names: str) -> None:
    existing = set(_inspector().get_table_names())
    missing = sorted(set(table_names) - existing)
    if missing:
        raise RuntimeError(
            "Cannot reconcile schema: required tables are missing: " + ", ".join(missing)
        )


def _ensure_foreign_key(
    table_name: str,
    column_name: str,
    referred_table: str,
    constraint_name: str,
) -> None:
    for foreign_key in _inspector().get_foreign_keys(table_name):
        if foreign_key["constrained_columns"] == [column_name] and foreign_key[
            "referred_table"
        ] == referred_table:
            return
    op.create_foreign_key(
        constraint_name,
        table_name,
        referred_table,
        [column_name],
        ["id"],
    )


def _ensure_required_uuid(
    table_name: str,
    column_name: str,
    update_statement: str,
    referred_table: str,
    constraint_name: str,
) -> None:
    column = _column(table_name, column_name)
    if column is None:
        op.add_column(
            table_name,
            sa.Column(column_name, postgresql.UUID(as_uuid=True), nullable=True),
        )
    op.get_bind().execute(sa.text(update_statement))
    missing_count = op.get_bind().scalar(
        sa.text(f"SELECT count(*) FROM {table_name} WHERE {column_name} IS NULL")
    )
    if missing_count:
        raise RuntimeError(
            f"Cannot reconcile schema safely: {table_name}.{column_name} cannot be "
            f"derived for {missing_count} row(s)"
        )
    column = _column(table_name, column_name)
    if column is not None and column["nullable"]:
        op.alter_column(
            table_name,
            column_name,
            existing_type=postgresql.UUID(as_uuid=True),
            nullable=False,
        )
    _ensure_foreign_key(table_name, column_name, referred_table, constraint_name)


def _reconcile_status_length() -> None:
    status_column = _column("media_assets", "status")
    if status_column is None:
        raise RuntimeError("Cannot reconcile schema: column media_assets.status is missing")
    column_type = status_column["type"]
    if not isinstance(column_type, sa.String) or column_type.length is None:
        raise RuntimeError("Cannot reconcile schema: media_assets.status is not a bounded string")
    current_length = column_type.length
    if current_length == ASSET_STATUS_LENGTH:
        return
    if current_length > ASSET_STATUS_LENGTH:
        raise RuntimeError(
            "Cannot reconcile schema safely: media_assets.status is wider than the canonical length 19"
        )
    op.alter_column(
        "media_assets",
        "status",
        existing_type=sa.String(length=current_length),
        type_=sa.String(length=ASSET_STATUS_LENGTH),
        existing_nullable=False,
    )


def _reconcile_tenant_columns() -> None:
    _ensure_required_uuid(
        "media_derivatives",
        "organisation_id",
        "UPDATE media_derivatives AS derivative "
        "SET organisation_id = asset.organisation_id "
        "FROM media_assets AS asset "
        "WHERE derivative.asset_id = asset.id AND derivative.organisation_id IS NULL",
        "organisations",
        "fk_media_derivatives_organisation_id",
    )
    _ensure_required_uuid(
        "transcripts",
        "organisation_id",
        "UPDATE transcripts AS transcript "
        "SET organisation_id = job.organisation_id "
        "FROM transcription_jobs AS job "
        "WHERE transcript.job_id = job.id AND transcript.organisation_id IS NULL",
        "organisations",
        "fk_transcripts_organisation_id",
    )
    version_tenant_join = (
        " FROM transcript_versions AS version "
        "JOIN transcripts AS transcript ON transcript.id = version.transcript_id "
        "JOIN transcription_jobs AS job ON job.id = transcript.job_id "
    )
    _ensure_required_uuid(
        "ai_processing_runs",
        "organisation_id",
        "UPDATE ai_processing_runs AS run SET organisation_id = job.organisation_id"
        + version_tenant_join
        + "WHERE run.transcript_version_id = version.id AND run.organisation_id IS NULL",
        "organisations",
        "fk_ai_processing_runs_organisation_id",
    )
    _ensure_required_uuid(
        "reports",
        "organisation_id",
        "UPDATE reports AS report SET organisation_id = job.organisation_id"
        + version_tenant_join
        + "WHERE report.transcript_version_id = version.id AND report.organisation_id IS NULL",
        "organisations",
        "fk_reports_organisation_id",
    )
    _ensure_required_uuid(
        "export_records",
        "organisation_id",
        "UPDATE export_records AS export SET organisation_id = job.organisation_id"
        + version_tenant_join
        + "WHERE export.transcript_version_id = version.id AND export.organisation_id IS NULL",
        "organisations",
        "fk_export_records_organisation_id",
    )


def _reconcile_editor_contract() -> None:
    operation_columns = {
        "transcript_id": postgresql.UUID(as_uuid=True),
        "from_version_id": postgresql.UUID(as_uuid=True),
        "to_version_id": postgresql.UUID(as_uuid=True),
        "segment_id": postgresql.UUID(as_uuid=True),
        "undone_at": sa.DateTime(timezone=True),
    }
    for column_name, column_type in operation_columns.items():
        if _column("transcript_edit_operations", column_name) is None:
            op.add_column(
                "transcript_edit_operations",
                sa.Column(column_name, column_type, nullable=True),
            )
    op.get_bind().execute(
        sa.text(
            "UPDATE transcript_edit_operations AS operation SET "
            "transcript_id = COALESCE(operation.transcript_id, version.transcript_id), "
            "from_version_id = COALESCE(operation.from_version_id, version.parent_version_id), "
            "to_version_id = COALESCE(operation.to_version_id, operation.version_id) "
            "FROM transcript_versions AS version "
            "WHERE operation.version_id = version.id"
        )
    )
    for column_name in ("transcript_id", "from_version_id", "to_version_id"):
        missing_count = op.get_bind().scalar(
            sa.text(
                f"SELECT count(*) FROM transcript_edit_operations WHERE {column_name} IS NULL"
            )
        )
        if missing_count:
            raise RuntimeError(
                "Cannot reconcile schema safely: transcript_edit_operations."
                f"{column_name} cannot be derived for {missing_count} row(s)"
            )
        column = _column("transcript_edit_operations", column_name)
        if column is not None and column["nullable"]:
            op.alter_column(
                "transcript_edit_operations",
                column_name,
                existing_type=postgresql.UUID(as_uuid=True),
                nullable=False,
            )
    version_column = _column("transcript_edit_operations", "version_id")
    if version_column is not None and not version_column["nullable"]:
        op.alter_column(
            "transcript_edit_operations",
            "version_id",
            existing_type=postgresql.UUID(as_uuid=True),
            nullable=True,
        )
    for column_name, referred_table in (
        ("transcript_id", "transcripts"),
        ("from_version_id", "transcript_versions"),
        ("to_version_id", "transcript_versions"),
        ("segment_id", "transcript_segments"),
    ):
        _ensure_foreign_key(
            "transcript_edit_operations",
            column_name,
            referred_table,
            f"fk_transcript_edit_operations_{column_name}",
        )

    annotation_columns = {
        "transcript_id": postgresql.UUID(as_uuid=True),
        "note": sa.Text(),
        "is_unclear": sa.Boolean(),
    }
    for column_name, column_type in annotation_columns.items():
        if _column("transcript_annotations", column_name) is None:
            op.add_column(
                "transcript_annotations",
                sa.Column(column_name, column_type, nullable=True),
            )
    op.get_bind().execute(
        sa.text(
            "UPDATE transcript_annotations AS annotation SET "
            "transcript_id = COALESCE(annotation.transcript_id, version.transcript_id), "
            "note = COALESCE(annotation.note, annotation.body), "
            "is_unclear = COALESCE(annotation.is_unclear, false) "
            "FROM transcript_versions AS version "
            "WHERE annotation.version_id = version.id"
        )
    )
    missing_count = op.get_bind().scalar(
        sa.text("SELECT count(*) FROM transcript_annotations WHERE transcript_id IS NULL")
    )
    if missing_count:
        raise RuntimeError(
            "Cannot reconcile schema safely: transcript_annotations.transcript_id cannot be "
            f"derived for {missing_count} row(s)"
        )
    transcript_column = _column("transcript_annotations", "transcript_id")
    if transcript_column is not None and transcript_column["nullable"]:
        op.alter_column(
            "transcript_annotations",
            "transcript_id",
            existing_type=postgresql.UUID(as_uuid=True),
            nullable=False,
        )
    kind_column = _column("transcript_annotations", "kind")
    if kind_column is not None and not kind_column["nullable"]:
        op.alter_column(
            "transcript_annotations",
            "kind",
            existing_type=sa.String(length=100),
            nullable=True,
        )
    _ensure_foreign_key(
        "transcript_annotations",
        "transcript_id",
        "transcripts",
        "fk_transcript_annotations_transcript_id",
    )


def _reconcile_report_template_optional() -> None:
    template_column = _column("reports", "template_id")
    if template_column is not None and not template_column["nullable"]:
        op.alter_column(
            "reports",
            "template_id",
            existing_type=postgresql.UUID(as_uuid=True),
            nullable=True,
        )


def _reconcile_media_metadata_probe() -> None:
    if _column("media_metadata", "raw_probe_json") is None:
        op.add_column(
            "media_metadata",
            sa.Column(
                "raw_probe_json",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'::json"),
            ),
        )
        op.alter_column("media_metadata", "raw_probe_json", server_default=None)


def _reconcile_job_cancellation() -> None:
    if _column("transcription_jobs", "cancel_requested_at") is None:
        op.add_column(
            "transcription_jobs",
            sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        )


def _reconcile_provider_cost_type() -> None:
    cost_column = _column("provider_usage_logs", "estimated_cost")
    if cost_column is None:
        raise RuntimeError(
            "Cannot reconcile schema: column provider_usage_logs.estimated_cost is missing"
        )
    column_type = cost_column["type"]
    if isinstance(column_type, sa.String):
        if column_type.length == 100:
            return
        if column_type.length is None or column_type.length > 100:
            raise RuntimeError(
                "Cannot reconcile schema safely: provider_usage_logs.estimated_cost has an "
                "unsupported string width"
            )
    op.alter_column(
        "provider_usage_logs",
        "estimated_cost",
        existing_type=column_type,
        type_=sa.String(length=100),
        existing_nullable=True,
        postgresql_using="estimated_cost::text",
    )


def _reconcile_audit_resource_ids() -> None:
    resource_column = _column("audit_logs", "resource_id")
    if resource_column is None:
        raise RuntimeError("Cannot reconcile schema: column audit_logs.resource_id is missing")
    column_type = resource_column["type"]
    if isinstance(column_type, postgresql.UUID):
        return
    if not isinstance(column_type, sa.String):
        raise RuntimeError(
            "Cannot reconcile schema safely: audit_logs.resource_id is neither UUID nor string"
        )
    invalid_count = op.get_bind().scalar(
        sa.text(
            "SELECT count(*) FROM audit_logs WHERE resource_id IS NOT NULL AND "
            "resource_id !~* "
            "'^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'"
        )
    )
    if invalid_count:
        raise RuntimeError(
            "Cannot reconcile schema safely: audit_logs.resource_id contains "
            f"{invalid_count} non-UUID value(s)"
        )
    op.alter_column(
        "audit_logs",
        "resource_id",
        existing_type=column_type,
        type_=postgresql.UUID(as_uuid=True),
        existing_nullable=True,
        postgresql_using="resource_id::uuid",
    )


def upgrade() -> None:
    _require_tables(
        "ai_processing_runs",
        "audit_logs",
        "export_records",
        "media_assets",
        "media_derivatives",
        "media_metadata",
        "organisations",
        "provider_usage_logs",
        "reports",
        "transcript_annotations",
        "transcript_edit_operations",
        "transcript_versions",
        "transcription_jobs",
        "transcripts",
    )
    _reconcile_status_length()
    _reconcile_tenant_columns()
    _reconcile_editor_contract()
    _reconcile_report_template_optional()
    _reconcile_media_metadata_probe()
    _reconcile_job_cancellation()
    _reconcile_provider_cost_type()
    _reconcile_audit_resource_ids()


def downgrade() -> None:
    return None
