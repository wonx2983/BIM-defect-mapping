"""Authentication request/response schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    """New user registration payload."""

    email: str = Field(..., min_length=5, max_length=320, examples=["user@example.com"])
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str = Field(..., min_length=1, max_length=255)
    organization_name: str = Field(..., min_length=1, max_length=255)

    model_config = {"json_schema_extra": {"examples": [{"email": "user@example.com", "password": "securepass123", "full_name": "John Doe", "organization_name": "Acme Construction"}]}}


class LoginRequest(BaseModel):
    """Login credentials."""

    email: str = Field(..., min_length=5, max_length=320)
    password: str = Field(..., min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    """Token refresh payload."""

    refresh_token: str


class TokenResponse(BaseModel):
    """JWT token pair response."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """User profile response."""

    id: uuid.UUID
    email: str
    full_name: str
    role: str
    organization_id: uuid.UUID
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
