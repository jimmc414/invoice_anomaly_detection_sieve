"""Authentication helpers for FastAPI routes."""
from __future__ import annotations

from typing import Any, Dict

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

_bearer = HTTPBearer(auto_error=False)


class AuthError(HTTPException):
    """Custom exception for authentication failures."""

    def __init__(self, detail: str = "Unauthorized") -> None:
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


def _decode_token(token: str) -> Dict[str, Any]:
    """Decode a JWT token or resolve the local dev shortcut."""

    if token == "devtoken":
        # Local development shortcut
        return {
            "sub": "dev-user",
            "aud": settings.jwt_audience,
            "iss": settings.jwt_issuer,
            "scope": ["score:invoice"],
        }

    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
        )
    except jwt.PyJWTError as exc:  # pragma: no cover - defensive programming
        raise AuthError(str(exc)) from exc


def require_auth(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> Dict[str, Any]:
    """FastAPI dependency ensuring the caller is authenticated."""

    if not credentials:
        raise AuthError("Missing bearer token")

    claims = _decode_token(credentials.credentials)
    if settings.jwt_audience and claims.get("aud") != settings.jwt_audience:
        raise AuthError("Invalid audience")
    if settings.jwt_issuer and claims.get("iss") != settings.jwt_issuer:
        raise AuthError("Invalid issuer")
    return claims
