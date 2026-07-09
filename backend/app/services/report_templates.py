"""Seed the eight required report templates on startup."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.domain import ReportTemplate

TEMPLATES: list[dict] = [
    {
        "kind": "presentation",
        "name": "General presentation report",
        "schema": {
            "sections": [
                "Executive summary",
                "Background",
                "Objectives",
                "Topics discussed",
                "Key findings",
                "Recommendations",
                "Conclusion",
            ],
        },
        "prompt_template": "Compose a presentation report from the supplied transcript.",
    },
    {
        "kind": "meeting",
        "name": "Meeting minutes",
        "schema": {
            "sections": [
                "Executive summary",
                "Attendees",
                "Topics discussed",
                "Decisions",
                "Action items",
                "Follow-up questions",
                "Conclusion",
            ],
        },
        "prompt_template": "Compose meeting minutes from the supplied transcript.",
    },
    {
        "kind": "workshop",
        "name": "Workshop report",
        "schema": {
            "sections": [
                "Executive summary",
                "Background",
                "Topics discussed",
                "Key findings",
                "Lessons learnt",
                "Recommendations",
                "Appendices",
            ],
        },
        "prompt_template": "Compose a workshop report from the supplied transcript.",
    },
    {
        "kind": "benchmarking",
        "name": "Benchmarking report",
        "schema": {
            "sections": [
                "Executive summary",
                "Background",
                "Objectives",
                "Topics discussed",
                "Key findings",
                "Risks",
                "Opportunities",
                "Recommendations",
            ],
        },
        "prompt_template": "Compose a benchmarking report from the supplied transcript.",
    },
    {
        "kind": "training",
        "name": "Training report",
        "schema": {
            "sections": [
                "Executive summary",
                "Background",
                "Objectives",
                "Topics discussed",
                "Lessons learnt",
                "Recommendations",
                "Action plan",
                "Conclusion",
            ],
        },
        "prompt_template": "Compose a training report from the supplied transcript.",
    },
    {
        "kind": "legal_policy",
        "name": "Legal or policy discussion report",
        "schema": {
            "sections": [
                "Executive summary",
                "Background",
                "Topics discussed",
                "Key findings",
                "Risks",
                "Challenges",
                "Recommendations",
                "Conclusion",
            ],
        },
        "prompt_template": "Compose a legal/policy report from the supplied transcript.",
    },
    {
        "kind": "technical_demo",
        "name": "Technical demonstration report",
        "schema": {
            "sections": [
                "Executive summary",
                "Background",
                "Objectives",
                "Topics discussed",
                "Key findings",
                "Lessons learnt",
                "Risks",
                "Recommendations",
                "Appendices",
            ],
        },
        "prompt_template": "Compose a technical demonstration report from the supplied transcript.",
    },
    {
        "kind": "project_implementation",
        "name": "Project implementation report",
        "schema": {
            "sections": [
                "Executive summary",
                "Background",
                "Objectives",
                "Topics discussed",
                "Key findings",
                "Challenges",
                "Action plan",
                "Follow-up questions",
                "Conclusion",
            ],
        },
        "prompt_template": "Compose a project implementation report from the supplied transcript.",
    },
]


def seed_report_templates(db: Session) -> None:
    existing = {
        template.kind
        for template in db.scalars(select(ReportTemplate).where(ReportTemplate.organisation_id.is_(None)))
    }
    for entry in TEMPLATES:
        if entry["kind"] in existing:
            continue
        db.add(ReportTemplate(organisation_id=None, **entry))
    db.commit()
