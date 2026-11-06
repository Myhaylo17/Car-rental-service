from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select

from src import worker
from src.application.bookings import BookingService
from src.application.schemas import BookingInput
from src.infrastructure.bookings import SqlBookingStore
from src.infrastructure.models import Booking, EmailOutbox
from tests.test_bookings import book


async def test_email_worker_marks_delivery(
    client, tokens, period, factory, monkeypatch
):
    assert (await book(client, tokens, period)).status_code == 201
    deliver = AsyncMock()
    monkeypatch.setattr(worker, "session_factory", factory)
    monkeypatch.setattr(worker, "deliver_email", deliver)
    assert await worker.process_one()
    deliver.assert_awaited_once()
    async with factory() as session:
        event = await session.scalar(select(EmailOutbox))
        assert event.sent_at is not None
        assert event.attempts == 1
    assert not await worker.process_one()


async def test_email_failure_retries_without_losing_booking(
    client, tokens, period, factory, monkeypatch
):
    assert (await book(client, tokens, period)).status_code == 201
    monkeypatch.setattr(worker, "session_factory", factory)
    monkeypatch.setattr(
        worker, "deliver_email", AsyncMock(side_effect=OSError("SMTP down"))
    )
    assert await worker.process_one()
    async with factory() as session:
        event = await session.scalar(select(EmailOutbox))
        assert event.sent_at is None and event.attempts == 1
        assert not event.dead_letter
        assert await session.scalar(select(func.count()).select_from(Booking)) == 1


async def test_booking_rolls_back_when_outbox_fails(client, tokens, period, factory):
    from src.infrastructure.models import User

    class BrokenOutbox(SqlBookingStore):
        async def enqueue(self, *args):
            raise OSError("Simulated DB write failure")

    async with factory() as session:
        user_id = await session.scalar(select(User.id))
    async with factory() as session:
        with pytest.raises(OSError):
            await BookingService(BrokenOutbox(session)).create(
                user_id,
                "outbox-rollback",
                BookingInput(**period),
            )
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(Booking)) == 0
        assert await session.scalar(select(func.count()).select_from(EmailOutbox)) == 0
