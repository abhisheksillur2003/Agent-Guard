from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import jwt
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash

from backend.app.core.config import get_settings
from backend.app.core.errors import AuthenticationError

JWT_ALGORITHM = "HS256"
password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return password_hasher.verify(password, password_hash)


def create_access_token(user_id: UUID, organization_id: UUID, role: str) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "org": str(organization_id),
        "role": role,
        "typ": "user",
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
        "jti": str(uuid4()),
    }
    return jwt.encode(
        payload,
        settings.auth_signing_key.get_secret_value(),
        algorithm=JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.auth_signing_key.get_secret_value(),
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "org", "role", "typ", "iat", "exp", "jti"]},
        )
    except InvalidTokenError as exc:
        raise AuthenticationError() from exc
    if payload.get("typ") != "user":
        raise AuthenticationError()
    return payload


def generate_agent_key() -> tuple[str, str, str]:
    prefix = secrets.token_hex(6)
    secret = secrets.token_urlsafe(32)
    credential = f"agk_{prefix}_{secret}"
    return credential, prefix, hash_agent_key(secret)


def parse_agent_key(credential: str) -> tuple[str, str]:
    parts = credential.split("_", maxsplit=2)
    if len(parts) != 3 or parts[0] != "agk" or not parts[1] or not parts[2]:
        raise AuthenticationError()
    return parts[1], parts[2]


def hash_agent_key(secret: str) -> str:
    pepper = get_settings().agent_key_pepper.get_secret_value().encode()
    return hmac.new(pepper, secret.encode(), hashlib.sha256).hexdigest()


def agent_key_matches(secret: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_agent_key(secret), expected_hash)
