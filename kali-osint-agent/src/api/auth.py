"""JWT authentication with passlib bcrypt."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from configs.settings import settings

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ---------------------------------------------------------------------------
# HTTP Bearer security scheme
# ---------------------------------------------------------------------------

security = HTTPBearer()

# ---------------------------------------------------------------------------
# In-memory user store (replace with DB lookup in production)
# ---------------------------------------------------------------------------

USERS_DB: dict[str, dict[str, str]] = {
    "admin": {
        "username": "admin",
        "hashed_password": pwd_context.hash("changeme"),
        "role": "admin",
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against its bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict[str, Any]) -> str:
    """Create a signed JWT access token.

    The token embeds all key/value pairs from *data* and adds an
    ``exp`` claim based on :pydata:`settings.jwt_expiration_minutes`.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expiration_minutes)
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT token, returning its payload."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return payload
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict[str, str]:
    """FastAPI dependency that extracts and validates the current user
    from the ``Authorization: Bearer <token>`` header."""
    payload = decode_token(credentials.credentials)
    username: str | None = payload.get("sub")
    if not username or username not in USERS_DB:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return USERS_DB[username]
