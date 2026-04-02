from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from sentinel_shared.config import CommonSettings, get_common_settings

bearer_scheme = HTTPBearer(auto_error=False)


class Role(StrEnum):
    ADMIN = "admin"
    ANALYST = "analyst"
    SERVICE = "service"


class TokenClaims(BaseModel):
    sub: str
    role: Role
    iss: str
    aud: str
    exp: int


def create_access_token(
    subject: str,
    role: Role,
    settings: CommonSettings,
    expires_minutes: int = 120,
) -> str:
    now = datetime.now(tz=UTC)
    payload = {
        "sub": subject,
        "role": role,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "exp": int((now + timedelta(minutes=expires_minutes)).timestamp()),
        "iat": int(now.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str, settings: CommonSettings) -> TokenClaims:
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
        )
        return TokenClaims.model_validate(payload)
    except jwt.PyJWTError as exc:  # pragma: no cover
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc


def require_roles(*roles: Role):
    async def dependency(
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
        settings: CommonSettings = Depends(get_common_settings),
    ) -> TokenClaims:
        if credentials is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )
        claims = decode_token(credentials.credentials, settings)
        if claims.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role",
            )
        return claims

    return dependency

