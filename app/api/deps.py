"""Shared FastAPI dependencies."""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import AuthVerificationUnavailable, decode_token
from app.models.models import User
from app.services.account_lifecycle import assert_auth_active, assert_user_active

bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the authenticated user from the JWT. Identity from token only."""
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")

    try:
        claims = decode_token(credentials.credentials)
    except AuthVerificationUnavailable:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Authentication verification is temporarily unavailable")
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")

    auth_id = claims.get("sub")
    if not auth_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token missing subject")

    await assert_auth_active(db, auth_id)
    from app.services.processing_boundary import bind_auth
    bind_auth(auth_id)

    user = (
        await db.execute(select(User).options(selectinload(User.persona)).where(User.auth_id == auth_id))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not provisioned")
    await assert_user_active(db, user.id)
    from app.services.processing_boundary import bind_actor
    bind_actor(user.id)
    return user
