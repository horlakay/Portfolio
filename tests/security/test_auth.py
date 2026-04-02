from __future__ import annotations

import pytest
from fastapi import HTTPException

from sentinel_shared.auth import Role, create_access_token, decode_token
from sentinel_shared.config import CommonSettings


def test_valid_jwt_roundtrip() -> None:
    settings = CommonSettings()
    token = create_access_token("alice", Role.ANALYST, settings)
    claims = decode_token(token, settings)
    assert claims.sub == "alice"


def test_invalid_jwt_rejected() -> None:
    with pytest.raises(HTTPException):
        decode_token("not-a-real-token", CommonSettings())

