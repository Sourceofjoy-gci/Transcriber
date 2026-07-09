from hashlib import sha256
from uuid import UUID

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.domain import AuditLog
from app.services.authorization import Principal
from app.services.redaction import redact_sensitive_data


def write_audit(
    db: Session,
    principal: Principal,
    action: str,
    resource_type: str,
    resource_id: UUID | None,
    outcome: str,
    request: Request | None = None,
    data: dict | None = None,
) -> None:
    client_host = request.client.host if request and request.client else None
    db.add(
        AuditLog(
            organisation_id=principal.organisation.id,
            actor_id=principal.user.id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=outcome,
            ip_hash=sha256(client_host.encode("utf-8")).hexdigest() if client_host else None,
            data=redact_sensitive_data(data or {}),
        )
    )
