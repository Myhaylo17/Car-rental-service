from sqlalchemy.ext.asyncio import AsyncSession

from src.application.authentication import Authentication, AuthPolicy
from src.config import get_settings
from src.infrastructure.auth_store import SqlAuthStore
from src.infrastructure.security import Argon2Passwords, JwtTokens


def authentication(db: AsyncSession) -> Authentication:
    settings = get_settings()
    return Authentication(
        SqlAuthStore(db),
        Argon2Passwords(),
        JwtTokens(settings),
        AuthPolicy(settings.access_token_minutes, settings.refresh_token_days),
    )
