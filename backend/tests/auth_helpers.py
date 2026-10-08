"""Helpers for minting real JWTs that the production ``verify_token`` accepts."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import jwt

import database

USER_A_ID = "user-a-0001"
USER_B_ID = "user-b-0002"


def make_token(
    user_id: str,
    email: Optional[str] = None,
    expires_in: timedelta = timedelta(days=7),
    secret: Optional[str] = None,
) -> str:
    return jwt.encode(
        {
            "userId": user_id,
            "email": email or f"{user_id}@example.test",
            "exp": datetime.utcnow() + expires_in,
        },
        secret or database.SECRET_KEY,
        algorithm="HS256",
    )


def auth_headers(user_id: str, **kwargs) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(user_id, **kwargs)}"}
