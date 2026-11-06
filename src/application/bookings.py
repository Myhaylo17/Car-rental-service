from datetime import UTC, datetime
from uuid import uuid4

from src.application.ports import BookingStore
from src.application.schemas import BookingInput, BookingOutput
from src.domain.booking import rental_total, validate_period
from src.domain.errors import DomainError


class BookingService:
    """All writers lock the car before checking/changing availability."""

    def __init__(self, store: BookingStore) -> None:
        self.store = store

    async def create(self, user_id: int, key: str, data: BookingInput) -> BookingOutput:
        async with self.store.transaction():
            email = await self.store.lock_user(user_id)
            existing = await self.store.find_idempotent(user_id, key)
            if existing:
                if (existing.car_id, existing.start_date, existing.end_date) != (
                    data.car_id,
                    data.start_date,
                    data.end_date,
                ):
                    raise DomainError(
                        409,
                        "idempotency_conflict",
                        "Key already used for another request.",
                    )
                return existing
            now = datetime.now(UTC)
            validate_period(data.start_date, data.end_date, now.date())
            car = await self.store.lock_car(data.car_id)
            if await self.store.has_overlap(car.id, data.start_date, data.end_date):
                raise DomainError(
                    409, "car_unavailable", "Car is already booked for these dates."
                )
            booking = BookingOutput(
                id=str(uuid4()),
                car_id=car.id,
                start_date=data.start_date,
                end_date=data.end_date,
                status="confirmed",
                daily_price=car.daily_price,
                total_price=rental_total(
                    car.daily_price, data.start_date, data.end_date
                ),
                currency=car.currency,
                created_at=now.replace(tzinfo=None),
                cancelled_at=None,
            )
            await self.store.create(user_id, key, booking)
            await self.store.enqueue(email, booking, "confirmed")
            return booking

    async def cancel(self, user_id: int, booking_id: str) -> BookingOutput:
        async with self.store.transaction():
            # Initial lookup only discovers the car. Refresh after acquiring its lock.
            initial = await self.store.get_owned(booking_id, user_id)
            await self.store.lock_car(initial.car_id)
            booking = await self.store.get_owned(booking_id, user_id)
            if booking.status == "cancelled":
                return booking
            if booking.start_date <= datetime.now(UTC).date():
                raise DomainError(
                    409, "cancellation_closed", "Only future rentals can be cancelled."
                )
            await self.store.cancel(booking_id)
            booking = await self.store.get_owned(booking_id, user_id)
            # Read owner without introducing a car -> user lock inversion.
            await self.store.enqueue("", booking, "cancelled")
            return booking
