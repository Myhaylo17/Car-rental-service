from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.errors import DomainError
from src.infrastructure.database import utcnow
from src.infrastructure.models import AuthSession, RefreshToken, User


class SqlAuthStore:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        async with self.db.begin():
            yield

    async def create_user(self, email: str, name: str, hashed: str) -> User:
        user = User(
            email=email, full_name=name, password_hash=hashed, created_at=utcnow()
        )
        self.db.add(user)
        try:
            await self.db.flush()
        except IntegrityError as exc:
            raise DomainError(
                409,
                "registration_conflict",
                "An account with this email already exists.",
            ) from exc
        return user

    async def user_by_email(self, email: str) -> User | None:
        return await self.db.scalar(select(User).where(User.email == email))

    async def user_by_id(self, user_id: int) -> User | None:
        return await self.db.get(User, user_id)

    async def create_session(
        self, sid: str, user_id: int, expires: datetime
    ) -> AuthSession:
        session = AuthSession(
            id=sid, user_id=user_id, expires_at=expires, revoked=False
        )
        self.db.add(session)
        await self.db.flush()
        return session

    async def session(self, sid: str, lock: bool = False) -> AuthSession | None:
        query = select(AuthSession).where(AuthSession.id == sid)
        if lock:
            query = query.with_for_update()
        return await self.db.scalar(query.execution_options(populate_existing=True))

    async def refresh_session_id(self, digest: str) -> str | None:
        return await self.db.scalar(
            select(RefreshToken.session_id).where(RefreshToken.digest == digest)
        )

    async def refresh_record(self, digest: str) -> RefreshToken:
        return await self.db.scalar(
            select(RefreshToken)
            .where(
                RefreshToken.digest == digest,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def create_refresh(self, digest: str, sid: str) -> None:
        self.db.add(RefreshToken(digest=digest, session_id=sid))
