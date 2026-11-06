from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.composition import authentication
from src.application.authentication import unauthorized
from src.application.schemas import UserOutput
from src.infrastructure.database import get_database, session_factory
from src.infrastructure.rate_limit import InMemoryRateLimiter

Database = Annotated[AsyncSession, Depends(get_database)]
bearer = HTTPBearer(auto_error=False)


def limiter(request: Request) -> InMemoryRateLimiter:
    return request.app.state.limiter


def client_ip(request: Request) -> str:
    # Do not trust spoofable X-Forwarded-For headers from arbitrary clients.
    return request.client.host if request.client else "unknown"


async def principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> tuple[UserOutput, str]:
    if credentials is None:
        raise unauthorized()
    # Authentication reads use a separate session, leaving the command UoW unopened.
    async with session_factory() as session:
        return await authentication(session).authenticate(credentials.credentials)


Principal = Annotated[tuple[UserOutput, str], Depends(principal)]
