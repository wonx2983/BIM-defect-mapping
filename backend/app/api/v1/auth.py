"""Authentication endpoints — register, login, refresh, profile."""

import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, UnauthorizedError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.api.deps import get_current_active_user
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


def _build_token_payload(user: User) -> dict:
    """Build JWT payload from a user instance."""
    return {
        "sub": str(user.id),
        "email": user.email,
        "org_id": str(user.organization_id),
        "role": user.role.value,
    }


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(body: RegisterRequest, response: Response, db: AsyncSession = Depends(get_db)):
    """Register a new user and organization. Returns JWT token pair."""
    # Check if email already exists
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise ConflictError("An account with this email already exists")

    # Create organization
    org = Organization(name=body.organization_name)
    db.add(org)
    await db.flush()

    # Create user as admin of the new org
    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        role=UserRole.ADMIN,
        organization_id=org.id,
    )
    db.add(user)
    await db.flush()

    # Generate tokens
    payload = _build_token_payload(user)
    access_token = create_access_token(payload)
    _media_cookie(response, access_token)
    return TokenResponse(
        access_token=access_token,
        refresh_token=create_refresh_token(payload),
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    """Authenticate with email and password. Returns JWT token pair."""
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.hashed_password):
        raise UnauthorizedError("Invalid email or password")

    if not user.is_active:
        raise UnauthorizedError("Account is deactivated")

    payload = _build_token_payload(user)
    access_token = create_access_token(payload)
    _media_cookie(response, access_token)
    return TokenResponse(
        access_token=access_token,
        refresh_token=create_refresh_token(payload),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(body: RefreshRequest, response: Response, db: AsyncSession = Depends(get_db)):
    """Refresh an expired access token using a valid refresh token."""
    try:
        payload = decode_token(body.refresh_token)
    except Exception:
        raise UnauthorizedError("Invalid or expired refresh token")

    if payload.get("type") != "refresh":
        raise UnauthorizedError("Invalid token type")

    try:
        user_id = uuid.UUID(payload.get("sub", ""))
    except (ValueError, TypeError):
        raise UnauthorizedError("Invalid token payload")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise UnauthorizedError("User not found or inactive")

    new_payload = _build_token_payload(user)
    access_token = create_access_token(new_payload)
    _media_cookie(response, access_token)
    return TokenResponse(
        access_token=access_token,
        refresh_token=create_refresh_token(new_payload),
    )


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_active_user)):
    """Get the current authenticated user's profile."""
    return UserResponse.model_validate(user)


def _media_cookie(response, token):
    from app.core.config import get_settings
    settings = get_settings()
    response.set_cookie("defectsync_media", token, httponly=True,
                        secure=settings.APP_ENV == "production", samesite="strict",
                        max_age=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60, path="/uploads")


@router.post("/logout", status_code=204)
async def logout(response: Response):
    response.delete_cookie("defectsync_media", path="/uploads")
