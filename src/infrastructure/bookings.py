from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.schemas import BookingOutput, CarOutput
from src.domain.errors import DomainError
from src.infrastructure.database import utcnow
from src.infrastructure.models import Booking, Car, EmailOutbox, User


class SqlBookingStore:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        async with self.session.begin():
            yield

    async def lock_user(self, user_id: int) -> str:
        user = await self.session.scalar(
            select(User)
            .where(
                User.id == user_id,
                User.is_active.is_(True),
            )
            .with_for_update()
        )
        if user is None:
            raise DomainError(401, "unauthorized", "Authentication required.")
        return user.email

    async def lock_car(self, car_id: int) -> CarOutput:
        # Includes inactive cars for cancellation of existing rentals.
        car = await self.session.scalar(
            select(Car).where(Car.id == car_id).with_for_update()
        )
        if car is None:
            raise DomainError(404, "car_not_found", "Car not found.")
        return CarOutput.model_validate(car)

    async def find_idempotent(self, user_id: int, key: str) -> BookingOutput | None:
        row = await self.session.scalar(
            select(Booking).where(
                Booking.user_id == user_id,
                Booking.idempotency_key == key,
            )
        )
        return BookingOutput.model_validate(row) if row else None

    async def has_overlap(self, car_id: int, start: date, end: date) -> bool:
        car_active = await self.session.scalar(
            select(Car.is_active).where(Car.id == car_id)
        )
        if not car_active:
            raise DomainError(409, "car_inactive", "Car is not available for rental.")
        return (
            await self.session.scalar(
                select(Booking.id)
                .where(
                    Booking.car_id == car_id,
                    Booking.status == "confirmed",
                    Booking.start_date < end,
                    Booking.end_date > start,
                )
                .limit(1)
            )
            is not None
        )

    async def create(self, user_id: int, key: str, booking: BookingOutput) -> None:
        self.session.add(
            Booking(user_id=user_id, idempotency_key=key, **booking.model_dump())
        )
        await self.session.flush()

    async def get_owned(self, booking_id: str, user_id: int) -> BookingOutput:
        row = await self.session.scalar(
            select(Booking)
            .where(
                Booking.id == booking_id,
                Booking.user_id == user_id,
            )
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise DomainError(404, "booking_not_found", "Booking not found.")
        return BookingOutput.model_validate(row)

    async def cancel(self, booking_id: str) -> None:
        await self.session.execute(
            update(Booking)
            .where(Booking.id == booking_id)
            .values(
                status="cancelled",
                cancelled_at=utcnow(),
            )
        )

    async def enqueue(self, email: str, booking: BookingOutput, event: str) -> None:
        if not email:
            email = await self.session.scalar(
                select(User.email)
                .join(
                    Booking,
                    Booking.user_id == User.id,
                )
                .where(Booking.id == booking.id)
            )
        self.session.add(
            EmailOutbox(
                id=str(uuid4()),
                recipient=email,
                subject=f"Booking {event}",
                payload={"event": event, "booking": booking.model_dump(mode="json")},
                available_at=utcnow(),
            )
        )
        await self.session.flush()

    async def list_owned(
        self, user_id: int, limit: int, offset: int
    ) -> list[BookingOutput]:
        rows = (
            await self.session.scalars(
                select(Booking)
                .where(
                    Booking.user_id == user_id,
                )
                .order_by(Booking.created_at.desc(), Booking.id)
                .limit(limit)
                .offset(offset)
            )
        ).all()
        return [BookingOutput.model_validate(row) for row in rows]
