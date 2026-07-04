"""Shared FastAPI dependencies."""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.core.config import settings
from app.core.security import decode_access_token
from app.models.user import User
from app.services import auth_service

# Extracts the bearer token from the Authorization header. ``tokenUrl`` is used by
# the interactive docs "Authorize" button.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.api_v1_prefix}/auth/login")


async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    """Resolve the authenticated user from a JWT, or raise 401."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception

    user_id = payload.get("sub")
    if not user_id:
        raise credentials_exception

    user = await auth_service.get_user_by_id(user_id)
    if user is None:
        raise credentials_exception

    return user
