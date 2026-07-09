"""Tests that the eight required report templates are seeded."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.domain import ReportTemplate
from app.services.report_templates import TEMPLATES, seed_report_templates


def _session() -> Session:
    from sqlalchemy import create_engine

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_seed_creates_all_required_kinds() -> None:
    session = _session()
    seed_report_templates(session)
    kinds = {row.kind for row in session.scalars(select(ReportTemplate))}
    expected = {entry["kind"] for entry in TEMPLATES}
    assert expected.issubset(kinds)


def test_seed_is_idempotent() -> None:
    session = _session()
    seed_report_templates(session)
    seed_report_templates(session)
    rows = list(session.scalars(select(ReportTemplate)))
    assert len(rows) == len(TEMPLATES)


def test_templates_include_all_required_sections() -> None:
    required = {
        "presentation",
        "meeting",
        "workshop",
        "benchmarking",
        "training",
        "legal_policy",
        "technical_demo",
        "project_implementation",
    }
    assert {entry["kind"] for entry in TEMPLATES} == required
