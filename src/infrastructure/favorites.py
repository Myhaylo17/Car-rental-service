from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.schemas import CarOutput
from src.infrastructure.catalog import SqlCatalog
from src.infrastructure.models import Car, Favorite


class SqlFavorites:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_owned(
        self, user_id: int, limit: int, offset: int
    ) -> list[CarOutput]:
        rows = (
            await self.db.scalars(
                select(Car)
                .join(Favorite, Favorite.car_id == Car.id)
                .where(
                    Favorite.user_id == user_id,
                    Car.is_active.is_(True),
                )
                .order_by(Car.id)
                .limit(limit)
                .offset(offset)
            )
        ).all()
        return [CarOutput.model_validate(row) for row in rows]

    async def add(self, user_id: int, car_id: int) -> None:
        async with self.db.begin():
            await SqlCatalog(self.db).get(car_id)
            try:
                async with self.db.begin_nested():
                    self.db.add(Favorite(user_id=user_id, car_id=car_id))
                    await self.db.flush()
            except IntegrityError:
                if await self.db.get(Favorite, (user_id, car_id)) is None:
                    raise

    async def remove(self, user_id: int, car_id: int) -> None:
        async with self.db.begin():
            await self.db.execute(
                delete(Favorite).where(
                    Favorite.user_id == user_id,
                    Favorite.car_id == car_id,
                )
            )
