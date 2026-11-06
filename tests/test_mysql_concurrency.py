import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from src.application.bookings import BookingService
from src.application.schemas import BookingInput
from src.domain.errors import DomainError
from src.infrastructure.bookings import SqlBookingStore
from src.infrastructure.database import utcnow
from src.infrastructure.models import Booking, EmailOutbox, User

pytestmark = [
    pytest.mark.mysql,
    pytest.mark.skipif(
        os.getenv("TEST_MYSQL") != "1",
        reason="Real MySQL required; set TEST_MYSQL=1 with an isolated test DB",
    ),
]


async def test_simultaneous_overlapping_bookings_have_one_winner(factory, period):
    async with factory() as session, session.begin():
        for i in (1, 2):
            session.add(
                User(
                    id=i,
                    email=f"user{i}@example.com",
                    full_name="Tester",
                    password_hash="unused",
                    created_at=utcnow(),
                )
            )
    ready = asyncio.Event()

    async def attempt(user_id):
        await ready.wait()
        async with factory() as session:
            try:
                return await BookingService(SqlBookingStore(session)).create(
                    user_id,
                    str(uuid4()),
                    BookingInput(**period),
                )
            except DomainError as exc:
                return exc

    tasks = [asyncio.create_task(attempt(i)) for i in (1, 2)]
    ready.set()
    results = await asyncio.gather(*tasks)
    assert sum(not isinstance(r, DomainError) for r in results) == 1
    assert [r.code for r in results if isinstance(r, DomainError)] == [
        "car_unavailable"
    ]
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(Booking)) == 1
        assert await session.scalar(select(func.count()).select_from(EmailOutbox)) == 1
