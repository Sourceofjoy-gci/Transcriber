from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)


class UserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    display_name: str
    is_active: bool


class MembershipSummary(BaseModel):
    organisation_id: UUID
    role_code: str
    status: str


class SessionResponse(BaseModel):
    user: UserSummary
    memberships: list[MembershipSummary]
    csrf_token: str


class LogoutResponse(BaseModel):
    revoked_at: datetime
