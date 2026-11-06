import hashlib
import secrets
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import uuid4

from src.application.schemas import LoginInput, RegisterInput, TokenOutput, UserOutput
from src.domain.errors import DomainError


def unauthorized() -> DomainError:
    return DomainError(401, "unauthorized", "Invalid or expired credentials.")


def now_utc() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class UserRecord(Protocol):
    id: int
    email: str
    full_name: str
    password_hash: str
    is_active: bool


class SessionRecord(Protocol):
    id: str
    user_id: int
    expires_at: datetime
    revoked: bool


class RefreshRecord(Protocol):
    used: bool


class AuthStore(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[None]: ...
    async def create_user(self, email: str, name: str, hashed: str) -> UserRecord: ...
    async def user_by_email(self, email: str) -> UserRecord | None: ...
    async def user_by_id(self, user_id: int) -> UserRecord | None: ...
    async def create_session(
        self, sid: str, user_id: int, expires: datetime
    ) -> SessionRecord: ...
    async def session(self, sid: str, lock: bool = False) -> SessionRecord | None: ...
    async def refresh_session_id(self, digest: str) -> str | None: ...
    async def refresh_record(self, digest: str) -> RefreshRecord: ...
    async def create_refresh(self, digest: str, sid: str) -> None: ...


class PasswordCodec(Protocol):
    async def hash(self, password: str) -> str: ...
    async def verify(
        self, password: str, hashed: str | None
    ) -> tuple[bool, str | None]: ...


class TokenCodec(Protocol):
    def encode(self, user_id: int, sid: str) -> str: ...
    def decode(self, raw: str) -> tuple[int, str]: ...


@dataclass(frozen=True)
class AuthPolicy:
    access_minutes: int
    refresh_days: int


class Authentication:
    """Authentication use cases independent of SQLAlchemy, JWT and Argon2."""

    def __init__(
        self,
        store: AuthStore,
        passwords: PasswordCodec,
        tokens: TokenCodec,
        policy: AuthPolicy,
    ) -> None:
        self.store = store
        self.passwords = passwords
        self.tokens = tokens
        self.policy = policy

    async def register(self, data: RegisterInput) -> UserOutput:
        hashed = await self.passwords.hash(data.password.get_secret_value())
        async with self.store.transaction():
            user = await self.store.create_user(str(data.email), data.full_name, hashed)
            return UserOutput.model_validate(user, from_attributes=True)

    async def issue(self, session: SessionRecord) -> TokenOutput:
        raw = secrets.token_urlsafe(48)
        await self.store.create_refresh(
            hashlib.sha256(raw.encode()).hexdigest(), session.id
        )
        return TokenOutput(
            access_token=self.tokens.encode(session.user_id, session.id),
            refresh_token=raw,
            expires_in=self.policy.access_minutes * 60,
        )

    async def login(self, data: LoginInput) -> TokenOutput:
        async with self.store.transaction():
            user = await self.store.user_by_email(str(data.email))
            valid, updated = await self.passwords.verify(
                data.password.get_secret_value(),
                user.password_hash if user else None,
            )
            if not valid or not user or not user.is_active:
                raise unauthorized()
            if updated:
                user.password_hash = updated
            session = await self.store.create_session(
                str(uuid4()),
                user.id,
                now_utc() + timedelta(days=self.policy.refresh_days),
            )
            return await self.issue(session)

    async def refresh(self, raw: str) -> TokenOutput:
        invalid = False
        result = None
        async with self.store.transaction():
            digest = hashlib.sha256(raw.encode()).hexdigest()
            sid = await self.store.refresh_session_id(digest)
            if sid is None:
                raise unauthorized()
            session = await self.store.session(sid, lock=True)
            if not session:
                raise unauthorized()
            token = await self.store.refresh_record(digest)
            user = await self.store.user_by_id(session.user_id)
            if (
                session.revoked
                or session.expires_at <= now_utc()
                or not user
                or not user.is_active
            ):
                raise unauthorized()
            if token.used:
                session.revoked = True
                invalid = True
            else:
                token.used = True
                result = await self.issue(session)
        # Commit family revocation before returning a replay error.
        if invalid or result is None:
            raise unauthorized()
        return result

    async def authenticate(self, raw: str) -> tuple[UserOutput, str]:
        user_id, sid = self.tokens.decode(raw)
        session = await self.store.session(sid)
        if (
            not session
            or session.user_id != user_id
            or session.revoked
            or session.expires_at <= now_utc()
        ):
            raise unauthorized()
        user = await self.store.user_by_id(user_id)
        if not user or not user.is_active:
            raise unauthorized()
        return UserOutput.model_validate(user, from_attributes=True), sid

    async def logout(self, sid: str) -> None:
        async with self.store.transaction():
            session = await self.store.session(sid, lock=True)
            if session:
                session.revoked = True
