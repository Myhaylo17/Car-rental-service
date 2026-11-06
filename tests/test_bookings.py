from datetime import date, timedelta
from uuid import uuid4

from sqlalchemy import func, select

from src.infrastructure.models import Booking, EmailOutbox
from tests.conftest import account
from tests.test_auth import auth


async def book(client, tokens, period, key=None):
    return await client.post(
        "/api/v1/bookings",
        json=period,
        headers={
            **auth(tokens),
            "Idempotency-Key": key or str(uuid4()),
        },
    )


async def test_booking_price_snapshot_outbox_and_idempotency(
    client, tokens, period, factory
):
    key = str(uuid4())
    first = await book(client, tokens, period, key)
    assert first.status_code == 201, first.text
    assert first.json()["total_price"] == "4501.50"
    second = await book(client, tokens, period, key)
    assert second.json()["id"] == first.json()["id"]
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(Booking)) == 1
        assert await session.scalar(select(func.count()).select_from(EmailOutbox)) == 1
    changed = {
        **period,
        "end_date": str(date.fromisoformat(period["end_date"]) + timedelta(days=1)),
    }
    assert (await book(client, tokens, changed, key)).status_code == 409


async def test_overlap_adjacent_period_and_cancel(client, tokens, period):
    first = await book(client, tokens, period)
    assert first.status_code == 201
    assert (await book(client, tokens, period)).status_code == 409
    adjacent = {
        **period,
        "start_date": period["end_date"],
        "end_date": str(date.fromisoformat(period["end_date"]) + timedelta(days=2)),
    }
    assert (await book(client, tokens, adjacent)).status_code == 201
    cancel = await client.post(
        f"/api/v1/bookings/{first.json()['id']}/cancel", headers=auth(tokens)
    )
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancelled"
    assert (await book(client, tokens, period)).status_code == 201


async def test_booking_owner_access(client, tokens, period):
    first = await book(client, tokens, period)
    other = await account(client, "other@example.com")
    path = f"/api/v1/bookings/{first.json()['id']}"
    assert (await client.get(path, headers=auth(other))).status_code == 404
    assert (await client.post(path + "/cancel", headers=auth(other))).status_code == 404
    assert (await client.get("/api/v1/bookings", headers=auth(other))).json() == []


async def test_invalid_period_and_required_idempotency_key(client, tokens, period):
    assert (
        await client.post("/api/v1/bookings", json=period, headers=auth(tokens))
    ).status_code == 422
    assert (
        await book(client, tokens, {**period, "end_date": period["start_date"]})
    ).status_code == 422
    assert (
        await book(client, tokens, {**period, "start_date": "2000-01-01"})
    ).status_code == 422


async def test_cancellation_is_idempotent(client, tokens, period, factory):
    first = await book(client, tokens, period)
    path = f"/api/v1/bookings/{first.json()['id']}/cancel"
    assert (await client.post(path, headers=auth(tokens))).status_code == 200
    assert (await client.post(path, headers=auth(tokens))).status_code == 200
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(EmailOutbox)) == 2
