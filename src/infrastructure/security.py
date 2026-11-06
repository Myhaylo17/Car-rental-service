import secrets
from datetime import timedelta
from uuid import uuid4

import jwt
from fastapi.concurrency import run_in_threadpool
from pwdlib import PasswordHash

from src.application.authentication import now_utc, unauthorized
from src.config import Settings

password_hasher = PasswordHash.recommended()
DUMMY_HASH = password_hasher.hash(secrets.token_urlsafe(32))


class Argon2Passwords:
    async def hash(self, password: str) -> str:
        return await run_in_threadpool(password_hasher.hash, password)

    async def verify(
        self, password: str, hashed: str | None
    ) -> tuple[bool, str | None]:
        return await run_in_threadpool(
            password_hasher.verify_and_update, password, hashed or DUMMY_HASH
        )


class JwtTokens:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def encode(self, user_id: int, sid: str) -> str:
        now = now_utc()
        return jwt.encode(
            {
                "sub": str(user_id),
                "sid": sid,
                "jti": str(uuid4()),
                "iat": now,
                "nbf": now,
                "exp": now + timedelta(minutes=self.settings.access_token_minutes),
                "iss": self.settings.jwt_issuer,
                "aud": self.settings.jwt_audience,
                "type": "access",
            },
            self.settings.jwt_secret_key.get_secret_value(),
            algorithm="HS256",
        )

    def decode(self, raw: str) -> tuple[int, str]:
        try:
            claims = jwt.decode(
                raw,
                self.settings.jwt_secret_key.get_secret_value(),
                algorithms=["HS256"],
                issuer=self.settings.jwt_issuer,
                audience=self.settings.jwt_audience,
                options={
                    "require": [
                        "sub",
                        "sid",
                        "jti",
                        "iat",
                        "nbf",
                        "exp",
                        "iss",
                        "aud",
                        "type",
                    ]
                },
            )
            if claims["type"] != "access" or not isinstance(claims["sid"], str):
                raise unauthorized()
            return int(claims["sub"]), claims["sid"]
        except (jwt.InvalidTokenError, ValueError, TypeError) as exc:
            raise unauthorized() from exc
