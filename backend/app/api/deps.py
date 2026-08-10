"""Shared FastAPI dependencies for authentication and authorization."""

import uuid
from typing import Callable

from fastapi import Depends, Header
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import decode_token
from app.db.session import get_db
from app.models.user import User, UserRole


async def get_current_user(
    authorization: str = Header(..., description="Bearer <token>"),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Extract and validate JWT from Authorization header, return the user.

    Raises:
        UnauthorizedError: If token is missing, invalid, or user not found.
    """
    if not authorization.startswith("Bearer "):
        raise UnauthorizedError("Invalid authorization header format")

    token = authorization.removeprefix("Bearer ").strip()

    try:
        payload = decode_token(token)
    except JWTError:
        raise UnauthorizedError("Invalid or expired token")

    if payload.get("type") != "access":
        raise UnauthorizedError("Invalid token type")

    user_id = payload.get("sub")
    if not user_id:
        raise UnauthorizedError("Invalid token payload")

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()

    if not user:
        raise UnauthorizedError("User not found")

    return user


async def get_current_active_user(
    user: User = Depends(get_current_user),
) -> User:
    """Ensure the current user is active.

    Raises:
        ForbiddenError: If the user account is deactivated.
    """
    if not user.is_active:
        raise ForbiddenError("Account is deactivated")
    return user


def require_role(*roles: UserRole) -> Callable:
    """Dependency factory that checks the user has one of the specified roles.

    Usage:
        @router.get("/admin", dependencies=[Depends(require_role(UserRole.ADMIN))])
    """

    async def role_checker(user: User = Depends(get_current_active_user)) -> User:
        if user.role not in roles:
            raise ForbiddenError(
                f"This action requires one of these roles: {', '.join(r.value for r in roles)}"
            )
        return user

    return role_checker
