import os
from collections.abc import AsyncIterator
from datetime import timedelta
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

os.environ.setdefault("MYSQL_PASSWORD", "test-password")
os.environ.setdefault(
    "JWT_SECRET_KEY", "91325ef60a47cd8b204f63519aaeb874c6802fdefd19917652be38704cda856f"
)

from src.config import get_settings  # noqa: E402
from src.infrastructure.database import utcnow  # noqa: E402
from src.infrastructure.models import Base, Car  # noqa: E402


class AllowAll:
    """API business tests isolate throttling; limiter has dedicated tests."""

    async def check(self, *args: object) -> None:
        return None


@pytest_asyncio.fixture
async def factory(tmp_path, monkeypatch):
    from src.api import dependencies
    from src.infrastructure import database

    if os.getenv("TEST_MYSQL") == "1":
        settings = get_settings()
        assert settings.mysql_database.endswith("_test"), (
            "Refusing destructive test on a non-test DB"
        )
        engine = create_async_engine(
            settings.database_url, isolation_level="READ COMMITTED"
        )
    else:
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(dependencies, "session_factory", factory)
    monkeypatch.setattr(database, "session_factory", factory)
    async with factory() as session, session.begin():
        session.add(
            Car(
                id=1,
                slug="toyota",
                brand="Toyota",
                model="Corolla",
                year=2024,
                category="sedan",
                transmission="automatic",
                fuel_type="hybrid",
                seats=5,
                daily_price=Decimal("1500.50"),
                currency="UAH",
                description="Family sedan",
                is_active=True,
            )
        )
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def client(factory) -> AsyncIterator[httpx.AsyncClient]:
    from src.infrastructure.database import get_database
    from src.main import create_application

    app = create_application()
    app.state.limiter = AllowAll()

    async def database():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_database] = database
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


async def account(client, email="alice@example.com"):
    password = "Safe-Rental-Phrase!48"
    register = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "full_name": "Alice Test",
            "password": password,
            "password_confirmation": password,
        },
    )
    assert register.status_code == 201, register.text
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert login.status_code == 200, login.text
    return login.json()


@pytest_asyncio.fixture
async def tokens(client):
    return await account(client)


@pytest.fixture
def period():
    start = utcnow().date() + timedelta(days=10)
    return {
        "car_id": 1,
        "start_date": str(start),
        "end_date": str(start + timedelta(days=3)),
    }
