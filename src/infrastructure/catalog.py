from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.schemas import CarFilters, CarOutput, CarPage
from src.domain.errors import DomainError
from src.infrastructure.models import Booking, Car


class SqlCatalog:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, car_id: int) -> CarOutput:
        car = await self.session.scalar(
            select(Car).where(Car.id == car_id, Car.is_active.is_(True))
        )
        if car is None:
            raise DomainError(404, "car_not_found", "Car not found.")
        return CarOutput.model_validate(car)

    async def names(self) -> list[tuple[str, str]]:
        """(brand, model) of active cars, used to match names in free text."""
        rows = await self.session.execute(
            select(Car.brand, Car.model).where(Car.is_active.is_(True)).distinct()
        )
        return [(brand, model) for brand, model in rows]

    async def search(self, filters: CarFilters) -> CarPage:
        conditions = [Car.is_active.is_(True)]
        if filters.q:
            conditions.append(
                or_(
                    Car.brand.contains(filters.q, autoescape=True),
                    Car.model.contains(filters.q, autoescape=True),
                    Car.description.contains(filters.q, autoescape=True),
                )
            )
        for name in ("brand", "category", "transmission", "fuel_type"):
            value = getattr(filters, name)
            if value is not None:
                conditions.append(getattr(Car, name) == value)
        if filters.min_price is not None:
            conditions.append(Car.daily_price >= filters.min_price)
        if filters.max_price is not None:
            conditions.append(Car.daily_price <= filters.max_price)
        if filters.min_seats is not None:
            conditions.append(Car.seats >= filters.min_seats)
        if filters.start_date and filters.end_date:
            busy = exists(
                select(Booking.id).where(
                    Booking.car_id == Car.id,
                    Booking.status == "confirmed",
                    Booking.start_date < filters.end_date,
                    Booking.end_date > filters.start_date,
                )
            )
            conditions.append(~busy)
        total = await self.session.scalar(
            select(func.count()).select_from(Car).where(*conditions)
        )
        orders = {
            "price_asc": (Car.daily_price.asc(), Car.id.asc()),
            "price_desc": (Car.daily_price.desc(), Car.id.asc()),
            "newest": (Car.year.desc(), Car.id.asc()),
        }
        statement = select(Car).where(*conditions).order_by(*orders[filters.sort])
        rows = (
            await self.session.scalars(
                statement.offset(
                    (filters.page - 1) * filters.page_size,
                ).limit(filters.page_size)
            )
        ).all()
        return CarPage(
            items=[CarOutput.model_validate(row) for row in rows],
            total=total or 0,
            page=filters.page,
            page_size=filters.page_size,
        )
